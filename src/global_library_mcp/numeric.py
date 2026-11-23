"""Numeric grounding: a number in a source is not an answer.

Phase 6's q40 failure: the question asked how many waterfalls a
survey confirmed; the adopted page contained real numbers (staff
counts, budgets) that were not the asked quantity, and the claim
screen's literal-presence check passed them. This module binds
quantities to what they count:

- quantities are extracted from Arabic and kanji numerals
  (period sources write 二十三, 一万二千, formal 參拾, 廿 for
  twenty), each with its counter/unit when present;
- a quantity is *bound* to a question when, in the cited OCR, at
  least one occurrence of that value sits in a window containing
  a core concept of the question (the asked target);
- quantities found only on table pages are reported separately:
  row/column structure cannot be resolved from raw OCR, so they
  are "table-unverified" and need the original image.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9,
           "壱": 1, "弐": 2, "貳": 2, "参": 3, "參": 3, "肆": 4, "伍": 5,
           "陸": 6, "漆": 7, "捌": 8, "玖": 9}
_SMALL_UNITS = {"十": 10, "拾": 10, "百": 100, "千": 1000}
_BIG_UNITS = {"万": 10000, "萬": 10000, "億": 100000000}
_KANJI_NUM_CHARS = set(_DIGITS) | set(_SMALL_UNITS) | set(_BIG_UNITS) | {"廿", "卅"}

_COUNTERS = (
    "人", "名", "円", "圓", "本", "件", "台", "臺", "個", "箇", "頭", "隻",
    "軒", "戸", "所", "箇所", "町村", "県", "郡", "村", "町", "m", "メートル",
    "km", "キロ", "里", "尺", "間", "坪", "年", "月", "日", "時", "分", "秒",
    "歳", "才", "頁", "ページ", "巻", "冊", "部", "点", "種", "等", "級",
)


def parse_kanji_number(token: str) -> float | None:
    """Parse a kanji numeral (二十三, 一万二千三百, 參拾, 廿四)."""
    if not token:
        return None
    token = token.replace("廿", "二十").replace("卅", "三十")
    total = 0.0
    section = 0.0
    current: float | None = None
    seen = False
    for char in token:
        if char in _DIGITS:
            current = _DIGITS[char]
            seen = True
        elif char in _SMALL_UNITS:
            section += (current if current is not None else 1) * _SMALL_UNITS[char]
            current = None
            seen = True
        elif char in _BIG_UNITS:
            section += current or 0
            total += (section if section else 1) * _BIG_UNITS[char]
            section = 0.0
            current = None
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + section + (current or 0)


_ARABIC_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_KANJI_RE = re.compile(r"[〇零一二三四五六七八九十百千拾万萬億壱弐貳参參肆伍陸漆捌玖廿卅]+")


def extract_quantities(text: str) -> list[dict[str, Any]]:
    """All quantity mentions: value, raw form, counter, span."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", text)
    found: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    def _counter_at(end: int) -> str | None:
        tail = normalized[end:end + 3]
        for counter in sorted(_COUNTERS, key=len, reverse=True):
            if tail.startswith(counter):
                return counter
        return None

    for match in _ARABIC_RE.finditer(normalized):
        raw = match.group(0)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        found.append({"value": value, "raw": raw, "unit": _counter_at(match.end()),
                      "start": match.start(), "end": match.end()})
        occupied.append((match.start(), match.end()))
    for match in _KANJI_RE.finditer(normalized):
        if any(match.start() < end and start < match.end() for start, end in occupied):
            continue
        token = match.group(0)
        # A lone 年-less era-year fragment like 四十三 is a number;
        # a single kanji that is part of a word (三菱, 千代田) is
        # caught by requiring either a unit char, a following
        # counter, or length >= 2.
        value = parse_kanji_number(token)
        if value is None:
            continue
        unit = _counter_at(match.end())
        has_unit_char = any(c in _SMALL_UNITS or c in _BIG_UNITS for c in token)
        if not (has_unit_char or unit or len(token) >= 2):
            continue
        found.append({"value": value, "raw": token, "unit": unit,
                      "start": match.start(), "end": match.end()})
    return sorted(found, key=lambda q: q["start"])


def numeric_values(text: str) -> set[float]:
    return {q["value"] for q in extract_quantities(text)}


_VERB_GLUE_RE = re.compile(r"^(?:.*?(された|される|した|する|でき|の))")


def target_terms(analysis: Any) -> list[str]:
    """Terms that name the asked target, for quantity binding.

    Core concepts arrive with verb glue from period question
    phrasing (確認された滝 for 滝): the binding window must look
    for the noun itself, so each concept contributes its variants
    plus its verb-stripped tail.
    """
    from global_library_mcp.question import concept_variants

    concepts = analysis.get("core_concepts") if isinstance(analysis, dict) else getattr(analysis, "core_concepts", None)
    terms: list[str] = []
    for concept in concepts or []:
        terms.extend(concept_variants(concept))
        tail = _VERB_GLUE_RE.sub("", concept)
        if tail and tail != concept:
            terms.append(tail)
    return [t for t in dict.fromkeys(terms) if t]


def quantity_binding(
    ocr_text: str,
    value: float,
    target_terms: list[str],
    page_kind: str | None = None,
    window: int = 40,
) -> dict[str, Any]:
    """Is ``value`` bound to the asked target anywhere in the OCR?

    An occurrence binds when a target term appears within
    ``window`` characters of it. Occurrences on table pages are
    counted apart: their row/column attachment cannot be read
    from raw OCR, so they never bind on their own.
    """
    normalized = unicodedata.normalize("NFKC", ocr_text or "")
    occurrences = [q for q in extract_quantities(ocr_text or "") if q["value"] == value]
    bound = 0
    for occurrence in occurrences:
        start = max(0, occurrence["start"] - window)
        end = min(len(normalized), occurrence["end"] + window)
        context = normalized[start:end]
        if any(term and term in context for term in target_terms):
            bound += 1
    return {
        "value": value,
        "occurrences": len(occurrences),
        "bound": bound,
        "on_table_page": page_kind == "table" and len(occurrences) > 0,
    }
