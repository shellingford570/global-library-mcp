"""b11 final-review performance measurement (section 43).

Seeds workspaces of 100 / 1,000 / 10,000 documents (the largest
with 30,000 citations and 1,000+ artefacts) and measures graph
generation, partial graph fetch, research progress and report
generation (JSON + Markdown). Seeding uses one bulk transaction
through the store's own connection (a perf fixture, not an API
test). Reports median / p95 / max over repeated runs and the
process peak RSS. Processed totals are reported separately
from displayed (paged) counts wherever the graph cap applies.
"""
from __future__ import annotations

import json
import resource
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401

from global_library_mcp.evidence_graph import build_project_graph  # noqa: E402
from global_library_mcp.synthesis import generate_research_report  # noqa: E402
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    project_research_progress, save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def seed(store: WorkspaceStore, pid: str, docs: int, cits_per_doc: int,
         artefacts: int) -> None:
    conn = store._conn
    with store._lock, conn:
        for i in range(docs):
            did = f"doc{i:06d}"
            conn.execute(
                "INSERT INTO saved_documents (saved_document_id,"
                " project_id, library_id, record_id, title,"
                " rights_snapshot, saved_at, updated_at) VALUES"
                " (?, ?, 'ndl', ?, ?, '{}', '2026-01-01T00:00:00Z',"
                " '2026-01-01T00:00:00Z')",
                (did, pid, f"R{i}", f"Doc {i}"))
            for j in range(cits_per_doc):
                conn.execute(
                    "INSERT INTO saved_citations (citation_id,"
                    " saved_document_id, page_id, citation_key,"
                    " quotation_verification_status, page_mapping_status,"
                    " provenance, rights_at_save, saved_at) VALUES"
                    " (?, ?, ?, ?, 'verified', 'verified',"
                    " 'system_fetched', '{}', '2026-01-01T00:00:00Z')",
                    (f"cit{i:06d}-{j}", did, f"p{j}",
                     f"ndl:R{i}:p{j}"))
    # Artefact rows are bulk-inserted: save_artefact validates
    # references against the whole project (O(docs+citations)
    # per save), which is measured SEPARATELY below as
    # artefact_save_at_scale instead of dominating the seed.
    import json as _json
    import uuid as _uuid
    with store._lock, conn:
        for k in range(artefacts):
            payload = {
                "claim": {"claim_id": f"c{k}",
                          "original_statement": f"Claim {k}."},
                "assessments": [{
                    "claim_id": f"c{k}", "status": "supported_candidate",
                    "library_id": "ndl",
                    "record_id": f"R{k % max(docs, 1)}"}]}
            conn.execute(
                "INSERT INTO research_artefacts (artefact_id,"
                " project_id, kind, title, payload, trust,"
                " provenance, operation_id, algorithm_version,"
                " model, created_at) VALUES (?, ?,"
                " 'b10_claim_assessment', ?, ?, 'server_generated',"
                " 'server', 'op_perf', 'b11', '{}',"
                " '2026-01-01T00:00:00Z')",
                ("art_" + _uuid.uuid4().hex[:20], pid, f"c{k}",
                 _json.dumps(payload, ensure_ascii=False)))


def timed(fn, runs: int = 3) -> dict:
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append(round((time.perf_counter() - t0) * 1000, 1))
    return {"median_ms": statistics.median(samples),
            "p95_ms": sorted(samples)[int(len(samples) * 0.95) - 1]
            if len(samples) > 1 else samples[0],
            "max_ms": max(samples), "runs": samples}


def main() -> None:
    out = {"environment": "this VM (1.5 shared CPU class)",
           "scales": []}
    for docs, cits_per_doc, arts in ((100, 3, 10), (1000, 3, 100),
                                     (10000, 3, 1000)):
        store = WorkspaceStore(":memory:")
        pid = store.create_project(f"perf-{docs}")["project_id"]
        t0 = time.perf_counter()
        seed(store, pid, docs, cits_per_doc, arts)
        seed_ms = round((time.perf_counter() - t0) * 1000, 1)
        graph = build_project_graph(store, pid, limit=50)
        row = {
            "documents": docs,
            "citations": docs * cits_per_doc,
            "artefacts": arts,
            "seed_ms": seed_ms,
            "graph_total_nodes": graph["total_nodes"],
            "graph_total_edges": graph["total_edges"],
            "graph_build_and_page": timed(
                lambda: build_project_graph(store, pid, limit=50)),
            "progress": timed(
                lambda: project_research_progress(store, pid)),
            "report": timed(
                lambda: generate_research_report(store, pid), runs=2),
            "artefact_save_at_scale": timed(
                lambda: save_artefact(store, pid, "claim_assessment",
                                      "scale-probe",
                                      {"assessments": []}), runs=2),
            "peak_rss_mb": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        }
        out["scales"].append(row)
        print(json.dumps(row, ensure_ascii=False))
    out_path = Path(__file__).with_name("b11-perf-final.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")


if __name__ == "__main__":
    main()
