"""Temporal relations: which era does a page's statement belong to?

Phase 4's gate knew a page *mentions* the asked era. That is not
enough: a 1934 history of the Tokyo subway mentions the Meiji era
constantly, but the subway's opening it describes happened in
1927. This module separates the time axes the brief requires:

- publication time      when the document was published
- described time        eras/years a statement is anchored to
- event time            when the described event is dated
- phase                 existence / planning / introduction /
                        diffusion, as stated (see semantics.py)

For each concept-bearing sentence it extracts temporal anchors
(era names, western years, era-year expressions like 明治四十三年)
and classifies the anchor against the asked era: ``in_era``,
``before_era``, ``after_era``, or ``none``. The key derived signal
is ``onset_after_era``: a sentence that dates the topic's onset
(opening / start / introduction) to *after* the asked era — that
contradicts an era-bound premise instead of supporting it.
"""
from __future__ import annotations

import re
from typing import Any

from global_library_mcp.question import ERAS, _kanji_number, normalize_text

_YEAR_RE = re.compile(r"(1[4-9]\d{2}|20\d{2})\s*年")
_ERA_YEAR_RE = re.compile(r"(明治|大正|昭和|平成|令和|慶応|江戸)\s*([一二三四五六七八九十百]+|\d+)\s*年")
_ONSET_CUES = (
    "開業", "営業を開始", "運転を開始", "運行を開始", "放送を開始",
    "始まつた", "始まった", "開始され", "導入され", "実用化され",
    "完成し", "落成", "創業", "開通", "実現",
)


def sentence_years(sentence_normalised: str) -> list[int]:
    """All years a (normalised) sentence is anchored to."""
    years: list[int] = []
    for match in _YEAR_RE.finditer(sentence_normalised):
        years.append(int(match.group(1)))
    for match in _ERA_YEAR_RE.finditer(sentence_normalised):
        era_range = ERAS.get(match.group(1))
        if era_range is None:
            continue
        token = match.group(2)
        offset = int(token) if token.isdigit() else _kanji_number(token)
        if offset:
            years.append(era_range[0] + offset - 1)
    return years


def sentence_eras(sentence_normalised: str) -> list[str]:
    return [name for name in ERAS if normalize_text(name) in sentence_normalised]


def anchor_class(sentence_normalised: str, asked_era: dict[str, Any] | None) -> str:
    """Classify a sentence's temporal anchor against the asked era."""
    if not asked_era:
        return "none"
    years = sentence_years(sentence_normalised)
    for year in years:
        if asked_era["start"] <= year <= asked_era["end"]:
            return "in_era"
    eras = sentence_eras(sentence_normalised)
    asked_name = asked_era.get("era") or asked_era.get("label")
    if asked_name and asked_name in eras:
        return "in_era"
    if years:
        return "after_era" if min(years) > asked_era["end"] else "before_era"
    other = [name for name in eras if name != asked_name]
    if other:
        ranges = [ERAS[name] for name in other if name in ERAS]
        if ranges and min(r[0] for r in ranges) > asked_era["end"]:
            return "after_era"
        if ranges and max(r[1] for r in ranges) <= asked_era["start"]:
            return "before_era"
    return "none"


def onset_after_era(sentences: list[str], asked_era: dict[str, Any] | None) -> list[str]:
    """Sentences dating the topic's onset to after the asked era."""
    hits: list[str] = []
    if not asked_era:
        return hits
    for sentence in sentences:
        if any(normalize_text(cue) in sentence for cue in _ONSET_CUES):
            if anchor_class(sentence, asked_era) == "after_era":
                hits.append(sentence[:120])
    return hits
