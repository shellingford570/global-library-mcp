import httpx
import pytest
import respx

from global_library_mcp.evidence import assess_ocr_quality, extract_terms
from global_library_mcp.service import LibraryService

BOOK = {"id": "994120", "title": "發電水力の開發", "responsibility": "臨時發電水力調査局", "published": 1911,
        "highlights": ["發電水力"]}
PAGE_TEXT = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"


def test_extract_terms_splits_japanese_question():
    terms = extract_terms("明治時代の発電水力の開発について教えて")
    assert "発電水力" in terms
    assert all(len(term) >= 2 for term in terms)
    assert len(terms) <= 4


def test_extract_terms_falls_back_to_cleaned_query():
    assert extract_terms("水力") == ["水力"]


def test_quality_gate_accepts_clean_text():
    quality = assess_ocr_quality(PAGE_TEXT)
    assert quality["usable"] is True
    assert quality["score"] > 0.9


def test_quality_gate_rejects_empty_and_broken_text():
    assert assess_ocr_quality("")["usable"] is False
    assert assess_ocr_quality(None)["usable"] is False
    broken = "�" * 30 + "短い"
    assert assess_ocr_quality(broken)["usable"] is False
    assert assess_ocr_quality("短い")["usable"] is False


def _mock_book_and_page_search():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": [BOOK]})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1})
    )


@pytest.mark.asyncio
@respx.mock
async def test_collect_evidence_returns_verified_page():
    _mock_book_and_page_search()
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": PAGE_TEXT})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("発電水力の開発", libraries=["ndl"])
    assert len(result["evidence"]) == 1
    evidence = result["evidence"][0]
    assert evidence["verified"] is True
    assert evidence["citation_key"] == "ndl:994120:994120_50"
    assert evidence["digital_frame"] == 50
    assert evidence["ocr_text"] == PAGE_TEXT
    assert evidence["image_url"].endswith("/994120/R0000050/full/full/0/default.jpg")
    assert result["unverified"] == []


@pytest.mark.asyncio
@respx.mock
async def test_collect_evidence_marks_mismatched_page_unverified():
    _mock_book_and_page_search()
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_51", "book": "994120", "page": 51, "contents": PAGE_TEXT})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("発電水力の開発", libraries=["ndl"])
    assert result["evidence"] == []
    assert len(result["unverified"]) == 1
    assert "did not match" in result["unverified"][0]["reason"]


@pytest.mark.asyncio
@respx.mock
async def test_collect_evidence_marks_missing_ocr_unverified():
    _mock_book_and_page_search()
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": ""})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("発電水力の開発", libraries=["ndl"])
    assert result["evidence"] == []
    assert len(result["unverified"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_collect_evidence_falls_back_to_term_search():
    def book_side_effect(request):
        keyword = request.url.params.get("keyword", "")
        if "について教えて" in keyword:
            return httpx.Response(200, json={"list": []})
        return httpx.Response(200, json={"list": [BOOK]})

    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(side_effect=book_side_effect)
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": PAGE_TEXT})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence("発電水力の開発について教えて", libraries=["ndl"])
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["citation_key"] == "ndl:994120:994120_50"
