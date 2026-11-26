"""Provider handoff candidate extraction.

DDB -> BSB (b6, section 17; structural verification hardened
in the b6 final review, section 8) and Finna -> NLF Digi
(b8, section 6, at the end of this module).

A DDB record may be handed to the BSB adapter ONLY when the
DDB metadata itself carries the BSB digital object identifier
in an official form - the URN (urn:nbn:de:bvb:12-bsbXXXXXXXX-N)
or a structurally parsed MDZ object URL on the exact official
host - AND the record's provider is the Bayerische
Staatsbibliothek, established from the structured provider
fields (provider_id, or the dataset label's parenthesised
provider code 00005860), never from free text. Identifiers are
parsed structurally: an MDZ-looking string embedded in another
host's URL (path or query) is not an MDZ URL, and a malformed
URN is not an identifier. Title/author similarity is never
used to guess an identifier. The extracted id is a CANDIDATE:
nothing here fetches the upstream URL; the verified id is
handed to the BSB adapter's own official endpoints, whose
strict manifest identity checks decide whether the object is
what the DDB record says it is.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_BSB_PROVIDER_CODE = "00005860"
# A complete URN token: the whole whitespace-delimited token
# must be the URN, with an 8-digit object id and a numeric or
# 'x' check digit.
_URN_TOKEN_RE = re.compile(r"^urn:nbn:de:bvb:12-(bsb\d{8})-(\d|x)$", re.IGNORECASE)
_MDZ_HOSTS = {"www.digitale-sammlungen.de", "digitale-sammlungen.de"}
_MDZ_PATH_RE = re.compile(r"^/(?:[a-z]{2}/)?view/(bsb\d{8})(?:[/?#]|$)")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_strings(item))
        return out
    return []


def _identifiers_in(text: str) -> list[tuple[str, str]]:
    """(object_id, basis) pairs structurally present in one
    metadata string."""
    found: list[tuple[str, str]] = []
    for token in re.split(r"[\s\"'<>]+", text or ""):
        match = _URN_TOKEN_RE.match(token.strip(".,;)"))
        if match:
            found.append((match.group(1).lower(), "official URN in the DDB record"))
    for token in re.split(r"[\s\"'<>]+", text or ""):
        if "://" not in token:
            continue
        try:
            parsed = urlparse(token)
        except ValueError:
            continue
        if parsed.scheme != "https" or (parsed.hostname or "") not in _MDZ_HOSTS:
            continue
        match = _MDZ_PATH_RE.match(parsed.path or "")
        if match:
            found.append((match.group(1).lower(), "MDZ object URL in the DDB record"))
    return found


def extract_bsb_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    """{status, bsb_object_id, basis} for a DDB record's raw
    metadata. status: candidate / no_candidate /
    refused_provider_mismatch / refused_ambiguous."""
    if not isinstance(raw, dict):
        return {"status": "no_candidate", "bsb_object_id": None, "basis": "no raw metadata"}
    provider_ids = _strings(raw.get("provider_id"))
    dataset = " ".join(_strings(raw.get("dataset_label")))
    is_bsb = _BSB_PROVIDER_CODE in provider_ids or f"({_BSB_PROVIDER_CODE})" in dataset
    candidates: list[tuple[str, str]] = []
    for text in _strings(raw.get("view")) + _strings(raw.get("preview")) + _strings(raw.get("url")):
        candidates.extend(_identifiers_in(text))
    if not candidates:
        return {"status": "no_candidate", "bsb_object_id": None,
                "basis": "the DDB record carries no structurally valid BSB object identifier"}
    if not is_bsb:
        return {"status": "refused_provider_mismatch", "bsb_object_id": None,
                "basis": "a BSB identifier appears but the DDB provider fields do not "
                         "identify the Bayerische Staatsbibliothek (00005860)"}
    ids = {c[0] for c in candidates}
    if len(ids) > 1:
        return {"status": "refused_ambiguous", "bsb_object_id": None,
                "basis": f"several different BSB identifiers in one DDB record: {sorted(ids)}"}
    return {"status": "candidate", "bsb_object_id": candidates[0][0],
            "basis": candidates[0][1] + "; provider is the Bayerische Staatsbibliothek (00005860)"}


# --- Finna -> NLF Digi (b8, section 6) -------------------------------------

_DIGI_HOSTS = {"digi.kansalliskirjasto.fi", "digi.nationallibrary.fi"}
_DIGI_GENRES = {"sanomalehti", "aikakauslehti", "teos"}
_DIGI_BINDING_RE = re.compile(r"^\d+$")


_NLF_DATA_SOURCE = "kansalliskirjasto"
_NLF_BUILDING_SEGMENT = "Kansalliskirjasto"
_NLF_LABELS = {"kansalliskirjasto", "national library of finland"}


def _finna_provider_is_nlf(finndoc: dict[str, Any]) -> tuple[bool, str]:
    """Structured National Library of Finland provider
    evidence in a Finna document payload: the record's data
    source prefix, or a buildings/institutions facet naming
    the National Library. Free text is never used."""
    data_source = str(finndoc.get("data_source") or "")
    if data_source == _NLF_DATA_SOURCE:
        return True, "Finna data source is kansalliskirjasto (National Library of Finland)"
    for entry in finndoc.get("buildings") or []:
        if isinstance(entry, dict):
            value = str(entry.get("value") or "")
            label = str(entry.get("label") or entry.get("translated") or "")
            if _NLF_BUILDING_SEGMENT in value.split("/") or label.strip().lower() in _NLF_LABELS:
                return True, "Finna buildings facet names the National Library of Finland"
    for label in finndoc.get("provider_institutions") or []:
        if str(label).strip().lower() in _NLF_LABELS:
            return True, "Finna institutions facet names the National Library of Finland"
    return False, "no structured National Library of Finland provider identifier in the Finna record"


def extract_digi_candidate(finndoc: dict[str, Any]) -> dict[str, Any]:
    """{status, binding_id, genre, basis} for a Finna document
    payload's provider links (b8, section 6; final review
    section 7).

    Candidate EXTRACTION and handoff IDENTITY are separate
    steps. A binding becomes a full ``candidate`` only when
    ALL of these hold: a provider link parses structurally as
    ``https://digi.kansalliskirjasto.fi/<genre>/binding/<digits>...``
    on the exact official host (no userinfo, no abnormal
    port); exactly ONE binding id and ONE genre are named
    (the same binding under two different genres is refused,
    never last-wins); and the Finna record's STRUCTURED
    provider fields identify the National Library of Finland
    as the provider of the record. Without the provider
    evidence the link is reported as
    ``candidate_provider_unverified`` - displayable as a
    candidate, never a confirmed handoff. Bibliographic
    correspondence (title/author/year/format) must still be
    checked by the caller against the Digi record itself;
    nothing here fetches any URL.
    """
    if not isinstance(finndoc, dict):
        return {"status": "no_candidate", "binding_id": None, "genre": None, "basis": "no Finna document"}
    found: dict[str, set[str]] = {}
    for link in finndoc.get("provider_links") or []:
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "")
        if any(ord(ch) < 0x20 for ch in url):
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _DIGI_HOSTS:
            continue
        if parsed.username or parsed.password:
            continue
        try:
            if parsed.port not in (None, 443):
                continue
        except ValueError:
            continue
        segments = [seg for seg in (parsed.path or "").split("/") if seg]
        if len(segments) < 3:
            continue
        genre, marker, binding = segments[0], segments[1], segments[2]
        if genre not in _DIGI_GENRES or marker != "binding" or not _DIGI_BINDING_RE.match(binding):
            continue
        found.setdefault(binding, set()).add(genre)
    if not found:
        return {"status": "no_candidate", "binding_id": None, "genre": None, "basis": "no structurally valid Digi binding link in the Finna record"}
    if len(found) > 1:
        return {
            "status": "refused_ambiguous",
            "binding_id": None,
            "genre": None,
            "basis": f"Finna record links to {len(found)} different Digi bindings: {sorted(found)}",
        }
    binding_id, genres = next(iter(found.items()))
    if len(genres) > 1:
        return {
            "status": "refused_ambiguous",
            "binding_id": None,
            "genre": None,
            "basis": f"Finna record links binding {binding_id} under conflicting genres: {sorted(genres)}",
        }
    genre = next(iter(genres))
    provider_ok, provider_basis = _finna_provider_is_nlf(finndoc)
    if not provider_ok:
        return {
            "status": "candidate_provider_unverified",
            "binding_id": binding_id,
            "genre": genre,
            "basis": ("Digi binding URL on the exact official host in the Finna record's "
                      "provider links, but " + provider_basis + "; candidate display "
                      "only, not a confirmed handoff"),
        }
    return {
        "status": "candidate",
        "binding_id": binding_id,
        "genre": genre,
        "basis": ("Digi binding URL on the exact official host in the Finna record's "
                  "provider links; " + provider_basis),
    }


def titles_correspond(ddb_title: str, bsb_title: str) -> bool:
    """Title correspondence signal for the handoff check: the
    normalised titles share at least half of the shorter title's
    content tokens (or one contains the other). This is a
    candidate signal only - it never proves two records are the
    same object; the identifier and provider checks above are
    the primary signals, and author/year disagreement must be
    checked separately by the caller."""
    import unicodedata

    def tokens(text: str) -> set[str]:
        text = unicodedata.normalize("NFKC", text or "").lower()
        return {t for t in re.split(r"[^a-zà-ÿ0-9一-鿿ぁ-んァ-ヶ]+", text) if len(t) >= 3}

    a, b = tokens(ddb_title), tokens(bsb_title)
    if not a or not b:
        return False
    if " ".join(sorted(a)) in " ".join(sorted(b)) or " ".join(sorted(b)) in " ".join(sorted(a)):
        return True
    return len(a & b) / min(len(a), len(b)) >= 0.5
