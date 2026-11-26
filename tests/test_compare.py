import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

BOOK_A = {"id": "994120", "title": "發電水力の開發", "published": 1911}
BOOK_B = {"id": "1018770", "title": "水力電気 上巻", "published": 1925}
OCR_A = "發電水力の開發では水車を用い、發電した電力を近傍へ送電した。發電所の建設が進んだ時代である。"
OCR_B = "水力電気の送電では高壓送電が主流となり、タービンの効率が向上した。發電所から都市へ送電する。"


def _mock_book(book, ocr):
    pid = book["id"]
    respx.get(f"https://lab.ndl.go.jp/dl/api/book/{pid}").mock(return_value=httpx.Response(200, json=book))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search", params={"f-book": pid}).mock(
        return_value=httpx.Response(200, json={"list": [{"id": f"{pid}_10", "book": pid, "page": 10}], "hit": 1}))
    respx.get(f"https://lab.ndl.go.jp/dl/api/page/{pid}_10").mock(
        return_value=httpx.Response(200, json={"id": f"{pid}_10", "book": pid, "page": 10, "contents": ocr}))


@pytest.mark.asyncio
@respx.mock
async def test_compare_two_documents():
    _mock_book(BOOK_A, OCR_A)
    _mock_book(BOOK_B, OCR_B)
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).compare_documents(
            [{"library_id": "ndl", "record_id": "994120"}, {"library_id": "ndl", "record_id": "1018770"}],
            aspects=["送電"])
    assert result["status"] == "compared"
    assert {d["title"] for d in result["documents"]} == {"發電水力の開發", "水力電気 上巻"}
    row = result["rows"][0]
    assert row["aspect"] == "送電"
    assert row["documents"]["ndl|994120"]["found"] is True
    assert row["documents"]["ndl|1018770"]["found"] is True
    excerpt = row["documents"]["ndl|994120"]["excerpts"][0]
    assert excerpt["citation_key"] == "ndl:994120:994120_10"
    assert "送電" in row["shared_terms"] or "送電" in excerpt["excerpt"]
    assert any("刊行年" in note for note in result["notes"])


@pytest.mark.asyncio
@respx.mock
async def test_compare_insufficient_when_no_pages():
    for book in (BOOK_A, BOOK_B):
        pid = book["id"]
        respx.get(f"https://lab.ndl.go.jp/dl/api/book/{pid}").mock(return_value=httpx.Response(200, json=book))
        respx.get("https://lab.ndl.go.jp/dl/api/page/search", params={"f-book": pid}).mock(
            return_value=httpx.Response(200, json={"list": [], "hit": 0}))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).compare_documents(
            [{"library_id": "ndl", "record_id": "994120"}, {"library_id": "ndl", "record_id": "1018770"}],
            aspects=["送電"])
    assert result["status"] == "insufficient_evidence"
    assert result["rows"][0]["documents"]["ndl|994120"]["found"] is False


@pytest.mark.asyncio
@respx.mock
async def test_compare_needs_two_documents():
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).compare_documents([{"library_id": "ndl", "record_id": "994120"}])
    assert result["status"] == "invalid_request"
