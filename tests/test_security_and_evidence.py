import httpx
import pytest
import respx

from global_library_mcp.adapters.ndl import NdlAdapter
from global_library_mcp.answer import OpenAICompatibleProvider
from global_library_mcp.http import sanitize_error
from global_library_mcp.mcp_server import get_citation, get_page_image
from global_library_mcp.service import LibraryService


def test_sanitize_error_redacts_query_credentials():
    value = "Client error for url 'https://api.example.test/search?wskey=secret&query=book'"
    assert "secret" not in sanitize_error(value)
    assert "wskey=%5Bredacted%5D" in sanitize_error(value)


def test_citation_status_distinguishes_page_and_record():
    assert get_citation({"library_id": "ndl", "page_id": "974405_2"})["citation_status"] == "page-level"
    assert get_citation({"library_id": "ndl", "record_id": "974405"})["citation_status"] == "record-level"


@pytest.mark.asyncio
async def test_page_image_rejects_non_positive_page():
    with pytest.raises(ValueError):
        await get_page_image("ndl", "974405", 0)


@pytest.mark.asyncio
async def test_page_image_unsupported_library_is_reasoned():
    result = await get_page_image("gallica", "cb123", 1)
    assert result["status"] == "unsupported"
    assert result["image_url"] is None


@pytest.mark.asyncio
@respx.mock
async def test_ndl_mapping_requires_matching_page_and_usable_ocr():
    respx.get("https://lab.ndl.go.jp/dl/api/page/974405_2").mock(
        return_value=httpx.Response(200, json={"id": "974405_3", "book": "974405", "page": 3, "contents": "wrong page"})
    )
    async with httpx.AsyncClient() as client:
        page = await NdlAdapter(client).get_page_text("974405_2")
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
@respx.mock
async def test_unknown_library_is_reported_and_result_limit_is_global():
    respx.get("https://www.loc.gov/search/").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "loc:1", "title": "One"}, {"id": "loc:2", "title": "Two"}]})
    )
    async with httpx.AsyncClient() as client:
        response = await LibraryService(client).search("x", ["loc", "missing"], limit=1)
    assert len(response.results) == 1
    assert response.errors == [{"library_id": "missing", "error": "Unknown library"}]


def test_llm_base_url_rejects_local_target():
    assert OpenAICompatibleProvider._validate_base_url("http://127.0.0.1:8080/v1")
    assert OpenAICompatibleProvider._validate_base_url("https://api.example.test/v1") is None
