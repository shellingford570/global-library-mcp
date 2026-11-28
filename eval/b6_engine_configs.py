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
for later in ("F", "G", "H", "Gx"):
    _KIND_STAGES[later] = _KIND_STAGES["E"]

# Routing mirrors the production service (service.py): Europeana
# is NOT routed while it is authentication-pending
# (EUROPEANA_API_KEY unset), and ID-only libraries are never
# keyword-routed. The b6 candidate originally routed to
# Europeana as well; the final review (section 13) removed it,
# which also reduced simulated attempts.
_ROUTING = {  # variant language -> libraries it is dispatched to (F+)
    "ja": ("ndl", "internet-archive"),
    "en": ("loc", "internet-archive"),
    "de": ("ddb", "internet-archive"),
    "fr": ("gallica", "internet-archive"),
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
    if config in ("F", "G", "H", "Gx"):
        # Routing: the original query still goes everywhere; every
        # other variant is dispatched by its language. Engine
        # variants carry the plan's own language field - exactly
        # what production routing uses (service.py reads
        # variant["language"]). b10 fix: the previous code ran
        # detect_language() on the variant TEXT, which misroutes
        # single-word variants (the German compound
        # "Dampfmaschine" was detected as English and sent to
        # loc/internet-archive, never to ddb; the Finnish
        # "höyrykone" was detected as German and sent to ddb).
        # Legacy (non-engine) variants keep text detection.
        from global_library_mcp.discovery import detect_language

        plan_languages = {}
        for variant in plan["variants"]:
            if variant.get("text") and variant.get("language"):
                plan_languages[variant["text"]] = variant["language"]
        for variant in variants[1:]:
            lang = plan_languages.get(variant) or detect_language(variant)["language"]
            if lang in _ROUTING:
                routing[variant] = _ROUTING[lang]
    return variants, {"routing": routing, "plan": plan}


def engine_rank_experimental(case, items, query_hits, plan):
    """G_experimental (final review, section 16): the NOT-shipped
    configuration that actually reorders results with the
    discovery ranker. Kept reproducible so the rejection stays
    verifiable; do not confuse with G_shipped below."""
    return _rank_discovery_for(case, items, query_hits)


def _rank_discovery_for(case, items, query_hits):
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.ranking import rank_discovery

    analysis = analyze_discovery_query(case["query"])
    return rank_discovery(analysis, items, query_hits)


def engine_rank(case, items, query_hits, plan):
    # G_shipped: ablation finding (all three datasets): replacing
    # the incumbent rank_candidates ordering with rank_discovery
    # kept Recall@10 but lowered MRR (dev 0.93->0.81). The
    # shipped design therefore keeps rank_candidates for order
    # and uses score_item only to attach explanations; the
    # replacement ranking remains available as G_experimental.
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.ranking import score_item
    from global_library_mcp.service import rank_candidates
    from global_library_mcp.question import analyze_question

    analysis = analyze_discovery_query(case["query"])
    for item in items:
        _score, reasons = score_item(analysis, item, query_hits)
        item._discovery_reasons = reasons
    return rank_candidates(analyze_question(case["query"]), items, query_hits)
