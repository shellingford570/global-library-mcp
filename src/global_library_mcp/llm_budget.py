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

# List prices, USD per 1M tokens (input, output), re-verified
# 2026-11-24 against OpenAI's published API pricing. API prices
# are separate from any ChatGPT subscription. Re-verify before
# any approved run; an unknown model blocks rather than guessing.
PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    # xAI (api.x.ai, OpenAI-compatible endpoint), list prices
    # verified 2026-11-24.
    "grok-4-fast": (0.20, 0.50),
    "grok-4.3": (1.25, 2.50),
}

# Conservative per-call token assumptions for the estimate:
# compacted evidence prompts are capped by compact_evidence,
# and the provider's output is short by design.
EST_INPUT_TOKENS_PER_CALL = 2500
EST_OUTPUT_TOKENS_PER_CALL = 400



class UsageLedger:
    """Runtime cost enforcement (Phase 9-B).

    BudgetPlan estimates BEFORE the run; this ledger enforces
    DURING it. ``can_afford`` projects the next call's worst
    case (the configured per-call token maxima) and refuses the
    call itself when it could exceed the remaining budget - a
    call that might breach the cap is never made. ``record``
    books provider-reported usage; when the provider reports
    none, the worst-case estimate is booked instead, never
    zero.
    """

    def __init__(self, model: str, max_cost_usd: float, max_calls: int,
                 max_input_tokens: int = 12000, max_output_tokens: int | None = None):
        import os

        self.model = model
        self.max_cost_usd = max_cost_usd
        self.max_calls = max_calls
        self.max_input_tokens = max_input_tokens
        # Phase 10-G: the ledger's output-token assumption and
        # the provider's max_tokens now share ONE source - the
        # LLM_MAX_OUTPUT_TOKENS env (default 1200). Before, the
        # two 1200s matched by coincidence, not construction.
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None
            else int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1200") or 1200)
        )
        import threading

        self._lock = threading.Lock()
        self._reserved_usd = 0.0
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.spent_usd = 0.0
        self.usage_reported = 0
        self.usage_estimated = 0

    def _cost(self, input_tokens: int, output_tokens: int) -> float | None:
        prices = PRICE_TABLE_USD_PER_MTOK.get(self.model)
        if prices is None:
            return None
        return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000

    def worst_case_next_usd(self) -> float | None:
        return self._cost(self.max_input_tokens, self.max_output_tokens)

    def can_afford(self) -> bool:
        worst = self.worst_case_next_usd()
        if worst is None or self.calls >= self.max_calls:
            return False
        return self.spent_usd + self._reserved_usd + worst <= self.max_cost_usd

    def reserve(self) -> bool:
        """Atomically check affordability and hold the worst
        case (Phase 10-G: check-then-act raced under concurrent
        callers; reserve+settle closes the window). Returns
        False without holding anything when the next call could
        breach the cap."""
        with self._lock:
            if not self.can_afford():
                return False
            self._reserved_usd += self.worst_case_next_usd() or 0.0
            return True

    def settle(self, usage: dict | None) -> None:
        """Release the oldest reservation and book the actual
        (or, when unreported, the worst case - never zero)."""
        with self._lock:
            self._reserved_usd = max(0.0, self._reserved_usd - (self.worst_case_next_usd() or 0.0))
            self._book(usage)

    def record(self, usage: dict | None) -> None:
        with self._lock:
            self._book(usage)

    def _book(self, usage: dict | None) -> None:
        self.calls += 1
        prompt = (usage or {}).get("prompt_tokens")
        completion = (usage or {}).get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            self.input_tokens += prompt
            self.output_tokens += completion
            self.usage_reported += 1
            cost = self._cost(prompt, completion)
        else:
            self.input_tokens += self.max_input_tokens
            self.output_tokens += self.max_output_tokens
            self.usage_estimated += 1
            cost = self.worst_case_next_usd()
        self.spent_usd += cost or 0.0

    def to_state(self) -> dict:
        """Persisted form, so a resumed run keeps the accumulated
        spend (Phase 10-G: the cap is per-campaign, not
        per-process, when the operator resumes with --resume)."""
        return {"model": self.model, "calls": self.calls,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "spent_usd": self.spent_usd, "usage_reported": self.usage_reported,
                "usage_estimated": self.usage_estimated}

    def restore(self, state: dict) -> None:
        if state.get("model") not in (None, self.model):
            raise ValueError("saved ledger state is for a different model")
        self.calls = int(state.get("calls") or 0)
        self.input_tokens = int(state.get("input_tokens") or 0)
        self.output_tokens = int(state.get("output_tokens") or 0)
        self.spent_usd = float(state.get("spent_usd") or 0.0)
        self.usage_reported = int(state.get("usage_reported") or 0)
        self.usage_estimated = int(state.get("usage_estimated") or 0)

    def summary(self) -> dict:
        return {
            "model": self.model, "calls": self.calls,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "spent_usd": round(self.spent_usd, 6),
            "max_cost_usd": self.max_cost_usd, "max_calls": self.max_calls,
            "remaining_usd": round(self.max_cost_usd - self.spent_usd, 6),
            "usage_reported": self.usage_reported,
            "usage_estimated": self.usage_estimated,
        }


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
