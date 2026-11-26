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
    ) -> dict[str, Any]:
        cap = _MODE_CAPS.get(mode, 8)
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
        for concept in analysis.concepts:
            for lang, label, kind in lexicon_mod.labels_for(concept):
                if kind == "historical":
                    add(label, lang, "historical", "spelling_variant",
                        f"historical form of {concept['concept_id']}", "lexicon:concepts", 2,
                        status=concept.get("verification_status"))
                    continue
                if lang == query_lang:
                    continue
                add(label, lang, "concept_translation", "translation",
                    f"{lang} label of {concept['concept_id']}", "lexicon:concepts", 3,
                    status=concept.get("verification_status"))
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
        return {
            "original_query": query,
            "normalized_query": norm(query),
            "query_language": analysis.query_language,
            "variants": variants,
            "skipped": skipped,
            "budget": {"variant_cap": cap, "variants_used": len(variants),
                       "mode": mode},
            "multilingual_enabled": expand_multilingual,
            "historical_enabled": expand_historical,
            "allowed_languages": sorted(allowed_languages),
        }
