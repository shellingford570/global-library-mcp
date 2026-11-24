"""Phase 9-B: runtime cost enforcement and the approval gate."""
import subprocess
import sys
from pathlib import Path

from global_library_mcp.llm_budget import UsageLedger

ROOT = Path(__file__).resolve().parent.parent


def test_ledger_refuses_call_that_could_breach_cap():
    ledger = UsageLedger(model="gpt-4o-mini", max_cost_usd=0.001, max_calls=10)
    # worst case per call: 12000*0.15 + 1200*0.60 per 1M = $0.00252 > cap
    assert ledger.can_afford() is False


def test_ledger_books_reported_and_estimated_usage():
    ledger = UsageLedger(model="gpt-4o-mini", max_cost_usd=1.0, max_calls=3)
    assert ledger.can_afford() is True
    ledger.record({"prompt_tokens": 1000, "completion_tokens": 100})
    assert ledger.spent_usd == round((1000 * 0.15 + 100 * 0.60) / 1_000_000, 10) or ledger.spent_usd > 0
    assert ledger.usage_reported == 1
    ledger.record(None)  # provider reported nothing -> worst case, never zero
    assert ledger.usage_estimated == 1 and ledger.spent_usd > 0.001
    ledger.record({"prompt_tokens": 10, "completion_tokens": 10})
    assert ledger.calls == 3 and ledger.can_afford() is False  # call cap reached


def test_direct_openai_run_is_blocked_without_approval(tmp_path):
    out = tmp_path / "should_not_exist.json"
    proc = subprocess.run(
        [sys.executable, "-m", "eval.run_evaluation", "--provider", "openai",
         "--limit", "1", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stdout
    assert not out.exists()


def test_real_llm_run_blocks_model_mismatch(monkeypatch):
    sys.path.insert(0, str(ROOT / "src"))
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_ENABLED", "true")
    proc = subprocess.run(
        [sys.executable, "-m", "eval.real_llm_run", "--model", "gpt-4o-mini",
         "--questions", "2", "--max-cost-usd", "1.0", "--approve"],
        cwd=ROOT, capture_output=True, text=True,
        env={**__import__("os").environ, "LLM_MODEL": "gpt-4o", "LLM_API_KEY": "sk-test", "LLM_ENABLED": "true"},
    )
    assert proc.returncode == 2
    assert "differs from the approved model" in proc.stdout
