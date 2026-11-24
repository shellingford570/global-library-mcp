"""Build the Phase 10-F balanced fixed-evidence case set (40).

Labels are fixed BEFORE any run and are derived from the
gold v2 audit's admission-independent relation labels and
from passage texts themselves - never from pipeline outputs.
human_verified is false throughout: the operator has not
hand-checked these cases, and the file says so.

Categories (brief 10-F):
- support x12: claim entailed by the fixed passage
- insufficient x8: no passage supplied; the only correct
  behaviour is to not answer
- related_not_supporting x8: passage is on-topic but does
  not entail the claim (neutral)
- contradiction x6: passage contradicts the claim /
  corrects the question's premise
- partial x6: three claims, exactly two entailed - the
  correct outcome is a partial answer of those two
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
gold = json.loads((ROOT / "eval" / "gold-passages-v2.json").read_text(encoding="utf-8"))
cases = gold["cases"] if isinstance(gold, dict) else gold

by_relation: dict[str, list[dict]] = {}
for case in cases:
    by_relation.setdefault(case.get("relation_label") or case.get("label"), []).append(case)


def base(case: dict, category: str, claims: list[dict], passages: list[dict]) -> dict:
    return {
        "id": "", "category": category,
        "question": case.get("question"),
        "claims": claims,
        "evidence": passages,
        "human_verified": False,
        "label_basis": case.get("label_basis") or "gold v2 admission-independent relation label",
        "source_case": case.get("id"),
    }


def passage_of(case: dict) -> dict:
    return {"citation_key": case["citation_key"], "passage_id": f"{case['citation_key']}#p1",
            "text": case["passage_text"], "char_start": case.get("char_start"), "char_end": None}


out: list[dict] = []

entail = [c for c in by_relation.get("entailment", [])]
supporting_extra = [c for c in cases if c.get("label") == "supporting" and c not in entail]
for case in entail[:12]:
    entry = base(case, "support",
                 [{"text": case["claim"], "expected": "entailment", "claim_style": "hypothesis",
                   "citations": [case["citation_key"]],
                   "evidence_passage_ids": [f"{case['citation_key']}#p1"]}],
                 [passage_of(case)])
    out.append(entry)
# Only 7 gold cases re-derive as entailment (Phase 9 audit).
# The remaining support cases use a verbatim sentence OF the
# passage as the claim - self-evident entailment, labelled as
# the "verbatim" claim style, complementing the hypothesis
# style. (Using the other "supporting" cases as-is would be
# wrong: the audit showed most are TOC/listing passages that
# do not entail their hypothesis claims at all.)
import re as _re2
for case in supporting_extra:
    if len([e for e in out if e["category"] == "support"]) >= 12:
        break
    sentences = [s for s in _re2.split(r"(?<=。)", case.get("passage_text") or "") if len(s) >= 12]
    if not sentences:
        continue
    entry = base(case, "support",
                 [{"text": sentences[0].rstrip("。"), "expected": "entailment", "claim_style": "verbatim",
                   "citations": [case["citation_key"]],
                   "evidence_passage_ids": [f"{case['citation_key']}#p1"]}],
                 [passage_of(case)])
    entry["label_basis"] = "claim is a verbatim sentence of the fixed passage (self-evident entailment, verbatim claim style)"
    out.append(entry)

for case in cases[:8]:
    out.append(base(case, "insufficient",
                    [{"text": case["claim"], "expected": "no_answer", "citations": [], "evidence_passage_ids": []}],
                    []))

neutral = [c for c in by_relation.get("neutral", []) if c.get("passage_text")]
for case in neutral[:8]:
    out.append(base(case, "related_not_supporting",
                    [{"text": case["claim"], "expected": "neutral",
                      "citations": [case["citation_key"]],
                      "evidence_passage_ids": [f"{case['citation_key']}#p1"]}],
                    [passage_of(case)]))

contra = by_relation.get("contradiction", [])
if len(contra) < 6:
    # One constructed era-shift contradiction: an entailed
    # claim whose era is moved one period later, against the
    # original era-anchored passage. Label basis states the
    # construction openly.
    import re as _re
    for case in entail:
        shifted = _re.sub(r"明治", "大正", case["claim"])
        if shifted != case["claim"] and "明治" in (case.get("passage_text") or ""):
            clone = dict(case)
            clone["claim"] = shifted
            clone["label_basis"] = "constructed era-shift contradiction (claim era moved Meiji->Taisho against a Meiji-anchored passage)"
            contra = contra + [clone]
            break
for case in contra[:6]:
    out.append(base(case, "contradiction",
                    [{"text": case["claim"], "expected": "contradiction",
                      "citations": [case["citation_key"]],
                      "evidence_passage_ids": [f"{case['citation_key']}#p1"]}],
                    [passage_of(case)]))

pool = [c for c in (entail + supporting_extra) if c.get("passage_text")]
neutral_pool = neutral[8:14]
for i in range(6):
    a, b, n = pool[i % len(pool)], pool[(i + 3) % len(pool)], neutral_pool[i % len(neutral_pool)]
    entry = base(a, "partial",
                 [{"text": a["claim"], "expected": "entailment",
                   "citations": [a["citation_key"]], "evidence_passage_ids": [f"{a['citation_key']}#p1"]},
                  {"text": b["claim"], "expected": "entailment",
                   "citations": [b["citation_key"]], "evidence_passage_ids": [f"{b['citation_key']}#p1"]},
                  {"text": n["claim"], "expected": "neutral",
                   "citations": [n["citation_key"]], "evidence_passage_ids": [f"{n['citation_key']}#p1"]}],
                 [passage_of(a), passage_of(b), passage_of(n)])
    entry["label_basis"] = "composed from gold v2 entailment/neutral cases; expected outcome is a partial answer of exactly the two entailed claims"
    out.append(entry)

for i, entry in enumerate(out, 1):
    entry["id"] = f"b{i:02d}"
    entry["evidence"] = [{"citation_key": p["citation_key"], "passages": [p]} for p in entry["evidence"]]

from collections import Counter
print(Counter(e["category"] for e in out), "total", len(out))
(ROOT / "eval" / "balanced-v1.json").write_text(
    json.dumps({"version": "balanced-v1", "human_verified": False,
                "note": "Fixed-evidence cases for verifier comparison and (with fresh approval) the next real-LLM experiment. Labels fixed 2026-11-24 before any run, from gold v2 admission-independent labels.",
                "cases": out}, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote eval/balanced-v1.json")
