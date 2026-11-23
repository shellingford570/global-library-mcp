"""Phase 7-B: the eight Phase 6 false answers must no longer be
admitted as evidence, and genuine era evidence still must be.

The fixtures (eval/phase7-fixtures.json) are the actual pages
the Phase 6 runs cited. Admission is recomputed with the current
pipeline pieces - no question-ID-specific handling anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from global_library_mcp.question import analyze_question
from global_library_mcp.relevance import assess_relevance, concept_families
from global_library_mcp.semantics import RuleBasedSemanticChecker
from global_library_mcp.service import admission_decision

FIXTURES = json.loads(
    (Path(__file__).resolve().parents[1] / "eval" / "phase7-fixtures.json").read_text(encoding="utf-8")
)["cases"]
CHECKER = RuleBasedSemanticChecker()


def _admission(case: dict) -> tuple[bool, dict]:
    analysis = analyze_question(case["question"])
    relevance = assess_relevance(analysis, case["page_text"], publication_year=None)
    semantics = CHECKER.assess(analysis, case["page_text"], publication_year=None)
    families = concept_families(analysis.core_concepts)
    anchor_matched = bool(families) and families[0] in relevance.get("matched_concepts", [])
    return admission_decision(
        analysis, relevance["status"], semantics, case["page_kind"], None, anchor_matched
    ) + ({"relevance": relevance, "semantics": semantics},)


@pytest.mark.parametrize("case", FIXTURES, ids=[c["id"] for c in FIXTURES])
def test_phase6_false_answer_page_is_not_admitted(case: dict) -> None:
    admitted, record, _verdicts = _admission(case)
    assert admitted is False, f"{case['id']} still admitted via {record}"


def test_demonym_no_longer_binds_stance_units() -> None:
    analysis = analyze_question("明治時代の日本人による宇宙飛行の記録について教えて")
    assert "日本人" not in analysis.core_concepts
    assert "宇宙飛行" in analysis.core_concepts


def test_contemporary_anchored_support_still_admitted() -> None:
    # A period source asserting the event with its own era anchor.
    text = (
        "明治四十三年に至り、水力発電は各地で開業した。"
        "発電所は相次いで建設され、送電も始まったのである。"
        "当時の技術者たちは国産の設備に誇りを持っていた。"
    )
    analysis = analyze_question("明治末期の水力発電技術について教えて")
    relevance = assess_relevance(analysis, text, publication_year=1911)
    semantics = CHECKER.assess(analysis, text, publication_year=1911)
    admitted, record = admission_decision(
        analysis, relevance["status"], semantics, "body", 1911, True
    )
    assert semantics["relation"] == "supports"
    assert admitted is True
    assert record["path"] in ("direct", "semantic")
    assert record["checks"]["era_anchor"] is True


def test_retrospective_anchored_support_still_admitted() -> None:
    text = (
        "電信は明治二年に開局した。同年、東京横浜間に電信線が架設された。"
        "その後、電信は全国へ広がっていったのである。"
    )
    analysis = analyze_question("明治時代の電信の開設について教えて")
    relevance = assess_relevance(analysis, text, publication_year=1960)
    semantics = CHECKER.assess(analysis, text, publication_year=1960)
    admitted, _record = admission_decision(
        analysis, relevance["status"], semantics, "body", 1960, True
    )
    assert semantics["relation"] == "supports"
    assert semantics["anchored_support"] is True
    assert admitted is True


def test_unanchored_retrospective_support_rejected() -> None:
    # Occurrence cues, no era anchor, later source: the q31 shape.
    text = (
        "テレビ放送は開始され、多くの人々が見た。"
        "放送は毎日のように行われ、番組も増えていった。"
    )
    analysis = analyze_question("大正時代のテレビ放送の開始について教えて")
    relevance = assess_relevance(analysis, text, publication_year=None)
    semantics = CHECKER.assess(analysis, text, publication_year=None)
    admitted, record = admission_decision(
        analysis, relevance["status"], semantics, "body", None, True
    )
    assert admitted is False
    assert record["checks"]["era_anchor"] is False
