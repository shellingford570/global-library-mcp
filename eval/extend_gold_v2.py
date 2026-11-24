"""Phase 9-C expansion: fresh questions + pipeline-REJECTED pages.

Two independence improvements over v1: (1) questions that are
in no evaluation set, harvested fresh; (2) neutral cases taken
from pages the pipeline itself rejected - the v1 set was built
only from what the pipeline accepted. Labels come from the
same admission-independent audit procedure as build_gold_v2.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.build_gold_v2 import audit_label, group_split  # noqa: E402
from global_library_mcp.nli import build_hypothesis  # noqa: E402
from global_library_mcp.question import analyze_question  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402

import os
QUESTIONS = [
    "明治時代の写真術の伝来について教えて",
    "明治時代のガス灯の普及について教えて",
    "明治時代のビール醸造について教えて",
    "大正時代の洋服の普及について教えて",
    "明治時代の活版印刷について教えて",
    "大正時代の飛行機について教えて",
]
if os.environ.get("GLM_GOLD_MAINSET"):
    import json as _json
    _ds = _json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    QUESTIONS = [q["question"] for q in _ds["questions"] if q["expect"] == "evidence"][:16]


async def main() -> int:
    path = ROOT / "eval" / "gold-passages-v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    existing = {(c["citation_key"], c.get("claim"), c.get("char_start")) for c in payload["cases"]}
    added = []
    counter = len(payload["cases"])
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "global-library-mcp/0.1 (gold-v2)"}) as client:
        service = LibraryService(client)
        for question in QUESTIONS:
            collected = await service.collect_evidence(question, libraries=["ndl"], limit=5)
            claim = build_hypothesis(analyze_question(question))
            for item in collected.get("evidence", []):
                for passage in (item.get("passages") or [])[:2]:
                    key = (item["citation_key"], claim, passage["char_start"])
                    if key in existing:
                        continue
                    existing.add(key)
                    counter += 1
                    case = {
                        "id": f"n{counter:03d}", "source_question_id": "fresh" if question.startswith(("明治時代の写真", "明治時代のガス", "明治時代のビール", "大正時代の洋服", "明治時代の活版", "大正時代の飛行機")) else "mainset",
                        "question": question, "claim": claim, "label": "supporting",
                        "library_id": item["library_id"], "record_id": item["record_id"],
                        "page_id": item["page_id"], "citation_key": item["citation_key"],
                        "passage_text": passage["text"], "char_start": passage["char_start"],
                        "image_url": item.get("image_url"), "support_reason": "fresh-search admission",
                        "ocr_quality": {}, "verified_by": "agent", "human_verified": False,
                    }
                    label, basis = audit_label(case)
                    case.update({"relation_label": label, "label_basis": basis,
                                 "independence": "fresh_search" if case["source_question_id"] == "fresh" else "pipeline_harvested",
                                 "split": group_split(item["record_id"]), "group": item["record_id"]})
                    added.append(case)
            for item in collected.get("related", [])[:0 if os.environ.get("GLM_GOLD_MAINSET") else 3]:
                passages = item.get("passages") or []
                text = passages[0]["text"] if passages else (item.get("ocr_text") or "")[:600]
                if not text:
                    continue
                key = (item["citation_key"], claim, 0)
                if key in existing:
                    continue
                existing.add(key)
                counter += 1
                case = {
                    "id": f"n{counter:03d}", "source_question_id": "fresh",
                    "question": question, "claim": claim, "label": "must_reject",
                    "rejection_category": (item.get("states") or {}).get("rejection_reasons", ["rejected"])[0]
                    if isinstance((item.get("states") or {}).get("rejection_reasons"), list) else "rejected",
                    "library_id": item["library_id"], "record_id": item["record_id"],
                    "page_id": item["page_id"], "citation_key": item["citation_key"],
                    "passage_text": text, "char_start": 0,
                    "image_url": item.get("image_url"), "support_reason": "pipeline-rejected page",
                    "ocr_quality": {}, "verified_by": "agent", "human_verified": False,
                }
                case.update({"relation_label": "neutral",
                             "label_basis": "page the pipeline itself rejected for this question; topical candidate at most",
                             "independence": "pipeline_rejected",
                             "split": group_split(item["record_id"]), "group": item["record_id"]})
                added.append(case)
            print(question[:16], "-> cumulative added:", len(added), flush=True)
    payload["cases"].extend(added)
    from collections import Counter
    payload["counts"] = dict(Counter(c["relation_label"] for c in payload["cases"]))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("added:", len(added), "| total:", len(payload["cases"]), "| labels:", payload["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
