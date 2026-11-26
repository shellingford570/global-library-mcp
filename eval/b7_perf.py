"""b7 workspace performance evaluation on synthetic data
(brief sections 37-38). No upstream access: all records are
generated locally. Measures store operations at three scales
and reports medians of repeated timings with the environment.

Usage: .venv/bin/python eval/b7_perf.py [--scales small,medium,large]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
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


def run_scale(name: str, spec: dict) -> dict:
    tmp = tempfile.mkdtemp(prefix=f"glm-b7-perf-{name}-")
    db = os.path.join(tmp, "workspace.db")
    t0 = time.perf_counter()
    store = WorkspaceStore(db)
    init_s = time.perf_counter() - t0
    project_ids = []
    doc_ids = []
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
            doc_ids.append(doc["saved_document_id"])
            for c in range(spec["citations_per_doc"]):
                store.save_citation(doc["saved_document_id"], {
                    "page_id": f"rec-{p}-{d}@{c}", "citation_key": f"k{p}-{d}-{c}",
                    "original_excerpt": "natural selection 自然選択の抜粋テキスト",
                    "provenance": "system_fetched",
                    "quotation_verification_status": "verified_against_fetched_ocr"})
    for n in range(spec["notes"]):
        store.save_note(project_ids[0], f"研究ノート {n}: ダーウィンへの考察",
                        title=f"ノート{n}")
    pid = project_ids[0]
    docs = store.list_documents(pid)
    result = {
        "scale": name,
        "spec": spec,
        "db_init_s": round(init_s, 4),
        "db_bytes": os.path.getsize(db),
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
    }
    payload = export_project(store, pid)
    result["json_export_ms"] = round(timed(lambda: export_project(store, pid)) * 1000, 2)
    other_path = os.path.join(tmp, "imported.db")
    other = WorkspaceStore(other_path)
    result["json_import_ms"] = round(timed(lambda: import_project(other, payload), repeat=1) * 1000, 2)
    result["backup_ms"] = round(timed(lambda: store.backup(os.path.join(tmp, "b.db"))) * 1000, 2)
    store.close(); other.close()
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
