"""Work/author resolution for bibliographic records (b6, sections
12-13).

Links a record to a lexicon work (work_id) or author (author_id)
as a CANDIDATE association with its basis stated. Resolution is
never an identity proof: records keep their own record_id,
pages, OCR, years and citations; a shared work_id groups
editions/translations for presentation without merging them.

Refusals are first-class outcomes: a title that matches a work
but whose author disagrees is NOT linked; a surname shared by
several authors links nobody.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from global_library_mcp import lexicon as lexicon_mod


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^一-鿿ぁ-んァ-ヶa-zà-ÿ0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _titles_of(work: dict) -> list[str]:
    titles = [work.get("original_title") or ""]
    for ts in (work.get("translated_titles") or {}).values():
        titles.extend(ts)
    return [t for t in titles if t]


def resolve_work(title: str, author: str) -> dict[str, Any]:
    """{work_id, status, basis} - status is one of linked /
    refused_author_mismatch / ambiguous / no_match."""
    title_n = _norm(title)
    author_n = _norm(author)
    candidates: list[dict] = []
    for work in lexicon_mod.load_lexicon()["works"]:
        if any(_norm(t) == title_n or (_norm(t) and _norm(t) in title_n and len(_norm(t)) >= 8)
               for t in _titles_of(work)):
            candidates.append(work)
    if not candidates:
        return {"work_id": None, "status": "no_match", "basis": "no lexicon work title matches"}
    if len(candidates) > 1:
        return {"work_id": None, "status": "ambiguous",
                "basis": f"title matches {len(candidates)} lexicon works"}
    work = candidates[0]
    author_entry = lexicon_mod.author_by_id(work["author_id"])
    if author_entry and author_n:
        forms = [n for names in author_entry["names"].values() for n in names]
        surname = _norm(author_entry.get("surname") or "")
        if not any(_norm(f) in author_n or author_n in _norm(f) for f in forms) and surname not in author_n:
            return {"work_id": None, "status": "refused_author_mismatch",
                    "basis": f"title matches {work['work_id']} but the record author "
                             f"({author}) does not match the work's author"}
    return {"work_id": work["work_id"], "status": "linked",
            "basis": "title match (original or translated title) with author agreement"}


def resolve_author(author_text: str) -> dict[str, Any]:
    """{author_id, status, basis} - refuses bare shared surnames."""
    author_n = _norm(author_text)
    if not author_n:
        return {"author_id": None, "status": "no_match", "basis": "record has no author text"}
    exact: list[dict] = []
    surname_hits: list[dict] = []
    for entry in lexicon_mod.load_lexicon()["authors"]:
        forms = [n for names in entry["names"].values() for n in names]
        if any(_norm(f) == author_n for f in forms):
            exact.append(entry)
        elif _norm(entry.get("surname") or "") == author_n:
            surname_hits.append(entry)
    if len(exact) == 1:
        return {"author_id": exact[0]["author_id"], "status": "linked",
                "basis": "full name form matches the lexicon entry"}
    if len(exact) > 1:
        return {"author_id": None, "status": "ambiguous",
                "basis": "the same full name form belongs to several lexicon authors"}
    if len(surname_hits) == 1:
        return {"author_id": surname_hits[0]["author_id"], "status": "linked_surname_only",
                "basis": "surname matches exactly one lexicon author (weak link, shown as candidate)"}
    if len(surname_hits) > 1:
        return {"author_id": None, "status": "refused_ambiguous_surname",
                "basis": f"surname is shared by {len(surname_hits)} lexicon authors; not identified"}
    return {"author_id": None, "status": "no_match", "basis": "no lexicon author matches"}
