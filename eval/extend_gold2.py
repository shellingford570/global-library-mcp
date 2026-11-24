"""Extend the gold dataset with a second harvest (Phase 8-F).

Merges new pipeline-admitted passages into eval/gold-passages.json,
deduped by (citation_key, char_start), ids continued, splits
re-assigned deterministically across the merged list.

Usage: python -m eval.extend_gold   (live NDL)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

QUESTIONS = [
    ("q02", "明治時代の鉄道開業について当時の資料は何を述べているか"),
    ("q04", "明治時代の郵便制度の始まりについて教えて"),
    ("q05", "横浜開港について当時の資料の記述を教えて"),
    ("q08", "日本の活版印刷の始まりについて当時の資料は何を述べているか"),
    ("q10", "日本の紡績業の機械化について当時の資料の記述を教えて"),
    ("q12", "水力発電の仕組みについて当時の技術書は何と説明しているか"),
    ("q15", "電灯の普及について当時の資料は何を述べているか"),
    ("q16", "水力電気の送電について当時の技術書の説明を教えて"),
    ("q18", "明治時代の種痘について当時の資料の記述を教えて"),
    ("q19", "コレラの流行と対策について当時の記録は何を述べているか"),
]


async def main() -> int:
    import httpx

    from global_library_mcp.nli import build_hypothesis
    from global_library_mcp.question import analyze_question
    from global_library_mcp.service import LibraryService

    out = ROOT / "eval" / "gold-passages.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    cases = payload["cases"]
    seen = {(c["citation_key"], c.get("char_start")) for c in cases}
    next_id = len(cases) + 1
    async with httpx.AsyncClient(timeout=30, follow_redirects=False,
                                 headers={"User-Agent": "global-library-mcp/0.1 (+https://github.com/shellingford570/global-library-mcp)"}) as client:
        service = LibraryService(client)
        for qid, question in QUESTIONS:
            collected = await service.collect_evidence(question, ["ndl"], 10)
            hypothesis = build_hypothesis(analyze_question(question))
            added = 0
            for page in collected["evidence"]:
                for passage in (page.get("passages") or [])[:3]:
                    key = (page["citation_key"], passage["char_start"])
                    if key in seen or not passage.get("quote_verified"):
                        continue
                    seen.add(key)
                    cases.append({
                        "id": f"g{next_id:03d}",
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
                    next_id += 1
                    added += 1
            print(f"{qid}: +{added} (total {len(cases)})", flush=True)
    for index, case in enumerate(cases):
        case["split"] = "dev" if index % 2 == 0 else "eval"
    payload["counts"] = {
        "total": len(cases),
        "supporting": sum(1 for c in cases if c["label"] == "supporting"),
        "must_reject": sum(1 for c in cases if c["label"] == "must_reject"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {payload['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
