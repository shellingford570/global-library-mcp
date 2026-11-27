"""b10 section 9: multilingual allocation policy comparison.

Runs the b6 fixed simulation, the b6 challenge simulation and
the b8 fixed evaluation under each expansion allocation policy
(A legacy / B diagonal / C user_priority / E hierarchy /
G primary_guarantee / H authority_first) by setting
GLM_EXPANSION_ALLOCATION for each subprocess run, and writes a
single comparison JSON. D (per-library language priority) is a
dispatch-layer policy and F (adaptive) a service-level policy;
neither is expressible in the shared expansion ordering, so
they are compared in the Stage 3 service evaluation instead -
recorded here as not_simulated, never silently dropped.

Usage: .venv/bin/python eval/b10_allocation_compare.py --out <file>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICIES = ("legacy", "diagonal", "user_priority", "hierarchy",
            "primary_guarantee", "authority_first")
LABELS = {
    "legacy": "A_legacy_b6_release",
    "diagonal": "B_diagonal_b8_b9_current",
    "user_priority": "C_user_language_priority",
    "hierarchy": "E_primary_secondary_hierarchy",
    "primary_guarantee": "G_minimum_language_guarantee",
    "authority_first": "H_compound_authority_priority",
}


def _run(script: str, args: list[str], policy: str, out: Path) -> dict:
    env = dict(os.environ)
    env["GLM_EXPANSION_ALLOCATION"] = policy
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        env.pop(var, None)
    subprocess.run(
        [sys.executable, str(ROOT / "eval" / script), *args,
         "--out", str(out)],
        check=True, env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads(out.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tmp = Path("/tmp/b10-alloc")
    tmp.mkdir(exist_ok=True)
    result: dict = {"policies": {}, "not_simulated": {
        "D_per_library_language_priority":
            "dispatch-layer policy; compared qualitatively in "
            "docs/b10-multilingual-routing.md",
        "F_adaptive_expansion":
            "needs result feedback; evaluated with the Stage 3 "
            "adaptive planner on the service evaluation",
    }}
    for policy in POLICIES:
        b6_fixed = _run("b6_eval.py", ["--dataset", "fixed",
                                       "--configs", "F"],
                        policy, tmp / f"b6fixed-{policy}.json")
        b6_chal = _run("b6_challenge.py", [], policy,
                       tmp / f"b6chal-{policy}.json")
        b8 = _run("b8_eval.py", [], policy, tmp / f"b8-{policy}.json")
        result["policies"][LABELS[policy]] = {
            "b6_fixed_F": b6_fixed["configs"]["F"]["aggregate"],
            "b6_challenge_F": b6_chal["configs"]["F"]["aggregate"],
            "b8_fixed_standard": b8["modes"]["fixed/standard"],
            "b8_fixed_quick": b8["modes"]["fixed/quick"],
        }
        print("done", LABELS[policy], flush=True)
    Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
