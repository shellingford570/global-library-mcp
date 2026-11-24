"""Phase 8-E: checker comparison on the frozen Phase 7 fixtures.

Runs the rule checker and the NLI checker over the same frozen
false-answer passages and reports each verdict side by side,
with timing. The NLI backend load is attempted at most once
(bounded); when it is unavailable the comparison records
not_checked honestly instead of retrying. No verdict here
changes any admission - this measures the checkers, nothing
else.

Usage: python -m eval.compare_checkers [--try-models]
Without --try-models, no model download is attempted at all.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--try-models", action="store_true",
                        help="attempt one bounded load of the NLI model")
    parser.add_argument("--out", default=str(ROOT / "eval" / "checker-comparison-phase8.json"))
    args = parser.parse_args()

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from global_library_mcp.nli import NliChecker, build_hypothesis
    from global_library_mcp.question import analyze_question
    from global_library_mcp.semantics import RuleBasedSemanticChecker

    fixtures = json.loads((ROOT / "eval" / "phase7-fixtures.json").read_text(encoding="utf-8"))
    rule = RuleBasedSemanticChecker()
    nli = NliChecker()
    rows = []
    for fixture in fixtures["cases"]:
        analysis = analyze_question(fixture["question"])
        hypothesis = build_hypothesis(analysis)
        started = time.perf_counter()
        verdict = rule.assess(analysis, fixture["page_text"], publication_year=fixture.get("publication_year"))
        rule_ms = (time.perf_counter() - started) * 1000
        if args.try_models:
            started = time.perf_counter()
            nli_result = nli.check_passage(fixture["page_text"], hypothesis)
            nli_ms = (time.perf_counter() - started) * 1000
        else:
            nli_result = {"verdict": "not_checked", "reason": "model load not attempted (no --try-models)"}
            nli_ms = 0.0
        rows.append({
            "id": fixture["id"],
            "question": fixture["question"],
            "hypothesis": hypothesis,
            "expected_safe_outcome": "must not ground an answer",
            "rule_relation": verdict.get("relation"),
            "rule_ms": round(rule_ms, 2),
            "nli_verdict": nli_result.get("verdict"),
            "nli_reason": nli_result.get("reason"),
            "nli_ms": round(nli_ms, 2),
        })
    payload = {
        "fixtures": len(rows),
        "nli_model": nli.model,
        "nli_load_error": nli.load_error,
        "rows": rows,
        "note": "NLI verdicts are signals only; admission remains with the rule/admission path.",
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}: {len(rows)} fixtures, nli_load_error={nli.load_error!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
