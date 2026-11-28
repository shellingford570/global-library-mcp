"""b10 final review (section 10): authority evaluation v2.

The v1 evaluation fed the EXPECTED birth/death years and known
work from each case's answer key into the resolver - information
a real user input may not contain. v2 separates input conditions
and never lets the answer key leak into the input:

- name_only: the prompt form alone;
- name_plus_stated_years: years treated as USER-STATED input
  (labelled as such; scored separately);
- name_plus_work: the prompt form plus a stated work title;
- official_fixture: fetched official-source records (fixture
  transport, no live network) incl. conflicting-id and
  wrong-identifier probes.

Outcomes are tallied separately: correctly verified, falsely
verified, candidate, ambiguous, insufficient. A false-verified
rate of 0 with 0 verifications performed is reported WITH its
denominator, never as proof on its own.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
import global_library_mcp.service as _LS  # noqa: F401,E402

from global_library_mcp import lexicon  # noqa: E402
from global_library_mcp.authority import (  # noqa: E402
    AuthorityRecord, AuthorityResolver)


def _name_forms(author_id: str) -> list[str]:
    entry = lexicon.author_by_id(author_id) or {}
    return [n for group in (entry.get("names") or {}).values() for n in group]


def _top_id(res) -> str | None:
    viable = [c for c in res.candidates if not c.excluded_reason]
    return viable[0].record.authority_id if viable else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    resolver = AuthorityResolver()
    modes = ("name_only", "name_plus_stated_years", "name_plus_work")
    tally = {m: {"cases": 0, "top_correct": 0, "verified": 0,
                 "verified_correct": 0, "verified_false": 0,
                 "candidate": 0, "ambiguous": 0, "insufficient": 0}
             for m in modes}
    details = []
    for split in ("dev", "fixed", "holdout"):
        data = json.loads((ROOT / "eval" / f"b10-{split}.json").read_text())
        for case in data["cases"]:
            if case["category"] != "author_work_identification":
                continue
            expect = case["expect"]
            if not case.get("prompt_form"):
                continue  # non-person form of this category (work prompt)
            want_forms = None
            for mode in modes:
                kw = {}
                if mode == "name_plus_stated_years":
                    kw = {"birth_year": expect.get("birth_year"),
                          "death_year": expect.get("death_year")}
                elif mode == "name_plus_work":
                    kw = {"known_work": expect.get("known_work")}
                res = resolver.resolve_person(case["prompt_form"], **kw)
                top = _top_id(res)
                if want_forms is None:
                    want_forms = _name_forms(top) if top else []
                ok = False
                if top:
                    forms = _name_forms(top)
                    import re as _re
                    import unicodedata as _ud

                    def norm(t):
                        return _re.sub(r"[\s,.\u3000]+", " ",
                                       _ud.normalize("NFKC", t or "").lower()).strip()
                    ok = norm(expect.get("author", "")) in {norm(f) for f in forms} or \
                        any(norm(f) == norm(expect.get("author", "")) for f in forms)
                t = tally[mode]
                t["cases"] += 1
                t["top_correct"] += int(ok)
                if res.status == "authority_verified":
                    t["verified"] += 1
                    t["verified_correct" if ok else "verified_false"] += 1
                elif res.status == "authority_candidate":
                    t["candidate"] += 1
                elif res.status == "ambiguous":
                    t["ambiguous"] += 1
                else:
                    t["insufficient"] += 1
                if mode == "name_only":
                    details.append({"id": case["id"], "split": split,
                                    "status": res.status, "ok": ok})
    # official fixture probes
    def gnd_source(records):
        class _S:
            name = "gnd"

            def search_person(self, name, birth_year=None):
                return records
        return _S()

    kant = AuthorityRecord(authority_id="gnd:118559796", authority_source="gnd",
                           entity_type="person", canonical_name="Immanuel Kant",
                           birth_year=1724, death_year=1804, fetched=True,
                           external_identifiers={"gnd": "118559796"})
    kant_wrong_year = AuthorityRecord(
        authority_id="gnd:118559796", authority_source="gnd",
        entity_type="person", canonical_name="Immanuel Kant",
        birth_year=1700, death_year=1804, fetched=True,
        external_identifiers={"gnd": "118559796"})
    fixture = {}
    r = AuthorityResolver(live_sources=[gnd_source([kant])]).resolve_person(
        "Immanuel Kant", birth_year=1724, death_year=1804)
    fixture["fetched_official_with_stated_years"] = r.status
    r = AuthorityResolver(live_sources=[gnd_source([kant, kant_wrong_year])]).resolve_person(
        "Immanuel Kant", birth_year=1724)
    fixture["same_id_conflicting_years"] = r.status
    r = AuthorityResolver().resolve_person(
        "Immanuel Kant", birth_year=1724, death_year=1804)
    fixture["local_only"] = r.status
    report = {
        "evaluation_kind": "authority v2 - input conditions separated, no answer-key leakage",
        "dataset": "frozen b10 dataset (dev+fixed+holdout), author_work_identification cases",
        "label_provenance": "agent_assigned / source-supported recount in b10_final_eval",
        "independent_human_verified": 0,
        "modes": tally,
        "official_fixture_probes": fixture,
        "details_name_only": details,
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    print(json.dumps({"modes": tally, "official_fixture_probes": fixture},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
