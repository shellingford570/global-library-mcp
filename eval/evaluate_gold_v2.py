"""Phase 9-C: strict evaluation over gold-passages-v2.

Changes from the Phase 8 evaluator (kept unchanged for
reproducibility): recognition counts ONLY relation ==
"supports" - `uncertain` is no longer scored as success - and
the negative side is measured per v2 label (contradiction /
neutral must not be certified; ambiguous / unverified are
counted but excluded from rates).
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

    gold = json.loads((ROOT / "eval" / "gold-passages-v2.json").read_text(encoding="utf-8"))
    checker = RuleBasedSemanticChecker()
    report: dict = {"version": gold["version"], "scoring": "strict: supports only", "by_split": {}}
    for split in ("dev", "eval"):
        cases = [c for c in gold["cases"] if c["split"] == split]
        entail = [c for c in cases if c["relation_label"] == "entailment"]
        negatives = [c for c in cases if c["relation_label"] in ("contradiction", "neutral")]
        strict = legacy = 0
        for case in entail:
            verdict = checker.assess(analyze_question(case["question"]), case["passage_text"])
            if verdict.get("relation") == "supports":
                strict += 1
            if verdict.get("relation") in ("supports", "uncertain"):
                legacy += 1
        refused = raw_supports = 0
        for case in negatives:
            verdict = checker.assess(analyze_question(case["question"]), case["passage_text"])
            if verdict.get("relation") == "supports":
                raw_supports += 1
            certified = verdict.get("relation") == "supports" and verdict.get("anchored_support")
            if not certified:
                refused += 1
        report["by_split"][split] = {
            "entailment_cases": len(entail),
            "recognised_strict": strict,
            "recognised_strict_rate": round(strict / len(entail), 3) if entail else None,
            "recognised_legacy_incl_uncertain": legacy,
            "negative_cases": len(negatives),
            "negatives_refused_certification": refused,
            "negatives_refused_rate": round(refused / len(negatives), 3) if negatives else None,
            "negatives_raw_supports_verdicts": raw_supports,
            "excluded_ambiguous_unverified": sum(1 for c in cases if c["relation_label"] in ("ambiguous", "unverified")),
        }
    out = ROOT / "eval" / "gold-evaluation-phase9.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
