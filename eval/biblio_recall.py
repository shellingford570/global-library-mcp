"""Bibliographic Recall@K, measured at the search stage alone.

Replicates collect_evidence's Stage 1 exactly (same query
variants, merge, series dedupe and rank_candidates ordering) and
records, for every answerable question, the rank of the first
candidate whose title carries a core concept ("topical"). This
is the bibliographic half of the Recall@K pair; the OCR-evidence
half (first evidence-producing document rank) comes from the
full evaluation runs. Output: eval/biblio-recall-phase6.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.evidence import extract_terms  # noqa: E402
from global_library_mcp.question import analyze_question, concept_variants, normalize_text  # noqa: E402
from global_library_mcp.service import LibraryService, rank_candidates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    out: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "global-library-mcp/0.1 (biblio recall)"}) as client:
        service = LibraryService(client)
        for name in ("questions.json", "holdout.json", "newset.json"):
            data = json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))
            items = data["questions"] if isinstance(data, dict) else data
            ranks: dict[str, int | None] = {}
            for item in items:
                if item["expect"] != "evidence":
                    continue
                question = item["question"]
                analysis = analyze_question(question)
                search_terms = extract_terms(question)
                merged, seen, hits = [], set(), {}
                for candidate_query in dict.fromkeys([question, *search_terms]):
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
                first = None
                for idx, result in enumerate(ranked, start=1):
                    title_n = normalize_text(result.title or "")
                    if any(variant in title_n for c in analysis.core_concepts for variant in concept_variants(c)):
                        first = idx
                        break
                ranks[item["id"]] = first
                await asyncio.sleep(0.2)
            total = len(ranks)
            recall = {f"@{k}": round(sum(1 for v in ranks.values() if v is not None and v <= k) / total, 3) for k in (3, 6, 10)}
            out[name] = {"answerable": total, "biblio_recall": recall, "first_topical_rank": ranks}
            print(name, recall)
    (ROOT / "eval" / "biblio-recall-phase6.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
