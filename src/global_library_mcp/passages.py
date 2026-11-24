"""Passage extraction (Phase 8-C).

The unit of evidence is not the page but the passage: the
sentence(s) that actually bear on the question, with their
position in the original OCR, their immediate context, their
era anchors and the concepts they carry. The quoted text is
always a verbatim slice of the fetched OCR - normalisation is
applied only to the *matching* copy, never to the quotation -
and `verify_quote` re-checks that property for any caller.

Cross-sentence binding stays conservative: a passage is one
sentence plus its neighbours as *context*. The neighbours are
displayed for the reader; they are not silently merged into
the quoted claim, because adjacency does not make two events
one event.
"""
from __future__ import annotations

import re
from typing import Any

_SENTENCE_RE = re.compile(r"[^。．！？\n]+[。．！？]?")


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) over the raw text, offsets exact."""
    spans: list[tuple[int, int, str]] = []
    for match in _SENTENCE_RE.finditer(text or ""):
        sentence = match.group(0)
        if len(sentence.strip()) >= 4:
            spans.append((match.start(), match.end(), sentence))
    return spans


def verify_quote(ocr_text: str, passage_text: str, char_start: int | None = None) -> bool:
    """A quotation must be a verbatim slice of the fetched OCR."""
    if not passage_text:
        return False
    if char_start is not None:
        return ocr_text[char_start:char_start + len(passage_text)] == passage_text
    return passage_text in ocr_text


def _stance_of(sentence: str) -> list[str]:
    from global_library_mcp.semantics import (
        _DIFFUSION_CUES,
        _LATER_CUES,
        _NEGATION_CUES,
        _OCCURRENCE_CUES,
        _PLANNING_CUES,
        _cue_hits,
    )

    stances = []
    if _cue_hits(sentence, _NEGATION_CUES):
        stances.append("negation")
    if _cue_hits(sentence, _LATER_CUES):
        stances.append("later")
    if _cue_hits(sentence, _PLANNING_CUES):
        stances.append("planning")
    if _cue_hits(sentence, _OCCURRENCE_CUES):
        stances.append("occurrence")
    if _cue_hits(sentence, _DIFFUSION_CUES):
        stances.append("diffusion")
    return stances


def extract_passages(
    analysis: Any,
    ocr_text: str,
    citation_key: str,
    image_url: str | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Concept-bearing passages of one page, verbatim and located."""
    from global_library_mcp.question import find_concept
    from global_library_mcp.relevance import concept_families
    from global_library_mcp.temporal import anchor_class, sentence_years

    families = concept_families(getattr(analysis, "core_concepts", []) or [])
    if not families or not ocr_text:
        return []
    spans = sentence_spans(ocr_text)
    passages: list[dict[str, Any]] = []
    for idx, (start, end, sentence) in enumerate(spans):
        matched = [fam for fam in families if find_concept(sentence, fam)]
        if not matched:
            continue
        era = getattr(analysis, "era", None)
        passage = {
            "passage_id": f"{citation_key}#p{len(passages) + 1}",
            "citation_key": citation_key,
            "text": sentence,
            "char_start": start,
            "char_end": end,
            "context_before": spans[idx - 1][2] if idx > 0 else "",
            "context_after": spans[idx + 1][2] if idx + 1 < len(spans) else "",
            "concepts": matched,
            "stance_cues": _stance_of(sentence),
            "era_anchor": {
                "class": anchor_class(sentence, era) if era else "no_era",
                "years": sentence_years(sentence),
            },
            "image_url": image_url,
            "quote_verified": verify_quote(ocr_text, sentence, start),
        }
        passages.append(passage)
        if len(passages) >= limit:
            break
    return passages
