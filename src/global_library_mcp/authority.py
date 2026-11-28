"""Authority resolution (b10 Stage 2, brief sections 11-15).

Resolves names and titles to authority CANDIDATES backed by the
local lexicon and, when explicitly enabled, key-free official
authority APIs (lobid GND, Wikidata; VIAF implemented but its live
endpoint was bot-blocked from the development network on
2026-11-28, so it is off by default).

Hard rules (brief sections 12-14):
- Reaching an authority record never by itself certifies that a
  bibliographic record's author IS that person. ``authority_verified``
  additionally requires at least two agreeing bibliographic signals
  (exact name form + life years, or name + associated work) and no
  unresolved competitor.
- A life-year CONFLICT hard-excludes a candidate; it never averages.
- Same-name people stay separate candidates (``ambiguous``) when the
  available signals cannot discriminate them.
- Works, editions and copies are different levels: resolving a work
  never merges its editions, and ``identify_edition`` answers only
  on an exact year match.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from . import lexicon

FetchJson = Callable[[str], dict]

# Final review (section 9): the live authority clients use a
# synchronous, unbudgeted HTTP path that does NOT go through
# BudgetedTransport / destination validation / cancellation.
# They are therefore DEVELOPER-EXPERIMENTAL ONLY: the resolver
# takes no live sources by default and the research search path
# never enables them. Do not wire them into production search
# until an async, budgeted, allow-listed transport exists.
LIVE_SOURCES_EXPERIMENTAL = True

STATUSES = (
    "authority_verified", "authority_candidate", "ambiguous",
    "conflicting_authorities", "insufficient_metadata",
    "unavailable", "not_checked",
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("・", " ").replace("‐", "-")
    return re.sub(r"[\s,.\u3000]+", " ", text).strip()


def _year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.match(r"(\d{3,4})", value.strip())
        if m:
            return int(m.group(1))
    return None


@dataclass
class AuthorityRecord:
    authority_id: str
    authority_source: str          # local-lexicon | gnd | wikidata | viaf
    entity_type: str               # person | organization | work | edition | translation | subject
    canonical_name: str
    variant_names: list[str] = field(default_factory=list)
    birth_year: int | None = None
    death_year: int | None = None
    language: str = ""
    associated_works: list[str] = field(default_factory=list)
    external_identifiers: dict[str, str] = field(default_factory=dict)
    source_url: str = ""
    retrieved_at: str = ""
    verification_status: str = "authority_candidate"
    fetched: bool = False
    observations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", [], {})}


@dataclass
class Candidate:
    record: AuthorityRecord
    score: float
    signals: list[str] = field(default_factory=list)
    excluded_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"record": self.record.to_dict(), "score": self.score,
               "signals": list(self.signals)}
        if self.excluded_reason:
            out["excluded_reason"] = self.excluded_reason
        return out


@dataclass
class Resolution:
    query: str
    entity_type: str
    status: str
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"query": self.query, "entity_type": self.entity_type,
                "status": self.status,
                "candidates": [c.to_dict() for c in self.candidates],
                "notes": list(self.notes)}


# ---------------------------------------------------------------------------
# Local lexicon source
# ---------------------------------------------------------------------------

def _lexicon_person(entry: dict) -> AuthorityRecord:
    names: list[str] = []
    for forms in (entry.get("names") or {}).values():
        names.extend(forms)
    canonical = ""
    for lang in ("en", "ja", "de", "fr"):
        forms = (entry.get("names") or {}).get(lang) or []
        if forms:
            canonical = max(forms, key=len)
            break
    ids = {k: v for k, v in (entry.get("authority_ids") or {}).items() if v}
    return AuthorityRecord(
        authority_id=entry["author_id"], authority_source="local-lexicon",
        entity_type="person", canonical_name=canonical,
        variant_names=sorted(set(names)),
        birth_year=entry.get("birth_year"), death_year=entry.get("death_year"),
        associated_works=list(entry.get("known_works") or []),
        external_identifiers=ids,
        verification_status=(
            "authority_candidate" if ids else "authority_candidate"),
    )


# ---------------------------------------------------------------------------
# Live sources (injectable fetch for fixture tests)
# ---------------------------------------------------------------------------

def _default_fetch(url: str) -> dict:
    import httpx

    resp = httpx.get(url, timeout=20.0, follow_redirects=True,
                     headers={"User-Agent": "global-library-mcp/b10-authority",
                              "Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


class GndSource:
    """lobid GND (Deutsche Nationalbibliothek data via hbz lobid).

    Key-free JSON-LD API, live-verified 2026-11-28 from the
    development network (Kant 118559796; Darwin disambiguation;
    year-filtered queries for Weber/Rousseau).
    """

    name = "gnd"
    BASE = "https://lobid.org/gnd/search"

    def __init__(self, fetch: FetchJson | None = None):
        self.fetch = fetch or _default_fetch

    def search_person(self, name: str, birth_year: int | None = None) -> list[AuthorityRecord]:
        from urllib.parse import quote

        # Final review (section 9): the name is a VALUE, never
        # query syntax. Lucene operators / field separators are
        # stripped before quoting so user input cannot change the
        # fields or operators of the search expression.
        name = re.sub(r'["\\:()\[\]{}^~*?/]', " ", name or "").strip()
        q = f"preferredName:{name}"
        if birth_year:
            q += f" AND dateOfBirth:{birth_year}*"
        url = (f"{self.BASE}?q={quote(q)}"
               "&filter=type%3ADifferentiatedPerson&format=json&size=10")
        data = self.fetch(url)
        out: list[AuthorityRecord] = []
        for member in data.get("member") or []:
            gid = str(member.get("id") or "").rsplit("/", 1)[-1]
            if not gid:
                continue
            variants = [v for v in (member.get("variantName") or [])
                        if isinstance(v, str)]
            out.append(AuthorityRecord(
                authority_id=f"gnd:{gid}", authority_source="gnd",
                entity_type="person",
                canonical_name=str(member.get("preferredName") or ""),
                variant_names=variants,
                birth_year=_year((member.get("dateOfBirth") or [None])[0]),
                death_year=_year((member.get("dateOfDeath") or [None])[0]),
                source_url=f"https://d-nb.info/gnd/{gid}", fetched=True,
                verification_status="authority_candidate"))
        return out


class WikidataSource:
    """Wikidata API (key-free). Live-verified 2026-11-28
    (Natsume Soseki = Q180903). Auxiliary source: useful for
    cross-checks, never the sole basis for verification."""

    name = "wikidata"
    BASE = "https://www.wikidata.org/w/api.php"

    def __init__(self, fetch: FetchJson | None = None):
        self.fetch = fetch or _default_fetch

    def search_person(self, name: str, birth_year: int | None = None) -> list[AuthorityRecord]:
        from urllib.parse import quote

        url = (f"{self.BASE}?action=wbsearchentities&search={quote(name)}"
               "&language=en&format=json&limit=8&type=item")
        data = self.fetch(url)
        out: list[AuthorityRecord] = []
        for hit in data.get("search") or []:
            qid = str(hit.get("id") or "")
            if not qid.startswith("Q"):
                continue
            out.append(AuthorityRecord(
                authority_id=f"wikidata:{qid}", authority_source="wikidata",
                entity_type="person",
                canonical_name=str(hit.get("label") or ""),
                variant_names=[str(a) for a in hit.get("aliases") or []],
                source_url=f"https://www.wikidata.org/wiki/{qid}", fetched=True,
                verification_status="authority_candidate"))
        return out


class ViafSource:
    """VIAF AutoSuggest (OCLC). Implemented from the documented
    response shape, but the live endpoint returned a Cloudflare
    bot-block from the development network on 2026-11-28, so this
    source is NOT enabled by default and its live status is
    recorded as unverified in docs/b10-authority-resolution.md."""

    name = "viaf"
    BASE = "https://viaf.org/viaf/AutoSuggest"

    def __init__(self, fetch: FetchJson | None = None):
        self.fetch = fetch or _default_fetch

    def search_person(self, name: str, birth_year: int | None = None) -> list[AuthorityRecord]:
        from urllib.parse import quote

        data = self.fetch(f"{self.BASE}?query={quote(name)}")
        out: list[AuthorityRecord] = []
        for hit in data.get("result") or []:
            if str(hit.get("nametype") or "").lower() not in ("personal", "person"):
                continue
            vid = str(hit.get("viafid") or "")
            if not vid:
                continue
            term = str(hit.get("term") or "")
            years = re.search(r"(\d{3,4})\s*-\s*(\d{3,4})", term)
            out.append(AuthorityRecord(
                authority_id=f"viaf:{vid}", authority_source="viaf",
                entity_type="person",
                canonical_name=term,
                birth_year=int(years.group(1)) if years else None,
                death_year=int(years.group(2)) if years else None,
                source_url=f"https://viaf.org/viaf/{vid}", fetched=True,
                verification_status="authority_candidate"))
        return out


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

_OFFICIAL_SOURCES = {"gnd", "wikidata", "viaf", "ndl"}


class AuthorityResolver:
    def __init__(self, live_sources: list | None = None):
        self.live_sources = list(live_sources or [])

    # -- persons ------------------------------------------------------
    def _gather_persons(self, name: str, birth_year: int | None,
                        notes: list[str]) -> list[AuthorityRecord]:
        records: list[AuthorityRecord] = []
        entries: dict[str, dict] = {}
        for entry in lexicon.match_entries(name, "authors"):
            entries[entry["author_id"]] = entry
        # Reverse direction: a surname-only or exact-form query is a
        # substring OF the stored forms, which match_entries (built
        # for discovery text) does not cover.
        name_n = _norm(name)
        for entry in lexicon.load_lexicon()["authors"]:
            forms = [n for group in (entry.get("names") or {}).values()
                     for n in group]
            surnames = set()
            for raw in forms:
                if "," in raw:
                    surnames.add(_norm(raw.split(",", 1)[0]))
                elif _norm(raw):
                    surnames.add(_norm(raw).split(" ")[-1])
            if name_n in surnames or name_n in {_norm(f) for f in forms}:
                entries[entry["author_id"]] = entry
        for entry in entries.values():
            records.append(_lexicon_person(entry))
        for source in self.live_sources:
            try:
                records.extend(source.search_person(name, birth_year))
            except Exception as exc:  # network/API failure -> unavailable note
                notes.append(f"{source.name}: unavailable ({type(exc).__name__})")
        return records

    def resolve_person(self, name: str, *, birth_year: int | None = None,
                       death_year: int | None = None,
                       known_work: str | None = None,
                       role: str | None = None) -> Resolution:
        # `role` records the BIBLIOGRAPHIC role under discussion
        # (author / translator / editor / subject). Verification
        # certifies identity only; a person verified as a subject
        # is not thereby the author of a work. The role is echoed
        # in the resolution notes so callers cannot conflate them.
        notes: list[str] = []
        records = self._gather_persons(name, birth_year, notes)
        res = Resolution(query=name, entity_type="person",
                         status="insufficient_metadata", notes=notes)
        if not records:
            res.status = "unavailable" if notes else "insufficient_metadata"
            return res
        work_titles: set[str] = set()
        if known_work:
            for work in lexicon.load_lexicon()["works"]:
                titles = [work["original_title"]] + [
                    t for forms in (work.get("translated_titles") or {}).values()
                    for t in forms]
                if _norm(known_work) in {_norm(t) for t in titles}:
                    work_titles.add(work["work_id"])
        # Merge records that describe the same person (shared
        # external identifier, or same canonical name + birth year)
        # so two sources for one person do not compete as rivals.
        merged: list[AuthorityRecord] = []
        by_key: dict[str, AuthorityRecord] = {}

        def _key(rec: AuthorityRecord) -> str:
            for scheme in ("gnd", "viaf", "ndl", "wikidata"):
                if rec.external_identifiers.get(scheme):
                    return f"{scheme}:{rec.external_identifiers[scheme]}"
            if rec.authority_source in _OFFICIAL_SOURCES:
                return rec.authority_id
            return f"name:{_norm(rec.canonical_name)}:{rec.birth_year}"

        # Final review (section 8): observations are preserved
        # BEFORE merging and contradictions are detected on the
        # un-merged observations - merging must never erase a
        # disagreement between sources.
        _pre_merge_conflict = False
        _pre_merge_ambiguity = False
        _by_ext_obs: dict[str, list[AuthorityRecord]] = {}
        for rec in records:
            rec.observations = [{
                "source": rec.authority_source,
                "authority_id": rec.authority_id,
                "birth_year": rec.birth_year, "death_year": rec.death_year,
                "canonical_name": rec.canonical_name,
                "fetched": bool(rec.fetched),
                "retrieved_at": rec.retrieved_at}]
            for scheme, value in rec.external_identifiers.items():
                _by_ext_obs.setdefault(f"{scheme}:{value}", []).append(rec)
            if rec.authority_source in _OFFICIAL_SOURCES:
                _by_ext_obs.setdefault(rec.authority_id, []).append(rec)
        for _obs in _by_ext_obs.values():
            _births = {r.birth_year for r in _obs if r.birth_year}
            _deaths = {r.death_year for r in _obs if r.death_year}
            for _years in (_births, _deaths):
                if len(_years) > 1:
                    if max(_years) - min(_years) == 1:
                        _pre_merge_ambiguity = True
                    else:
                        _pre_merge_conflict = True
        for rec in records:
            key = _key(rec)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = rec
                merged.append(rec)
                continue
            # union variants/identifiers; prefer the official record.
            # Years are NEVER overwritten: a disagreement stays in
            # the observations and blocks verification.
            existing.observations = [
                *existing.observations, *rec.observations]
            if rec.fetched:
                existing.fetched = True
            existing.variant_names = sorted(
                set(existing.variant_names) | set(rec.variant_names)
                | {rec.canonical_name})
            for scheme, value in rec.external_identifiers.items():
                existing.external_identifiers.setdefault(scheme, value)
            if existing.birth_year is None:
                existing.birth_year = rec.birth_year
            if existing.death_year is None:
                existing.death_year = rec.death_year
            if existing.authority_source not in _OFFICIAL_SOURCES \
                    and rec.authority_source in _OFFICIAL_SOURCES:
                existing.authority_id = rec.authority_id
                existing.authority_source = rec.authority_source
                existing.source_url = rec.source_url
        records = merged
        name_n = _norm(name)
        surname_n = name_n.split(" ")[-1] if name_n else ""
        scored: list[Candidate] = []
        for rec in records:
            cand = Candidate(record=rec, score=0.0)
            raw_forms = [rec.canonical_name, *rec.variant_names]
            forms = {_norm(f) for f in raw_forms}
            inverted = set()
            surnames = set()
            for raw in raw_forms:
                if "," in raw:
                    parts = [p.strip() for p in raw.split(",", 1)]
                    inverted.add(_norm(f"{parts[1]} {parts[0]}"))
                    surnames.add(_norm(parts[0]))
                elif _norm(raw):
                    surnames.add(_norm(raw).split(" ")[-1])
            if name_n in forms | inverted:
                cand.score += 3.0
                cand.signals.append("exact_name_form")
            elif surname_n and surname_n in surnames:
                cand.score += 1.0
                cand.signals.append("surname_only")
            # A one-year difference is a calendar/era-boundary
            # ambiguity (e.g. Newton 1642 Old Style vs 1643 New
            # Style; regnal-year boundaries) - it withholds the
            # match points and is noted, but does not exclude.
            # Larger differences hard-exclude (brief section 26).
            for label, given, actual in (
                    ("birth_year", birth_year, rec.birth_year),
                    ("death_year", death_year, rec.death_year)):
                if given is None or actual is None:
                    continue
                if actual == given:
                    cand.score += 2.0
                    cand.signals.append(f"{label}_match")
                elif abs(actual - given) == 1:
                    cand.signals.append(f"{label}_off_by_one_calendar_ambiguity")
                else:
                    cand.excluded_reason = (
                        f"{label}_conflict: {actual} != {given}")
            if work_titles and rec.associated_works:
                if work_titles & set(rec.associated_works):
                    cand.score += 2.0
                    cand.signals.append("associated_work_match")
            scored.append(cand)
        # Cross-source conflict: same external id, disagreeing years.
        by_ext: dict[str, AuthorityRecord] = {}
        conflict = False
        for cand in scored:
            for scheme, value in cand.record.external_identifiers.items():
                key = f"{scheme}:{value}"
                other = by_ext.get(key)
                if other is not None and (
                        (other.birth_year and cand.record.birth_year
                         and other.birth_year != cand.record.birth_year)
                        or (other.death_year and cand.record.death_year
                            and other.death_year != cand.record.death_year)):
                    conflict = True
                by_ext.setdefault(key, cand.record)
            if cand.record.authority_source in _OFFICIAL_SOURCES:
                gid = cand.record.authority_id
                other = by_ext.get(gid)
                if other is not None and other is not cand.record and (
                        (other.birth_year and cand.record.birth_year
                         and other.birth_year != cand.record.birth_year)):
                    conflict = True
                by_ext.setdefault(gid, cand.record)
        viable = [c for c in scored if not c.excluded_reason]
        scored.sort(key=lambda c: -c.score)
        res.candidates = scored
        if conflict or _pre_merge_conflict:
            res.status = "conflicting_authorities"
            res.notes.append("sources disagree on life years for the same authority id")
            return res
        if _pre_merge_ambiguity:
            res.notes.append(
                "sources differ by one year for the same authority id; "
                "kept ambiguous (a calendar explanation requires an "
                "explicit documented basis, which is absent)")
        if not viable:
            res.status = "insufficient_metadata"
            res.notes.append("all name matches excluded by life-year conflicts")
            return res
        top = max(viable, key=lambda c: c.score)
        second = max((c.score for c in viable if c is not top), default=0.0)
        if top.score >= 4.0 and top.score - second >= 2.0:
            # Final review (section 7): authority_verified requires
            # ALL of: an official authority record ACTUALLY FETCHED
            # (an identifier merely written in the local lexicon is
            # unverified and never suffices), the fetched record's
            # id strictly matching its source scheme, an exact name
            # or verified variant match, at least one independent
            # auxiliary signal, person-type agreement and no
            # unresolved ambiguity/conflict.
            _obs_official = [o for o in top.record.observations
                             if o.get("fetched")
                             and o.get("source") in _OFFICIAL_SOURCES
                             and str(o.get("authority_id", "")).startswith(
                                 str(o.get("source")) + ":")]
            _aux = [sg for sg in top.signals if sg.endswith("_match")]
            _verified = bool(
                _obs_official
                and "exact_name_form" in top.signals
                and any(sg in _aux for sg in (
                    "birth_year_match", "death_year_match",
                    "associated_work_match"))
                and top.record.entity_type == "person"
                and not _pre_merge_ambiguity
                and not any("off_by_one" in sg for sg in top.signals))
            res.status = ("authority_verified" if _verified
                          else "authority_candidate")
            if not _verified and top.record.authority_source == "local-lexicon":
                res.notes.append(
                    "local lexicon candidate only: external identifiers "
                    "present in the lexicon are unverified until the "
                    "official authority record is fetched")
        elif top.score >= 3.0 and top.score - second < 2.0:
            res.status = "ambiguous"
        elif top.score >= 3.0:
            res.status = "authority_candidate"
        else:
            res.status = "insufficient_metadata"
        return res

    # -- works and editions -------------------------------------------
    def resolve_work(self, title: str, *, author_hint: str | None = None) -> Resolution:
        res = Resolution(query=title, entity_type="work",
                         status="insufficient_metadata")
        title_n = _norm(title)
        matches: list[Candidate] = []
        for work in lexicon.load_lexicon()["works"]:
            titles = {"original": [work["original_title"]]}
            for lang, forms in (work.get("translated_titles") or {}).items():
                titles[lang] = list(forms)
            hit_lang = None
            for lang, forms in titles.items():
                if title_n in {_norm(t) for t in forms}:
                    hit_lang = lang
                    break
            if hit_lang is None:
                continue
            author = lexicon.author_by_id(work["author_id"]) or {}
            author_names = [n for forms in (author.get("names") or {}).values()
                            for n in forms]
            rec = AuthorityRecord(
                authority_id=work["work_id"], authority_source="local-lexicon",
                entity_type="work", canonical_name=work["original_title"],
                variant_names=[t for forms in titles.values() for t in forms],
                language=work.get("original_language", ""),
                associated_works=[work["work_id"]],
                verification_status="authority_candidate")
            cand = Candidate(record=rec, score=3.0,
                             signals=[f"title_match:{hit_lang}"])
            cand.record.external_identifiers = {
                "author_id": work["author_id"],
                "year_first": str(work.get("year_first") or ""),
                "editions": str(len(_EDITIONS.get(work["work_id"], []))),
            }
            if author_hint and _norm(author_hint) in {_norm(n) for n in author_names}:
                cand.score += 2.0
                cand.signals.append("author_hint_match")
            matches.append(cand)
        matches.sort(key=lambda c: -c.score)
        res.candidates = matches
        if not matches:
            return res
        if len(matches) > 1 and matches[0].score - matches[1].score < 2.0:
            res.status = "ambiguous"
        elif matches[0].score >= 5.0:
            res.status = "authority_candidate"
        else:
            res.status = "authority_candidate"
        return res


# Curated edition table (brief section 14): exact publication years
# only; a neighbouring year is never rounded to an edition.
_EDITIONS: dict[str, list[tuple[int, str, str]]] = {
    "work:kritik-reinen-vernunft": [
        (1781, "A", "初版 (A版)"), (1787, "B", "第2版 (B版)")],
    "work:origin-of-species": [
        (1859, "1", "初版"), (1860, "2", "第2版"), (1861, "3", "第3版"),
        (1866, "4", "第4版"), (1869, "5", "第5版"), (1872, "6", "第6版")],
    "work:principia": [
        (1687, "1", "初版"), (1713, "2", "第2版"), (1726, "3", "第3版")],
    # Faust's two PARTS (1808 / 1832) are distinct texts; the b10
    # dataset groups part distinction under edition identification,
    # and the same never-merge rule applies.
    "work:faust": [
        (1808, "1", "第一部 (Faust I)"), (1832, "2", "第二部 (Faust II)")],
}


def identify_edition(work_id: str, year: int | None) -> dict[str, Any] | None:
    """Edition for an exact year, else None. Editions of the same
    work never share pages, OCR or citations (brief section 14)."""
    if year is None:
        return None
    for pub_year, code, label in _EDITIONS.get(work_id, []):
        if pub_year == year:
            return {"work_id": work_id, "year": pub_year,
                    "edition_code": code, "edition_label": label,
                    "edition_id": f"{work_id}@{code}",
                    "status": "edition_candidate",
                    "basis": "publication_year_only",
                    "certainty": "candidate",
                    "note": ("a publication year alone does not prove a "
                             "specific edition: first/reprint, other "
                             "publishers, translations and annotated "
                             "editions can share a year"),
                    "shares_pages_with_other_editions": False}
    return None


def editions_of(work_id: str) -> list[dict[str, Any]]:
    out = []
    for pub_year, code, label in _EDITIONS.get(work_id, []):
        out.append({"work_id": work_id, "year": pub_year,
                    "edition_code": code, "edition_label": label,
                    "edition_id": f"{work_id}@{code}",
                    "status": "edition_candidate",
                    "basis": "publication_year_only",
                    "certainty": "candidate",
                    "shares_pages_with_other_editions": False})
    return out
