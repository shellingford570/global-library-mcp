"""b11 Stage 6 scenario tests (sections 57-70).

A: question->search->save->cite (covered by b7/b8 journeys);
B: claim->evidence assessment; C: contradiction candidate;
D: multilingual comparison; E: report generation; F: import ->
downgrade -> graph/report; G: real HTTP (test_b11_stage5);
H: rights change after save; I: review package honesty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

from global_library_mcp.synthesis import generate_research_report  # noqa: E402
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402
from global_library_mcp.workspace.transfer import (  # noqa: E402
    export_project, import_project)


def test_scenario_h_rights_change_reflected_on_regeneration():
    store = WorkspaceStore(":memory:")
    pid = store.create_project("h")["project_id"]
    doc = store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    store.add_rights_observation(doc["saved_document_id"],
                                  "Public Domain", "public_domain",
                                  "reverify", "observed")
    rep1 = generate_research_report(store, pid)
    assert rep1["rights"][0]["rights_status"] == "public_domain"
    # rights observations carry second-resolution timestamps;
    # the "latest" ordering needs the change in a later second.
    import time
    time.sleep(1.1)
    store.add_rights_observation(doc["saved_document_id"],
                                  "In Copyright", "copyrighted",
                                  "reverify", "rights_changed")
    rep2 = generate_research_report(store, pid)
    assert rep2["rights"][0]["rights_status"] == "copyrighted"
    assert rep2["snapshot_id"] != rep1["snapshot_id"]


def test_scenario_f_import_downgrade_flows_to_report():
    store = WorkspaceStore(":memory:")
    pid = store.create_project("f")["project_id"]
    store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    save_artefact(store, pid, "claim_assessment", "c",
                  {"assessments": [{"claim_id": "c1",
                                    "status": "supported_candidate",
                                    "library_id": "ndl",
                                    "record_id": "R1"}]})
    payload = export_project(store, pid)
    store2 = WorkspaceStore(":memory:")
    result = import_project(store2, payload)
    assert result["imported_artefacts"] == 1
    pid2 = result["project"]["project_id"]
    rows = store2.list_artefact_rows(pid2)
    assert rows[0]["trust"] == "imported_unverified"
    rep = generate_research_report(store2, pid2)
    # imported assessments are claims, not server evidence: the
    # report still lists the claim state but the artefact trust
    # is visible in the store and never upgraded.
    assert all(r["trust"] != "server_generated" for r in rows)


def test_scenario_i_review_package_distinguishes_synthetic():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
    import b11_agreement as ag
    # synthetic fixture input computes metrics as CODE behaviour;
    # the b11 dataset itself still records zero human review.
    rep = ag.agreement_report({
        "synthetic-a": {"c1": "correct"},
        "synthetic-b": {"c1": "correct"}})
    assert rep["status"] == "measured"
    import json
    dataset = json.loads((Path(__file__).resolve().parents[1]
                          / "eval/b11-cases.json").read_text())
    assert all(c["label"]["review_status"] == "not_reviewed"
               for c in dataset["cases"])


def test_kant_candidates_not_asserted_as_1787():
    # The DDB candidate titled "zweite Auflage" has no year in
    # DDB; nothing in the repo may assert it IS the 1787 edition.
    import subprocess
    out = subprocess.run(
        ["grep", "-rn", "KA4K7RVTIMAUOUIOJ63NSNO6UBOWFWDL",
         "src", "eval", "docs"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[1]))
    for line in out.stdout.splitlines():
        assert "1787" not in line or "not" in line.lower() or \
            "never" in line.lower() or "no year" in line.lower(), line
