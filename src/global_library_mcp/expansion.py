"""Query expansion for multilingual discovery (b6, section 15).

Turns a discovery analysis into a bounded, fully explained list
of search variants. Every variant carries its kind, its relation
to the original query (synonym / near-synonym / translation /
spelling variant / related), the reason it exists and its
source. Expansion is for DISCOVERY ONLY: it never feeds
evidence admission, never rewrites the user's text, and never
translates sentences. Users can disable multilingual or
historical expansion; the original query always runs first and
is always preferred when expansion would blur meaning.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from global_library_mcp import lexicon as lexicon_mod
from global_library_mcp.discovery import DiscoveryQueryAnalysis
from global_library_mcp.question import latin_variants, script_variants

_MODE_CAPS = {"quick": 3, "standard": 8, "deep": 14}
_ALL_LANGS = ("ja", "en", "de", "fr", "fi", "sv", "nl")

# b10 section 9 allocation policies for the concept-translation
# fan-out (see QueryExpansionEngine.expand). "legacy" is the
# b6-release sequential order; "diagonal" the b8/b9 interleave;
# "primary_guarantee" the b8 section-19 experiment (not adopted
# then); "hierarchy" concept-major allocation; "user_priority"
# prefers the caller's requested languages; "authority_first"
# is structurally identical to "diagonal" for translations -
# its content (compounds and authority forms first) is already
# guaranteed by the priority sort, which the b10 comparison
# verifies numerically instead of assuming.
_ALLOCATION_POLICIES = ("diagonal", "legacy", "primary_guarantee",
                        "hierarchy", "user_priority", "authority_first")

# Historical kana orthography (search-only): wi/we kana and the
# iteration mark. Word-level old-kana spellings live in the
# lexicon's historical_variants, not in free rewriting.
_KANA_HISTORICAL = {"ヰ": "イ", "ヱ": "エ", "ゐ": "い", "ゑ": "え"}


def _historical_kana(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in ("ゝ", "ヽ") and out:
            out.append(out[-1])
        elif ch in ("ゞ", "ヾ") and out:
            prev = out[-1]
            voiced = {"か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご",
                      "さ": "ざ", "し": "じ", "す": "ず", "せ": "ぜ", "そ": "ぞ",
                      "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で", "と": "ど"}
            out.append(voiced.get(prev, prev))
        else:
            out.append(_KANA_HISTORICAL.get(ch, ch))
    return "".join(out)


_UK_US = [("organisation", "organization"), ("colour", "color"), ("behaviour", "behavior"),
          ("centre", "center"), ("theatre", "theater"), ("harbour", "harbor"),
          ("labour", "labor"), ("fibre", "fiber"), ("defence", "defense")]

_DE_HEADS = ("maschine", "kraft", "bahn", "geschichte", "wissenschaft", "theorie",
             "lehre", "kunde", "werk", "wesen", "tum")


def _english_variants(term: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if "-" in term:
        out.append((term.replace("-", " "), "hyphen removed"))
    elif " " in term and len(term.split()) == 2:
        out.append((term.replace(" ", "-"), "hyphenated form"))
    for uk, us in _UK_US:
        if uk in term.lower():
            out.append((term.lower().replace(uk, us), "British/American spelling"))
        if us in term.lower():
            out.append((term.lower().replace(us, uk), "British/American spelling"))
    return out


def _german_compound_split(term: str) -> str | None:
    """Conservative compound split: only when a long word ends in
    a known scholarly head noun and the remainder is itself a
    plausible stem (>=4 chars). Produces a two-word search
    variant; the original compound always remains primary."""
    lowered = term.lower()
    if len(lowered) < 10 or " " in lowered:
        return None
    for head in _DE_HEADS:
        if lowered.endswith(head) and len(lowered) - len(head) >= 4:
            stem = term[: len(term) - len(head)]
            return f"{stem} {term[len(term) - len(head):]}"
    return None


class QueryExpansionEngine:
    def expand(
        self,
        analysis: DiscoveryQueryAnalysis,
        *,
        mode: str = "standard",
        expand_multilingual: bool = True,
        expand_historical: bool = True,
        target_languages: list[str] | None = None,
        allocation: str | None = None,
    ) -> dict[str, Any]:
        cap = _MODE_CAPS.get(mode, 8)
        # b10 section 9: the multilingual ALLOCATION policy -
        # how concept-translation candidates compete for the
        # variant cap across languages. The b10 comparison
        # (docs/b10-multilingual-routing.md, measured on the
        # b6 fixed + challenge simulations, the b6 dev/holdout
        # sets and the b8 fixed evaluation) found the b6-release
        # concept-major order ("legacy") at least as good as the
        # b8 diagonal interleave on every corpus and better on
        # the challenge set (0.9167 vs 0.8611), the b8 set
        # (0.7667 vs 0.7500; cross-language 0.7500 vs 0.6667)
        # and MRR, so it is the default again; "diagonal"
        # remains available, and the guarantee/hierarchy
        # policies - which improved b8 but regressed b6 fixed -
        # were NOT adopted, per the brief's rule against
        # one-sided trade-offs. The GLM_EXPANSION_ALLOCATION
        # environment variable is an evaluation hook only.
        import os as _os

        allocation = allocation \
            or _os.environ.get("GLM_EXPANSION_ALLOCATION") or "legacy"
        if allocation not in _ALLOCATION_POLICIES:
            allocation = "legacy"
        query = analysis.raw
        query_lang = analysis.query_language["language"]
        # Final review (section 5): the two expansion toggles and
        # the explicit target languages gate EVERY candidate path
        # centrally here - original titles, author works and
        # concept labels included. A variant in a language other
        # than the query language is a multilingual candidate,
        # whoever generated it; a historical-form candidate is a
        # historical candidate, whoever generated it.
        if target_languages:
            allowed_languages = set(target_languages) | ({query_lang} if query_lang != "unknown" else set())
        elif expand_multilingual:
            allowed_languages = set(_ALL_LANGS)
        else:
            allowed_languages = {query_lang} if query_lang != "unknown" else set()
        variants: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        seen: set[str] = set()
        seen_skipped: set[str] = set()

        def norm(text: str) -> str:
            return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower()).strip()

        def skip(text: str, reason: str) -> None:
            if text and text not in seen_skipped:
                seen_skipped.add(text)
                skipped.append({"candidate": text, "reason": reason})

        def add(text: str, language: str, kind: str, relation: str, reason: str,
                source: str, priority: int, status: str | None = None) -> None:
            key = norm(text)
            if not text or key == norm(query) or key in seen:
                return
            if kind == "historical" and not expand_historical:
                skip(text, "historical expansion disabled")
                return
            if (language and language != "unknown" and language != query_lang
                    and language not in allowed_languages):
                skip(text, "multilingual expansion disabled"
                     if not expand_multilingual else
                     f"language {language} not in the requested document languages")
                return
            seen.add(key)
            variant = {"text": text, "language": language, "kind": kind,
                       "relation": relation, "reason": reason, "source": source,
                       "priority": priority}
            if status is not None:
                variant["lexicon_verification_status"] = status
            variants.append(variant)

        # 1) Works matched: original + translated titles (priority 1).
        for work in analysis.works:
            add(work["original_title"], work.get("original_language") or "en",
                "original_title", "synonym", f"original title of {work['work_id']}",
                "lexicon:works", 1, status=work.get("verification_status"))
            for lang, titles in (work.get("translated_titles") or {}).items():
                for title in titles:
                    add(title, lang, "translated_title", "translation",
                        f"translated title of {work['work_id']}", "lexicon:works", 1,
                        status=work.get("verification_status"))
        # 2) Specific authors: name forms in other languages (1),
        #    then their works' titles (2). Ambiguous authors are
        #    never expanded into a specific person's works.
        for author in analysis.authors:
            for lang, names in (author.get("names") or {}).items():
                for name in names:
                    add(name, lang, "author_name", "translation",
                        f"name form of {author['author_id']}", "lexicon:authors", 1,
                        status=author.get("verification_status"))
            for work in lexicon_mod.works_by_author(author["author_id"]):
                add(work["original_title"], work.get("original_language") or "en",
                    "original_title", "synonym", f"work of {author['author_id']}",
                    "lexicon:works", 2, status=work.get("verification_status"))
        seen_ambiguous: set[str] = set()
        for author in analysis.ambiguous_authors:
            if author["surname"] in seen_ambiguous:
                continue
            seen_ambiguous.add(author["surname"])
            skip(author["surname"],
                 "ambiguous author (shared surname); not expanded into a specific person's works")
        # 3) Concepts: labels in other languages (3), historical
        #    forms (2), related concepts (5, standard/deep only).
        #    b8: translations are added in a diagonal interleave
        #    across (concept, language) so that, under the variant
        #    cap, later languages in the lexicon order (fi/sv/nl)
        #    are not structurally starved by earlier ones
        #    (en/de/fr) whenever a query matches several concepts.
        _translations: list[tuple[int, int, int, str, str, dict]] = []
        _lang_order = {lang: index for index, lang in enumerate(lexicon_mod._LANGUAGES)}
        for concept_index, concept in enumerate(analysis.concepts):
            _label_counts: dict[str, int] = {}
            for lang, label, kind in lexicon_mod.labels_for(concept):
                if kind == "historical":
                    add(label, lang, "historical", "spelling_variant",
                        f"historical form of {concept['concept_id']}", "lexicon:concepts", 2,
                        status=concept.get("verification_status"))
                    continue
                if lang == query_lang:
                    continue
                label_index = _label_counts.get(lang, 0)
                _label_counts[lang] = label_index + 1
                _translations.append((concept_index, _lang_order.get(lang, 99),
                                      label_index, lang, label, concept))
        # First labels of every (concept, language) pair come
        # before second labels of any pair: a whole language is
        # worth more than a spelling doublet in a language that
        # is already represented.
        # Final review (section 19): the diagonal can still
        # starve the last languages (sv/nl) when three or more
        # concepts match. A primary-concept-per-language
        # guarantee was evaluated in this round: it improved
        # the b8 fixed set (Standard Recall@10 0.75 -> 0.8583)
        # but regressed the b6 fixed simulation (Recall@10
        # 0.8819 -> 0.8542), so per the brief it was NOT
        # adopted. The languages that miss out under the cap
        # are reported in languages_not_represented below
        # instead of being silently dropped.
        # b10 section 9: the ordering is now chosen by the
        # allocation policy so the alternatives can be compared
        # on BOTH fixed corpora before any adoption decision.
        # Items are (concept_index, lang_order, label_index,
        # lang, label, concept).
        if allocation == "legacy":
            # A: b6-release sequential order (concept, then
            # lexicon language order, then label).
            _translations.sort(key=lambda item: (item[0], item[1], item[2]))
        elif allocation == "primary_guarantee":
            # G: the primary concept's first label in EVERY
            # language precedes all other translations; the
            # remainder keeps the diagonal order.
            _translations.sort(key=lambda item: (
                0 if (item[0] == 0 and item[2] == 0) else 1,
                item[2], item[0] + item[1], item[1], item[0]))
        elif allocation == "hierarchy":
            # E: concept-major hierarchy - every language of
            # the primary concept (all label rounds) before the
            # secondary concepts are served at all.
            _translations.sort(key=lambda item: (item[0], item[2], item[1]))
        elif allocation == "user_priority":
            # C: the caller's requested languages (in their
            # stated order) win the interleave; unrequested
            # languages follow in lexicon order.
            _pref = list(target_languages or [])

            def _pref_rank(item: tuple) -> int:
                return _pref.index(item[3]) if item[3] in _pref \
                    else 100 + item[1]

            _translations.sort(key=lambda item: (
                item[2], _pref_rank(item), item[0] + item[1], item[0]))
        else:
            # B (diagonal interleave, the b8/b9 default) and H
            # (authority_first: identical here by construction -
            # see the policy table above).
            _translations.sort(key=lambda item: (item[2], item[0] + item[1], item[1], item[0]))
        for _ci, _li, _bi, lang, label, concept in _translations:
            add(label, lang, "concept_translation", "translation",
                f"{lang} label of {concept['concept_id']}", "lexicon:concepts", 3,
                status=concept.get("verification_status"))
        for concept in analysis.concepts:
            if mode in ("standard", "deep"):
                for ref in concept.get("related", []):
                    related = next((c for c in lexicon_mod.load_lexicon()["concepts"]
                                    if c["concept_id"] == ref), None)
                    if related:
                        for lang, label, kind in lexicon_mod.labels_for(related):
                            if kind == "label" and lang == query_lang:
                                add(label, lang, "related_concept", "related",
                                    f"related concept {ref} of {concept['concept_id']}",
                                    "lexicon:concepts", 5,
                                    status=related.get("verification_status"))
        # 4) Script / spelling variants of the query and its terms.
        bases = [query, *analysis.terms]
        for base in bases:
            if expand_historical:
                for sv in script_variants(base):
                    add(sv, "ja", "historical", "spelling_variant",
                        "old/new kanji script variant", "question:script_variants", 2)
                kana = _historical_kana(base)
                if kana != base:
                    add(kana, "ja", "historical", "spelling_variant",
                        "historical kana orthography normalised", "expansion:kana", 2)
            for lv in latin_variants(base):
                add(lv, query_lang if query_lang != "unknown" else "en", "spelling_variant",
                    "spelling_variant", "umlaut transliteration / diacritic fold",
                    "question:latin_variants", 4)
            for ev, why in _english_variants(base):
                add(ev, "en", "spelling_variant", "spelling_variant", why, "expansion:english", 4)
            split = _german_compound_split(base)
            if split:
                # b8: a compound split is a same-language
                # orthographic decomposition of the query itself,
                # so it sits with the historical spelling variants
                # (priority 2), not below the cross-language
                # concept translations (3). With fi/sv/nl labels
                # added, the translation fan-out otherwise crowded
                # it out of the deep-mode cap entirely.
                add(split, "de", "compound_split", "spelling_variant",
                    "German compound split (search-only)", "expansion:german", 2)
        # The cap applies AFTER priority ordering, so a flood of
        # low-priority candidates can never crowd out exact
        # titles, author forms or historical spellings.
        variants.sort(key=lambda v: v["priority"])
        overflow = variants[cap:]
        variants = variants[:cap]
        for extra in overflow:
            skip(extra["text"], "variant cap reached")
        # Section 19 reporting: which languages had candidates
        # but received no selected variant, and why. Surfaced in
        # the plan so a dropped language is explicit, never
        # silent.
        represented = {v["language"] for v in variants if v.get("language")}
        candidate_languages = represented | {
            v["language"] for v in overflow if v.get("language")}
        not_represented = sorted(candidate_languages - represented)
        return {
            "original_query": query,
            "normalized_query": norm(query),
            "query_language": analysis.query_language,
            "variants": variants,
            "skipped": skipped,
            "languages_represented": sorted(represented),
            "languages_not_represented": not_represented,
            "cap_reason": ("variant cap reached" if overflow else None),
            "budget": {"variant_cap": cap, "variants_used": len(variants),
                       "mode": mode},
            "allocation": allocation,
            "multilingual_enabled": expand_multilingual,
            "historical_enabled": expand_historical,
            "allowed_languages": sorted(allowed_languages),
        }
