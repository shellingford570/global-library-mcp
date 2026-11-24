"""Pluggable claim verifiers (Phase 10-C).

One interface, four implementations, compared - never merged
silently:

- A. LexicalVerifier: the deterministic screening in
  claims.py (bigram overlap + date/numeric binding over the
  cited passage). Fast and auditable, but lexical coverage is
  not semantic entailment; its "entailment" means "passed
  lexical screening" and the reason string says so.
- B. NliVerifier: a multilingual NLI model over
  (passage = premise, claim = hypothesis). Returns
  not_checked when no backend is loadable.
- C. LlmJudgeVerifier: an LLM asked to judge entailment.
  A judge that is the SAME model as the claim producer is
  refused (not_checked): a model approving its own output is
  not independent verification. Any span the judge quotes is
  checked for literal existence in the passage; a fabricated
  quote downgrades the verdict to not_checked. Live use
  requires operator approval - this class only runs when a
  judge callable is injected.
- D. HybridVerifier: deterministic checks keep veto power
  (a claim whose numbers/dates/passage binding fail can
  never be promoted by a semantic judge); otherwise the
  semantic verdict governs.

Verdicts: entailment / contradiction / neutral / ambiguous /
not_checked, each with a reason and, where determinable, the
character span of the grounding excerpt. Verifiers run in
SHADOW mode by default: service.answer records their
verdicts under "verifier_shadow" when GLM_SHADOW_VERIFIERS
names them, and the publish decision never consults them.
"""
from __future__ import annotations

import os
from typing import Any, Callable

VERDICTS = ("entailment", "contradiction", "neutral", "ambiguous", "not_checked")


def _verdict(verifier: str, verdict: str, reason: str,
             span: tuple[int, int] | None = None) -> dict[str, Any]:
    return {"verifier": verifier, "verdict": verdict if verdict in VERDICTS else "not_checked",
            "reason": reason, "span": list(span) if span else None}


class LexicalVerifier:
    name = "lexical"

    def verify(self, claim: dict[str, Any], evidence: list[dict[str, Any]],
               analysis: Any = None) -> dict[str, Any]:
        from global_library_mcp.claims import verify_claim

        by_key = {i.get("citation_key"): i for i in evidence if i.get("citation_key")}
        screened = verify_claim(claim, by_key, analysis=analysis)
        support = screened.get("support")
        mapping = {"supported": "entailment", "conflicting": "contradiction",
                   "unsupported": "neutral", "uncertain": "ambiguous",
                   "not_checked": "not_checked"}
        span = None
        for entry in screened.get("verified_against") or []:
            if entry.get("char_start") is not None:
                span = (entry["char_start"], entry["char_end"])
                break
        return _verdict(self.name, mapping.get(support, "not_checked"),
                        f"lexical screening ({screened.get('support_detail')}); "
                        "lexical coverage is not semantic proof", span)


class NliVerifier:
    name = "nli"

    def __init__(self, checker: Any = None):
        self._checker = checker

    def verify(self, claim: dict[str, Any], evidence: list[dict[str, Any]],
               analysis: Any = None) -> dict[str, Any]:
        from global_library_mcp.nli import NliChecker

        checker = self._checker or NliChecker()
        passage_text = _claim_passage_text(claim, evidence)
        if not passage_text:
            return _verdict(self.name, "not_checked", "no cited passage text available")
        result = checker.check_passage(passage_text, claim.get("text") or "")
        verdict = result.get("verdict") or result.get("relation") or "not_checked"
        if verdict not in VERDICTS:
            verdict = "not_checked"
        return _verdict(self.name, verdict,
                        f"NLI over cited passage: {result.get('detail') or result.get('reason') or 'model verdict'}")


