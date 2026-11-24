"""Phase 10-C: pluggable claim verifiers, shadow mode."""
from global_library_mcp.verifiers import (
    HybridVerifier, LexicalVerifier, LlmJudgeVerifier, NliVerifier)

KEY = "ndl:1:p1"
SENT = "臨時發電水力調査局は明治四十三年に設置された"
EVIDENCE = [{"citation_key": KEY, "ocr_text": SENT + "。",
             "passages": [{"passage_id": f"{KEY}#p1", "citation_key": KEY,
                           "text": SENT, "char_start": 0, "char_end": len(SENT)}]}]
CLAIM = {"text": SENT, "citations": [KEY], "evidence_passage_ids": [f"{KEY}#p1"]}


def test_lexical_verifier_maps_screening():
    v = LexicalVerifier().verify(CLAIM, EVIDENCE)
    assert v["verdict"] == "entailment"
    assert "not semantic proof" in v["reason"]
    assert v["span"] == [0, len(SENT)]


def test_nli_verifier_not_checked_without_backend():
    class _NoBackend:
        def check_passage(self, passage_text, hypothesis):
            return {"verdict": "not_checked", "detail": "no weights"}
    v = NliVerifier(checker=_NoBackend()).verify(CLAIM, EVIDENCE)
    assert v["verdict"] == "not_checked"


def test_llm_judge_refuses_same_model():
    judge = lambda passage, claim: {"verdict": "entailment", "reason": "ok", "quote": SENT}
    v = LlmJudgeVerifier(judge=judge, judge_model="m1", producer_model="m1").verify(CLAIM, EVIDENCE)
    assert v["verdict"] == "not_checked"
    assert "not independent" in v["reason"]


def test_llm_judge_rejects_fabricated_quote():
    judge = lambda passage, claim: {"verdict": "entailment", "reason": "ok", "quote": "存在しない引用文"}
    v = LlmJudgeVerifier(judge=judge, judge_model="judge", producer_model="prod").verify(CLAIM, EVIDENCE)
    assert v["verdict"] == "not_checked"
    assert "does not exist" in v["reason"]


def test_llm_judge_accepts_real_quote_with_span():
    judge = lambda passage, claim: {"verdict": "entailment", "reason": "ok", "quote": "明治四十三年に設置された"}
    v = LlmJudgeVerifier(judge=judge, judge_model="judge", producer_model="prod").verify(CLAIM, EVIDENCE)
    assert v["verdict"] == "entailment"
    assert v["span"] == [10, 22]


def test_hybrid_never_promotes_failed_binding():
    class _EagerNli:
        def verify(self, claim, evidence, analysis=None):
            return {"verifier": "nli", "verdict": "entailment", "reason": "model", "span": None}
    bad = {"text": "全く関係のない主張文です", "citations": [KEY], "evidence_passage_ids": [f"{KEY}#p1"]}
    v = HybridVerifier(semantic=_EagerNli()).verify(bad, EVIDENCE)
    assert v["verdict"] == "neutral"
