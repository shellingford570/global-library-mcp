"""Build the Phase 8-F gold passage dataset from real pipeline output.

Positives are harvested from LIVE collect_evidence runs: only
pages the full pipeline admitted, and only passages whose
quote verifies verbatim against the fetched OCR. Negatives are
the frozen Phase 7 false-answer fixtures, labelled with the
rejection category from the Phase 7 diagnosis. Every case is
agent-verified (verified_by="agent", human_verified=false) -
nothing here claims expert human confirmation.

Splits are assigned deterministically (alternating) and frozen
with the file; the dev half may inform development, the eval
half is for measurement only.

Usage: python -m eval.build_gold   (live NDL; ~8 questions)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

QUESTIONS = [
    ("v01", "明治時代の郵便制度の発達について教えて"),
    ("v03", "明治時代のガス灯の導入と広がりについて教えて"),
    ("v04", "明治時代の新聞の創刊と発展について教えて"),
    ("v05", "昭和初期のラジオ放送の聴取者の広がりについて教えて"),
    ("v07", "大正時代の電話加入者の増加について教えて"),
    ("n01", "明治時代の鉄道開業について、新橋と横浜の間の鉄道がどのように開通したか当時の資料の記述を教えて"),
    ("n02", "明治時代の郵便制度の創設について当時の資料の記述を教えて"),
    ("n06", "明治時代のビール醸造の始まりについて当時の資料の記述を教えて"),
]

NEGATIVE_CATEGORY = {
    "q31": "ocr_garbage_index_blob",
    "q35": "unanchored_support",
    "q40": "numeric_mismatch_enumerative_page",
    "q52": "mentions_only_contents_page",
    "h03": "mentions_only_index",
    "h05": "compound_halves_no_assertion",
    "h22": "mentions_only",
    "h31": "subject_mismatch",
}


async def main() -> int:
    import httpx

    from global_library_mcp.nli import build_hypothesis
    from global_library_mcp.question import analyze_question
    from global_library_mcp.service import LibraryService

    cases: list[dict] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=False,
                                 headers={"User-Agent": "global-library-mcp/0.1 (+https://github.com/shellingford570/global-library-mcp)"}) as client:
        service = LibraryService(client)
        for qid, question in QUESTIONS:
            collected = await service.collect_evidence(question, ["ndl"], 10)
            hypothesis = build_hypothesis(analyze_question(question))
            for page in collected["evidence"]:
                for passage in (page.get("passages") or [])[:2]:
                    if not passage.get("quote_verified"):
                        continue
                    cases.append({
                        "id": f"g{len(cases) + 1:03d}",
                        "source_question_id": qid,
                        "question": question,
                        "claim": hypothesis,
                        "label": "supporting",
                        "library_id": page["library_id"],
                        "record_id": page["record_id"],
                        "page_id": page["page_id"],
                        "citation_key": page["citation_key"],
                        "passage_text": passage["text"],
                        "char_start": passage["char_start"],
                        "image_url": page.get("image_url"),
                        "support_reason": "pipeline-admitted passage with occurrence/diffusion stance cues: "
                                          + ", ".join(passage.get("stance_cues") or []),
                        "ocr_quality": (page.get("quality") or {}),
                        "verified_by": "agent",
                        "human_verified": False,
                    })
            print(f"{qid}: cumulative gold positives {len(cases)}", flush=True)
    fixtures = json.loads((ROOT / "eval" / "phase7-fixtures.json").read_text(encoding="utf-8"))
    for fixture in fixtures["cases"]:
        cases.append({
            "id": f"g{len(cases) + 1:03d}",
            "source_question_id": fixture["id"],
            "question": fixture["question"],
            "claim": None,
            "label": "must_reject",
            "rejection_category": NEGATIVE_CATEGORY.get(fixture["id"], "unsafe_promotion"),
            "library_id": "ndl",
            "record_id": fixture["record_id"],
            "page_id": fixture["page_id"],
            "citation_key": fixture["citation_key"],
            "passage_text": fixture["page_text"][:400],
            "char_start": None,
            "image_url": None,
            "support_reason": None,
            "ocr_quality": {},
            "verified_by": "agent",
            "human_verified": False,
        })
    for index, case in enumerate(cases):
        case["split"] = "dev" if index % 2 == 0 else "eval"
    payload = {
        "version": "gold-passages-v1-2026-11-24",
        "license_note": "Passages are short excerpts of public-domain historical OCR (NDL Digital Collections) recorded for evaluation; rights follow each source record.",
        "schema": "question / claim / label(supporting|must_reject) / record_id / page_id / passage_text / image_url / support_reason / ocr_quality / verified_by / human_verified / split(dev|eval)",
        "counts": {
            "total": len(cases),
            "supporting": sum(1 for c in cases if c["label"] == "supporting"),
            "must_reject": sum(1 for c in cases if c["label"] == "must_reject"),
        },
        "cases": cases,
    }
    out = ROOT / "eval" / "gold-passages.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {payload['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
