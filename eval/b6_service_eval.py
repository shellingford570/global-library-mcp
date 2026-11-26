"""Evaluation B (b6 final review, section 15): integration
evaluation through the REAL LibraryService.

Unlike evaluation A (b6_eval.py - a string-matching simulation
of variant generation), this harness runs the production code
path end to end: discovery analysis, expansion, routing,
variant ordering, early stop, the HTTP budget, bibliographic
filters, ranking and result explanations. Upstream libraries
are replaced by fixed HTTP fixtures served through a
BudgetedTransport subclass, so wire requests and bytes are
really counted by the production budget code. Adapter parsing
is the real adapter code for NDL / Internet Archive / LoC /
DDB; Gallica and Europeana fixtures return errors, as they do
from this network today.

Timings measured here are fixture-environment timings (no
network latency); they compare code paths, not upstream speed.

Usage:
  .venv/bin/python eval/b6_service_eval.py --out eval/results-b6-service-eval.json
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

from b6_eval import sim_normalize, variant_matches  # noqa: E402
from global_library_mcp.http import BudgetedTransport  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIXTURE_LIBRARIES = ("ndl", "internet-archive", "loc", "ddb")


def _matches(query: str, rec: dict) -> bool:
    text = sim_normalize(" ".join([rec.get("title") or "", rec.get("author") or "",
                                   " ".join(rec.get("subjects") or [])]))
    return variant_matches(query, text, sim_normalize(rec.get("title") or ""))


class FixtureTransport(BudgetedTransport):
    """Serves the fixed corpus through the real adapters."""

    def __init__(self, corpus: list[dict]):
        super().__init__()
        self.corpus = corpus

    def _records(self, library_id: str, query: str) -> list[dict]:
        return [r for r in self.corpus
                if r["library_id"] == library_id and _matches(query, r)]

    async def _send(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        host, path = url.host, url.path
        params = dict(url.params)
        if host == "archive.org" and path == "/advancedsearch.php":
            raw_q = params.get("q", "")
            query = raw_q[1:].split(") AND")[0] if raw_q.startswith("(") else raw_q
            docs = [{"identifier": r["record_id"], "title": r["title"],
                     "creator": r.get("author"), "date": str(r.get("year") or ""),
                     "description": " ".join(r.get("subjects") or [])}
                    for r in self._records("internet-archive", query)]
            return httpx.Response(200, json={"response": {"docs": docs}}, request=request)
        if host == "archive.org" and path.startswith("/metadata/"):
            rid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={
                "metadata": {"identifier": rid, "mediatype": "texts"},
                "files": [{"name": f"{rid}_djvu.xml"}, {"name": f"{rid}_djvu.txt"}],
            }, request=request)
        if host == "archive.org" and path.startswith("/download/"):
            parts = path.split("/")
            rid = parts[2]
            rec = next((r for r in self.corpus if r["record_id"] == rid), None)
            words = " ".join([rec["title"] if rec else "",
                              " ".join((rec or {}).get("subjects") or []),
                              (rec or {}).get("author") or ""])
            xml = ('<DjVuXML><BODY>'
                   f'<OBJECT data="x" width="100" height="100"><PARAM name="PAGE" value="p1"/>'
                   f'<LINE><WORD coords="0,0,1,1">{words}</WORD></LINE></OBJECT>'
                   '<OBJECT data="y" width="100" height="100"><PARAM name="PAGE" value="p2"/>'
                   f'<LINE><WORD coords="0,0,1,1">{words}</WORD></LINE></OBJECT>'
                   '</BODY></DjVuXML>')
            return httpx.Response(200, text=xml, request=request)
        if host == "lab.ndl.go.jp" and path == "/dl/api/book/search":
            items = [{"id": r["record_id"], "title": r["title"],
                      "responsibility": r.get("author"),
                      "published": r.get("year"), "highlights": []}
                     for r in self._records("ndl", params.get("keyword", ""))]
            return httpx.Response(200, json={"list": items}, request=request)
        if host == "www.loc.gov" and path == "/search/":
            results = [{"id": f"https://www.loc.gov/item/{r['record_id']}/",
                        "title": r["title"], "contributor": [r.get("author")],
                        "date": str(r.get("year") or ""),
                        "language": [r.get("language")] if r.get("language") else [],
                        "item": {}}
                       for r in self._records("loc", params.get("q", ""))]
            return httpx.Response(200, json={"results": results}, request=request)
        if host == "api.deutsche-digitale-bibliothek.de":
            docs = [{"id": r["record_id"], "title": r["title"],
                     "creator": r.get("author"), "date": r.get("year")}
                    for r in self._records("ddb", params.get("q", ""))]
            return httpx.Response(200, json={"response": {"docs": docs}}, request=request)
        if host == "gallica.bnf.fr":
            return httpx.Response(403, text="Forbidden", request=request)
        return httpx.Response(404, text="no fixture", request=request)


def _select_cases() -> list[dict]:
    fixed = json.loads((ROOT / "b6-fixed.json").read_text(encoding="utf-8"))
    corpus = json.loads((ROOT / "b6-corpus.json").read_text(encoding="utf-8"))
    by_id = {r["record_id"]: r for r in corpus}
    chosen = []
    for case in fixed:
        rel = case["relevant_record_ids"]
        if rel and all(by_id[r]["library_id"] in FIXTURE_LIBRARIES for r in rel):
            chosen.append(case)
        if len(chosen) >= 10:
            break
    return chosen


async def _run() -> dict:
    corpus = json.loads((ROOT / "b6-corpus.json").read_text(encoding="utf-8"))
    cases = _select_cases()
    import hashlib, subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parent,
                                capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        commit = "unknown"
    report: dict = {"evaluation_kind": "B: real LibraryService over fixed HTTP fixtures",
                    "label_source": "agent_assigned", "cases": len(cases), "modes": {},
                    "commit": commit,
                    "corpus_sha256": hashlib.sha256(
                        (ROOT / "b6-corpus.json").read_bytes()).hexdigest()[:16],
                    "dataset_sha256": hashlib.sha256(
                        (ROOT / "b6-fixed.json").read_bytes()).hexdigest()[:16]}
    for mode in ("quick", "standard"):
        transport = FixtureTransport(corpus)
        client = httpx.AsyncClient(transport=transport)
        service = LibraryService(client)
        rows = []
        for case in cases:
            started = time.monotonic()
            out = await service.research_materials(case["query"], mode=mode, limit=10)
            elapsed = time.monotonic() - started
            ids = [m["record_id"] for m in out["materials"]]
            rel = case["relevant_record_ids"]
            rows.append({
                "id": case["id"], "query": case["query"],
                "recall@10": len(set(ids[:10]) & set(rel)) / len(rel) if rel else 0.0,
                "materials": len(ids),
                "http_requests": out["http_stats"].get("requests"),
                "bytes_received": out["http_stats"].get("bytes_received"),
                "bytes_on_wire": out["http_stats"].get("bytes_on_wire"),
                "executed_variants": len((out.get("discovery") or {}).get("variant_execution", [])),
                "elapsed_s": round(elapsed, 3),
                "answerable": out["answerable"],
            })
        # Warm-cache rerun of the first case: the bibliographic
        # cache must absorb the repeated searches.
        hits_before = service.cache_stats["search_hits"]
        await service.research_materials(cases[0]["query"], mode=mode, limit=10)
        report["modes"][mode] = {
            "cases": rows,
            "recall@10": round(sum(r["recall@10"] for r in rows) / len(rows), 4) if rows else 0.0,
            "avg_http_requests": round(sum(r["http_requests"] or 0 for r in rows) / len(rows), 1) if rows else 0.0,
            "avg_bytes_received": int(sum(r["bytes_received"] or 0 for r in rows) / len(rows)) if rows else 0,
            "avg_elapsed_s": round(sum(r["elapsed_s"] for r in rows) / len(rows), 3) if rows else 0.0,
            "warm_rerun_cache_hits": service.cache_stats["search_hits"] - hits_before,
        }
        await client.aclose()
    # Filter behaviour through the real pipeline (section 3/4):
    transport = FixtureTransport(corpus)
    client = httpx.AsyncClient(transport=transport)
    service = LibraryService(client)
    kant = next(c for c in cases if "カント" in c["query"]) if any("カント" in c["query"] for c in cases) else cases[0]
    filtered = await service.research_materials(kant["query"], mode="standard", author="Immanuel Kant")
    report["filter_check"] = {
        "case": kant["id"], "author_filter": "Immanuel Kant",
        "materials_after": len(filtered["materials"]),
        # Judged by the production filter's own match record, not a naive
        # substring test: the lexicon legitimately matches name forms such
        # as カント, which a Latin substring check would wrongly reject.
        "all_materials_match_author": all(
            (m.get("filter_match") or {}).get("author_match") in ("exact_or_variant", "surname")
            for m in filtered["materials"]),
        "filters": filtered["filters"],
    }
    await client.aclose()
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    report = asyncio.run(_run())
    print(json.dumps({k: v for k, v in report.items() if k != "modes"}, ensure_ascii=False))
    for mode, data in report["modes"].items():
        print(mode, {k: v for k, v in data.items() if k != "cases"})
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
