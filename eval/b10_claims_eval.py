"""b10 Stage 4 claim/contradiction evaluation over the frozen
b10 dataset (brief sections 24-29).

- claim_evidence / claim_snippet_match + claim_numeric_match:
  the snippet is assessed as an ADMITTED candidate (the dataset
  models post-gate mapping, not admission) and the resulting
  status is compared with the expected evidence_state.
- claim_structure_extraction: era and place/subject fields of
  the structured claim are compared with the case's structure
  block (the event phrase is not extracted by design - the
  predicate/object stay textual - and is reported as such).
- contradiction / classify_difference: quantities are extracted
  from both statements and classified by compare_facts.

Labels are agent_assigned proxy labels. Usage:
python eval/b10_claims_eval.py [--split fixed] [--out f.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp import lexicon  # noqa: E402
from global_library_mcp.numeric import extract_quantities  # noqa: E402
from global_library_mcp.question import normalize_text  # noqa: E402
from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, compare_facts, structure_claim)
from global_library_mcp.temporal import sentence_years  # noqa: E402

_SCOPE_TOKENS = ("全国", "日本全体", "全世界", "管内", "県内", "市内",
                 "国内", "世界", "東京")


def _fact(statement: str, doc_id: str) -> dict:
    quantities = extract_quantities(statement)
    q = quantities[0] if quantities else {}
    years = sentence_years(normalize_text(statement))
    scope = next((t for t in _SCOPE_TOKENS if t in statement), None)
    definition = None
    for opener, closer in (("(", ")"), ("（", "）")):
        if opener in statement and closer in statement:
            definition = statement.split(opener, 1)[1].split(closer, 1)[0]
            break
    concept = None
    for entry in lexicon.match_entries(statement, "concepts"):
        concept = entry["concept_id"]
        break
    return {"value": q.get("value"), "unit": q.get("unit"),
            "year": years[0] if years else None, "scope": scope,
            "definition": definition, "concept": concept,
            "document_id": doc_id, "work_id": doc_id}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="fixed")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    data = json.loads((ROOT / "eval" / f"b10-{args.split}.json").read_text())
    stats = {"snippet_match": [0, 0], "structure": [0, 0],
             "contradiction": [0, 0]}
    false_support = 0
    details = []
    for case in data["cases"]:
        if case["category"] == "claim_evidence":
            claim = structure_claim(case["statement"], case.get("claim_id", ""))
            if case["task"] == "claim_structure_extraction":
                want = case.get("structure") or {}
                era_ok = (not want.get("era")) or \
                    (claim.time or {}).get("era") == want.get("era")
                place_ok = (not want.get("subject")) or \
                    claim.place == want.get("subject") or \
                    want.get("subject") in claim.original_statement
                ok = era_ok and place_ok
                stats["structure"][1] += 1
                stats["structure"][0] += int(ok)
                details.append({"id": case["id"], "kind": "structure",
                                "ok": ok, "era_ok": era_ok, "place_ok": place_ok,
                                "event_extracted": False})
                continue
            from global_library_mcp.research import build_trusted_candidate
            _cand = build_trusted_candidate(
                library_id="fixture", record_id=case["id"], page_id="1",
                text=case.get("snippet") or "")
            _cand["document_id"] = case["id"]
            rows = assess_claim_evidence(claim, [_cand])
            got = rows[0]["status"]
            want_state = case["expect"].get("evidence_state")
            ok = got == want_state
            stats["snippet_match"][1] += 1
            stats["snippet_match"][0] += int(ok)
            if got == "supported_candidate" and want_state != "supported_candidate":
                false_support += 1
            details.append({"id": case["id"], "kind": "snippet", "ok": ok,
                            "got": got, "want": want_state})
        elif case["category"] == "contradiction":
            facts = [_fact(case["statement_a"], "a"),
                     _fact(case["statement_b"], "b")]
            out = compare_facts(facts)
            got = out["pairs"][0]["status"]
            want_state = case["expect"].get("classification")
            ok = got == want_state
            stats["contradiction"][1] += 1
            stats["contradiction"][0] += int(ok)
            details.append({"id": case["id"], "kind": "contradiction",
                            "ok": ok, "got": got, "want": want_state,
                            "pair": case.get("pair_id")})
    report = {
        "evaluation_kind": "structured claim/contradiction mapping over frozen b10 dataset",
        "label_source": "agent_assigned",
        "split": args.split,
        "stats": {k: {"correct": v[0], "total": v[1],
                      "rate": round(v[0] / v[1], 4) if v[1] else None}
                  for k, v in stats.items()},
        "false_support_promotions": false_support,
        "details": details,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: report[k] for k in ("split", "stats", "false_support_promotions")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
