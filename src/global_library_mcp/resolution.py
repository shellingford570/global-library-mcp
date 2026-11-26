"""Work/author resolution for bibliographic records (b6,
sections 12-13; strictness hardened in the b6 final review,
section 6).

Links a record to a lexicon work (work_id) or author (author_id)
as a CANDIDATE association with its basis stated. Resolution is
never an identity proof: the local lexicon is unverified
(every entry carries verification_status=unverified), so no
outcome here is ever "authority_verified". Records keep their
own record_id, pages, OCR, years and citations; a shared
work_id groups editions/translations for presentation without
merging them.

Statuses (work):
- candidate_exact_title_and_author: the record title is exactly
  a lexicon title AND the record author agrees by a full name
  form. work_id is set.
- candidate_title_only: the title matches exactly but the author
  could not be checked (author metadata missing, or agreement
  only at surname level), OR the lexicon title appears inside a
  longer record title (commentaries, studies and reviews live
  here - they are about the work, not the work). work_id is NOT
  set; candidate_work_id names the possible work.
- refused_author_mismatch: the title matches but the record
  author is a different person.
- ambiguous: several lexicon works/authors fit equally.
- insufficient_metadata: not enough metadata to judge.
- no_match.

Statuses (author): candidate_exact / candidate_surname_only /
refused_ambiguous_surname / ambiguous / insufficient_metadata /
no_match. A bare surname shared by several lexicon authors
identifies nobody; a surname substring never identifies
anybody.
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


def _author_agreement(work: dict, author_n: str) -> str:
    """'full' / 'surname' / 'none' - how the record author agrees
    with the work's lexicon author. Equality only: substrings of
    a name never count (Erasmus Darwin is not Charles Darwin)."""
    author_entry = lexicon_mod.author_by_id(work["author_id"])
    if not author_entry or not author_n:
        return "none"
    forms = {_norm(n) for names in author_entry["names"].values() for n in names}
    if author_n in forms:
        return "full"
    surname = _norm(author_entry.get("surname") or "")
    if surname and author_n == surname:
        return "surname"
    # "Surname, Given" cataloguing form of the same person.
    if surname and author_n.startswith(surname + " "):
        given = author_n[len(surname) + 1:].replace(" ", "")
        full_forms = {f.replace(",", "").replace(" ", "") for f in forms}
        if any(given and len(given) >= 2 and given in f for f in full_forms):
            return "full"
    return "none"


def resolve_work(title: str, author: str) -> dict[str, Any]:
    """{work_id, candidate_work_id, status, basis,
    verification_status} for a bibliographic record."""
    title_n = _norm(title)
    author_n = _norm(author)
    base = {"work_id": None, "candidate_work_id": None,
            "verification_status": "lexicon_unverified"}
    if not title_n:
        return {**base, "status": "insufficient_metadata",
                "basis": "record has no title to resolve"}
    exact: list[dict] = []
    contained: list[dict] = []
    for work in lexicon_mod.load_lexicon()["works"]:
        for t in _titles_of(work):
            tn = _norm(t)
            if tn and tn == title_n:
                exact.append(work)
                break
            if tn and len(tn) >= 8 and tn in title_n:
                contained.append(work)
                break
    candidates = exact or contained
    if not candidates:
        return {**base, "status": "no_match", "basis": "no lexicon work title matches"}
    if len(candidates) > 1:
        return {**base, "status": "ambiguous",
                "basis": f"title matches {len(candidates)} lexicon works"}
    work = candidates[0]
    is_exact = bool(exact)
    if not author_n:
        return {**base, "candidate_work_id": work["work_id"],
                "status": "candidate_title_only",
                "basis": "title matches but the record has no author metadata; "
                         "author agreement was NOT checked"}
    agreement = _author_agreement(work, author_n)
    if agreement == "none":
        return {**base, "status": "refused_author_mismatch",
                "basis": f"title matches {work['work_id']} but the record author "
                         f"({author}) does not match the work's author"}
    if not is_exact:
        return {**base, "candidate_work_id": work["work_id"],
                "status": "candidate_title_only",
                "basis": "the work's title appears inside a longer record title; "
                         "this may be a commentary, study or review about the work, "
                         "not the work itself"}
    if agreement == "surname":
        return {**base, "candidate_work_id": work["work_id"],
                "status": "candidate_title_only",
                "basis": "title matches exactly; the record author is given as a "
                         "surname only, so author agreement is surname-level"}
    return {**base, "work_id": work["work_id"],
            "status": "candidate_exact_title_and_author",
            "basis": "exact title match (original or translated title) and full "
                     "author name agreement; lexicon candidate, not authority-verified"}


def resolve_author(author_text: str) -> dict[str, Any]:
    """{author_id, status, basis, verification_status} - refuses
    bare shared surnames and never matches by substring."""
    author_n = _norm(author_text)
    base = {"author_id": None, "verification_status": "lexicon_unverified"}
    if not author_n:
        return {**base, "status": "insufficient_metadata",
                "basis": "record has no author metadata; no author link attempted"}
    exact: list[dict] = []
    surname_hits: list[dict] = []
    for entry in lexicon_mod.load_lexicon()["authors"]:
        forms = [n for names in entry["names"].values() for n in names]
        if any(_norm(f) == author_n for f in forms):
            exact.append(entry)
        elif _norm(entry.get("surname") or "") == author_n:
            surname_hits.append(entry)
    if len(exact) == 1:
        return {**base, "author_id": exact[0]["author_id"], "status": "candidate_exact",
                "basis": "full name form matches the lexicon entry (candidate, not authority-verified)"}
    if len(exact) > 1:
        return {**base, "status": "ambiguous",
                "basis": "the same full name form belongs to several lexicon authors"}
    if len(surname_hits) == 1:
        return {**base, "author_id": surname_hits[0]["author_id"], "status": "candidate_surname_only",
                "basis": "surname matches exactly one lexicon author (weak candidate link)"}
    if len(surname_hits) > 1:
        return {**base, "status": "refused_ambiguous_surname",
                "basis": f"surname is shared by {len(surname_hits)} lexicon authors; not identified"}
    return {**base, "status": "no_match", "basis": "no lexicon author matches"}
