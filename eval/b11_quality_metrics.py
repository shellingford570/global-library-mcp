"""b11 research-quality metrics, measured individually
(final review section 39).

Each metric is computed over a small AGENT-LABELLED fixture set
built into this file (labels are the fixture author's intent,
not human annotation and not source-confirmed ground truth).
Anything this script does not measure is reported as
"unmeasured" - implementation existence is never presented as
a measured accuracy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401

from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, build_trusted_candidate, compare_facts,
    register_admitted_evidence, structure_claim)
from global_library_mcp.synthesis import generate_research_report  # noqa: E402
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402

# (statement, fields a reader can identify in it)
EXTRACTION_CASES = [
    ("明治二十三年に東京で蒸気機関が導入された。",
     {"year": 1890, "place": "東京", "subject": "蒸気機関"}),
    ("1890年に横浜で発電所が建設された。",
     {"year": 1890, "place": "横浜", "subject": "発電所"}),
    ("大正五年に大阪で電話が開通した。",
     {"year": 1916, "place": "大阪", "subject": "電話"}),
    ("1900年に京都で市電が運行を開始した。",
     {"year": 1900, "place": "京都", "subject": "市電"}),
]
FIELDS = ("subject", "predicate", "object", "year", "place",
          "quantity", "unit", "negation", "condition")


def extraction_metrics() -> dict:
    per_field_hits = {f: 0 for f in FIELDS}
    per_field_total = {f: 0 for f in FIELDS}
    preserved = 0
    for statement, expected in EXTRACTION_CASES:
        claim = structure_claim(statement)
        d = claim.to_dict()
        if claim.original_statement == statement:
            preserved += 1
        for field, want in expected.items():
            per_field_total[field] += 1
            got = None
            if field == "year":
                got = (d.get("time") or {}).get("years_mentioned") or []
                hit = want in got
            elif field == "place":
                hit = d.get("place") == want
            elif field == "subject":
                hit = d.get("subject") == want
            else:
                hit = False
            per_field_hits[field] += 1 if hit else 0
    rates = {}
    for f in FIELDS:
        rates[f] = (round(per_field_hits[f] / per_field_total[f], 4)
                    if per_field_total[f] else "unmeasured")
    return {"cases": len(EXTRACTION_CASES), "per_field_rate": rates,
            "fields_without_labelled_cases": [
                f for f in FIELDS if not per_field_total[f]],
            "original_statement_preservation_rate":
                round(preserved / len(EXTRACTION_CASES), 4)}


def _token(text: str, record: str = "1") -> str:
    return register_admitted_evidence(
        library_id="ndl", record_id=record, page_id="1", text=text,
        document_identity_state="upstream_confirmed",
        page_identity_state="verified_mapping",
        admission_state="admitted")


def resolution_and_error_metrics() -> dict:
    # reference resolution: genuine tokens resolve, forged don't
    claim = structure_claim("明治25年に横浜で発電所が建設された。")
    good = build_trusted_candidate(
        **{"evidence_ref_token": _token("明治25年 横浜 発電所"),
           "text": "明治25年 横浜 発電所"})
    try:
        forged = build_trusted_candidate(
            **{"evidence_ref_token": "evr_forged", "text": "x"})
    except Exception:
        forged = None
    resolved = sum(x is not None for x in (good, forged))
    # false support: unrelated evidence must not support
    rows = assess_claim_evidence(claim, [build_trusted_candidate(
        **{"evidence_ref_token": _token("全く無関係な文章。天気の話。", "9"),
           "text": "全く無関係な文章。天気の話。"})])
    false_support = sum(1 for r in rows
                        if r["status"] == "supported_candidate")
    # false contradiction: identical facts must not contradict
    fact = {"subject": "発電所", "predicate": "出力", "object": "電力",
            "place": "横浜", "unit": "kW", "value": 100.0,
            "library_id": "ndl", "record_id": "1"}
    out = compare_facts([fact, dict(fact, record_id="2")])
    false_contra = sum(1 for p in out["pairs"]
                       if p["status"] == "contradiction_candidate")
    # independence misrecognition: bare assertions never confirm
    a = dict(fact, independence_basis="verified")
    b = dict(fact, record_id="2", independence_basis="different document")
    out2 = compare_facts([a, b])
    return {
        "evidence_reference_resolution_rate": {
            "resolved": resolved, "of": 2,
            "genuine_resolved": good is not None,
            "forged_resolved": forged is not None},
        "false_support_rate": {"false_support": false_support,
                               "of": len(rows)},
        "false_contradiction_rate": {"false_contradiction": false_contra,
                                     "of": len(out["pairs"])},
        "independence_misrecognition": {
            "independently_confirmed":
                out2["independently_confirmed_source_count"],
            "user_asserted": out2["independence_user_asserted_count"]}}


def report_resolution_metric() -> dict:
    store = WorkspaceStore(":memory:")
    pid = store.create_project("metrics")["project_id"]
    store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    save_artefact(store, pid, "claim_assessment", "c", {
        "claim": {"claim_id": "c1", "original_statement": "S."},
        "assessments": [
            {"claim_id": "c1", "status": "supported_candidate",
             "library_id": "ndl", "record_id": "R1"},
            {"claim_id": "c1", "status": "insufficient_evidence",
             "library_id": "ndl", "record_id": "MISSING"}]})
    rep = generate_research_report(store, pid)
    total_refs = len(rep["record_refs"]) + rep["unresolved_count"]
    return {"resolved_refs": len(rep["record_refs"]),
            "total_refs": total_refs,
            "report_citation_resolution_rate":
                round(len(rep["record_refs"]) / total_refs, 4)
                if total_refs else "unmeasured"}


def main() -> None:
    result = {
        "fixture": "agent-labelled built-in fixtures (not human, "
                   "not source-confirmed)",
        "extraction": extraction_metrics(),
        "resolution_and_errors": resolution_and_error_metrics(),
        "report": report_resolution_metric(),
        "unmeasured": [
            "predicate/object/quantity/unit/negation/condition "
            "extraction rates (no labelled cases in the fixture)",
            "real-model NLI quality",
            "independent human evaluation (0 reviewers)"],
    }
    out = Path(__file__).with_name("b11-quality-metrics.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
