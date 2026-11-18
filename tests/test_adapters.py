import httpx
import pytest
import respx

from global_library_mcp.adapters.gallica import GallicaAdapter
from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter
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
async def test_ndl_book_search_and_page_mapping():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [{"id": "974405", "title": "発電水力事業概覧", "responsibility": "調査局 編", "published": "1913", "highlights": ["発電水力"]}]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/974405_2").mock(return_value=httpx.Response(200, json={"id": "974405_2", "book": "974405", "page": 2, "contents": "発電水力", "coordjson": "[]", "highlights": []}))
    async with httpx.AsyncClient() as client:
        adapter = NdlAdapter(client)
        result = await adapter.search("発電")
        page = await adapter.get_page_text("974405_2")
    assert result[0].record_id == "974405"
    assert result[0].fulltext_status == "available"
    assert page["contents"] == "発電水力"
    assert page["digital_frame"] == 2
    assert page["image_url"].endswith("/974405/R0000002/full/full/0/default.jpg")


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
async def test_internet_archive_adapter_normalizes_record():
    respx.get("https://archive.org/advancedsearch.php").mock(return_value=httpx.Response(200, json={"response": {"docs": [{"identifier": "item-1", "title": "Railway source", "creator": "Author", "date": "1890"}]}}))
    async with httpx.AsyncClient() as client:
        result = await InternetArchiveAdapter(client).search("railway")
    assert result[0].record_id == "item-1"
    assert result[0].landing_url.endswith("/details/item-1")


@pytest.mark.asyncio
@respx.mock
async def test_service_returns_partial_results_on_failure():
    respx.get("https://www.loc.gov/search/").mock(return_value=httpx.Response(200, json={"results": [{"id": "loc:1", "title": "Shared title"}]}))
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(side_effect=httpx.ConnectError("down"))
    respx.get("https://gallica.bnf.fr/SRU").mock(return_value=httpx.Response(200, text="<x/>"))
    respx.get("https://archive.org/advancedsearch.php").mock(return_value=httpx.Response(200, json={"response": {"docs": []}}))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).search("query", ["loc", "ndl", "gallica", "internet-archive"])
    assert any(item.library_id == "loc" for item in result.results)
    assert any(item["library_id"] == "ndl" for item in result.errors)
