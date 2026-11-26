"""Discovery-side language model (b6, section 5).

Separate from question.QuestionAnalysis, which drives evidence
admission and MUST NOT change: this module only informs
bibliographic discovery - which languages a query is written in,
which document languages might hold the material, and which
lexicon concepts / authors / works the query mentions.

Language detection is heuristic and honest about uncertainty:
short proper nouns are reported as unknown rather than forced
into a language, and a bare surname never decides the language
of the whole query.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from global_library_mcp import lexicon as lexicon_mod

_HIRAGANA = re.compile(r"[ぁ-ん]")
_KATAKANA = re.compile(r"[ァ-ヶー]")
_KANJI = re.compile(r"[一-鿿]")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")

_DE_WORDS = {"der", "die", "das", "und", "im", "von", "über", "geschichte", "wissenschaft",
             "philosophie", "jahrhundert", "entwicklung", "gesellschaft", "natur"}
_FR_WORDS = {"le", "la", "les", "de", "des", "du", "une", "et", "en", "au", "aux",
             "histoire", "philosophie", "révolution", "siècle"}
_EN_WORDS = {"the", "of", "and", "in", "history", "century", "what", "how", "development",
             "between", "during", "early", "late"}
_DE_CHARS = set("äöüßÄÖÜ")
_FR_CHARS = set("çœæàâéèêëîïô")


def detect_language(text: str) -> dict[str, Any]:
    """{language, confidence, mixed_language, unknown, signals}.

    language is one of ja/en/de/fr/unknown. mixed_language is set
    when two language communities are both substantially present
    (e.g. a Japanese question quoting a German title)."""
    raw = text or ""
    signals: dict[str, float] = {"ja": 0.0, "en": 0.0, "de": 0.0, "fr": 0.0}
    if _HIRAGANA.search(raw) or _KATAKANA.search(raw):
        signals["ja"] += 3.0
    kanji = len(_KANJI.findall(raw))
    if kanji:
        signals["ja"] += min(kanji, 4) * 0.5  # kanji alone: weak ja evidence
    latin_words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]*", raw)
    lowered = [w.lower() for w in latin_words]
    if any(ch in _DE_CHARS for ch in raw):
        signals["de"] += 2.0
    if any(ch in _FR_CHARS for ch in raw):
        signals["fr"] += 1.5
    for word in lowered:
        if word in _DE_WORDS:
            signals["de"] += 1.0
        if word in _FR_WORDS:
            signals["fr"] += 1.0
        if word in _EN_WORDS:
            signals["en"] += 1.0
    if latin_words and not (signals["de"] or signals["fr"]):
        signals["en"] += 0.5
    # Lexicon voting: a query built from a German or French
    # scholarly label (Dampfmaschine, machine a vapeur) carries
    # that language even without stopwords or diacritics.
    for section in ("concepts", "works"):
        for entry in lexicon_mod.match_entries(raw, section):
            lang = entry.get("_matched_language")
            if lang in signals and lang != "ja":
                signals[lang] += 1.5
    best = max(signals, key=lambda k: signals[k])
    total = sum(signals.values())
    # Short proper-noun-only input: refuse to decide.
    tokens = [t for t in re.split(r"\s+", raw.strip()) if t]
    if total < 1.5 or (len(tokens) <= 2 and kanji == 0 and not _HIRAGANA.search(raw)
                        and not _KATAKANA.search(raw) and signals[best] < 2.0):
        return {"language": "unknown", "confidence": 0.2, "mixed_language": False,
                "unknown": True, "signals": signals}
    confidence = round(signals[best] / total, 2) if total else 0.0
    second = sorted(signals.values())[-2] if total else 0.0
    mixed = bool(total and second >= 2.0 and signals[best] - second <= 1.5)
    return {"language": best, "confidence": max(confidence, 0.35), "mixed_language": mixed,
            "unknown": False, "signals": signals}


_STOPWORDS = {
    "en": {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "for", "with", "by",
           "from", "as", "was", "were", "are", "is", "what", "when", "where", "which", "who",
           "how", "why", "that", "this", "about", "into", "during", "between"},
    "de": {"der", "die", "das", "den", "dem", "des", "und", "oder", "im", "in", "von", "zu",
           "über", "ein", "eine", "ist", "war", "mit", "für", "als", "auch", "sich"},
    "fr": {"le", "la", "les", "de", "des", "du", "une", "un", "et", "en", "au", "aux", "est",
           "dans", "sur", "par", "pour", "avec", "qui", "que"},
}


def extract_terms_unicode(text: str, language: str) -> list[str]:
    """Content terms for Latin-script languages using Unicode word
    characters (the b5 English path was ASCII-only, which broke
    German/French concept extraction)."""
    words = re.findall(r"[^\W\d_][^\W_'-]*", unicodedata.normalize("NFKC", text), re.UNICODE)
    stops = _STOPWORDS.get(language, set())
    terms: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        phrase = " ".join(run[:3])
        if phrase not in terms:
            terms.append(phrase)
        for word in run:
            if len(word) >= 5 and word not in terms:
                terms.append(word)
        run.clear()

    for word in words:
        if word.lower() in stops:
            flush()
            continue
        run.append(word)
    flush()
    return terms[:6]


@dataclass
class DiscoveryQueryAnalysis:
    raw: str
    query_language: dict[str, Any]
    requested_document_languages: list[str] | None
    terms: list[str]
    concepts: list[dict[str, Any]]
    authors: list[dict[str, Any]]
    works: list[dict[str, Any]]
    era: dict[str, Any] | None
    ambiguous_authors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "query_language": self.query_language,
            "requested_document_languages": self.requested_document_languages,
            "terms": self.terms,
            "concepts": [c["concept_id"] for c in self.concepts],
            "authors": [a["author_id"] for a in self.authors],
            "works": [w["work_id"] for w in self.works],
            "ambiguous_authors": [a["surname"] for a in self.ambiguous_authors],
            "era": self.era,
        }


def analyze_discovery_query(
    query: str,
    *,
    requested_document_languages: list[str] | None = None,
    user_language_override: str | None = None,
) -> DiscoveryQueryAnalysis:
    """Discovery-only analysis. Never feeds evidence admission."""
    from global_library_mcp.question import _detect_era, extract_terms

    detection = detect_language(query)
    if user_language_override:
        detection = {**detection, "language": user_language_override, "user_override": True,
                     "confidence": 1.0, "unknown": False}
    language = detection["language"]
    if language == "ja" or detection["signals"].get("ja", 0) > 0:
        terms = extract_terms(query)
    elif language in ("de", "fr", "en"):
        terms = extract_terms_unicode(query, language)
    else:
        terms = extract_terms(query) or extract_terms_unicode(query, "en")
    concepts = lexicon_mod.match_entries(query, "concepts")
    works = lexicon_mod.match_entries(query, "works")
    authors = lexicon_mod.match_entries(query, "authors")
    # A matched work identifies its author more strongly than a
    # shared surname surface does: when a work matched, drop
    # same-surname authors whose only match was the generic
    # surname surface, and include the work's author.
    if works:
        work_authors = {w["author_id"] for w in works}
        kept: list[dict[str, Any]] = []
        for author in authors:
            if author["author_id"] in work_authors:
                kept.append(author)
            elif any(lexicon_mod.author_by_id(wid) and lexicon_mod.author_by_id(wid)["surname"] == author["surname"]
                     for wid in work_authors):
                surface = author.get("_matched_surface") or ""
                given = (author.get("given_names") or "").split()
                if not any(g and g.lower() in query.lower() for g in given) and \
                        not any(n in query for n in author["names"].get("ja", []) if "・" in n and n != surface):
                    continue  # generic surname surface only; the work decides
                kept.append(author)
            else:
                kept.append(author)
        authors = kept
        for wid in work_authors:
            if all(a["author_id"] != wid for a in authors):
                author = lexicon_mod.author_by_id(wid)
                if author:
                    authors.append({**author, "_matched_surface": "", "_matched_language": "", "_via_work": True})
    # Surname-only matches: a query naming just "Muller" or
    # "Darwin" matches no full name form, so scan surnames too and
    # mark them as surname-only (they feed the ambiguity logic
    # below, never a specific identification).
    matched_ids = {a["author_id"] for a in authors}
    query_norm = query.lower()
    for author in lexicon_mod.load_lexicon()["authors"]:
        if author["author_id"] in matched_ids:
            continue
        surname = (author.get("surname") or "").lower()
        if surname and len(surname) >= 3 and surname in query_norm:
            authors.append({**author, "_matched_surface": author["surname"],
                            "_matched_language": "", "_surname_only": True})
    # Author ambiguity: a bare surname shared by several authors,
    # with no given name, work title or life dates in the query,
    # identifies nobody. Such matches stay ambiguous and must not
    # be expanded into a specific person's works.
    ambiguous: list[dict[str, Any]] = []
    specific: list[dict[str, Any]] = []
    by_surname: dict[str, list[dict]] = {}
    for author in authors:
        by_surname.setdefault(author["surname"], []).append(author)
    work_author_ids = {w["author_id"] for w in works}
    for surname, group in by_surname.items():
        if len(group) <= 1:
            specific.extend(group)
            continue
        corroborated = [a for a in group if a["author_id"] in work_author_ids
                        or any(g.lower() in query.lower() for g in a.get("given_names", "").lower().split())]
        if corroborated:
            specific.extend(corroborated)
            ambiguous.extend(a for a in group if a not in corroborated)
        else:
            ambiguous.extend(group)
    return DiscoveryQueryAnalysis(
        raw=query, query_language=detection,
        requested_document_languages=requested_document_languages,
        terms=terms, concepts=concepts, authors=specific, works=works,
        era=_detect_era(query), ambiguous_authors=ambiguous)
