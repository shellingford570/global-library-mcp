"""b10 Stage 3 ranking comparison (brief sections 20-21).

Retrieval is held constant (b6 simulation, config F variants and
routing, fixed corpora); only the RANKER varies:

- R0: service.rank_candidates (b9 incumbent)
- R1: ranking.rank_discovery (b6 discovery scorer)
- R2: research_ranker.ResearchRanker (strict tier + lexical fusion)

Metrics per corpus: Recall@5/10/20, Precision@5, MRR, nDCG@10,
cross-language discovery rate. Labels are agent-assigned proxy
labels, as in every b6/b8 simulation report.

Usage: python eval/b10_ranking_compare.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
import b6_eval  # noqa: E402
from global_library_mcp.discovery import analyze_discovery_query  # noqa: E402
from global_library_mcp.question import analyze_question  # noqa: E402
from global_library_mcp.ranking import rank_discovery  # noqa: E402
from global_library_mcp.research_ranker import ResearchRanker  # noqa: E402
from global_library_mcp.service import rank_candidates  # noqa: E402


def _retrieve(case, corpus):
    variants, plan = b6_eval.get_variants("F", case["query"])
    routing = plan.get("routing", {}) if isinstance(plan, dict) else {}
    hits: dict[str, int] = {}
    attempts = 0
    for variant in variants:
        for lib in routing.get(variant, b6_eval.SEARCHABLE_LIBRARIES):
            attempts += 1
            for rec in corpus:
                if rec["library_id"] != lib:
                    continue
                rt = b6_eval.record_text(rec)
                if b6_eval.variant_matches(variant, rt, b6_eval.sim_normalize(rec.get("title") or "")):
                    hits[rec["record_id"]] = hits.get(rec["record_id"], 0) + 1
    by_id = {r["record_id"]: r for r in corpus}
    items = []
    for rid in hits:
        rec = by_id[rid]
        items.append(SimpleNamespace(
            title=rec["title"], author=rec["author"],
            description=" ".join(rec["subjects"]), subjects=rec["subjects"],
            library_id=rec["library_id"], record_id=rid,
            year=rec.get("year"), language=rec.get("language"),
            work_id=rec.get("work_id"), ocr=rec.get("ocr"),
            material_type=rec.get("material_type")))
    query_hits = {(it.library_id, it.record_id): hits[it.record_id] for it in items}
    return items, query_hits, by_id, attempts


def _metrics(ranked_ids, rel, by_id, qlang):
    out = {}
    for k in (5, 10, 20):
        out[f"recall@{k}"] = len(set(ranked_ids[:k]) & set(rel)) / len(rel)
    out["precision@5"] = len(set(ranked_ids[:5]) & set(rel)) / 5 if ranked_ids else 0.0
    ranks = [ranked_ids.index(r) + 1 for r in rel if r in ranked_ids]
    out["mrr"] = 1.0 / min(ranks) if ranks else 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(ranked_ids[:10]) if r in rel)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), 10)))
    out["ndcg@10"] = dcg / idcg if idcg else 0.0
    out["cross"] = any(r in rel and by_id[r]["language"] != qlang
                       for r in ranked_ids[:10])
    return out


def _run(corpus_path, dataset_path, ranker_name):
    corpus = json.loads(Path(corpus_path).read_text())
    cases = json.loads(Path(dataset_path).read_text())
    ranker = ResearchRanker()
    agg: dict[str, list] = {}
    n_rel = 0
    for case in cases:
        rel = case.get("relevant_record_ids") or []
        if not rel or not all(isinstance(x, str) and ":" in x or "-" in x for x in rel):
            if not rel:
                continue
        if not rel:
            continue
        items, query_hits, by_id, _ = _retrieve(case, corpus)
        if ranker_name == "R0":
            ranked = rank_candidates(analyze_question(case["query"]),
                                     list(items), query_hits)
        elif ranker_name == "R1":
            ranked = rank_discovery(analyze_discovery_query(case["query"]),
                                    list(items), query_hits)
        else:
            ranked = ranker.rank(analyze_discovery_query(case["query"]),
                                 list(items), query_hits)
        m = _metrics([it.record_id for it in ranked], rel, by_id,
                     case["query_language"])
        n_rel += 1
        for k, v in m.items():
            agg.setdefault(k, []).append(v)
    return {k: round(sum(v) / len(v), 4) for k, v in agg.items()} | {"cases": n_rel}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    corpora = {
        "b6_fixed": (ROOT / "eval/b6-corpus.json", ROOT / "eval/b6-fixed.json"),
        "b6_challenge": (ROOT / "eval/b6-challenge-corpus.json",
                         ROOT / "eval/b6-challenge.json"),
        "b6_dev": (ROOT / "eval/b6-corpus.json", ROOT / "eval/b6-dev.json"),
        "b6_holdout": (ROOT / "eval/b6-corpus.json", ROOT / "eval/b6-holdout.json"),
    }
    report = {"evaluation_kind": "ranking comparison over fixed simulation retrieval (config F)",
              "label_source": "agent_assigned", "rankers": {}}
    for name in ("R0", "R1", "R2"):
        report["rankers"][name] = {}
        for corpus_name, (cp, dp) in corpora.items():
            if not dp.exists():
                continue
            report["rankers"][name][corpus_name] = _run(cp, dp, name)
            print(name, corpus_name, report["rankers"][name][corpus_name])
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
