import httpx
import pytest
import respx

from global_library_mcp.answer import MockProvider
from global_library_mcp.service import LibraryService

BOOK = {"id": "994120", "title": "發電水力の開發", "responsibility": "臨時發電水力調査局", "published": 1911,
        "highlights": ["發電水力"]}
PAGE_TEXT = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"


def _mock_ndl(page_json):
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": [BOOK]})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json=page_json)
    )


@pytest.mark.asyncio
@respx.mock
async def test_research_answers_from_verified_evidence():
    _mock_ndl({"id": "994120_50", "book": "994120", "page": 50, "contents": PAGE_TEXT})
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("発電水力の開発", libraries=["ndl"], provider=MockProvider())
    assert result["status"] == "answered"
    assert result["available"] is True
    assert len(result["citations"]) == 1
    citation = result["citations"][0]
    assert citation["citation_key"] == "ndl:994120:994120_50"
    assert citation["digital_frame"] == 50
    assert citation["image_url"].endswith("/994120/R0000050/full/full/0/default.jpg")


@pytest.mark.asyncio
@respx.mock
async def test_research_withholds_answer_on_bogus_citation():
    _mock_ndl({"id": "994120_50", "book": "994120", "page": 50, "contents": PAGE_TEXT})
    provider = MockProvider(citations=["ndl:999999:999999_1"])
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("発電水力の開発", libraries=["ndl"], provider=provider)
    assert result["status"] == "citation_validation_failed"
    assert result["answer"] is None
    assert result["citations"] == []
    assert len(result["evidence"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_research_reports_insufficient_evidence():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": []})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("存在しない主題", libraries=["ndl"], provider=MockProvider())
    assert result["status"] == "insufficient_evidence"
    assert result["answer"] is None
    assert "確認" in result["message"]


@pytest.mark.asyncio
@respx.mock
async def test_research_llm_unavailable_keeps_evidence(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    _mock_ndl({"id": "994120_50", "book": "994120", "page": 50, "contents": PAGE_TEXT})
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("発電水力の開発", libraries=["ndl"])
    assert result["status"] == "llm_unavailable"
    assert result["answer"] is None
    assert len(result["evidence"]) == 1
