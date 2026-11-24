"""Phase 8-G: real-LLM evaluation entry point (budget-guarded).

Prints the run plan and exits WITHOUT any API call unless
every precondition in llm_budget.BudgetPlan holds: API key in
env, LLM_ENABLED=true, model priced, estimate within the
operator's cap, and an explicit --approve flag. When runnable,
it delegates to eval/run_evaluation.py --provider openai,
writing results to a separate file that records the real
provider and model. MockProvider results are never merged in.

Usage:
  python -m eval.real_llm_run --model gpt-4o-mini --questions 20 \
      --max-cost-usd 1.00 [--approve]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--questions", type=int, default=20)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()

    import os

    os.environ.setdefault("LLM_MODEL", args.model)
    from global_library_mcp.llm_budget import BudgetPlan

    plan = BudgetPlan(
        model=args.model,
        questions=args.questions,
        max_calls=args.questions,  # at most one provider call per question
        cap_usd=args.max_cost_usd,
        approved=args.approve,
    ).evaluate()
    print(plan.describe())
    if not plan.runnable:
        print("no API call was made")
        return 2
    out = ROOT / "eval" / f"results-phase8-llm-{args.model}.json"
    cmd = [sys.executable, "-m", "eval.run_evaluation", "--provider", "openai",
           "--limit", str(args.questions), "--out", str(out)]
    print("running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
