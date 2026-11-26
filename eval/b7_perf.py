"""b7 workspace performance evaluation on synthetic data
(brief sections 37-38; final review section 31 adds record
counts, excerpt sizes, WAL/SHM disk usage, memory, cold vs warm
cache, concurrent write/export timings and a measured restore
time). No upstream access: all records are generated locally.
Measures store operations at three scales and reports medians
of repeated timings with the environment.

Usage: .venv/bin/python eval/b7_perf.py [--scales small,medium,large]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import statistics
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from global_library_mcp.workspace.exports import to_bibtex, to_csl_json, to_ris
from global_library_mcp.workspace.store import WorkspaceStore
from global_library_mcp.workspace.transfer import export_project, import_project

SCALES = {
    "small": {"projects": 1, "docs_per_project": 100, "citations_per_doc": 3, "notes": 100},
    "medium": {"projects": 5, "docs_per_project": 200, "citations_per_doc": 3, "notes": 1000},
    "large": {"projects": 20, "docs_per_project": 500, "citations_per_doc": 3, "notes": 10000},
}


def timed(fn, repeat=3):
    values = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        values.append(time.perf_counter() - start)
    return statistics.median(values)


def _count(store, table):
    return store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def run_scale(name: str, spec: dict) -> dict:
    tmp = tempfile.mkdtemp(prefix=f"glm-b7-perf-{name}-")
    db = os.path.join(tmp, "workspace.db")
    t0 = time.perf_counter()
    store = WorkspaceStore(db)
    init_s = time.perf_counter() - t0
    project_ids = []
    for p in range(spec["projects"]):
        project = store.create_project(f"プロジェクト{p} 進化論の研究",
                                       "synthetic", tags=["進化論", "明治時代"])
        project_ids.append(project["project_id"])
        for d in range(spec["docs_per_project"]):
            doc = store.save_document(
                project["project_id"], "internet-archive", f"rec-{p}-{d}",
                {"title": f"On the Origin of Species 第{d}版 資料",
                 "author": "Darwin, Charles", "publication_date": "1859",
                 "language_raw": "en",
                 "rights_snapshot": {"statement": "Public Domain"}})
            for c in range(spec["citations_per_doc"]):
                store.save_citation(doc["saved_document_id"], {
                    "page_id": f"rec-{p}-{d}@{c}", "citation_key": f"k{p}-{d}-{c}",
                    "original_excerpt": "natural selection 自然選択の抜粋テキスト",
                    "rights_at_save": {"statement": "Public Domain"},
                    "provenance": "system_fetched",
                    "quotation_verification_status": "verified_against_fetched_ocr"})
    for n in range(spec["notes"]):
        store.save_note(project_ids[0], f"研究ノート {n}: ダーウィンへの考察",
                        title=f"ノート{n}")
    pid = project_ids[0]
    docs = store.list_documents(pid)
    payload = export_project(store, pid)
    excerpt_sizes = [len(c.get("original_excerpt") or "")
                     for c in payload["saved_citations"]]
    result = {
        "scale": name,
        "spec": spec,
        "db_init_s": round(init_s, 4),
        "records": {
            "projects_total": _count(store, "projects"),
            "documents_total": _count(store, "saved_documents"),
            "citations_total": _count(store, "saved_citations"),
            "notes_total": _count(store, "research_notes"),
            "documents_in_measured_project": len(docs),
            "citations_in_measured_project": len(payload["saved_citations"]),
            "notes_in_measured_project": len(payload["research_notes"]),
            "exported_records": sum(len(payload[k]) for k in
                                    ("saved_documents", "saved_citations",
                                     "research_notes", "search_history",
                                     "saved_comparisons", "collections")),
            "excerpt_chars_avg": round(statistics.mean(excerpt_sizes), 1) if excerpt_sizes else 0,
            "excerpt_chars_max": max(excerpt_sizes) if excerpt_sizes else 0,
        },
        "list_projects_ms": round(timed(lambda: store.list_projects()) * 1000, 2),
        "save_document_ms": round(timed(lambda: store.save_document(
            pid, "ndl", f"extra-{time.time_ns()}",
            {"title": "追加資料", "author": "著者", "publication_date": "1900"})) * 1000, 2),
        "save_note_ms": round(timed(lambda: store.save_note(
            pid, "追加ノート本文", title="追加")) * 1000, 2),
        "local_search_ms": round(timed(lambda: store.local_search(pid, "進化論")) * 1000, 2),
        "local_search_cjk_ms": round(timed(lambda: store.local_search(pid, "自然選択")) * 1000, 2),
        "bibtex_1000_ms": round(timed(lambda: to_bibtex(docs * max(1, 1000 // max(1, len(docs))))[:1000]) * 1000, 2),
        "ris_1000_ms": round(timed(lambda: to_ris(docs * max(1, 1000 // max(1, len(docs))))[:1000]) * 1000, 2),
        "csl_1000_ms": round(timed(lambda: to_csl_json(docs * max(1, 1000 // max(1, len(docs))))[:1000]) * 1000, 2),
        "json_export_ms": round(timed(lambda: export_project(store, pid)) * 1000, 2),
    }
    # concurrent writers: 4 threads x 25 notes each
    def _write_notes():
        for i in range(25):
            store.save_note(pid, f"同時書き込み {threading.current_thread().name}-{i}")
    threads = [threading.Thread(target=_write_notes) for _ in range(4)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result["concurrent_write_100_notes_ms"] = round((time.perf_counter() - start) * 1000, 2)
    # concurrent exports: 4 threads exporting the same project
    def _export():
        export_project(store, pid)
    threads = [threading.Thread(target=_export) for _ in range(4)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result["concurrent_export_x4_ms"] = round((time.perf_counter() - start) * 1000, 2)
    # import into a fresh store (one measured import)
    other_path = os.path.join(tmp, "imported.db")
    other = WorkspaceStore(other_path)
    result["json_import_ms"] = round(timed(lambda: import_project(other, payload), repeat=1) * 1000, 2)
    imported_pid = other.list_projects()[-1]["project_id"]
    result["records"]["imported_documents"] = len(other.list_documents(imported_pid))
    result["records"]["imported_citations"] = len(other.list_citations(imported_pid))
    result["records"]["imported_notes"] = len(other.list_notes(imported_pid))
    other.close()
    # backup + store-level restore (validate + swap + reopen)
    backup_path = os.path.join(tmp, "b.db")
    result["backup_ms"] = round(timed(lambda: store.backup(backup_path)) * 1000, 2)

    def _restore():
        candidate = os.path.join(tmp, "candidate.db")
        shutil.copyfile(backup_path, candidate)
        verdict = WorkspaceStore.validate_backup(candidate)
        assert verdict["ok"], verdict["problems"]
        os.replace(candidate, os.path.join(tmp, "restored.db"))
        reopened = WorkspaceStore(os.path.join(tmp, "restored.db"))
        reopened.list_projects()
        reopened.close()
    result["restore_ms"] = round(timed(_restore) * 1000, 2)
    # disk usage including WAL/SHM while the store is open
    result["disk_bytes"] = {
        "db": os.path.getsize(db),
        "wal": os.path.getsize(db + "-wal") if os.path.exists(db + "-wal") else 0,
        "shm": os.path.getsize(db + "-shm") if os.path.exists(db + "-shm") else 0,
    }
    result["db_bytes"] = result["disk_bytes"]["db"]
    result["process_max_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    store.close()
    # cold-cache local search: first query on a freshly opened store
    cold = WorkspaceStore(db)
    start = time.perf_counter()
    cold.local_search(pid, "進化論")
    result["local_search_cold_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["local_search_warm_ms"] = round(
        timed(lambda: cold.local_search(pid, "進化論")) * 1000, 2)
    cold.close()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="small,medium,large")
    ap.add_argument("--out", default="eval/results-b7-perf.json")
    args = ap.parse_args()
    results = {"environment": {"python": platform.python_version(),
                               "platform": platform.platform(),
                               "machine": platform.machine()},
               "scales": []}
    for name in args.scales.split(","):
        print(f"running scale {name}...", flush=True)
        results["scales"].append(run_scale(name, SCALES[name]))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
