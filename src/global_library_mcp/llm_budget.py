"""Real-LLM evaluation budget guard (Phase 8-G).

A real-LLM run may start only when every precondition holds:
an API key is configured (env only, never logged), the model
is known to the price table, the operator approved the run,
and the pre-run cost estimate fits the operator's cap. The
estimate is computed BEFORE any call; usage during the run is
recorded by the evaluation runner in its own results file,
kept strictly separate from MockProvider results.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# List prices, USD per 1M tokens (input, output). Re-verify
# against the provider's pricing page before any approved run;
# an unknown model blocks the run rather than guessing a price.
PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}

# Conservative per-call token assumptions for the estimate:
# compacted evidence prompts are capped by compact_evidence,
# and the provider's output is short by design.
EST_INPUT_TOKENS_PER_CALL = 2500
EST_OUTPUT_TOKENS_PER_CALL = 400


def estimate_cost_usd(model: str, calls: int) -> float | None:
    prices = PRICE_TABLE_USD_PER_MTOK.get(model)
    if prices is None:
        return None
    per_call = (EST_INPUT_TOKENS_PER_CALL * prices[0] + EST_OUTPUT_TOKENS_PER_CALL * prices[1]) / 1_000_000
    return round(per_call * calls, 4)


@dataclass
class BudgetPlan:
    model: str
    questions: int
    max_calls: int
    cap_usd: float | None
    approved: bool
    est_cost_usd: float | None = field(default=None)
    blockers: list[str] = field(default_factory=list)

    def evaluate(self) -> "BudgetPlan":
        self.est_cost_usd = estimate_cost_usd(self.model, self.max_calls)
        self.blockers = []
        if not (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
            self.blockers.append("no API key configured (LLM_API_KEY / OPENAI_API_KEY)")
        if os.getenv("LLM_ENABLED", "false").lower() not in {"1", "true", "yes"}:
            self.blockers.append("LLM_ENABLED is not set to true")
        if self.est_cost_usd is None:
            self.blockers.append(f"model {self.model!r} is not in the price table; add a verified price first")
        if self.cap_usd is None:
            self.blockers.append("no cost cap given (--max-cost-usd)")
        elif self.est_cost_usd is not None and self.est_cost_usd > self.cap_usd:
            self.blockers.append(f"estimate ${self.est_cost_usd} exceeds cap ${self.cap_usd}")
        if not self.approved:
            self.blockers.append("run not approved (--approve flag absent)")
        return self

    @property
    def runnable(self) -> bool:
        return not self.blockers

    def describe(self) -> str:
        lines = [
            f"model: {self.model}",
            f"questions: {self.questions}, max LLM calls: {self.max_calls}",
            f"estimated cost: ${self.est_cost_usd} (cap: ${self.cap_usd})",
        ]
        if self.blockers:
            lines.append("BLOCKED:")
            lines.extend(f"  - {b}" for b in self.blockers)
        else:
            lines.append("all preconditions met; run may start")
        return "\n".join(lines)
