"""b10 Stage 4: structured questions/claims, claim-evidence
mapping, cross-source comparison (brief sections 23-29)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, compare_facts, structure_claim,
    structure_question)


def test_question_structure_hydro():
    rq = structure_question("明治時代の日本で水力発電所が建設されたのは本当か")
    assert rq.research_intent == "historical_fact_check"
    assert rq.time_range and rq.time_range["start"] == 1868
    assert "concept:hydroelectric-power" in rq.entities["concepts"]
    assert rq.expected_evidence_type == "primary_source_text"


def test_claim_structure_brief_example():
    claim = structure_claim("明治時代の日本で水力発電所が建設された")
    assert claim.subject == "concept:hydroelectric-power"
    assert claim.time and claim.time["era"] == "明治"
    assert claim.place == "日本"
    # nothing invented: no quantity in the text -> none in the claim
    assert claim.quantity is None


def test_claim_quantity_and_year():
    claim = structure_claim("発電所は明治30年に完成し、出力は120キロワットだった")
    assert claim.quantity is not None
    assert claim.time and 1897 in (claim.time.get("years_mentioned") or [])


def test_evidence_mapping_statuses():
    claim = structure_claim("明治時代の日本で水力発電所が建設された")
    rows = assess_claim_evidence(claim, [
        {"document_id": "ok", "admitted": True,
         "text": "明治25年、日本において水力発電所が建設された。"},
        {"document_id": "retro", "admitted": True,
         "text": "1925年に明治期の発電事業を回顧した資料"},
        {"document_id": "neg", "admitted": True,
         "text": "明治時代には日本に水力発電所は存在しなかった。"},
        {"document_id": "unadmitted", "admitted": False,
         "text": "明治25年、日本において水力発電所が建設された。"},
    ])
    by_id = {r["document_id"]: r["status"] for r in rows}
    assert by_id["ok"] == "supported_candidate"
    assert by_id["retro"] == "contextual_only"      # retrospective != support
    assert by_id["neg"] == "conflicting_candidate"  # negation
    assert by_id["unadmitted"] == "not_checked"     # gate not passed


def test_evidence_year_conflict():
    claim = structure_claim("発電所は明治30年に完成した")
    rows = assess_claim_evidence(claim, [
        {"document_id": "x", "admitted": True,
         "text": "原文は明治13年の完成と記す"}])
    assert rows[0]["status"] == "conflicting_candidate"


def test_compare_facts_unit_difference_not_contradiction():
    out = compare_facts([
        {"value": 500, "unit": "馬力", "document_id": "a", "work_id": "w1"},
        {"value": 373, "unit": "キロワット", "document_id": "b", "work_id": "w2"}])
    assert out["pairs"][0]["status"] == "differing_unit"


def test_compare_facts_translation_same_unit():
    out = compare_facts([
        {"value": 500, "unit": "馬力", "document_id": "a", "work_id": "w1"},
        {"value": 500, "unit": "horsepower", "document_id": "b", "work_id": "w2"}])
    assert out["pairs"][0]["status"] == "consistent_candidate"


def test_compare_facts_independence_count():
    out = compare_facts([
        {"value": 120, "unit": "kw", "document_id": "ndl-copy", "work_id": "w1"},
        {"value": 120, "unit": "kw", "document_id": "ia-copy", "work_id": "w1"},
        {"value": 150, "unit": "kw", "document_id": "other", "work_id": "w2"}])
    assert out["document_count"] == 3
    assert out["independent_source_count"] == 2  # same work twice = one source
    statuses = {(p["a"], p["b"]): p["status"] for p in out["pairs"]}
    assert statuses[("ndl-copy", "other")] == "contradiction_candidate"
    # never a CONFIRMED contradiction anywhere
    assert all("confirmed" not in p["status"] for p in out["pairs"])
