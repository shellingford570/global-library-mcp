"""Inter-reviewer agreement for b11 human review (section 21).

Computes percent agreement, Cohen's kappa (2 reviewers) and
Krippendorff's alpha (nominal, any number of reviewers) from
filled review CSV/JSON files.  With fewer than two reviewers or
no overlapping judged cases the result is explicitly
``unmeasured`` - blank judgements never count as reviewed, and
synthetic test input is never reported as human evaluation.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter


JUDGEMENT_VOCAB = ("correct", "partially_correct", "incorrect",
                   "insufficient_evidence", "cannot_judge",
                   "out_of_scope")


def load_judgements(text: str, fmt: str = "csv") -> dict[str, dict[str, str]]:
    """Return {reviewer_id: {case_id: judgement}} (final review
    section 37 import rules): blank judgements are excluded,
    a reviewer identity is required, judgements outside the
    closed vocabulary are REJECTED (never silently dropped or
    coerced), and a conflicting duplicate (same reviewer, same
    case, different judgement) is an error - identical
    duplicates are idempotent."""
    def put(out: dict, rid: str, case_id: str, j: str) -> None:
        if not rid:
            raise ValueError("reviewer_id is required")
        if j not in JUDGEMENT_VOCAB:
            raise ValueError(f"judgement outside the vocabulary: {j!r}")
        prev = out.setdefault(rid, {}).get(case_id)
        if prev is not None and prev != j:
            raise ValueError(
                f"conflicting duplicate judgement for {case_id} "
                f"by {rid}: {prev!r} vs {j!r}")
        out[rid][case_id] = j

    out: dict[str, dict[str, str]] = {}
    if fmt == "json":
        data = json.loads(text)
        for reviewer, mapping in data.items():
            for case_id, j in mapping.items():
                if j:
                    put(out, reviewer, case_id, j)
        return out
    for row in csv.DictReader(io.StringIO(text)):
        j = (row.get("judgement") or "").strip()
        rid = (row.get("reviewer_id") or "").strip()
        if j:
            put(out, rid, row["case_id"], j)
    return out


def cohens_kappa(a: dict[str, str], b: dict[str, str]) -> dict:
    common = sorted(set(a) & set(b))
    if not common:
        return {"status": "unmeasured", "reason": "no overlapping cases"}
    n = len(common)
    agree = sum(1 for c in common if a[c] == b[c]) / n
    ca, cb = Counter(a[c] for c in common), Counter(b[c] for c in common)
    cats = set(ca) | set(cb)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    kappa = (agree - pe) / (1 - pe) if pe < 1 else 1.0
    return {"status": "measured", "n": n, "percent_agreement": agree,
            "cohens_kappa": kappa}


def krippendorff_alpha_nominal(reviewers: dict[str, dict[str, str]]) -> dict:
    cases = set()
    for m in reviewers.values():
        cases |= set(m)
    units = []
    for c in sorted(cases):
        vals = [m[c] for m in reviewers.values() if c in m]
        if len(vals) >= 2:
            units.append(vals)
    if not units:
        return {"status": "unmeasured", "reason": "no multi-judged cases"}
    total_pairs = sum(len(u) * (len(u) - 1) for u in units)
    disagree = 0
    marginals: Counter = Counter()
    for u in units:
        for i, x in enumerate(u):
            marginals[x] += len(u) - 1
            for j, y in enumerate(u):
                if i != j and x != y:
                    disagree += 1
    do = disagree / total_pairs if total_pairs else 0.0
    tot = sum(marginals.values())
    de = 1.0 - sum((v / tot) ** 2 for v in marginals.values()) if tot else 0.0
    alpha = 1.0 - do / de if de > 0 else 1.0
    return {"status": "measured", "units": len(units),
            "krippendorff_alpha_nominal": alpha}


def agreement_report(reviewers: dict[str, dict[str, str]]) -> dict:
    if len(reviewers) < 2:
        return {"status": "unmeasured",
                "reason": "fewer than two reviewers with judgements",
                "reviewer_count": len(reviewers)}
    ids = sorted(reviewers)
    rep: dict = {"status": "measured", "reviewer_count": len(ids),
                 "alpha": krippendorff_alpha_nominal(reviewers)}
    if len(ids) == 2:
        rep["kappa"] = cohens_kappa(reviewers[ids[0]], reviewers[ids[1]])
    return rep
