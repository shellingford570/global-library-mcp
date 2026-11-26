"""b6 challenge set runner (final review section 18).

Runs the fixed challenge cases (eval/b6-challenge.json) against
their own corpus (eval/b6-challenge-corpus.json) with the same
simulation harness as b6_eval, and reports the section-17
negative metrics for cases with no relevant records. Labels are
agent-assigned; no human gold set exists.

Usage: .venv/bin/python eval/b6_challenge.py --configs A,F --out eval/results-b6-challenge.json
"""
from __future__ import annotations

import argparse, hashlib, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from b6_eval import run_case  # noqa: E402

ROOT = Path(__file__).resolve().parent


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="A,F")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    corpus = json.loads((ROOT / "b6-challenge-corpus.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / "b6-challenge.json").read_text(encoding="utf-8"))
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT.parent).stdout.strip()
    except Exception:
        commit = "unknown"
    report = {"dataset": "challenge", "cases_total": len(cases),
              "cases_with_relevant": sum(1 for c in cases if c["relevant_record_ids"]),
              "cases_without_relevant": sum(1 for c in cases if not c["relevant_record_ids"]),
              "label_source": "agent_assigned",
              "commit": commit,
              "dataset_sha256": _sha(ROOT / "b6-challenge.json"),
              "corpus_sha256": _sha(ROOT / "b6-challenge-corpus.json"),
              "lexicon_sha256": _sha(ROOT.parent / "src/global_library_mcp/data/search_lexicon.json"),
              "configs": {}}
    for config in args.configs.split(","):
        results = [run_case(c, corpus, config) for c in cases]
        scored = [r for r in results if r["relevant"]]
        negatives = [r for r in results if not r["relevant"]]
        agg = {}
        for key in ("recall@5", "recall@10", "recall@20", "precision@5", "mrr", "ndcg@10"):
            agg[key] = round(sum(r.get(key, 0.0) for r in scored) / len(scored), 4) if scored else 0.0
        agg["cross_language_rate"] = round(
            sum(1 for r in scored if r.get("cross_language_hit")) / len(scored), 4) if scored else 0.0
        agg["avg_attempts"] = round(sum(r["attempts"] for r in results) / len(results), 1)
        # Section 17 negative metrics: for no-relevant cases any
        # retrieved record is a false candidate.
        agg["negative_cases"] = len(negatives)
        agg["false_candidate_rate"] = round(
            sum(1 for r in negatives if r["retrieved"]) / len(negatives), 4) if negatives else 0.0
        agg["irrelevant_retrieval_rate"] = round(
            sum(len(r["retrieved"]) for r in negatives) / max(1, sum(1 for _ in negatives) * 20), 4) if negatives else 0.0
        report["configs"][config] = {"aggregate": agg, "cases": results}
        print(config, agg)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
