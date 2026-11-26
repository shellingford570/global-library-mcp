"""DDB -> BSB candidate extraction (b6, section 17).

A DDB record may be handed to the BSB adapter ONLY when the
DDB metadata itself carries the BSB digital object identifier
in an official identifier field - in practice the URN
(urn:nbn:de:bvb:12-bsbXXXXXXXX-N) present in the record's
display fields - AND the record's provider is the Bayerische
Staatsbibliothek (DDB provider code 00005860). Title/author
similarity is never used to guess an identifier. The extracted
id is a CANDIDATE: the BSB adapter's strict manifest identity
checks decide whether the object is what the DDB record says
it is, and a title comparison runs before any link is shown.
"""
from __future__ import annotations

import re
from typing import Any

_BSB_PROVIDER_CODE = "00005860"
_URN_RE = re.compile(r"urn:nbn:de:bvb:12-(bsb\d{8})-\d")
_URL_RE = re.compile(r"digitale-sammlungen\.de/(?:[a-z]{2}/)?(?:view/)?(bsb\d{8})")


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


def extract_bsb_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    """{status, bsb_object_id, basis} for a DDB record's raw
    metadata. status: candidate / no_candidate /
    refused_provider_mismatch."""
    if not isinstance(raw, dict):
        return {"status": "no_candidate", "bsb_object_id": None, "basis": "no raw metadata"}
    provider_ids = _strings(raw.get("provider_id"))
    dataset = " ".join(_strings(raw.get("dataset_label")))
    is_bsb = _BSB_PROVIDER_CODE in provider_ids or f"({_BSB_PROVIDER_CODE})" in dataset
    candidates: list[tuple[str, str]] = []
    for text in _strings(raw.get("view")) + _strings(raw.get("preview")) + _strings(raw.get("url")):
        for match in _URN_RE.finditer(text):
            candidates.append((match.group(1), "official URN in the DDB record"))
        for match in _URL_RE.finditer(text):
            candidates.append((match.group(1), "MDZ object URL in the DDB record"))
    if not candidates:
        return {"status": "no_candidate", "bsb_object_id": None,
                "basis": "the DDB record carries no BSB object identifier"}
    if not is_bsb:
        return {"status": "refused_provider_mismatch", "bsb_object_id": None,
                "basis": "a BSB identifier appears but the DDB provider is not the Bayerische Staatsbibliothek"}
    ids = {c[0] for c in candidates}
    if len(ids) > 1:
        return {"status": "refused_ambiguous", "bsb_object_id": None,
                "basis": f"several different BSB identifiers in one DDB record: {sorted(ids)}"}
    return {"status": "candidate", "bsb_object_id": candidates[0][0],
            "basis": candidates[0][1] + "; provider is the Bayerische Staatsbibliothek (00005860)"}


def titles_correspond(ddb_title: str, bsb_title: str) -> bool:
    """Conservative title correspondence for the handoff check:
    the normalised titles share at least half of the shorter
    title's content tokens (or one contains the other)."""
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
