"""Evaluation for b8 (brief section 19): fixed fixture
evaluation through the REAL LibraryService research path.

PROXY EVALUATION: the relevance labels in eval/b8-*.json are
agent-assigned, and the corpus (eval/b8-corpus.json) is a
fixed fixture served through a BudgetedTransport subclass to
the REAL Finna / KB / Japan Search adapters. Fixture results
are never live verification and are never mixed with the live
results in docs/b8-live-verification.md.

Metrics per set and mode: Recall@5/@10/@20, Precision@5,
MRR, nDCG@10, cross-language discovery rate (among cases
flagged cross_language with relevant records, the fraction
with at least one relevant record in the top 10 whose
language differs from the query language family), average
HTTP requests, partial failures. For the negative set:
materials returned per case (bibliographic false positives
are reported, not hidden).

Usage:
  .venv/bin/python eval/b8_eval.py --out eval/results-b8-eval.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx  # noqa: E402

from global_library_mcp.service import LibraryService  # noqa: E402  (import order: service first)
from global_library_mcp.http import BudgetedTransport  # noqa: E402

ROOT = Path(__file__).resolve().parent
_LANG3 = {"fi": "fin", "sv": "swe", "nl": "nld", "ja": "jpn", "en": "eng"}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _tokens(text: str) -> list[str]:
    parts = re.split(r"[^0-9a-zà-ÿåäöæøéèêàâîôûäöüß一-鿿ぁ-んァ-ヶ]+", _norm(text))
    return [p for p in parts if len(p) >= 2]


def _matches(query: str, rec: dict) -> bool:
    text = _norm(" ".join([rec.get("title") or "", rec.get("author") or "",
                           " ".join(rec.get("subjects") or [])]))
    query_norm = _norm(query).strip()
    if query_norm and query_norm in text:
        return True
    return any(token in text for token in _tokens(query))


def _kb_urn(rec: dict) -> str:
    return rec["record_id"]


class FixtureTransport(BudgetedTransport):
    """Serves the fixed corpus to the real new-library
    adapters, host by host."""

    def __init__(self, corpus: list[dict]):
        super().__init__()
        self.corpus = corpus

    def _records(self, library_id: str, query: str) -> list[dict]:
        return [r for r in self.corpus
                if r["library_id"] == library_id and _matches(query, r)]

    async def _send(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        host, path = url.host, url.path
        params = url.params
        if host == "api.finna.fi" and path == "/api/v1/search":
            records = self._records("finna", params.get("lookfor", ""))
            limit = int(params.get("limit", "10") or 10)
            page = int(params.get("page", "1") or 1)
            window = records[(page - 1) * limit: page * limit]
            body = {
                "resultCount": len(records),
                "records": [
                    {
                        "id": r["record_id"],
                        "title": r["title"],
                        "authors": {"primary": {r["author"]: {}}} if r.get("author") else {},
                        "year": r.get("year"),
                        "languages": [_LANG3.get(r["language"], "eng")],
                        "formats": [{"value": "0/Book/", "translated": "Kirja"}],
                        "buildings": [{"value": "0/Test/", "translated": "Test Library"}],
                        "usageRights": [],
                    }
                    for r in window
                ],
                "status": "OK",
            }
            return httpx.Response(200, json=body)
        if host == "api.finna.fi" and path == "/api/v1/record":
            wanted = params.get("id", "")
            found = [r for r in self.corpus
                     if r["library_id"] == "finna" and r["record_id"] == wanted]
            body = {"resultCount": len(found),
                    "records": [{"id": r["record_id"], "title": r["title"],
                                 "languages": [_LANG3.get(r["language"], "eng")],
                                 "usageRights": [], "formats": [], "buildings": []}
                                for r in found],
                    "status": "OK"}
            return httpx.Response(200, json=body)
        if host == "jsru.kb.nl":
            records = self._records("kb-delpher", params.get("query", ""))
            rows = []
            for r in records:
                rows.append(
                    "<srw:record><srw:recordData>"
                    f"<dc:date>{r.get('year')}/01/01 00:00:00</dc:date>"
                    f"<dc:identifier>http://resolver.kb.nl/resolve?urn={_kb_urn(r)}:ocr</dc:identifier>"
                    f"<dc:title>{r['title']}</dc:title><dc:type>artikel</dc:type>"
                    "</srw:recordData></srw:record>"
                )
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                f"<srw:numberOfRecords>{len(records)}</srw:numberOfRecords>"
                f"<srw:records>{''.join(rows)}</srw:records></srw:searchRetrieveResponse>"
            )
            return httpx.Response(200, text=body, headers={"content-type": "text/xml"})
        if host == "jpsearch.go.jp" and path == "/rdf/sparql":
            sparql = params.get("query", "")
            match = re.search(r'LCASE\("((?:[^"\\]|\\.)*)"\)', sparql)
            literal = match.group(1).replace('\\"', '"').replace("\\\\", "\\") if match else ""
            records = self._records("japan-search", literal)
            bindings = [
                {"s": {"type": "uri", "value": f"https://jpsearch.go.jp/data/{r['record_id']}"},
                 "name": {"type": "literal", "value": r["title"], "xml:lang": "ja"}}
                for r in records
            ]
            return httpx.Response(200, json={"head": {"vars": ["s", "name"]},
                                             "results": {"bindings": bindings}})
        return httpx.Response(404, text="no fixture for this host")


def _metrics(ids: list[str], relevant: set[str]) -> dict:
    def recall(k: int) -> float:
        return len(set(ids[:k]) & relevant) / len(relevant) if relevant else 0.0

    precision5 = len(set(ids[:5]) & relevant) / 5 if relevant else 0.0
    mrr = 0.0
    for index, rid in enumerate(ids):
        if rid in relevant:
            mrr = 1.0 / (index + 1)
            break
    dcg = sum(1.0 / math.log2(index + 2) for index, rid in enumerate(ids[:10]) if rid in relevant)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(relevant), 10)))
    return {
        "recall@5": round(recall(5), 4),
        "recall@10": round(recall(10), 4),
        "recall@20": round(recall(20), 4),
        "precision@5": round(precision5, 4),
        "mrr": round(mrr, 4),
        "ndcg@10": round(dcg / ideal, 4) if ideal else 0.0,
    }


async def _run_set(service: LibraryService, cases: list[dict], mode: str,
                   id_map: dict[str, str], corpus_by_id: dict[str, dict]) -> dict:
    rows = []
    for case in cases:
        started = time.monotonic()
        out = await service.research_materials(
            case["query"], libraries=case["libraries"], mode=mode, limit=20)
        elapsed = time.monotonic() - started
        materials = out.get("materials") or []
        ids = [id_map.get(m.get("record_id"), m.get("record_id")) for m in materials]
        relevant = set(case["relevant_record_ids"])
        row = {
            "id": case["id"], "query": case["query"],
            "materials": len(ids),
            "http_requests": (out.get("http_stats") or {}).get("requests"),
            "elapsed_s": round(elapsed, 3),
            "errors": out.get("errors") or [],
        }
        if relevant:
            row.update(_metrics(ids, relevant))
            if case.get("cross_language"):
                found_cross = any(
                    corpus_by_id.get(rid, {}).get("language") not in (None, _query_family(case["query"]))
                    for rid in ids[:10] if rid in relevant
                )
                row["cross_language_found"] = bool(found_cross)
        rows.append(row)
    positive = [r for r in rows if "recall@10" in r]
    aggregate = {}
    if positive:
        for key in ("recall@5", "recall@10", "recall@20", "precision@5", "mrr", "ndcg@10"):
            aggregate[key] = round(sum(r[key] for r in positive) / len(positive), 4)
        cross = [r for r in positive if "cross_language_found" in r]
        aggregate["cross_language_cases"] = len(cross)
        aggregate["cross_language_discovery_rate"] = (
            round(sum(1 for r in cross if r["cross_language_found"]) / len(cross), 4) if cross else None)
        aggregate["avg_http_requests"] = round(
            sum(r["http_requests"] or 0 for r in positive) / len(positive), 1)
    else:
        aggregate["cases_returning_materials"] = sum(1 for r in rows if r["materials"] > 0)
        aggregate["total_materials_returned"] = sum(r["materials"] for r in rows)
    aggregate["cases"] = rows
    return aggregate


def _query_family(query: str) -> str:
    if re.search(r"[ぁ-んァ-ヶ一-鿿]", query):
        return "ja"
    lowered = query.lower()
    if any(ch in lowered for ch in "åäö") and any(w in lowered for w in ("och", "historia", "vatten", "järnväg", "tidning")):
        return "sv"
    if any(w in lowered for w in ("historia", "rautatie", "vesivoima", "itsenäisyys", "suomen")):
        return "fi"
    if any(w in lowered for w in ("waterkracht", "spoorweg", "onderwijs", "stoommachine", "locomotief", "dam", "geschiedenis")):
        return "nl"
    return "en"


async def _run() -> dict:
    corpus_doc = json.loads((ROOT / "b8-corpus.json").read_text(encoding="utf-8"))
    corpus = corpus_doc["records"]
    id_map: dict[str, str] = {}
    corpus_by_id: dict[str, dict] = {}
    for rec in corpus:
        short = rec.get("corpus_id") or rec["record_id"]
        id_map[rec["record_id"]] = short
        corpus_by_id[short] = rec
    report: dict = {"kind": "fixture proxy evaluation (agent-assigned labels)",
                    "modes": {}}
    for set_name in ("dev", "fixed", "negative"):
        cases = json.loads((ROOT / f"b8-{set_name}.json").read_text(encoding="utf-8"))["cases"]
        for mode in ("quick", "standard"):
            transport = FixtureTransport(corpus)
            client = httpx.AsyncClient(transport=transport)
            service = LibraryService(client)
            report["modes"][f"{set_name}/{mode}"] = await _run_set(
                service, cases, mode, id_map, corpus_by_id)
            await client.aclose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = asyncio.run(_run())
    for name, data in report["modes"].items():
        summary = {k: v for k, v in data.items() if k != "cases"}
        print(name, summary)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
