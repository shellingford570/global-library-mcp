"""Phase 8-G: the real-LLM budget guard blocks unsafe runs."""
import os

from global_library_mcp.llm_budget import BudgetPlan, estimate_cost_usd


def test_estimate_math():
    # gpt-4o-mini: 2500 in * $0.15/M + 400 out * $0.60/M = $0.000615/call
    assert estimate_cost_usd("gpt-4o-mini", 100) == 0.0615
    assert estimate_cost_usd("no-such-model", 10) is None


def test_blocked_without_key_approval_and_cap(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    plan = BudgetPlan(model="gpt-4o-mini", questions=20, max_calls=20,
                      cap_usd=None, approved=False).evaluate()
    assert not plan.runnable
    assert len(plan.blockers) >= 4


def test_runnable_when_all_preconditions_met(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_ENABLED", "true")
    plan = BudgetPlan(model="gpt-4o-mini", questions=20, max_calls=20,
                      cap_usd=1.00, approved=True).evaluate()
    assert plan.runnable, plan.blockers
    assert plan.est_cost_usd is not None and plan.est_cost_usd < 1.00


def test_cap_blocks_expensive_plan(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_ENABLED", "true")
    plan = BudgetPlan(model="gpt-4o", questions=100, max_calls=100,
                      cap_usd=0.10, approved=True).evaluate()
    assert not plan.runnable
    assert any("exceeds cap" in b for b in plan.blockers)
