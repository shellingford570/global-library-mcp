"""b11 evaluation-set builder (brief sections 15-22).

The b11 set is a NEW, separate evaluation set.  Existing datasets
(b6/b8/b10) are never modified; cases carried over keep their
original expectations verbatim and gain a b11 label record with the
section-19 provenance vocabulary.  New cases are generated from
frozen fixture snippets and lexicon entries; every new label starts
as ``agent_assigned`` except author-identity cases whose GND
identifier was confirmed against lobid with an exact birth-year
match (recorded in ``B11_GND_CONFIRMED`` below, verified
2026-11-28).  No OCR/page ground truth is invented for originals
that were not obtained: such cases expect ``unknown`` outcomes.

Run:  python eval/b11_dataset.py --out eval/b11-cases.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKED_AT = "2026-11-28"

# GND identifiers confirmed live against lobid.org on 2026-11-28:
# exact preferredName + birth-year match against the lexicon entry.
# (Einstein/Hegel/Goethe/Nietzsche/Herschel/Dostoevsky/Tolstoy were
# attempted and NOT confirmed by this method; they stay unconfirmed.)
B11_GND_CONFIRMED = {
    "author:marx": "118578537",
    "author:descartes": "118524844",
    "author:spencer": "118616080",
    "author:smith-adam": "118615033",
    "author:hugo": "118554654",
    "author:nishida": "118588230",
}

PROVENANCE_VOCAB = {
    "agent_assigned", "bibliographic_source_supported",
    "authority_source_supported", "original_page_checked",
    "human_reviewed", "independent_human_verified",
    "conflicting_review", "unresolved",
}


def _label(provenance: str, **kw) -> dict:
    lab = {"provenance": provenance, "checked_at": kw.pop("checked_at", None),
           "source_url": kw.pop("source_url", None),
           "authority_id": kw.pop("authority_id", None),
           "checked_fields": kw.pop("checked_fields", []),
           "review_status": kw.pop("review_status", "not_reviewed")}
    lab.update(kw)
    assert lab["provenance"] in PROVENANCE_VOCAB
    return lab


def _entities_from_b10(case: dict) -> dict:
    task = case.get("task") or {}
    if not isinstance(task, dict):
        task = {}
    return {
        "persons": [task["author_id"]] if task.get("author_id") else [],
        "works": [task["work_id"]] if task.get("work_id") else [],
        "concepts": [task["concept_id"]] if task.get("concept_id") else [],
        "documents": [task["record_id"]] if task.get("record_id") else [],
        "source_families": [task["library_id"]] if task.get("library_id") else [],
    }


def build() -> list[dict]:
    cases: list[dict] = []
    # 1) carried-over b10 cases: expectations verbatim, provenance
    # re-expressed in the section-19 vocabulary.
    for split in ("dev", "fixed", "holdout"):
        data = json.loads((ROOT / f"eval/b10-{split}.json").read_text())
        rows = data["cases"] if isinstance(data, dict) else data
        for c in rows:
            lp = c.get("label_provenance") or {}
            src = lp.get("source") if isinstance(lp, dict) else lp
            # The b10 final-review re-audit reduced source-supported
            # labels from 68 to 21 of 260 but did not annotate WHICH
            # cases; the frozen b10 files still carry the pre-audit
            # claims.  b11 therefore does NOT inherit the claim:
            # carried cases are agent_assigned with the original
            # claim preserved verbatim in original_provenance.
            prov = "agent_assigned"
            lab = _label(prov, carried_from=f"b10-{split}",
                         original_provenance=c.get("label_provenance"))
            cases.append({
                "case_id": f"b11-carry-{c['id']}",
                "category": c.get("category"),
                "origin": f"b10-{split}",
                "task": c.get("task"), "expect": c.get("expect"),
                "entities": _entities_from_b10(c),
                "label": lab,
            })
    # 2) author-identity cases for the six newly GND-confirmed
    # authors (authority_source_supported) and for attempted-but-
    # unconfirmed authors (agent_assigned, explicitly unresolved).
    lex = json.loads((ROOT / "src/global_library_mcp/data/"
                      "search_lexicon.json").read_text())
    authors = {a["author_id"]: a for a in lex.get("authors", [])}
    for aid, gnd in B11_GND_CONFIRMED.items():
        a = authors[aid]
        cases.append({
            "case_id": f"b11-gnd-{aid.split(':')[1]}",
            "category": "author_identity",
            "origin": "b11-new",
            "task": {"author_id": aid, "name_en": (a["names"]["en"] or [""])[0],
                     "birth_year": a.get("birth_year")},
            "expect": {"gnd": gnd},
            "entities": {"persons": [aid], "works": [], "concepts": [],
                         "documents": [], "source_families": ["gnd"]},
            "label": _label(
                "authority_source_supported",
                source_url=f"https://lobid.org/gnd/{gnd}.html",
                authority_id=f"gnd:{gnd}",
                checked_fields=["preferredName", "dateOfBirth"],
                checked_at=CHECKED_AT),
        })
    for aid in ("author:einstein", "author:hegel", "author:goethe",
                "author:nietzsche", "author:herschel",
                "author:dostoevsky", "author:tolstoy"):
        a = authors.get(aid)
        if not a:
            continue
        cases.append({
            "case_id": f"b11-gnd-unconfirmed-{aid.split(':')[1]}",
            "category": "author_identity",
            "origin": "b11-new",
            "task": {"author_id": aid,
                     "name_en": (a["names"]["en"] or [""])[0],
                     "birth_year": a.get("birth_year")},
            "expect": {"gnd": None, "note": "not confirmed by the "
                       "lobid exact-name+birth-year method on "
                       "2026-11-28; must not be asserted"},
            "entities": {"persons": [aid], "works": [], "concepts": [],
                         "documents": [], "source_families": ["gnd"]},
            "label": _label("unresolved",
                            checked_fields=["preferredName", "dateOfBirth"],
                            checked_at=CHECKED_AT),
        })
    # 3) new proxy cases for the b11 feature areas (agent_assigned).
    templates = []
    for i, (va, vb, unit) in enumerate([
            ("100", "100", "kW"), ("50", "60", "MW"), ("12", "12", "km"),
            ("3.5", "3.5", "kg"), ("1900", "1900", "year")]):
        templates.append({
            "case_id": f"b11-compare-{i}", "category": "numeric_comparison",
            "task": {"a": {"value": va, "unit": unit, "subject": "engine",
                           "predicate": "output", "object": "power",
                           "place": "site"},
                     "b": {"value": vb, "unit": unit, "subject": "engine",
                           "predicate": "output", "object": "power",
                           "place": "site"}},
            "expect": {"pair_status_in": ["agreement_candidate",
                                          "value_conflict",
                                          "insufficient_context"]}})
    for i in range(5):
        templates.append({
            "case_id": f"b11-missingcond-{i}", "category": "numeric_comparison",
            "task": {"a": {"value": "10", "unit": "kW"},
                     "b": {"value": "10", "unit": "kW"}},
            "expect": {"pair_status": "insufficient_context"}})
    for i, snippet in enumerate([
            "The mill produced 40 kW in 1890.",
            "出力は明治二十三年に四十キロワットであった。",
            "Die Leistung betrug 40 kW im Jahr 1890."]):
        templates.append({
            "case_id": f"b11-claim-{i}", "category": "claim_evidence",
            "task": {"snippet": snippet},
            "expect": {"quantity": "40", "unit": "kW"}})
    for i in range(4):
        templates.append({
            "case_id": f"b11-indep-{i}", "category": "source_independence",
            "task": {"sources": [{"document_id": f"d{i}a"},
                                  {"document_id": f"d{i}b"}]},
            "expect": {"independence": "unknown",
                       "independently_confirmed_source_count": 0}})
    for i in range(4):
        templates.append({
            "case_id": f"b11-report-{i}", "category": "report_integrity",
            "task": {"require": ["markdown", "json", "report_id",
                                  "snapshot_id", "resolvable_refs"]},
            "expect": {"ungrounded_statements": 0}})
    for t in templates:
        t.setdefault("origin", "b11-new")
        t.setdefault("entities", {"persons": [], "works": [],
                                  "concepts": [], "documents": [],
                                  "source_families": []})
        t["label"] = _label("agent_assigned")
        cases.append(t)
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/b11-cases.json")
    args = ap.parse_args()
    cases = build()
    payload = {
        "dataset": "b11-research-validation",
        "created": CHECKED_AT,
        "case_count": len(cases),
        "sha256": hashlib.sha256(json.dumps(
            cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "cases": cases,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    from collections import Counter
    print("cases:", len(cases))
    print("provenance:", Counter(c["label"]["provenance"] for c in cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
