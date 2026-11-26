"""Performance comparison for b8 (brief section 24).

Configurations:
  A: b7 default libraries only (loc, ndl, gallica,
     internet-archive) - the new-library hosts must see ZERO
     requests.
  B: the b8 libraries explicitly selected (finna, kb-delpher,
     japan-search, dpla) via plain search.
  C: language-targeted research routing - research_materials
     in standard mode with languages=[fi, sv, nl] over the new
     libraries (expansion variants are the routing mechanism).

All upstream responses are fixed fixtures served to the REAL
adapters through a counting BudgetedTransport, so attempts
and bytes are counted by the production budget code.
Fixture-environment timings (no network latency): they
compare code paths, not upstream speed.

Usage:
  .venv/bin/python eval/b8_perf.py --out eval/results-b8-perf.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx  # noqa: E402

from global_library_mcp.service import LibraryService  # noqa: E402  (import order)
from b8_eval import FixtureTransport  # noqa: E402

ROOT = Path(__file__).resolve().parent
NEW_HOSTS = {"api.finna.fi", "jsru.kb.nl", "resolver.kb.nl", "jpsearch.go.jp", "api.dp.la"}


class CountingTransport(FixtureTransport):
    def __init__(self, corpus):
        super().__init__(corpus)
        self.attempts: dict[str, int] = {}
        self.bytes_sent_up: dict[str, int] = {}

    async def _send(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.attempts[host] = self.attempts.get(host, 0) + 1
        if host in NEW_HOSTS:
            response = await super()._send(request)
        elif host == "archive.org":
            response = httpx.Response(200, json={"response": {"docs": [], "numFound": 0}})
        elif host == "www.loc.gov":
            response = httpx.Response(200, json={"results": [], "pagination": {"total": 0}})
        elif host in ("ndlsearch.ndl.go.jp", "iss.ndl.go.jp"):
            response = httpx.Response(
                200,
                text='<?xml version="1.0"?><searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><numberOfRecords>0</numberOfRecords></searchRetrieveResponse>',
                headers={"content-type": "text/xml"},
            )
        elif host == "gallica.bnf.fr":
            response = httpx.Response(
                200,
                text='<?xml version="1.0"?><searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><numberOfRecords>0</numberOfRecords></searchRetrieveResponse>',
                headers={"content-type": "text/xml"},
            )
        else:
            response = httpx.Response(404, text="no fixture")
        body = response.content or b""
        self.bytes_sent_up[host] = self.bytes_sent_up.get(host, 0) + len(body)
        return response


QUERIES_A = ["明治時代の水力発電", "Origin of Species", "産業革命"]
QUERIES_B = ["Suomen historia", "waterkracht", "浮世絵"]
QUERIES_C = ["水力発電の歴史", "鉄道の歴史"]


async def _run() -> dict:
    corpus = json.loads((ROOT / "b8-corpus.json").read_text(encoding="utf-8"))["records"]
    report: dict = {"kind": "fixture-environment performance comparison (no network latency)"}

    # --- A: defaults only --------------------------------------
    transport = CountingTransport(corpus)
    client = httpx.AsyncClient(transport=transport)
    service = LibraryService(client)
    started = time.monotonic()
    first_done = None
    results_a = 0
    for query in QUERIES_A:
        out = await service.search(query, None, 10)
        results_a += len(out.results)
        if first_done is None:
            first_done = time.monotonic() - started
    report["A_defaults"] = {
        "elapsed_s": round(time.monotonic() - started, 3),
        "first_result_s": round(first_done, 3) if first_done else None,
        "results": results_a,
        "attempts_by_host": dict(transport.attempts),
        "new_library_attempts": sum(v for h, v in transport.attempts.items() if h in NEW_HOSTS),
        "bytes_by_host": dict(transport.bytes_sent_up),
    }
    await client.aclose()

    # --- B: new libraries explicitly selected -------------------
    transport = CountingTransport(corpus)
    client = httpx.AsyncClient(transport=transport)
    service = LibraryService(client)
    started = time.monotonic()
    first_done = None
    results_b = 0
    errors_b: list = []
    for query in QUERIES_B:
        out = await service.search(query, ["finna", "kb-delpher", "japan-search", "dpla"], 10)
        results_b += len(out.results)
        errors_b.extend(out.errors)
        if first_done is None:
            first_done = time.monotonic() - started
    report["B_new_libraries_explicit"] = {
        "elapsed_s": round(time.monotonic() - started, 3),
        "first_result_s": round(first_done, 3) if first_done else None,
        "results": results_b,
        "errors": errors_b,
        "attempts_by_host": dict(transport.attempts),
        "bytes_by_host": dict(transport.bytes_sent_up),
    }
    await client.aclose()

    # --- C: language-targeted research routing ------------------
    transport = CountingTransport(corpus)
    client = httpx.AsyncClient(transport=transport)
    service = LibraryService(client)
    started = time.monotonic()
    first_done = None
    rows = []
    for query in QUERIES_C:
        out = await service.research_materials(
            query, libraries=["finna", "kb-delpher", "japan-search"],
            mode="standard", limit=10, languages=["fi", "sv", "nl"])
        if first_done is None:
            first_done = time.monotonic() - started
        rows.append({
            "query": query,
            "materials": len(out.get("materials") or []),
            "http_requests": (out.get("http_stats") or {}).get("requests"),
            "bytes_received": (out.get("http_stats") or {}).get("bytes_received"),
            "bytes_on_wire": (out.get("http_stats") or {}).get("bytes_on_wire"),
            "executed_variants": len((out.get("discovery") or {}).get("executed_variants") or []),
        })
    hits_before = service.cache_stats["search_hits"]
    await service.research_materials(
        QUERIES_C[0], libraries=["finna", "kb-delpher", "japan-search"],
        mode="standard", limit=10, languages=["fi", "sv", "nl"])
    report["C_language_routing"] = {
        "elapsed_s": round(time.monotonic() - started, 3),
        "first_result_s": round(first_done, 3) if first_done else None,
        "cases": rows,
        "attempts_by_host": dict(transport.attempts),
        "warm_rerun_cache_hits": service.cache_stats["search_hits"] - hits_before,
    }
    await client.aclose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = asyncio.run(_run())
    for key, value in report.items():
        if isinstance(value, dict):
            print(key, {k: v for k, v in value.items() if k != "cases"})
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
