"""b10 Stage 5: workspace artefacts, progress, graph (sections
34-35) and Zotero-format export validation with synthetic data
(section 36). Uses a throwaway workspace database only."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    list_artefacts, project_relationship_graph,
    project_research_progress, save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def _store(tmp_path):
    store = WorkspaceStore(tmp_path / "ws.db")
    project = store.create_project("b10 test project")
    return store, project["project_id"]


def test_artefact_roundtrip_and_progress(tmp_path):
    store, pid = _store(tmp_path)
    save_artefact(store, pid, "claim_assessment", "hydro claim", {
        "claim": {"claim_id": "c1"},
        "assessments": [{"status": "insufficient_evidence"},
                        {"status": "supported_candidate"}]})
    save_artefact(store, pid, "contradiction", "unit pair", {
        "pairs": [{"status": "contradiction_candidate", "a": "x", "b": "y"}]})
    save_artefact(store, pid, "authority_resolution", "weber", {
        "status": "ambiguous"})
    arts = list_artefacts(store, pid)
    assert {a["kind"] for a in arts} == {
        "b10_claim_assessment", "b10_contradiction", "b10_authority_resolution"}
    progress = project_research_progress(store, pid)
    assert progress["claims_with_insufficient_evidence"] == 1
    assert progress["contradiction_candidates"] == 1
    assert progress["unverified_authority_candidates"] == 1
    # a plain note is not an artefact and stays untouched
    store.save_note(pid, "ordinary research note", title="memo")
    assert len(list_artefacts(store, pid)) == 3
    # b11 Stage 0: artefacts live in a dedicated table, not notes
    assert project_research_progress(store, pid)["research_notes"] == 1


def test_artefact_kind_validation(tmp_path):
    store, pid = _store(tmp_path)
    try:
        save_artefact(store, pid, "nonsense", "x", {})
        raise AssertionError("should reject unknown kinds")
    except ValueError:
        pass


def test_graph_candidate_edges(tmp_path):
    store, pid = _store(tmp_path)
    store.save_document(pid, "ndl", "100", {
        "title": "Kritik A", "author": "Immanuel Kant",
        "work_id_candidate": "work:kritik-reinen-vernunft",
        "author_id_candidate": "author:kant"})
    store.save_document(pid, "ddb", "200", {
        "title": "Kritik B", "author": "Immanuel Kant",
        "work_id_candidate": "work:kritik-reinen-vernunft",
        "author_id_candidate": "author:kant"})
    graph = project_relationship_graph(store, pid)
    relations = {e["relation"] for e in graph["edges"]}
    assert "same_work_candidate" in relations
    assert all(e["certainty"] == "candidate" for e in graph["edges"])


def test_existing_data_untouched(tmp_path):
    store, pid = _store(tmp_path)
    version_before = store.schema_version
    save_artefact(store, pid, "research_question", "q", {"question": {"text": "q"}})
    assert store.schema_version == version_before  # no migration
    assert store.integrity_check() == "ok"
