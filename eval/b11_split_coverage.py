"""Split-assignment coverage for the b11 evaluation set
(final review section 36).

Reports, per entity kind (person / work / concept / document /
source_family): how many of the 294 cases carry at least one
identifier, how many carry none, and how many cases are
ungroupable (no identifier of any kind). Cross-split duplicate
statements are scoped: "0 duplicates" is asserted ONLY over
cases with assigned identifiers; cases without identifiers
cannot be deduplicated by this method and their duplicate risk
is reported as UNCONFIRMED, never as zero.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("persons", "works", "concepts", "documents", "source_families")


def coverage(cases: list[dict]) -> dict:
    total = len(cases)
    per_kind = {}
    for kind in KINDS:
        assigned = sum(1 for c in cases
                       if (c.get("entities") or {}).get(kind))
        per_kind[kind] = {
            "assigned_cases": assigned,
            "assignment_rate": round(assigned / total, 4) if total else 0,
            "unassigned_cases": total - assigned}
    ungroupable = sum(
        1 for c in cases
        if not any((c.get("entities") or {}).get(k) for k in KINDS))
    grouped = json.loads((ROOT / "eval" / "b11-grouped-splits.json")
                         .read_text(encoding="utf-8"))
    return {
        "dataset": "b11-research-validation",
        "total_cases": total,
        "per_kind": per_kind,
        "ungroupable_cases": ungroupable,
        "groupable_cases": total - ungroupable,
        "cross_split_entity_overlap_among_assigned":
            grouped.get("cross_split_entity_overlap"),
        "component_count": grouped.get("component_count"),
        "duplicate_statement_scope": (
            "cross-split entity overlap 0 applies ONLY to cases "
            "with assigned identifiers; the "
            f"{ungroupable} identifier-less cases cannot be "
            "grouped or deduplicated by entity, so their "
            "duplicate risk is UNCONFIRMED, not zero"),
        "method_note": (
            "identifiers are the dataset's own entity strings; "
            "name variants of the same entity are not merged "
            "unless the dataset records the same identifier"),
    }


def main() -> None:
    data = json.loads((ROOT / "eval" / "b11-cases.json")
                      .read_text(encoding="utf-8"))
    result = coverage(data["cases"])
    out = ROOT / "eval" / "b11-split-coverage.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
