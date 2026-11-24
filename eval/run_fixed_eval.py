"""Phase 10-F harness: verifier comparison over FIXED evidence.

No search runs here - the evidence is saved in
eval/balanced-v1.json, so retrieval quality and semantic
verification are measured separately. Offline verifiers
(lexical, NLI-when-available, hybrid) cost nothing. An LLM
judge is only constructed when a judge callable is injected
by an approved runner; this harness never calls a paid API
on its own.

Metrics (brief 10-F): entailment precision/recall,
contradiction detection rate, false-support rate,
false-rejection rate, partial-answer success, citation
accuracy (cited passages exist), per-verifier latency.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def score(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["expected"] == "entailment" and r["verdict"] == "entailment")
    fp = sum(1 for r in rows if r["expected"] != "entailment" and r["verdict"] == "entailment")
    fn = sum(1 for r in rows if r["expected"] == "entailment" and r["verdict"] != "entailment")
    contra_total = sum(1 for r in rows if r["expected"] == "contradiction")
    contra_hit = sum(1 for r in rows if r["expected"] == "contradiction" and r["verdict"] == "contradiction")
    return {
        "claims": len(rows),
        "entailment_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "entailment_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "false_support_rate": round(fp / max(sum(1 for r in rows if r["expected"] != "entailment"), 1), 3),
        "false_rejection_rate": round(fn / max(sum(1 for r in rows if r["expected"] == "entailment"), 1), 3),
        "contradiction_detection": round(contra_hit / contra_total, 3) if contra_total else None,
        "citation_accuracy": round(sum(1 for r in rows if r["citation_ok"]) / max(len(rows), 1), 3),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(ROOT / "eval" / "balanced-v1.json"))
    parser.add_argument("--verifiers", default="lexical,nli,hybrid")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from global_library_mcp.verifiers import get_verifiers

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    verifiers = get_verifiers([n.strip() for n in args.verifiers.split(",") if n.strip()])
    report: dict = {"cases": len(data["cases"]), "human_verified": data.get("human_verified"), "verifiers": {}}
    for verifier in verifiers:
        rows = []
        started = time.perf_counter()
        for case in data["cases"]:
            known = {p["passage_id"] for e in case["evidence"] for p in e["passages"]}
            for claim in case["claims"]:
                verdict = verifier.verify(claim, case["evidence"])
                rows.append({
                    "case": case["id"], "category": case["category"],
                    "expected": claim["expected"], "verdict": verdict["verdict"],
                    "citation_ok": all(p in known for p in claim.get("evidence_passage_ids") or []),
                })
        elapsed = time.perf_counter() - started
        report["verifiers"][verifier.name] = {**score(rows), "seconds": round(elapsed, 2), "rows": rows}
        print(verifier.name, report["verifiers"][verifier.name]["entailment_precision"],
              report["verifiers"][verifier.name]["entailment_recall"],
              report["verifiers"][verifier.name]["false_support_rate"])
    out = Path(args.out) if args.out else ROOT / "eval" / "results-balanced-v1-verifiers.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
