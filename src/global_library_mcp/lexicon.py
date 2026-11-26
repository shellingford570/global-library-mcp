"""Loader and lookups for the multilingual search lexicon (b6).

The lexicon is a local, version-controlled compilation of
bibliographic facts (names, titles, subject labels) used ONLY to
widen discovery. It is never treated as proof of identity: an
author match here does not establish that two records share an
author, and a work match does not merge editions. Malformed
entries are rejected loudly at load time so a bad edit cannot
silently corrupt search behaviour.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).parent / "data" / "search_lexicon.json"
_LANGUAGES = ("ja", "en", "de", "fr")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, Any]:
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    for section, key in (("concepts", "concept_id"), ("authors", "author_id"), ("works", "work_id")):
        seen: set[str] = set()
        for entry in data.get(section, []):
            entry_id = entry.get(key)
            if not entry_id or entry_id in seen:
                raise ValueError(f"lexicon: duplicate or missing {key} in {section}: {entry_id!r}")
            seen.add(entry_id)
            if section == "concepts":
                labels = entry.get("labels") or {}
                if not any(labels.get(lang) for lang in _LANGUAGES):
                    raise ValueError(f"lexicon: concept {entry_id} has no labels")
                for ref in entry.get("related", []) + entry.get("excluded_confusions", []):
                    if ref not in {c["concept_id"] for c in data["concepts"]}:
                        raise ValueError(f"lexicon: concept {entry_id} references unknown concept {ref}")
            if section == "authors" and not (entry.get("names") or {}):
                raise ValueError(f"lexicon: author {entry_id} has no names")
            if section == "works":
                if entry.get("author_id") not in {a["author_id"] for a in data["authors"]}:
                    raise ValueError(f"lexicon: work {entry_id} references unknown author {entry.get('author_id')}")
    return data


def _all_forms(entry: dict, section: str) -> list[tuple[str, str]]:
    """(language, surface) pairs an entry can be matched by."""
    out: list[tuple[str, str]] = []
    if section == "concepts":
        for lang, labels in (entry.get("labels") or {}).items():
            for label in labels:
                out.append((lang, label))
        for lang, variants in (entry.get("historical_variants") or {}).items():
            for variant in variants:
                out.append((lang, variant))
    elif section == "authors":
        for lang, names in (entry.get("names") or {}).items():
            for name in names:
                out.append((lang, name))
    elif section == "works":
        out.append((entry.get("original_language") or "en", entry.get("original_title") or ""))
        for lang, titles in (entry.get("translated_titles") or {}).items():
            for title in titles:
                out.append((lang, title))
    return [(lang, s) for lang, s in out if s]


def match_entries(text: str, section: str) -> list[dict[str, Any]]:
    """Lexicon entries (concepts/authors/works) whose any-language
    surface appears in the text. Matching is substring on the
    NFKC-normalised text - a discovery signal, not an identity
    assertion."""
    data = load_lexicon()
    haystack = _norm(text)
    found: list[dict[str, Any]] = []
    for entry in data[section]:
        for lang, surface in _all_forms(entry, section):
            needle = _norm(surface)
            if len(needle) >= 2 and needle in haystack:
                found.append({**entry, "_matched_surface": surface, "_matched_language": lang})
                break
    return found


def labels_for(concept: dict, languages: tuple[str, ...] = _LANGUAGES) -> list[tuple[str, str, str]]:
    """(language, label, kind) for a concept: kind is 'label' or
    'historical'."""
    out: list[tuple[str, str, str]] = []
    for lang in languages:
        for label in (concept.get("labels") or {}).get(lang, []):
            out.append((lang, label, "label"))
        for variant in (concept.get("historical_variants") or {}).get(lang, []):
            out.append((lang, variant, "historical"))
    return out


def author_by_id(author_id: str) -> dict | None:
    for author in load_lexicon()["authors"]:
        if author["author_id"] == author_id:
            return author
    return None


def work_by_id(work_id: str) -> dict | None:
    for work in load_lexicon()["works"]:
        if work["work_id"] == work_id:
            return work
    return None


def works_by_author(author_id: str) -> list[dict]:
    return [w for w in load_lexicon()["works"] if w["author_id"] == author_id]


def authors_sharing_surname(surname_norm: str) -> list[dict]:
    return [a for a in load_lexicon()["authors"] if _norm(a.get("surname") or "") == surname_norm]
