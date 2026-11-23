"""Phase 6-A: classify *where* each failed answerable question died.

For every evidence-labelled question in the Phase 5 run-3 results
whose status is not "answered", re-run collect_evidence live and
classify the failure stage:

  S0 no_candidates        bibliographic search returned nothing
  S1 candidate_miss       candidates exist but none is topical
                          (title carries no core concept) - the
                          right book is absent or buried deep
  S2 budget_miss          a topical candidate exists beyond the
                          fetched document budget
  S3 page_miss            topical document fetched, but no page
                          passed the OCR quality gate
  S4 gate_reject          quality-passed pages all screened out by
                          the relevance gate
  S5 semantic_reject      relevant pages demoted by the semantic /
                          temporal layer
  S6 downstream           evidence was collected; the failure is
                          in answer generation / claim screening

Output: eval/diagnosis-phase6.json with per-question stage,
candidate ranks, page ids and verdict reasons.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.question import analyze_question, concept_variants, normalize_text  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def topical_ranks(candidates: list[dict], analysis) -> list[int]:
    ranks = []
    for idx, item in enumerate(candidates, start=1):
        title_n = normalize_text(item.get("title") or "")
        if any(variant in title_n for c in analysis.core_concepts for variant in concept_variants(c)):
            ranks.append(idx)
    return ranks


async def main() -> int:
    failures = []
    for name in ("results-phase5.json", "results-phase5-holdout.json"):
        data = json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))
        for record in data["records"]:
            if record["expect"] == "evidence" and record["status"] != "answered":
                failures.append({"dataset": name, "id": record["id"], "question": record["question"],
                                 "phase5_status": record["status"]})
    print(f"diagnosing {len(failures)} failed answerable questions")
    out = []
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "global-library-mcp/0.1 (diagnosis)"}) as client:
        service = LibraryService(client)
        for item in failures:
            analysis = analyze_question(item["question"])
            try:
                result = await service.collect_evidence(item["question"], libraries=["ndl"], limit=5)
            except Exception as exc:  # noqa: BLE001
                out.append({**item, "stage": "error", "error": f"{type(exc).__name__}: {exc}"})
                continue
            candidates = (result.get("search") or {}).get("results", [])
            ranks = topical_ranks(candidates, analysis)
            tried = (result.get("retrieval") or {}).get("documents_tried", 0)
            evidence = result.get("evidence", [])
            related = result.get("related", [])
            unverified = result.get("unverified", [])
            fetched_topical = [r for r in ranks if r <= tried]
            if evidence:
                stage = "S6 downstream"
            elif not candidates:
                stage = "S0 no_candidates"
            elif not ranks:
                stage = "S1 candidate_miss"
            elif not fetched_topical:
                stage = "S2 budget_miss"
            elif any((p.get("semantics") or {}).get("relation") == "contradicts" for p in result.get("premise_contradictions", [])) or \
                    any((p.get("relevance") or {}).get("status") == "relevant" for p in related):
                stage = "S5 semantic_reject"
            elif related:
                stage = "S4 gate_reject"
            elif unverified:
                stage = "S3 page_miss"
            else:
                stage = "S3 page_miss"
            out.append({
                **item, "stage": stage,
                "candidates": len(candidates), "topical_ranks": ranks[:5],
                "documents_tried": tried,
                "evidence_pages": [p["citation_key"] for p in evidence],
                "related": [{"key": p["citation_key"], "relevance": (p.get("relevance") or {}).get("status"),
                             "semantics": (p.get("semantics") or {}).get("relation"),
                             "reasons": ((p.get("relevance") or {}).get("reasons") or [])[:2]} for p in related[:4]],
                "unverified_reasons": [u.get("reason") for u in unverified[:3]],
            })
            print(f"{item['id']}: {stage} (candidates={len(candidates)}, topical={ranks[:3]}, tried={tried})")
            await asyncio.sleep(0.25)
    payload = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "diagnoses": out}
    (ROOT / "eval" / "diagnosis-phase6.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(Counter(d["stage"] for d in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
