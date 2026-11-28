"""b11 Stage 4 tests (sections 40-48): synthesis + reports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

from global_library_mcp.research import structure_question  # noqa: E402
from global_library_mcp.synthesis import (  # noqa: E402
    build_timeline, classify_claim_states, further_research_candidates,
    generate_research_report, multilingual_comparison, numeric_synthesis)
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def test_synthesis_never_creates_confirmed_facts():
    out = classify_claim_states([
        {"claim_id": "a", "status": "supported_candidate"},
        {"claim_id": "b", "status": "verified"},       # not a real status
        {"claim_id": "c", "status": "confirmed"}])     # must not survive
    states = {o["state"] for o in out}
    assert states <= {"supported_candidate", "unresolved"}
    assert "confirmed" not in states and "verified" not in states


def test_timeline_kinds_distinct_and_no_causality():
    t = build_timeline([
        {"label": "pub", "year": 1890, "date_kind": "publication_date"},
        {"label": "event", "year": 1889, "date_kind": "event_date"},
        {"label": "bad", "year": 1900, "date_kind": "invented"},
        {"label": "nodate", "date_kind": "event_date"}])
    assert [e["label"] for e in t["events"]] == ["event", "pub"]
    assert t["undated_count"] == 2
    assert t["causality"] == "not_asserted"


def test_numeric_synthesis_no_cross_fact_aggregation():
    rows = numeric_synthesis([
        {"value": 100, "unit": "kW", "subject": "mill A", "place": "X"},
        {"value": 1, "unit": "MW", "subject": "mill B", "place": "Y"}])
    assert rows[0]["original_value"] == 100
    assert rows[0]["normalized_unit"] in ("W", "kW", "MW")
    assert "conversion" in rows[0]
    for r in rows:
        assert not any(k in r for k in ("average", "sum", "total",
                                        "rate", "mean"))


def test_multilingual_concept_is_not_claim():
    out = multilingual_comparison(
        [{"concept_id": "concept:steam-engine"}],
        [{"claim_id": "c1", "subject": "s"}])  # incomplete structure
    assert out["concept_alignments"] == 1
    assert out["claim_alignments"] == []


def test_further_research_candidates_unconfirmed():
    out = further_research_candidates(["missing edition year"])
    assert out[0]["existence"] == "unconfirmed"


def _demo_store():
    store = WorkspaceStore(":memory:")
    pid = store.create_project("demo")["project_id"]
    store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    save_artefact(store, pid, "research_question", "q",
                  {"question": structure_question(
                      "蒸気機関はいつ導入されたか").to_dict()})
    save_artefact(store, pid, "claim_assessment", "c",
                  {"assessments": [
                      {"claim_id": "c1", "status": "supported_candidate",
                       "library_id": "ndl", "record_id": "R1"},
                      {"claim_id": "c2", "status": "insufficient_evidence",
                       "library_id": "ndl", "record_id": "MISSING"}]})
    return store, pid


def test_report_reproducibility_and_ref_integrity():
    store, pid = _demo_store()
    rep = generate_research_report(store, pid, git_commit="abc123")
    for key in ("report_id", "schema_version", "project_id",
                "snapshot_id", "generated_at", "code_version",
                "git_commit", "evidence_policy_version",
                "rights_policy_version", "source_count",
                "unresolved_count"):
        assert key in rep, key
    assert rep["unresolved_count"] == 1
    assert rep["record_refs"] == [{"library_id": "ndl", "record_id": "R1"}]
    assert "Research Report" in rep["markdown"]
    # snapshot changes when project state changes
    store.save_document(pid, "ndl", "R2", {"title": "Doc2"})
    rep2 = generate_research_report(store, pid)
    assert rep2["snapshot_id"] != rep["snapshot_id"]


def test_report_contains_no_upstream_text():
    store, pid = _demo_store()
    rep = generate_research_report(store, pid)
    assert "ocr" not in rep["markdown"].lower()
