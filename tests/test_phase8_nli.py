"""Phase 8-E: hypothesis building and the NLI signal checker."""
from global_library_mcp.nli import NliChecker, build_hypothesis, nli_verdict
from global_library_mcp.question import analyze_question


def test_hypothesis_is_declarative_and_era_bound():
    analysis = analyze_question("明治時代に地下鉄は普及していましたか")
    hypothesis = build_hypothesis(analysis)
    assert hypothesis is not None
    assert "明治" in hypothesis and "地下鉄" in hypothesis
    assert hypothesis.endswith("普及していた") or "普及" in hypothesis


def test_nli_verdict_thresholds():
    assert nli_verdict({"entailment": 0.9, "contradiction": 0.05, "neutral": 0.05}) == "entailment"
    assert nli_verdict({"entailment": 0.1, "contradiction": 0.8, "neutral": 0.1}) == "contradiction"
    assert nli_verdict({"entailment": 0.4, "contradiction": 0.3, "neutral": 0.3}) == "neutral"
    assert nli_verdict(None) == "not_checked"


def test_nli_checker_with_injected_backend():
    checker = NliChecker(backend=lambda premise, hypothesis: {"entailment": 0.92, "contradiction": 0.03, "neutral": 0.05})
    result = checker.check_passage("何らかの本文", "明治時代に日本で地下鉄が存在した")
    assert result["verdict"] == "entailment"
    assert "never approves" in result["note"]


def test_nli_checker_without_hypothesis():
    checker = NliChecker(backend=lambda p, h: {})
    assert checker.check_passage("本文", None)["verdict"] == "not_checked"
