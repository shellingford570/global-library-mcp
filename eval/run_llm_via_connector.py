"""Run the approved real-LLM evaluation with a connector-held key.

The API key itself never enters this process: a short-lived
surrogate (hsurr:*) is fetched from the credential service for
the registered connection and placed in the environment of
THIS process only; the egress layer swaps it for the real key
on requests to the registered host. Nothing is printed or
persisted. All guards still apply in order: BudgetPlan
(pre-run estimate + approval + priced model), the evaluation
runner's own approval gate, and the UsageLedger during the
run.

Usage (after operator approval):
  python -m eval.run_llm_via_connector --connection custom.xai \
      --base-url https://api.x.ai/v1 --model grok-4.3 \
      --questions 20 --max-cost-usd 1.00
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection", default="custom.xai")
    parser.add_argument("--base-url", default="https://api.x.ai/v1")
    parser.add_argument("--model", default="grok-4.3")
    parser.add_argument("--questions", type=int, default=20)
    parser.add_argument("--max-cost-usd", type=float, default=1.00)
    args = parser.parse_args()

    from dynamic_credentials import dynamic_credential_entry

    entry = dynamic_credential_entry(args.connection, "access_token")
    surrogate = str(entry["surrogate"]).strip()
    if not surrogate.startswith("hsurr:"):
        print("credential service did not return a surrogate; aborting")
        return 2
    os.environ["LLM_API_KEY"] = surrogate
    os.environ["LLM_API_BASE"] = args.base_url
    os.environ["LLM_MODEL"] = args.model
    os.environ["LLM_ENABLED"] = "true"

    from global_library_mcp.llm_budget import BudgetPlan

    plan = BudgetPlan(
        model=args.model, questions=args.questions,
        max_calls=args.questions, cap_usd=args.max_cost_usd, approved=True,
    ).evaluate()
    print(plan.describe())
    print(f"base_url: {args.base_url}")
    if not plan.runnable:
        print("BLOCKED - no API call was made.")
        return 2
    os.environ["GLM_LLM_APPROVED"] = "1"
    os.environ["GLM_LLM_MAX_COST_USD"] = str(args.max_cost_usd)

    out = ROOT / "eval" / f"results-phase9-llm-{args.model}.json"
    sys.argv = ["run_evaluation", "--provider", "openai",
                "--limit", str(args.questions), "--out", str(out)]
    from eval.run_evaluation import main as eval_main

    return asyncio.run(eval_main())


if __name__ == "__main__":
    raise SystemExit(main())
