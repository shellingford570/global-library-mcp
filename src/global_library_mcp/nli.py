"""NLI checking (Phase 8-E).

Roles stay separate (brief 7): embeddings measure topic
similarity, a reranker measures query-document relevance, an
LLM understands and generates - and NLI measures whether a
passage *entails, contradicts or is neutral about a stated
hypothesis*. The question is never fed to the model raw: the
claim to be verified is first written as a hypothesis sentence
(`build_hypothesis`), then the fetched OCR passage is the
premise.

An NLI verdict is a signal, never an approval: this checker
records its verdict in the semantics payload as an auxiliary
field and returns `not_checked` as the governing relation
unless a deployment explicitly composes it otherwise. Model
loading is attempted at most once per process, with a hard
timeout; on any failure the checker degrades to `not_checked`
with the reason recorded - no retry loops, and the rest of the
system (search, OCR display, rule checking) is unaffected.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

DEFAULT_NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

_load_state: dict[str, Any] = {"attempted": False, "backend": None, "error": None}


_FRAGMENT_SUFFIXES = ("していま", "していた", "しました", "された", "される", "できた", "されたい")


def build_hypothesis(analysis: Any) -> str | None:
    """The claim a question asks about, as one declarative sentence.

    Era-bound diffusion: 「明治時代に日本で地下鉄が普及していた」
    Era-bound existence: 「明治時代に日本で地下鉄が存在した」
    Era-free:            「日本で地下鉄が存在した」
    Returns None when no core concept can anchor a claim.
    Verb-fragment pseudo-concepts (普及していま) are never the
    claim's subject.
    """
    concepts = [c for c in (getattr(analysis, "core_concepts", None) or []) if c]
    topics = [c for c in concepts if not any(c.endswith(s) for s in _FRAGMENT_SUFFIXES)]
    if not topics:
        return None
    concept = max(topics, key=len)
    era = getattr(analysis, "era", None)
    era_label = era["label"] if era else None
    if era_label and ("年" in era_label or era_label.endswith("時代")):
        era_part = f"{era_label}に"
    elif era_label:
        era_part = f"{era_label}時代に"
    else:
        era_part = ""
    raw = getattr(analysis, "raw", "") or ""
    if "普及" in raw:
        verb = "普及していた"
    else:
        verb = "存在した"
    return f"{era_part}日本で{concept}が{verb}"


def nli_verdict(scores: dict[str, float] | None) -> str:
    """Map raw NLI class scores to a verdict label."""
    if not scores:
        return "not_checked"
    entail = float(scores.get("entailment", 0.0))
    contra = float(scores.get("contradiction", 0.0))
    if entail >= 0.6 and entail >= contra:
        return "entailment"
    if contra >= 0.6 and contra > entail:
        return "contradiction"
    return "neutral"


class NliChecker:
    """Hypothesis-based NLI signal over fetched passages.

    `backend` is a callable (premise, hypothesis) -> scores dict.
    With no backend, `load_backend` is attempted at most once
    (bounded by GLM_NLI_LOAD_TIMEOUT_S, default 120s); failure is
    final for the process and reported, never retried.
    """

    name = "nli"

    def __init__(self, backend: Callable[[str, str], dict[str, float]] | None = None,
                 model: str | None = None) -> None:
        self.backend = backend
        self.model = model or os.environ.get("GLM_SEMANTIC_NLI_MODEL", DEFAULT_NLI_MODEL)
        self.load_error: str | None = None

    def ensure_backend(self) -> bool:
        if self.backend is not None:
            return True
        if _load_state["attempted"]:
            self.load_error = _load_state["error"]
            return False
        _load_state["attempted"] = True
        timeout = float(os.environ.get("GLM_NLI_LOAD_TIMEOUT_S", "120"))
        result: dict[str, Any] = {}

        def _load() -> None:
            try:
                from transformers import pipeline  # type: ignore

                pipe = pipeline("zero-shot-classification", model=self.model)
                labels = ["entailment", "contradiction", "neutral"]

                def backend(premise: str, hypothesis: str) -> dict[str, float]:
                    out = pipe(premise[:2000], candidate_labels=labels, hypothesis=hypothesis)
                    return {label: float(score) for label, score in zip(out["labels"], out["scores"])}

                result["backend"] = backend
            except Exception as exc:  # download, import, OOM - all final
                result["error"] = f"{type(exc).__name__}: {exc}"[:300]

        worker = threading.Thread(target=_load, daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            _load_state["error"] = f"model load exceeded {timeout:.0f}s; giving up (no retry)"
        elif "backend" in result:
            _load_state["backend"] = result["backend"]
            self.backend = result["backend"]
            return True
        else:
            _load_state["error"] = result.get("error", "unknown load failure")
        self.load_error = _load_state["error"]
        return False

    def check_passage(self, passage_text: str, hypothesis: str | None) -> dict[str, Any]:
        """NLI verdict for one passage against one hypothesis."""
        if not hypothesis:
            return {"verdict": "not_checked", "reason": "no hypothesis could be built"}
        if not self.ensure_backend():
            return {"verdict": "not_checked", "reason": self.load_error or "nli backend unavailable",
                    "model": self.model}
        try:
            scores = self.backend(passage_text, hypothesis)  # type: ignore[misc]
        except Exception as exc:
            return {"verdict": "not_checked", "reason": f"inference failed: {exc}"[:200], "model": self.model}
        return {"verdict": nli_verdict(scores), "scores": scores, "model": self.model,
                "note": "NLI output is a signal, not a truth guarantee; it never approves an answer by itself"}
