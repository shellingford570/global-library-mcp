import httpx
import pytest
import respx

from global_library_mcp.answer import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_answer_provider_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    async with httpx.AsyncClient() as client:
        result = await OpenAICompatibleProvider(client).answer("質問", [{"title": "証拠"}])
    assert result["available"] is False
    assert "LLM is disabled" in result["reason"]


@pytest.mark.asyncio
@respx.mock
async def test_answer_provider_uses_structured_response(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.openai.com/v1")
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"根拠付き回答","citations":[1],"limitations":[]}'}}]}))
    async with httpx.AsyncClient() as client:
        result = await OpenAICompatibleProvider(client).answer("質問", [{"title": "証拠", "landing_url": "https://example.test"}])
    assert route.called
    assert result["available"] is True
    assert result["citations"] == [1]
