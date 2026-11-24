"""Evaluate checkers against the Phase 8-F gold passage dataset.

Type A (passage given, search excluded): the rule checker's
relation over supporting passages - how much genuine period
prose it recognises at all.
Type D (wrong evidence given): over must_reject cases, whether
the era-assertion path would refuse certification (relation is
not supports, or supports without an anchor).
Types B and C need the live pipeline; C is the four-set
regression in eval/run_evaluation.py and B is reported from
its per-record gating (Recall B). This script is offline.

Usage: python -m eval.evaluate_gold
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from global_library_mcp.question import analyze_question
    from global_library_mcp.semantics import RuleBasedSemanticChecker

    gold = json.loads((ROOT / "eval" / "gold-passages.json").read_text(encoding="utf-8"))
    checker = RuleBasedSemanticChecker()
    report: dict = {"version": gold["version"], "by_split": {}}
    for split in ("dev", "eval"):
        cases = [c for c in gold["cases"] if c["split"] == split]
        supporting = [c for c in cases if c["label"] == "supporting"]
        rejected = [c for c in cases if c["label"] == "must_reject"]
        a_recognised = 0
        for case in supporting:
            verdict = checker.assess(analyze_question(case["question"]), case["passage_text"])
            if verdict.get("relation") in ("supports", "uncertain"):
                a_recognised += 1
        d_refused = 0
        for case in rejected:
            verdict = checker.assess(analyze_question(case["question"]), case["passage_text"])
            certified = verdict.get("relation") == "supports" and verdict.get("anchored_support")
            if not certified:
                d_refused += 1
        report["by_split"][split] = {
            "type_A_supporting_cases": len(supporting),
            "type_A_recognised": a_recognised,
            "type_A_rate": round(a_recognised / len(supporting), 3) if supporting else None,
            "type_D_reject_cases": len(rejected),
            "type_D_refused_certification": d_refused,
            "type_D_rate": round(d_refused / len(rejected), 3) if rejected else None,
        }
    out = ROOT / "eval" / "gold-evaluation-phase8.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
