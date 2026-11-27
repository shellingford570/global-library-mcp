"""b10 Stage 2 authority evaluation over the frozen b10 dataset.

Runs the LOCAL AuthorityResolver (offline, deterministic) over the
author/work, original/translated-title and edition categories of
the dev/fixed/holdout splits and reports:

- top-candidate correctness for identify tasks,
- FALSE VERIFICATIONS: cases where the resolver returned
  authority_verified for the wrong entity (target: 0),
- edition identification accuracy on exact years,
- appropriate ambiguity for surname-only prompts.

Labels are the dataset's own (mostly agent_assigned /
bibliographic_source_supported); this is a proxy evaluation, not
human verification. Usage: python eval/b10_authority_eval.py [--split fixed]
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
from global_library_mcp.authority import AuthorityResolver, identify_edition  # noqa: E402
from global_library_mcp import lexicon  # noqa: E402

_WORK_ID_BY_SLUG = {}


def _work_slug(work_id: str) -> str:
    return work_id.replace("work:", "")


_SLUG_MAP = {"origin-of-species": "darwin-origin",
             "kritik-reinen-vernunft": "kant-kritik",
             "das-kapital": "marx-kapital",
             "principia": "newton-principia",
             "contrat-social": "rousseau-contrat",
             "faust": "goethe-faust",
             "wealth-of-nations": "smith-wealth",
             "crime-and-punishment": "dostoevsky-crime",
             "les-miserables": "hugo-miserables",
             "war-and-peace": "tolstoy-war"}


def _slug(work_id: str) -> str:
    raw = _work_slug(work_id)
    return _SLUG_MAP.get(raw, raw)


def _author_name(author_id: str) -> str:
    entry = lexicon.author_by_id(author_id) or {}
    forms = [n for group in (entry.get("names") or {}).values() for n in group]
    return forms


def _name_matches(forms, want: str) -> bool:
    import unicodedata, re
    def norm(t):
        t = unicodedata.normalize("NFKC", t or "").lower()
        return re.sub(r"[\s,.\u3000]+", " ", t).strip()
    want_n = norm(want)
    for form in forms:
        if norm(form) == want_n:
            return True
        if "," in form:
            parts = [x.strip() for x in form.split(",", 1)]
            if norm(f"{parts[1]} {parts[0]}") == want_n:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="fixed")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    data = json.loads((ROOT / "eval" / f"b10-{args.split}.json").read_text())
    resolver = AuthorityResolver()
    stats = {"identify_author": [0, 0], "identify_author_from_variant": [0, 0],
             "work_titles": [0, 0], "editions": [0, 0], "traps_scored": [0, 0]}
    traps_deferred = 0
    # Resolver-addressable trap probes: (name to resolve, check).
    # Remaining traps concern search/ranking roles (translator,
    # editor, about-vs-by) scored in Stages 3-4, not here.
    trap_probes = {
        "surname_only_weber": ("Weber", "not_verified_multi"),
        "surname_only_darwin": ("Darwin", "not_verified_multi"),
        "name_order_kant": ("Kant, Immanuel", "top_is:author:kant"),
        "old_script_fukuzawa": ("福沢諭吉", "top_is:author:fukuzawa"),
        "old_script_ogai": ("森鴎外", "top_is:author:ogai"),
        "pen_name_soseki": ("夏目漱石", "top_is:author:soseki"),
        "initials_only": ("J.-J. Rousseau", "not_verified"),
    }
    false_verified = 0
    surname_ambiguous_ok = 0
    surname_total = 0
    details = []
    for case in data["cases"]:
        cat = case["category"]
        if case.get("task") == "author_trap":
            probe = trap_probes.get(case.get("trap_id", ""))
            if probe is None:
                traps_deferred += 1
                continue
            name, check = probe
            res = resolver.resolve_person(name)
            viable = [c for c in res.candidates if not c.excluded_reason]
            if check == "not_verified_multi":
                ok = (res.status != "authority_verified" and len(viable) >= 2)
            elif check == "not_verified":
                ok = res.status != "authority_verified"
            else:
                want_id = check.split(":", 1)[1]
                ok = bool(viable) and viable[0].record.authority_id == want_id
            stats["traps_scored"][1] += 1
            stats["traps_scored"][0] += int(ok)
            if res.status == "authority_verified" and not ok:
                false_verified += 1
            details.append({"id": case["id"], "status": res.status,
                            "ok": ok, "trap": case.get("trap_id")})
            continue
        if cat == "author_work_identification":
            expect = case["expect"]
            res = resolver.resolve_person(
                case["prompt_form"],
                birth_year=expect.get("birth_year"),
                death_year=expect.get("death_year"),
                known_work=expect.get("known_work"))
            top = res.candidates[0] if res.candidates else None
            forms = _author_name(top.record.authority_id) if top else []
            got = forms[0] if forms else ""
            want = expect.get("author", "")
            ok = (bool(top) and not top.excluded_reason
                  and _name_matches(forms, want))
            key = ("identify_author_from_variant"
                   if case["task"] == "identify_author_from_variant"
                   else "identify_author")
            stats[key][1] += 1
            stats[key][0] += int(ok)
            if res.status == "authority_verified" and not ok:
                false_verified += 1
            if case["task"] == "identify_author_from_variant":
                surname_total += 1
                surname_ambiguous_ok += int(
                    res.status in ("ambiguous", "insufficient_metadata")
                    or (ok and res.status != "authority_verified"))
            details.append({"id": case["id"], "status": res.status,
                            "ok": ok, "got": got, "want": want})
        elif cat == "original_translated_title":
            res = resolver.resolve_work(case["given_title"],
                                        author_hint=case["expect"].get("author"))
            top = res.candidates[0] if res.candidates else None
            got = _slug(top.record.authority_id) if top else ""
            ok = got == case["expect"].get("work", "")
            stats["work_titles"][1] += 1
            stats["work_titles"][0] += int(ok)
            details.append({"id": case["id"], "status": res.status,
                            "ok": ok, "got": got,
                            "want": case["expect"].get("work")})
        elif cat == "edition_identification":
            if case.get("task") == "must_not_merge":
                probes = {
                    "kant-A-vs-B": ("work:kritik-reinen-vernunft", 1781, 1787),
                    "origin-1-vs-6": ("work:origin-of-species", 1859, 1872),
                    "principia-editions": ("work:principia", 1687, 1726),
                }
                probe = probes.get(case.get("trap_id", ""))
                if probe is None:
                    traps_deferred += 1
                    continue
                wid, y1, y2 = probe
                e1, e2 = identify_edition(wid, y1), identify_edition(wid, y2)
                ok = bool(e1 and e2 and e1["edition_id"] != e2["edition_id"])
                stats.setdefault("must_not_merge", [0, 0])
                stats["must_not_merge"][1] += 1
                stats["must_not_merge"][0] += int(ok)
                details.append({"id": case["id"], "ok": ok,
                                "trap": case.get("trap_id")})
                continue
            res = resolver.resolve_work(case["title"])
            top = res.candidates[0] if res.candidates else None
            edition = (identify_edition(top.record.authority_id, case.get("year"))
                       if top else None)
            got = ""
            if edition:
                slug = {"kritik-reinen-vernunft": "kant-kritik",
                        "origin-of-species": "darwin-origin",
                        "principia": "newton-principia",
                        "faust": "goethe-faust"}.get(
                            _work_slug(edition["work_id"]),
                            _work_slug(edition["work_id"]))
                got = f"{slug}-{edition['edition_code']}"
            want = case["expect"].get("edition", "")
            ok = got == want
            stats["editions"][1] += 1
            stats["editions"][0] += int(ok)
            details.append({"id": case["id"], "status": res.status,
                            "ok": ok, "got": got, "want": want})
    report = {
        "evaluation_kind": "local AuthorityResolver over frozen b10 dataset",
        "label_source": "dataset provenance (agent_assigned / bibliographic_source_supported)",
        "split": args.split,
        "stats": {k: {"correct": v[0], "total": v[1],
                      "rate": round(v[0] / v[1], 4) if v[1] else None}
                  for k, v in stats.items()},
        "false_verified": false_verified,
        "traps_deferred_to_stage3_4": traps_deferred,
        "surname_variant_not_falsely_verified": {
            "ok": surname_ambiguous_ok, "total": surname_total},
        "details": details,
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    print(json.dumps({k: report[k] for k in
                      ("split", "stats", "false_verified",
                       "surname_variant_not_falsely_verified")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