class LlmJudgeVerifier:
    name = "llm_judge"

    def __init__(self, judge: Callable[[str, str], dict[str, Any]] | None = None,
                 judge_model: str = "", producer_model: str = ""):
        self._judge = judge
        self.judge_model = judge_model
        self.producer_model = producer_model

    def verify(self, claim: dict[str, Any], evidence: list[dict[str, Any]],
               analysis: Any = None) -> dict[str, Any]:
        if self.judge_model and self.producer_model and self.judge_model == self.producer_model:
            return _verdict(self.name, "not_checked",
                            "judge model equals the claim producer model - not independent verification")
        if self._judge is None:
            return _verdict(self.name, "not_checked",
                            "no judge configured (live judging requires operator approval)")
        passage_text = _claim_passage_text(claim, evidence)
        if not passage_text:
            return _verdict(self.name, "not_checked", "no cited passage text available")
        try:
            judged = self._judge(passage_text, claim.get("text") or "")
        except Exception as exc:  # judge failures never break the pipeline
            return _verdict(self.name, "not_checked", f"judge call failed: {type(exc).__name__}")
        verdict = judged.get("verdict")
        if verdict not in VERDICTS:
            return _verdict(self.name, "not_checked", "judge returned an unrecognised verdict")
        quote = judged.get("quote") or ""
        span = None
        if quote:
            at = passage_text.find(quote)
            if at < 0:
                return _verdict(self.name, "not_checked",
                                "judge quoted text that does not exist in the cited passage")
            span = (at, at + len(quote))
        return _verdict(self.name, verdict, str(judged.get("reason") or "LLM judge verdict"), span)


class HybridVerifier:
    name = "hybrid"

    def __init__(self, semantic: Any = None):
        self._semantic = semantic or NliVerifier()
        self._lexical = LexicalVerifier()

    def verify(self, claim: dict[str, Any], evidence: list[dict[str, Any]],
               analysis: Any = None) -> dict[str, Any]:
        lexical = self._lexical.verify(claim, evidence, analysis=analysis)
        # Deterministic vetoes: a claim the deterministic layer
        # positively refutes (conflicting sources) or cannot
        # bind to any passage at all is never promoted by a
        # semantic judge.
        if lexical["verdict"] == "contradiction":
            return _verdict(self.name, "contradiction",
                            f"deterministic veto: {lexical['reason']}", lexical["span"])
        semantic = self._semantic.verify(claim, evidence, analysis=analysis)
        if semantic["verdict"] == "not_checked":
            return _verdict(self.name, "not_checked",
                            f"semantic layer unavailable; deterministic screening alone is not entailment "
                            f"({lexical['reason']})", lexical["span"])
        if lexical["verdict"] == "neutral" and semantic["verdict"] == "entailment":
            return _verdict(self.name, "neutral",
                            "semantic judge says entailment but deterministic binding failed - "
                            "not promoted", semantic["span"])
        return _verdict(self.name, semantic["verdict"],
                        f"hybrid: semantic verdict with deterministic checks passed ({semantic['reason']})",
                        semantic["span"])


def _claim_passage_text(claim: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    by_id = {p["passage_id"]: p for item in evidence for p in (item.get("passages") or [])}
    texts = [by_id[p]["text"] for p in claim.get("evidence_passage_ids") or [] if p in by_id]
    if texts:
        return "\n".join(texts)
    keys = set(claim.get("citations") or [])
    for item in evidence:
        if item.get("citation_key") in keys and item.get("passages"):
            return item["passages"][0]["text"]
    return ""


def get_verifiers(names: list[str], **kwargs: Any) -> list[Any]:
    registry = {"lexical": LexicalVerifier, "nli": NliVerifier,
                "llm_judge": LlmJudgeVerifier, "hybrid": HybridVerifier}
    out = []
    for name in names:
        cls = registry.get(name.strip())
        if cls is not None:
            out.append(cls(**kwargs) if name.strip() == "llm_judge" else cls())
    return out


def shadow_verify(claims: list[dict[str, Any]], evidence: list[dict[str, Any]],
                  analysis: Any = None) -> list[dict[str, Any]]:
    """Run the verifiers named by GLM_SHADOW_VERIFIERS (comma
    list) over verified claims and return their verdicts.
    Shadow only: callers must not feed these into admission."""
    names = [n for n in (os.getenv("GLM_SHADOW_VERIFIERS") or "").split(",") if n.strip()]
    if not names:
        return []
    rows = []
    for verifier in get_verifiers(names):
        for claim in claims:
            verdict = verifier.verify(claim, evidence, analysis=analysis)
            rows.append({"claim_id": claim.get("claim_id"), **verdict})
    return rows
