"""b6 multilingual discovery evaluation (fixture-based proxy metrics).

Simulates keyword-catalogue search over the fixed fixture corpus
(eval/b6-corpus.json): a record is "returned" for a search variant
when the variant's tokens all appear in the record's searchable
fields after normalisation. This measures exactly what b6 changes
- variant generation, routing dispatches, discovery ranking and
grouping - against agent-assigned proxy relevance labels. It is
NOT a measurement of live catalogue recall.

Usage: .venv/bin/python eval/b6_eval.py --dataset fixed --configs A
"""
from __future__ import annotations

import argparse, json, math, re, sys, unicodedata
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from global_library_mcp.question import (  # noqa: E402
    analyze_question, extract_terms, latin_variants, normalize_text, script_variants,
)
from global_library_mcp.service import rank_candidates  # noqa: E402

ROOT = Path(__file__).resolve().parent
SEARCHABLE_LIBRARIES = ("loc", "ndl", "gallica", "internet-archive", "ddb", "europeana")

_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "é": "e", "è": "e", "ê": "e",
                       "ë": "e", "à": "a", "â": "a", "î": "i", "ï": "i", "ô": "o", "û": "u",
                       "ç": "c", "œ": "oe", "æ": "ae", "š": "s", "č": "c"})


def sim_normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().translate(_FOLD)
    # old kanji -> new kanji for matching (search-side only)
    for variant in [text]:
        pass
    return re.sub(r"[^\w\s-]", " ", text)


def record_text(rec: dict) -> str:
    parts = [rec.get("title") or "", rec.get("author") or "", " ".join(rec.get("subjects") or [])]
    raw = " ".join(parts)
    expanded = [raw]
    for sv in script_variants(raw):
        expanded.append(sv)
    return sim_normalize(" ".join(expanded))


def variant_matches(variant: str, rec_text: str, rec_title_n: str) -> bool:
    v = sim_normalize(variant)
    tokens = [t for t in re.split(r"\s+", v) if len(t) >= 2]
    if not tokens:
        return False
    if v.strip() and v.strip() in rec_title_n:
        return True
    return all(t in rec_text for t in tokens)


def baseline_variants(query: str) -> list[str]:
    """Replicates the b5 collect_evidence variant construction."""
    terms = extract_terms(query)
    variants = list(dict.fromkeys([query, *terms]))
    term_variants = variants[1:]
    variants = variants[:1] + [
        v for v in term_variants
        if not any(v != other and v in other for other in term_variants)
    ]
    script_extra: list[str] = []
    for variant in list(variants):
        for sv in script_variants(variant):
            if sv not in variants and sv not in script_extra:
                script_extra.append(sv)
    variants += script_extra[:3]
    latin_extra: list[str] = []
    for variant in list(variants):
        for lv in latin_variants(variant):
            if lv not in variants and lv not in latin_extra:
                latin_extra.append(lv)
    variants += latin_extra[:3]
    return variants


def get_variants(config: str, query: str) -> tuple[list[str], dict]:
    if config == "A":
        return baseline_variants(query), {}
    # B-H are provided by the b6 engine (eval/b6_engine_configs.py).
    from b6_engine_configs import engine_variants  # type: ignore

    return engine_variants(config, query)


def run_case(case: dict, corpus: list[dict], config: str) -> dict:
    variants, plan = get_variants(config, case["query"])
    hits: dict[str, int] = {}
    attempts = 0
    routing = plan.get("routing", {}) if isinstance(plan, dict) else {}
    for variant in variants:
        for lib in routing.get(variant, SEARCHABLE_LIBRARIES):
            attempts += 1
            for rec in corpus:
                if rec["library_id"] != lib:
                    continue
                rt = record_text(rec)
                if variant_matches(variant, rt, sim_normalize(rec.get("title") or "")):
                    hits[rec["record_id"]] = hits.get(rec["record_id"], 0) + 1
    by_id = {r["record_id"]: r for r in corpus}
    items = []
    for rid, count in hits.items():
        rec = by_id[rid]
        items.append(SimpleNamespace(
            title=rec["title"], author=rec["author"], description=" ".join(rec["subjects"]),
            library_id=rec["library_id"], record_id=rid, year=rec.get("year"),
            language=rec.get("language"), work_id=rec.get("work_id"), ocr=rec.get("ocr"),
            material_type=rec.get("material_type")))
    query_hits = {(it.library_id, it.record_id): hits[it.record_id] for it in items}
    if config in ("A", "B", "C", "D", "E", "F"):
        analysis = analyze_question(case["query"])
        ranked = rank_candidates(analysis, items, query_hits)
    else:
        from b6_engine_configs import engine_rank  # type: ignore

        ranked = engine_rank(case, items, query_hits, plan)
    ranked_ids = [it.record_id for it in ranked]
    rel = case["relevant_record_ids"]
    out = {"id": case["id"], "variants": variants, "attempts": attempts,
           "retrieved": ranked_ids[:20], "relevant": rel}
    if rel:
        for k in (5, 10, 20):
            out[f"recall@{k}"] = len(set(ranked_ids[:k]) & set(rel)) / len(rel)
        out["precision@5"] = len(set(ranked_ids[:5]) & set(rel)) / 5 if ranked_ids else 0.0
        ranks = [ranked_ids.index(r) + 1 for r in rel if r in ranked_ids]
        out["mrr"] = 1.0 / min(ranks) if ranks else 0.0
        dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(ranked_ids[:10]) if r in rel)
        ideal = sorted(rel, key=lambda r: ranked_ids.index(r) if r in ranked_ids else 99)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), 10)))
        out["ndcg@10"] = dcg / idcg if idcg else 0.0
        qlang = case["query_language"]
        cross = [r for r in ranked_ids[:10] if r in rel and by_id[r]["language"] != qlang]
        out["cross_language_hit"] = bool(cross)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fixed", choices=["dev", "fixed", "holdout"])
    ap.add_argument("--configs", default="A")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    corpus = json.loads((ROOT / "b6-corpus.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / f"b6-{args.dataset}.json").read_text(encoding="utf-8"))
    report: dict = {"dataset": args.dataset, "cases": len(cases), "configs": {}}
    for config in args.configs.split(","):
        results = [run_case(c, corpus, config) for c in cases]
        scored = [r for r in results if r["relevant"]]
        agg = {}
        for key in ("recall@5", "recall@10", "recall@20", "precision@5", "mrr", "ndcg@10"):
            agg[key] = round(sum(r.get(key, 0.0) for r in scored) / len(scored), 4) if scored else 0.0
        agg["cross_language_rate"] = round(
            sum(1 for r in scored if r.get("cross_language_hit")) / len(scored), 4) if scored else 0.0
        agg["avg_attempts"] = round(sum(r["attempts"] for r in results) / len(results), 1)
        agg["avg_variants"] = round(sum(len(r["variants"]) for r in results) / len(results), 1)
        report["configs"][config] = {"aggregate": agg, "cases": results}
        print(config, agg)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
