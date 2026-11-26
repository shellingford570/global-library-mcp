"""Ablation configurations B-H for the b6 fixture evaluation.

Each config cumulatively enables one b6 feature on top of the b5
baseline (A, in b6_eval.baseline_variants):
  B + historical expansion   C + author name variants
  D + work titles            E + concept translations/related
  F + language routing       G + discovery ranking
  H + duplicate grouping (presentation layer)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from global_library_mcp.discovery import analyze_discovery_query  # noqa: E402
from global_library_mcp.expansion import QueryExpansionEngine  # noqa: E402

_KIND_STAGES = {
    "B": {"historical"},
    "C": {"historical", "author_name"},
    "D": {"historical", "author_name", "original_title", "translated_title"},
    "E": {"historical", "author_name", "original_title", "translated_title",
          "concept_translation", "related_concept", "spelling_variant", "compound_split"},
}
for later in ("F", "G", "H"):
    _KIND_STAGES[later] = _KIND_STAGES["E"]

_ROUTING = {  # variant language -> libraries it is dispatched to (F+)
    "ja": ("ndl", "internet-archive"),
    "en": ("loc", "internet-archive", "europeana"),
    "de": ("ddb", "internet-archive", "europeana"),
    "fr": ("gallica", "internet-archive", "europeana"),
}


def engine_variants(config: str, query: str):
    from b6_eval import SEARCHABLE_LIBRARIES, baseline_variants

    analysis = analyze_discovery_query(query)
    plan = QueryExpansionEngine().expand(analysis, mode="standard")
    allowed = _KIND_STAGES[config]
    variants = baseline_variants(query)
    routing: dict[str, tuple] = {}
    for variant in plan["variants"]:
        if variant["kind"] in allowed and variant["text"] not in variants:
            variants.append(variant["text"])
    if config in ("F", "G", "H"):
        # Routing: the original query still goes everywhere; every
        # other variant is dispatched by its detected language.
        # Unknown-language variants keep the full dispatch.
        from global_library_mcp.discovery import detect_language

        for variant in variants[1:]:
            lang = detect_language(variant)["language"]
            if lang in _ROUTING:
                routing[variant] = _ROUTING[lang]
    return variants, {"routing": routing, "plan": plan}


def engine_rank(case, items, query_hits, plan):
    # Ablation finding (all three datasets): replacing the
    # incumbent rank_candidates ordering with rank_discovery
    # kept Recall@10 but lowered MRR (dev 0.93->0.81). The
    # shipped design therefore keeps rank_candidates for order
    # and uses score_item only to attach explanations; the
    # replacement ranking remains available as an opt-in.
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.ranking import score_item
    from global_library_mcp.service import rank_candidates
    from global_library_mcp.question import analyze_question

    analysis = analyze_discovery_query(case["query"])
    for item in items:
        _score, reasons = score_item(analysis, item, query_hits)
        item._discovery_reasons = reasons
    return rank_candidates(analyze_question(case["query"]), items, query_hits)
