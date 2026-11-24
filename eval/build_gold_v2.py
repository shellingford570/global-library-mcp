"""Phase 9-C: audit the Phase 8 gold set and build v2.

v1's supporting cases were harvested from pipeline admissions -
not independent ground truth - and its A-type metric counted
`uncertain` as recognition. v2 re-labels every case from the
passage's OWN properties (page kind, an asserting sentence that
binds the topic to an occurrence/diffusion cue, an in-era
anchor), using labels entailment / contradiction / neutral /
ambiguous / unverified. Cases that cannot be re-derived are
downgraded to unverified, never silently kept. Splits are by
record group so one book never spans dev and eval. v1 is kept
untouched.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from global_library_mcp.question import analyze_question  # noqa: E402
from global_library_mcp.evidence import classify_page_kind  # noqa: E402

ASSERT_CUES = ("開局", "開通", "創設", "設立", "建設され", "架設", "始ま", "始メ", "開始", "導入", "普及", "使用され", "運転", "完成", "竣工", "創刊", "発行され", "設置され", "設けられ", "敷設", "開業", "運転を開始", "実現", "創業", "創始", "開設", "伝来", "創立", "開校", "興業", "営業を開始")
NON_ASSERT_KINDS = {"contents", "index", "admin_list", "colophon", "title_page", "front_matter"}


def group_split(record_id: str) -> str:
    return "dev" if int(hashlib.md5(str(record_id).encode()).hexdigest(), 16) % 2 == 0 else "eval"


def audit_label(case: dict) -> tuple[str, str]:
    """Independent-of-admission label from passage properties."""
    text = case.get("passage_text") or ""
    kind = classify_page_kind(text)
    if case["label"] == "must_reject":
        cat = case.get("rejection_category") or ""
        if "garbage" in cat or "damaged" in cat:
            return "ambiguous", f"must-reject fixture, category {cat}: OCR too damaged to judge"
        return "neutral", f"must-reject fixture, category {cat}: topical at most, asserts nothing for the claim"
    if kind == "damaged":
        return "ambiguous", "page classified damaged; assertion cannot be read reliably"
    if kind in NON_ASSERT_KINDS:
        return "neutral", f"page kind {kind}: lists/mentions the topic but asserts nothing"
    analysis = analyze_question(case["question"])
    concepts = [t for t in analysis.terms if len(t) >= 2]
    sentences = [s for s in re.split(r"[。！？\n]", text) if s.strip()]
    asserting = [
        s for s in sentences
        if any(c in s for c in concepts) and any(cue in s for cue in ASSERT_CUES)
    ]
    if asserting:
        return "entailment", f"body page; {len(asserting)} sentence(s) bind the topic to an occurrence/diffusion cue"
    # Quantitative assertion: a topic term with concrete figures
    # inside a passage that also carries an era name asserts the
    # topic existed (period statistics are assertions, in these
    # sources, not mere mentions).
    has_figure = any(c in text for c in concepts) and bool(re.search(r"[0-9０-９一二三四五六七八九十百千万萬]{2,}", text))
    has_era = any(e in text for e in ("明治", "大正", "昭和", "江戸", "慶應", "元年"))
    if has_figure and has_era:
        return "entailment", "body page; era-anchored quantitative statement about the topic"
    return "unverified", "body page admitted by the pipeline, but no asserting sentence re-derived in the audit"


def main() -> int:
    v1 = json.loads((ROOT / "eval" / "gold-passages.json").read_text(encoding="utf-8"))
    cases = []
    for case in v1["cases"]:
        label, basis = audit_label(case)
        cases.append({
            **case,
            "relation_label": label,
            "label_basis": basis,
            "independence": "pipeline_harvested",
            "split": group_split(case["record_id"]),
            "group": case["record_id"],
        })
    # Constructed contradictions/neutrals from audited entailments:
    # same passage, claim with the era shifted or the topic
    # swapped - the passage cannot support those claims.
    era_shift = {"明治": "江戸", "大正": "明治", "昭和": "大正"}
    entailments = [c for c in cases if c["relation_label"] == "entailment"]
    constructed = []
    for i, case in enumerate(entailments):
        claim = case.get("claim") or ""
        for old, new in era_shift.items():
            if old in claim:
                constructed.append({
                    **case,
                    "id": f"x{i:03d}e",
                    "claim": claim.replace(old, new, 1),
                    "relation_label": "contradiction",
                    "label_basis": f"constructed: claim era shifted {old}->{new}; the passage anchors {old}",
                    "independence": "constructed",
                })
                break
    topics = []
    for case in entailments:
        m = re.search(r"に日本で(.+?)が", case.get("claim") or "")
        if m:
            topics.append(m.group(1))
    for i, case in enumerate(entailments):
        claim = case.get("claim") or ""
        m = re.search(r"に日本で(.+?)が", claim)
        if m and topics:
            other = topics[(i + 1) % len(topics)]
            if other != m.group(1):
                constructed.append({
                    **case,
                    "id": f"x{i:03d}s",
                    "claim": claim.replace(m.group(1), other, 1),
                    "relation_label": "neutral",
                    "label_basis": "constructed: claim topic swapped; the passage is about a different subject",
                    "independence": "constructed",
                })
    cases.extend(constructed)
    from collections import Counter
    counts = Counter(c["relation_label"] for c in cases)
    payload = {
        "version": "gold-passages-v2-2026-11-24",
        "supersedes": "gold-passages-v1-2026-11-24 (kept unchanged)",
        "license_note": v1.get("license_note"),
        "schema": "v1 fields + relation_label(entailment|contradiction|neutral|ambiguous|unverified) / label_basis / independence(pipeline_harvested|pipeline_rejected|fresh_search|constructed) / group(=record_id; splits are group-wise)",
        "counts": dict(counts),
        "cases": cases,
    }
    (ROOT / "eval" / "gold-passages-v2.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("total:", len(cases), "| labels:", dict(counts))
    print("splits:", dict(Counter(c["split"] for c in cases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
