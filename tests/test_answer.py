import httpx
import pytest
import respx

from global_library_mcp.answer import MockProvider, OpenAICompatibleProvider

EVIDENCE = [{"citation_key": "ndl:994120:994120_50", "title": "發電水力の開發", "ocr_text": "本文",
             "page_id": "994120_50", "digital_frame": 50, "landing_url": "https://example.test"}]


@pytest.mark.asyncio
async def test_answer_provider_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    async with httpx.AsyncClient() as client:
        result = await OpenAICompatibleProvider(client).answer("質問", EVIDENCE)
    assert result["available"] is False
    assert "LLM is disabled" in result["reason"]


@pytest.mark.asyncio
@respx.mock
async def test_answer_provider_uses_structured_response(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.openai.com/v1")
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"根拠付き回答","citations":["ndl:994120:994120_50"],"limitations":[]}'}}]}))
    async with httpx.AsyncClient() as client:
        result = await OpenAICompatibleProvider(client).answer("質問", EVIDENCE)
    assert route.called
    assert result["available"] is True
    assert result["citations"] == ["ndl:994120:994120_50"]


@pytest.mark.asyncio
@respx.mock
async def test_answer_provider_rejects_invented_citation(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.openai.com/v1")
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"捏造","citations":["ndl:999999:999999_1"],"limitations":[]}'}}]}))
    async with httpx.AsyncClient() as client:
        result = await OpenAICompatibleProvider(client).answer("質問", EVIDENCE)
    assert result["available"] is False
    assert "outside the supplied evidence" in result["reason"]


@pytest.mark.asyncio
async def test_mock_provider_cites_first_evidence():
    result = await MockProvider().answer("質問", EVIDENCE)
    assert result["available"] is True
    assert result["citations"] == ["ndl:994120:994120_50"]
