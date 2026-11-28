"""Local NLI backend interface for b11 (sections 23-30).

b11 does NOT download any NLI model.  This module defines the
backend interface, an unavailable backend (the production
default) and a deterministic SYNTHETIC backend used only for
tests and proxy evaluation.  Every result carries ``nli_status``:

- ``unavailable``      - no real model configured/approved;
- ``synthetic_test``   - produced by SyntheticNLIBackend;
- ``shadow_evaluated`` - produced by a real local model running
  in shadow mode (requires the separate approval documented in
  docs/b11-nli-model-selection.md; not the case in b11).

Shadow contract (section 27): NLI output is recorded ALONGSIDE
the rule-based status, never instead of it.  ``shadow_assess``
returns the rule-based status unchanged in every code path: NLI
cannot promote a gate-rejected candidate, cannot confirm a
contradiction, and cannot turn insufficient evidence into
support.  Model scores are signals, not probabilities of truth.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

NLI_STATUSES = ("unavailable", "synthetic_test", "shadow_evaluated")
NLI_LABELS = ("entailment", "contradiction", "neutral", "not_checked")


class LocalNLIBackend(ABC):
    """Interface a future approved local NLI model must satisfy."""

    backend_kind: str = "abstract"
    model_id: str | None = None
    model_revision: str | None = None

    @abstractmethod
    def status(self) -> str:
        """One of NLI_STATUSES."""

    @abstractmethod
    def predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        """Return {label, scores{entailment, contradiction, neutral},
        model_id, model_revision, backend_kind}.  Implementations
        must be local-only, bounded (premise/hypothesis truncated
        by the caller contract) and deterministic about failure:
        raise NLINotAvailable rather than guessing."""


class NLINotAvailable(RuntimeError):
    pass


class UnavailableNLIBackend(LocalNLIBackend):
    backend_kind = "unavailable"

    def status(self) -> str:
        return "unavailable"

    def predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        raise NLINotAvailable(
            "no NLI model is approved/downloaded in b11; see "
            "docs/b11-nli-model-selection.md for the approval proposal")


_TOKEN_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?|[a-zA-Z]+|[\u3040-\u30ff\u4e00-\u9fff]+")
_NEGATIONS = ("not", "no", "never", "ない", "なかった", "ず", "nicht",
              "kein", "keine", "pas", "ne", "ei")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class SyntheticNLIBackend(LocalNLIBackend):
    """Deterministic lexical-overlap stand-in for tests/proxy eval.

    This is NOT a model: it scores shared content tokens, shared
    numbers and negation asymmetry.  Its outputs exist so the
    shadow plumbing, status separation and evaluation harness can
    be verified before any real model is approved.  Results must
    never be presented as model quality.
    """

    backend_kind = "synthetic"
    model_id = "synthetic-lexical-overlap-v1"
    model_revision = "b11"

    def status(self) -> str:
        return "synthetic_test"

    def predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        p, h = _tokens(premise), _tokens(hypothesis)
        if not p or not h:
            return {"label": "not_checked",
                    "scores": {"entailment": 0.0, "contradiction": 0.0,
                               "neutral": 1.0},
                    "model_id": self.model_id,
                    "model_revision": self.model_revision,
                    "backend_kind": self.backend_kind}
        pset, hset = set(p), set(h)
        overlap = len(pset & hset) / max(1, len(hset))
        pnums = {t for t in pset if t[0].isdigit()}
        hnums = {t for t in hset if t[0].isdigit()}
        num_conflict = bool(hnums) and hnums != (pnums & hnums) and \
            bool(pnums) and not hnums <= pnums
        pneg = any(t in _NEGATIONS for t in pset)
        hneg = any(t in _NEGATIONS for t in hset)
        if num_conflict or (pneg != hneg and overlap > 0.5):
            label = "contradiction"
            scores = {"entailment": 0.05, "contradiction": 0.9,
                      "neutral": 0.05}
        elif overlap >= 0.6:
            label = "entailment"
            scores = {"entailment": round(overlap, 3),
                      "contradiction": 0.05,
                      "neutral": round(1 - overlap - 0.05, 3)}
        else:
            label = "neutral"
            scores = {"entailment": round(overlap / 2, 3),
                      "contradiction": 0.05,
                      "neutral": round(1 - overlap / 2 - 0.05, 3)}
        return {"label": label, "scores": scores,
                "model_id": self.model_id,
                "model_revision": self.model_revision,
                "backend_kind": self.backend_kind}


def shadow_assess(*, rule_based_status: str, premise: str,
                  hypothesis: str,
                  backend: LocalNLIBackend) -> dict[str, Any]:
    """Record an NLI shadow verdict next to the rule-based status.

    The returned ``rule_based_status`` is ALWAYS the input value;
    there is no code path here that promotes, demotes or confirms
    anything.  ``nli_relation`` uses ``candidate`` wording for
    contradiction so a shadow signal is never displayed as a
    confirmed contradiction.
    """
    record: dict[str, Any] = {
        "rule_based_status": rule_based_status,
        "nli_status": backend.status(),
        "nli_relation": "not_checked",
        "nli_scores": None,
        "nli_model_id": backend.model_id,
        "nli_model_revision": backend.model_revision,
        "nli_backend_kind": backend.backend_kind,
        "note": "shadow only: NLI never changes the governing status",
    }
    try:
        out = backend.predict(premise, hypothesis)
    except NLINotAvailable as exc:
        record["nli_reason"] = str(exc)[:200]
        return record
    label = out.get("label")
    if label == "contradiction":
        record["nli_relation"] = "contradiction_candidate"
    elif label in ("entailment", "neutral"):
        record["nli_relation"] = label
    record["nli_scores"] = out.get("scores")
    return record
