"""b9 performance evaluation (brief section 37).

Configurations:
  A: local research path - LibraryService.search over a stub
     adapter (the core the research profile wraps);
  B: external profile, bibliographic/reference only;
  C: REMOVED in the final review - the excerpt tool no longer
     exists, so there is no excerpt path to benchmark;
  D: external profile under concurrent synthetic users
     (1 / 2 / 5 / 10 / 20).

All upstream data is synthetic and in-process; no real API is
touched and no load is placed on any library.

Usage: .venv/bin/python eval/b9_perf.py --out eval/results-b9-perf.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import global_library_mcp.service  # noqa: F401,E402  (import order)
import httpx  # noqa: E402

from global_library_mcp.adapters.base import LibraryAdapter  # noqa: E402
from global_library_mcp.external import ids as ext_ids  # noqa: E402
from global_library_mcp.external.auth import Principal, TokenValidator  # noqa: E402
from global_library_mcp.external.rights_policy import decide_transfer  # noqa: E402
from global_library_mcp.external.server import build_external_server  # noqa: E402
from global_library_mcp.models import SearchResult  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402
from tests.test_b9_external import _FakeRegistry, _FakeService, _config, _token  # noqa: E402


def timed(fn, repeats=5):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(samples), 2),
            "min_ms": round(min(samples), 2), "max_ms": round(max(samples), 2)}


async def timed_async(coro_fn, repeats=5):
    samples = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = await coro_fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(samples), 2),
            "min_ms": round(min(samples), 2), "max_ms": round(max(samples), 2)}, result


class _StubAdapter(LibraryAdapter):
    library_id = "stub"
    library_name = "Stub"

    def __init__(self):
        pass

    async def search(self, query, limit=10):
        return [SearchResult(library_id="stub", library_name="Stub",
                             record_id=f"r{i}", title=f"Stub Book {i}",
                             landing_url="https://example.org/x")
                for i in range(limit)]


async def main_async() -> dict:
    report: dict = {}

    # --- A: local research core -------------------------------------
    client = httpx.AsyncClient()
    service = LibraryService(client)
    service.adapters = {"stub": _StubAdapter()}
    service.default_libraries = ["stub"]
    a, _ = await timed_async(lambda: service.search("darwin", ["stub"], 10))
    report["A_local_search"] = a
    await client.aclose()

    # --- B: external, references only --------------------------------
    server, ctx = build_external_server(
        _config(), service=_FakeService(), registry=_FakeRegistry())
    ctx.local_principal = Principal(
        user_id="perf", scopes={"catalog:search", "metadata:read",
                                "libraries:read", "references:read"})
    ctx.runtime.consent.grant("perf", {"bibliographic", "references",
                                       "rights", "search_terms_upstream"})

    async def call(name, args):
        result = await server.call_tool(name, args)
        content = result[0] if isinstance(result, tuple) else result
        return "".join(getattr(c, "text", "") for c in content)

    init, _ = await timed_async(lambda: server.list_tools(), repeats=3)
    report["B_tools_list"] = init
    search_t, search_out = await timed_async(
        lambda: call("search", {"query": "darwin perf", "limit": 5}))
    report["B_search"] = search_t
    report["B_search_response_bytes"] = len(search_out.encode("utf-8"))
    doc_id = ext_ids.make_document_id("ndl", "12345")
    fetch_t, fetch_out = await timed_async(lambda: call("fetch", {"id": doc_id}))
    report["B_fetch"] = fetch_t
    report["B_fetch_response_bytes"] = len(fetch_out.encode("utf-8"))

    # Cache: the second identical search is served per-user.
    await call("search", {"query": "cache probe", "limit": 5})
    cache_t, _ = await timed_async(
        lambda: call("search", {"query": "cache probe", "limit": 5}))
    report["B_search_cached"] = cache_t

    # --- component timings -------------------------------------------
    validator = TokenValidator(_config())
    token = _token()
    report["auth_validate"] = timed(lambda: validator.validate(token))
    report["rights_decision"] = timed(
        lambda: decide_transfer("ndl", "Public Domain"))

    # --- C: excerpt path - removed in the final review --------
    report["C_excerpt"] = ("removed: the final review deleted the "
                           "excerpt tool; no excerpt path exists")

    # --- D: concurrent users ------------------------------------------
    report["D_concurrent"] = {}
    for users in (1, 2, 5, 10, 20):
        server_d, ctx_d = build_external_server(
            _config(), service=_FakeService(), registry=_FakeRegistry())
        for i in range(users):
            user = f"d-user-{i}"
            ctx_d.runtime.consent.grant(user, {"bibliographic", "references",
                                               "rights", "search_terms_upstream"})

        async def one(i):
            ctx_d.local_principal = Principal(
                user_id=f"d-user-{i}",
                scopes={"catalog:search", "metadata:read", "libraries:read",
                        "references:read"})
            result = await server_d.call_tool(
                "search", {"query": f"concurrent {i}", "limit": 3})
            return result

        start = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(users)))
        wall = (time.perf_counter() - start) * 1000
        report["D_concurrent"][str(users)] = {
            "wall_ms": round(wall, 2),
            "per_user_ms": round(wall / users, 2),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = asyncio.run(main_async())
    report["note"] = ("synthetic in-process measurements on the "
                      "development VM (1.5 shared CPUs); indicative, "
                      "not a production benchmark")
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
