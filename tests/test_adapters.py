import httpx
import pytest
import respx

from global_library_mcp.adapters.gallica import GallicaAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.adapters.ndl import NdlAdapter
from global_library_mcp.service import LibraryService


@pytest.mark.asyncio
@respx.mock
async def test_loc_adapter_normalizes_record():
    respx.get("https://www.loc.gov/search/").mock(return_value=httpx.Response(200, json={"results": [{"id": "https://loc.gov/item/1", "title": "A book", "contributor": ["A. Author"], "date": "1890", "language": ["eng"], "rights": "Public domain"}]}))
    async with httpx.AsyncClient() as client:
        result = await LocAdapter(client).search("book")
    assert result[0].record_id.endswith("/1")
    assert result[0].author == "A. Author"
    assert result[0].rights.statement == "Public domain"


@pytest.mark.asyncio
@respx.mock
async def test_ndl_adapter_parses_atom():
    xml = """<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><entry><id>ndl:1</id><title>日本の本</title><link href=\"https://ndlsearch.ndl.go.jp/books/R1\"/><dc:creator>著者</dc:creator><dc:date>1900</dc:date></entry></feed>"""
    respx.get("https://ndlsearch.ndl.go.jp/api/opensearch").mock(return_value=httpx.Response(200, text=xml))
    async with httpx.AsyncClient() as client:
        result = await NdlAdapter(client).search("日本")
    assert result[0].record_id == "ndl:1"
    assert result[0].title == "日本の本"


@pytest.mark.asyncio
@respx.mock
async def test_gallica_adapter_parses_sru():
    xml = """<searchRetrieveResponse xmlns=\"http://www.loc.gov/zing/srw/\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><records><record><recordData><dc:title xmlns:dc=\"http://purl.org/dc/elements/1.1/\">French source</dc:title><dc:identifier xmlns:dc=\"http://purl.org/dc/elements/1.1/\">https://gallica.bnf.fr/ark:/12148/x</dc:identifier></recordData></record></records></searchRetrieveResponse>"""
    respx.get("https://gallica.bnf.fr/SRU").mock(return_value=httpx.Response(200, text=xml))
    async with httpx.AsyncClient() as client:
        result = await GallicaAdapter(client).search("source")
    assert result[0].title == "French source"
    assert result[0].landing_url.startswith("https://gallica")


@pytest.mark.asyncio
@respx.mock
async def test_service_returns_partial_results_on_failure():
    respx.get("https://www.loc.gov/search/").mock(return_value=httpx.Response(200, json={"results": [{"id": "loc:1", "title": "Shared title"}]}))
    respx.get("https://ndlsearch.ndl.go.jp/api/opensearch").mock(side_effect=httpx.ConnectError("down"))
    respx.get("https://gallica.bnf.fr/SRU").mock(return_value=httpx.Response(200, text="<x/>"))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).search("query")
    assert any(item.library_id == "loc" for item in result.results)
    assert any(item["library_id"] == "ndl" for item in result.errors)
