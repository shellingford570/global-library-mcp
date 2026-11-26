"""Discovery ranking (b6, section 19).

Ranks bibliographic candidates for DISCOVERY presentation only.
It is deliberately separate from evidence admission: a high
discovery rank means "worth the researcher's attention", never
"admissible as evidence". Every score carries its reasons so
the UI and MCP clients can explain why a record is shown.

Signals follow the query intent: author searches weight author
matches, title searches weight title matches. OCR availability
is a small auxiliary bonus only - a record without OCR is never
demoted out of the results for that reason.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from global_library_mcp import lexicon as lexicon_mod
from global_library_mcp.discovery import DiscoveryQueryAnalysis


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def score_item(analysis: DiscoveryQueryAnalysis, item: Any,
               query_hits: dict[tuple[str, str], int]) -> tuple[float, list[str]]:
    language = getattr(item, "language", None)
    title_n = _norm(getattr(item, "title", "") or "")
    author_n = _norm(getattr(item, "author", "") or "")
    subjects_n = _norm(" ".join(getattr(item, "subjects", []) or [])) if hasattr(item, "subjects") else ""
    score = 0.0
    reasons: list[str] = []
    query_n = _norm(analysis.raw)
    if query_n and query_n in title_n:
        score += 10
        reasons.append("title contains the full query")
    for work in analysis.works:
        titles = [work["original_title"], *(t for ts in (work.get("translated_titles") or {}).values() for t in ts)]
        if any(_norm(t) and _norm(t) in title_n for t in titles):
            score += 8
            reasons.append(f"title matches {work['work_id']} (original or translated title)")
            break
        item_work = getattr(item, "work_id", None)
        if item_work and item_work == work["work_id"]:
            score += 8
            reasons.append(f"record belongs to {work['work_id']}")
            break
    for author in analysis.authors:
        forms = [n for names in (author.get("names") or {}).values() for n in names]
        if any(_norm(f) and _norm(f) in author_n for f in forms):
            score += 6
            reasons.append(f"author matches {author['author_id']}")
            break
        surname = _norm(author.get("surname") or "")
        if surname and surname in author_n:
            score += 2
            reasons.append("author surname matches")
            break
    concept_score = 0.0
    for concept in analysis.concepts:
        # A concept label in the title counts fully when the
        # label's language is the record's own language (the
        # catalogue's own wording), and less when it is a
        # cross-language coincidence.
        best = 0.0
        for label_lang, label, _kind in lexicon_mod.labels_for(concept):
            if _norm(label) and _norm(label) in title_n:
                best = max(best, 3.0 if label_lang == language else 1.5)
            elif _norm(label) and _norm(label) in subjects_n:
                best = max(best, 1.0)
        if best:
            concept_score += best
            reasons.append(f"title/subject matches {concept['concept_id']}")
    score += min(concept_score, 6)
    # Material-type intent: a query asking for newspapers should
    # surface newspapers (section 19 lists material-type match).
    raw_lower = analysis.raw.lower()
    wants_news = any(w in raw_lower for w in ("新聞", "newspaper", "zeitung", "journal", "journaux", "新聞"))
    if wants_news and getattr(item, "material_type", None) == "newspaper":
        score += 2
        reasons.append("material type matches the query (newspaper)")
    era = analysis.era
    year = getattr(item, "year", None)
    if era and isinstance(year, int):
        if era["start"] <= year <= era["end"]:
            score += 2
            reasons.append("publication year inside the requested era")
        else:
            score -= 2
            reasons.append("publication year outside the requested era")
    wanted = analysis.requested_document_languages or [analysis.query_language["language"]]
    if language and language in wanted:
        score += 1
        reasons.append("document language matches the request")
    if getattr(item, "ocr", None):
        score += 0.5
        reasons.append("OCR available (auxiliary signal only)")
    hits = query_hits.get((getattr(item, "library_id", ""), getattr(item, "record_id", "")), 1)
    if hits > 1:
        score += min(hits - 1, 2)
        reasons.append(f"found by {hits} search variants")
    return score, reasons


def rank_discovery(analysis: DiscoveryQueryAnalysis, items: list[Any],
                    query_hits: dict[tuple[str, str], int]) -> list[Any]:
    scored = []
    for item in items:
        score, reasons = score_item(analysis, item, query_hits)
        item._discovery_score = score
        item._discovery_reasons = reasons
        scored.append(item)
    return sorted(scored, key=lambda it: -it._discovery_score)
