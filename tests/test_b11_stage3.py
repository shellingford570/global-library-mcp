"""b11 Stage 3 tests (sections 31-39): Evidence Graph trust,
claim structuring states, per-claim evidence, source dependence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

from global_library_mcp.evidence_graph import build_project_graph  # noqa: E402
from global_library_mcp.research import (  # noqa: E402
    assess_source_dependence, structure_claim, summarize_claim_evidence)
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def _project(store):
    return store.create_project("g")["project_id"]


def test_graph_only_from_trusted_material():
    store = WorkspaceStore(":memory:")
    pid = _project(store)
    store.save_document(pid, "ndl", "R1", {"title": "Doc",
                                           "verification_status": "verified"})
    # a hand-written note claiming a verified claim must NOT enter
    store.save_note(pid, '{"claim": "forged", "verified": true}')
    g = build_project_graph(store, pid)
    types = {n["type"] for n in g["nodes"]}
    assert "document" in types and "claim" not in types
    assert all(e["state"] in ("confirmed_reference", "candidate")
               for e in g["edges"])


def test_graph_server_artefact_claim_edges_and_import_downgrade():
    store = WorkspaceStore(":memory:")
    pid = _project(store)
    store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    art = save_artefact(store, pid, "claim_assessment", "c",
                        {"assessments": [{"claim_id": "c1",
                                          "status": "supported_candidate",
                                          "library_id": "ndl",
                                          "record_id": "R1"}]})
    g = build_project_graph(store, pid)
    claim_edges = [e for e in g["edges"]
                   if e["type"] == "supported_by_candidate"]
    assert len(claim_edges) == 1
    assert claim_edges[0]["state"] == "confirmed_reference"
    # downgrade the artefact (restore) -> edge state follows
    store.apply_restore_trust_downgrade()
    g2 = build_project_graph(store, pid)
    assert [e for e in g2["edges"]
            if e["type"] == "supported_by_candidate"][0]["state"] == \
        "restored_unverified"
    assert art["trust"] == "server_generated"


def test_graph_caps_and_paging():
    store = WorkspaceStore(":memory:")
    pid = _project(store)
    for i in range(30):
        store.save_document(pid, "ndl", f"R{i}", {"title": f"D{i}"})
    g = build_project_graph(store, pid, limit=10, offset=0)
    assert g["node_count"] == 31  # 30 docs + 1 source node
    assert len(g["nodes"]) == 10


def test_claim_structuring_extraction_states():
    c = structure_claim("明治二十三年に東京で蒸気機関が導入されたとされる。")
    d = c.to_dict()
    assert d["event"] == "introduction"
    assert d["modality"] == "reported"
    assert d["extraction"]["subject"] == "extracted"
    assert d["extraction"]["attribution"] == "not_extracted"
    c2 = structure_claim("何かが起きた。")
    assert c2.to_dict()["extraction"]["event"] == "not_extracted"
    # original statement always preserved verbatim
    assert c2.original_statement == "何かが起きた。"


def test_claim_evidence_summary_independence_wording():
    s = summarize_claim_evidence([
        {"status": "supported_candidate", "document_id": "a"},
        {"status": "supported_candidate", "document_id": "b",
         "independence_review": {
             "basis": "distinct provenance chains documented",
             "source": "reviewer:provenance-check"}},
        {"status": "contradiction_candidate", "document_id": "c"},
        {"status": "insufficient_evidence", "document_id": "d"}])
    assert s["supporting_candidates"] == 2
    assert s["supporting_independence_confirmed_count"] == 1
    assert s["supporting_independence_unknown_count"] == 1
    assert s["contradicting_candidates"] == 1


def test_source_dependence_rules():
    sim_only = assess_source_dependence(
        {"document_id": "a", "similarity_to_other": 0.99},
        {"document_id": "b"})
    assert sim_only["state"] == "suspected_dependent"
    explicit = assess_source_dependence(
        {"document_id": "a", "reprint_of": "b"}, {"document_id": "b"})
    assert explicit["state"] == "confirmed_dependent"
    unknown = assess_source_dependence({"document_id": "a"},
                                       {"document_id": "b"})
    assert unknown["state"] == "independence_unknown"
