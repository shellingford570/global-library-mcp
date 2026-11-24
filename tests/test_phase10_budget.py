"""Phase 10-G: ledger hardening - reserve/settle, resume, bounds."""
import asyncio
import os

import httpx
import pytest
import respx

from global_library_mcp.answer import OpenAICompatibleProvider
from global_library_mcp.llm_budget import UsageLedger


def test_reserve_blocks_second_concurrent_call():
    ledger = UsageLedger(model="gpt-4o-mini", max_cost_usd=0.005, max_calls=10)
    assert ledger.reserve() is True
    # worst case per call = (12000*0.15 + 1200*0.60)/1e6 = 0.00252
    assert ledger.reserve() is False  # 2 x 0.00252 > 0.005 with one held
    ledger.settle({"prompt_tokens": 100, "completion_tokens": 10})
    assert ledger.calls == 1
    assert ledger.spent_usd < 0.001


def test_ledger_state_survives_restore():
    ledger = UsageLedger(model="gpt-4o-mini", max_cost_usd=1.0, max_calls=10)
    ledger.record({"prompt_tokens": 5000, "completion_tokens": 200})
    state = ledger.to_state()
    resumed = UsageLedger(model="gpt-4o-mini", max_cost_usd=1.0, max_calls=10)
    resumed.restore(state)
    assert resumed.calls == 1 and resumed.spent_usd == ledger.spent_usd
    with pytest.raises(ValueError):
        resumed.restore({"model": "gpt-4o"})


def test_output_cap_single_source(monkeypatch):
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "777")
    ledger = UsageLedger(model="gpt-4o-mini", max_cost_usd=1.0, max_calls=1)
    assert ledger.max_output_tokens == 777


@pytest.mark.asyncio
@respx.mock
async def test_provider_refuses_oversized_payload(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("GLM_LLM_MAX_INPUT_TOKENS", "200")
    async with httpx.AsyncClient() as client:
        provider = OpenAICompatibleProvider(client)
        result = await provider.answer("質問", [{"citation_key": "k", "ocr_text": "あ" * 500,
                                                 "title": "t", "library_name": "l"}])
    assert result["available"] is False
    assert "input-token bound" in result["reason"]
