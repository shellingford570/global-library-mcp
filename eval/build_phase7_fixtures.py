"""Phase 7-A: reproduce the Phase 6 false answers as fixed fixtures.

For each of the eight cases, take the page the Phase 6 run
actually cited, fetch its OCR from the library (the original),
and record: bibliographic context (from a fresh collect run),
the page text, page kind, and the gate verdicts computed on the
fixture itself. Output: eval/phase7-fixtures.json - the offline
regression fixtures used by tests/test_phase7_fixtures.py.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.evidence import classify_page_kind  # noqa: E402
from global_library_mcp.question import analyze_question  # noqa: E402
from global_library_mcp.relevance import assess_relevance  # noqa: E402
from global_library_mcp.semantics import RuleBasedSemanticChecker  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASES = ["q31", "q35", "q40", "q52", "h03", "h05", "h22", "h31"]


async def main() -> int:
    questions: dict[str, dict] = {}
    for name in ("questions.json", "holdout.json"):
        data = json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))
        for item in data["questions"]:
            questions[item["id"]] = item
    cited: dict[str, str] = {}
    for name in ("results-phase6.json", "results-phase6-holdout.json"):
        data = json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))
        for record in data["records"]:
            if record["id"] in CASES and record["citations"]:
                cited[record["id"]] = record["citations"][0]
    fixtures = []
    checker = RuleBasedSemanticChecker()
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "global-library-mcp/0.1 (phase7 fixtures)"}) as client:
        service = LibraryService(client)
        for case_id in CASES:
            item = questions[case_id]
            key = cited[case_id]
            library_id, record_id, page_id = key.split(":", 2)
            adapter = service.adapters[library_id]
            page = await adapter.get_page_text(page_id)
            text = page.get("contents") or ""
            analysis = analyze_question(item["question"])
            relevance = assess_relevance(analysis, text, publication_year=None)
            semantics = checker.assess(analysis, text, publication_year=None)
            fixtures.append({
                "id": case_id, "question": item["question"], "expect": item["expect"],
                "citation_key": key, "record_id": record_id, "page_id": page_id,
                "page_text": text,
                "page_kind": classify_page_kind(text),
                "relevance": relevance, "semantics": semantics,
                "analysis": {"core_concepts": analysis.core_concepts, "era": analysis.era, "intent": analysis.intent},
            })
            print(f"{case_id}: kind={classify_page_kind(text)} relevance={relevance['status']} semantics={semantics['relation']} len={len(text)}")
            await asyncio.sleep(0.3)
    (ROOT / "eval" / "phase7-fixtures.json").write_text(
        json.dumps({"cases": fixtures}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("fixtures saved:", len(fixtures))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
