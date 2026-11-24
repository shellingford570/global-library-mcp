"""Phase 9-F: shadow-mode disagreement analysis (offline).

Runs the rule checker over gold-passages-v2 WITHOUT touching
any admission decision, and classifies every disagreement with
the audited labels: checker over-acceptance (says supports for
a contradiction/neutral case), checker under-recognition
(fails an entailment case), and anchor-only saves (raw
supports verdict that the era anchor refuses). This is the
record a future NLI/LLM checker will be compared against in
the same shadow fashion.
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
    rows = []
    for case in gold["cases"]:
        verdict = checker.assess(analyze_question(case["question"]), case["passage_text"])
        relation = verdict.get("relation")
        certified = relation == "supports" and bool(verdict.get("anchored_support"))
        label = case["relation_label"]
        if label == "entailment":
            cls = "agree_support" if relation == "supports" else "under_recognition"
        elif label in ("contradiction", "neutral"):
            if certified:
                cls = "over_acceptance"
            elif relation == "supports":
                cls = "anchor_saved"
            else:
                cls = "agree_refuse"
        else:
            cls = "excluded_label"
        rows.append({"id": case["id"], "label": label, "relation": relation,
                     "anchored": verdict.get("anchored_support"), "class": cls})
    from collections import Counter
    summary = dict(Counter(r["class"] for r in rows))
    payload = {"summary": summary, "rows": rows,
               "note": "shadow analysis only; no admission decision was influenced"}
    (ROOT / "eval" / "shadow-analysis-phase9.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
