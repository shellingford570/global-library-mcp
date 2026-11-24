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
    ("v02", "江戸時代の寺子屋ではどのような教育が行われていたか教えて"),
    ("v06", "明治時代の自転車の輸入と国産化について教えて"),
    ("v08", "明治時代の鉄道網の拡大について教えて"),
    ("n03", "明治時代の東京におけるガス灯の設置について当時の資料の記述を教えて"),
    ("n04", "大正時代の関東大震災について当時の記録は何を述べているか"),
    ("n05", "明治時代の尋常小学校で使われた教科書について当時の資料の記述を教えて"),
    ("n07", "明治時代の断髪令と洋服の着用について当時の資料の記述を教えて"),
    ("n08", "明治時代の三越呉服店の百貨店化について当時の資料の記述を教えて"),
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
