"""Evidence Graph scale evaluation (section 38): synthetic
in-memory store with 100 / 1,000 / 10,000 document nodes."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.evidence_graph import build_project_graph  # noqa: E402
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def run(n: int) -> dict:
    store = WorkspaceStore(":memory:")
    pid = store.create_project(f"scale-{n}")["project_id"]
    for i in range(n):
        store.save_document(pid, "stub", f"rec-{i}",
                            {"title": f"Doc {i}",
                             "verification_status": "verified"})
    t0 = time.time()
    g = build_project_graph(store, pid, limit=50)
    dt = time.time() - t0
    return {"documents": n, "node_count": g["node_count"],
            "edge_count": g["edge_count"],
            "omitted_nodes": g["omitted_nodes"],
            "seconds": round(dt, 3)}


if __name__ == "__main__":
    for n in (100, 1000, 10000):
        print(run(n))
