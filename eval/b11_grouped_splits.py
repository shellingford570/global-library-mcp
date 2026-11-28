"""Entity-grouped splits for the b11 evaluation set (section 18).

Groups are connected components over shared entities (person /
work / concept / document / source family).  Components are
assigned to splits by a seeded hash of the component key, so the
same entity never appears in two splits (cross-split entity
overlap is 0 by construction and is also measured).  The output
records counts, entity counts, overlap, the dataset SHA-256, the
algorithm and the fixed seed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SEED = 20261128
SPLITS = ("dev", "fixed", "holdout")
ALGORITHM = "connected-components over shared entities; split = sha256(seed|component_key) mod 3"


def components(cases: list[dict]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for c in cases:
        find(c["case_id"])
    for c in cases:
        ents = []
        for kind, values in (c.get("entities") or {}).items():
            ents += [f"{kind}:{v}" for v in values or []]
        for e in ents:
            find(e)
            union(c["case_id"], e)
    groups: dict[str, list[str]] = {}
    for c in cases:
        groups.setdefault(find(c["case_id"]), []).append(c["case_id"])
    return sorted(groups.values(), key=lambda g: g[0])


def assign(cases: list[dict]) -> dict:
    comps = components(cases)
    by_id = {c["case_id"]: c for c in cases}
    split_of: dict[str, str] = {}
    for comp in comps:
        key = "|".join(sorted(comp))
        h = int(hashlib.sha256(f"{SEED}|{key}".encode()).hexdigest(), 16)
        for cid in comp:
            split_of[cid] = SPLITS[h % 3]
    out = {"algorithm": ALGORITHM, "seed": SEED,
           "dataset_sha256": hashlib.sha256(json.dumps(
               cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
           "splits": {}}
    entity_sets: dict[str, set] = {}
    for split in SPLITS:
        ids = sorted(cid for cid, s in split_of.items() if s == split)
        ents = set()
        for cid in ids:
            for kind, values in (by_id[cid].get("entities") or {}).items():
                ents |= {f"{kind}:{v}" for v in values or []}
        entity_sets[split] = ents
        out["splits"][split] = {"case_count": len(ids),
                                "entity_count": len(ents),
                                "case_ids": ids}
    overlap = 0
    names = list(SPLITS)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            overlap += len(entity_sets[names[i]] & entity_sets[names[j]])
    out["cross_split_entity_overlap"] = overlap
    out["component_count"] = len(comps)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/b11-cases.json")
    ap.add_argument("--out", default="eval/b11-grouped-splits.json")
    args = ap.parse_args()
    payload = json.loads(Path(args.dataset).read_text())
    result = assign(payload["cases"])
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print({k: v["case_count"] for k, v in result["splits"].items()},
          "overlap:", result["cross_split_entity_overlap"],
          "components:", result["component_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
