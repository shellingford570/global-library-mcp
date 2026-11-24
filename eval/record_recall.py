"""Recall A for newset2: did the frozen ground-truth record
reach the ranked candidate pool, and at what rank?

Replicates the search stage (same variants, dedupe, substring
variant reduction and ranking as collect_evidence) and reports
the rank of each question's expected record. Recall B (a
verified OCR page obtained) is read from the full evaluation
run's records. Output: eval/record-recall-phase7.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.evidence import extract_terms  # noqa: E402
from global_library_mcp.question import analyze_question, normalize_text  # noqa: E402
from global_library_mcp.service import LibraryService, rank_candidates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    data = json.loads((ROOT / "eval" / "newset2.json").read_text(encoding="utf-8"))
    ranks: dict[str, int | None] = {}
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "global-library-mcp/0.1 (record recall)"}) as client:
        service = LibraryService(client)
        for item in data["questions"]:
            expected = item.get("expected_records")
            if not expected:
                continue
            question = item["question"]
            analysis = analyze_question(question)
            search_terms = extract_terms(question)
            variants = list(dict.fromkeys([question, *search_terms]))
            terms = variants[1:]
            variants = variants[:1] + [
                v for v in terms if not any(v != o and v in o for o in terms)
            ]
            merged, seen, hits = [], set(), {}
            for candidate_query in variants:
                resp = await service.search(candidate_query, ["ndl"], 5)
                for result in resp.results:
                    key = (result.library_id, result.record_id)
                    hits[key] = hits.get(key, 0) + 1
                    if key not in seen:
                        seen.add(key)
                        merged.append(result)
            deduped, series = [], set()
            for result in merged:
                skey = (result.library_id, normalize_text(result.title or ""), normalize_text(result.author or ""))
                if skey in series:
                    continue
                series.add(skey)
                deduped.append(result)
            ranked = rank_candidates(analysis, deduped[:30], hits)
            rank = next((i for i, r in enumerate(ranked, start=1) if r.record_id in expected), None)
            ranks[item["id"]] = rank
            print(item["id"], "expected record rank:", rank)
            await asyncio.sleep(0.2)
    total = len(ranks)
    summary = {f"@{k}": round(sum(1 for v in ranks.values() if v is not None and v <= k) / total, 3) for k in (3, 6, 10, 30)}
    out = {"set": "newset2", "measured": total, "recall_a": summary, "ranks": ranks}
    (ROOT / "eval" / "record-recall-phase7.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Recall A:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
