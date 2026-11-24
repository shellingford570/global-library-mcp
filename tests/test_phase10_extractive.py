"""Phase 10-D: extractive answers quote passages, call no provider."""
import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

BOOK = {"id": "994120", "title": "発電水力調査書", "responsibility": "逓信省",
        "published": 1911, "highlights": ["発電水力"]}
TEXT = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"


def _mock():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [BOOK]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": TEXT}))


class _ExplodingProvider:
    async def answer(self, query, evidence):
        raise AssertionError("extractive mode must not call a provider")


@pytest.mark.asyncio
@respx.mock
async def test_extractive_quotes_passage_without_provider():
    _mock()
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer(
            "発電水力の開発", libraries=["ndl"], provider=_ExplodingProvider(), mode="extractive")
    assert result["status"] == "answered_extractive"
    assert result["llm_called"] is not True if "llm_called" in result else True
    assert "發電水力の開發は明治四十三年に始まり" in result["answer"]
    assert result["claims"][0]["verified_against"][0]["passage_id"].endswith("#p1")
    assert result["answer_mode"] == "extractive"
