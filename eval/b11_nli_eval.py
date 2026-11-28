"""b11 NLI proxy evaluation (sections 29-30).

Runs the labelled case set (eval/b11_nli_cases.json) against the
SYNTHETIC backend only - no model is downloaded in b11.  The
output is a PROXY measurement of the evaluation harness and the
synthetic stand-in, explicitly not a measurement of any real
NLI model.  A future real-model run requires the approval
documented in docs/b11-nli-model-selection.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from global_library_mcp.nli_backend import (  # noqa: E402
    SyntheticNLIBackend, shadow_assess)


def run(cases: list[dict]) -> dict:
    backend = SyntheticNLIBackend()
    rows = []
    confusion: Counter = Counter()
    for c in cases:
        rec = shadow_assess(rule_based_status="not_evaluated",
                            premise=c["premise"],
                            hypothesis=c["hypothesis"], backend=backend)
        predicted = rec["nli_relation"]
        expected = c["expected_relation"]
        ok = predicted == expected or (
            expected == "contradiction"
            and predicted == "contradiction_candidate")
        confusion[(expected, predicted)] += 1
        rows.append({"case_id": c["case_id"], "language": c["language"],
                     "kind": c["kind"], "expected": expected,
                     "predicted": predicted, "agree": ok})
    n = len(rows)
    agree = sum(1 for r in rows if r["agree"])
    return {
        "evaluation_kind": "proxy_synthetic_backend",
        "warning": "NOT a real NLI model measurement; the synthetic "
                   "backend is a lexical-overlap stand-in",
        "backend": backend.model_id, "nli_status": backend.status(),
        "cases": n, "agreement": agree / n if n else 0.0,
        "confusion": {f"{k[0]}->{k[1]}": v for k, v in
                      sorted(confusion.items())},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/b11_nli_cases.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cases = json.loads(Path(args.cases).read_text())["cases"]
    result = run(cases)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    print("proxy agreement:", result["agreement"], "cases:", result["cases"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
