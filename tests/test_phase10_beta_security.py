"""Phase 10-H: the Research Beta path must never call an LLM.

With beta defaults (LLM_ENABLED unset, no API key), both the
generative answer path and the materials path run to
completion while a trap route watches every plausible LLM
host. Any call out would fail the test.
"""
import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

BOOK = {"id": "994120", "title": "発電水力調査書", "responsibility": "逓信省",
        "published": 1911, "highlights": ["発電水力"]}
TEXT = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"


def _mock_ndl():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [BOOK]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": TEXT}))


@pytest.mark.asyncio
@respx.mock
async def test_beta_paths_make_no_llm_calls(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    trap = respx.post(url__regex=r"https://(api\.openai\.com|api\.x\.ai)/.*").mock(
        return_value=httpx.Response(500, json={"error": "trap"}))
    _mock_ndl()
    async with httpx.AsyncClient() as client:
        service = LibraryService(client)
        answer = await service.answer("発電水力の開発", libraries=["ndl"])
        materials = await service.research_materials("発電水力の開発", libraries=["ndl"])
    assert trap.call_count == 0
    # The generative path degrades honestly; materials work fully.
    assert answer["status"] in ("llm_unavailable", "insufficient_evidence", "answer_withheld")
    assert materials.get("materials") or materials.get("candidates") or materials.get("evidence")
