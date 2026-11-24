"""OCR evidence pipeline helpers.

This module holds the pure, testable pieces of the evidence-first flow:
turning a natural-language question into in-document search terms, and
gating OCR text through a simple, honestly-labelled quality heuristic.

The quality heuristic is deliberately simple (character counts and the
ratio of replacement/control characters). It is a screening signal, not
a proof that the OCR is correct; the original page image remains the
ground truth and is always linked from the evidence record.
"""
from __future__ import annotations

import re
import unicodedata

# Characters that mark OCR or decoding trouble.
_REPLACEMENT = "�"

# Japanese particles and common question fragments used to split a
# natural-language question into content terms. This is a heuristic for
# search recall only; it never alters the stored question or the OCR.
_SPLIT_RE = re.compile(r"[\s　、。・，,.？?！!「」『』（）()\[\]はがをにへとのでもやか]+")
_QUESTION_TAIL_RE = re.compile(
    r"(について|とは|を教えて|について教えて|したの|したか|ですか|ますか|でしょうか|には|では).*$"
)

MIN_TERM_LENGTH = 2
MAX_TERMS = 4


_EN_STOPWORDS = {
    "how", "did", "does", "do", "what", "when", "where", "why", "who",
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "is",
    "are", "was", "were", "tell", "me", "about", "please", "explain",
    "develop", "developed", "history",
}


def extract_terms(query: str) -> list[str]:
    """Extract up to MAX_TERMS content terms from a question string."""
    cleaned = _QUESTION_TAIL_RE.sub("", query.strip())
    parts = [part.strip() for part in _SPLIT_RE.split(cleaned)]
    terms: list[str] = []
    for part in parts:
        if part.lower() in _EN_STOPWORDS:
            continue  # English function words are not search concepts
        if len(part) >= MIN_TERM_LENGTH and part not in terms:
            terms.append(part)
        if len(terms) >= MAX_TERMS:
            break
    if not terms and cleaned:
        terms = [cleaned]
    return terms


def assess_ocr_quality(text: str | None) -> dict:
    """Screen OCR text for basic usability.

    Returns a dict with character counts, the ratio of suspicious
    characters, a 0..1 score and a boolean ``usable`` flag. The gate is
    intentionally conservative: very short text or text with many
    replacement/control characters is not usable as answer evidence.
    """
    if not text or not text.strip():
        return {
            "chars": 0,
            "replacement_ratio": 1.0,
            "control_ratio": 1.0,
            "score": 0.0,
            "usable": False,
            "notes": ["OCR text is empty"],
        }
    total = len(text)
    replacements = text.count(_REPLACEMENT)
    controls = sum(1 for ch in text if unicodedata.category(ch) == "Cc" and ch not in "\n\t")
    replacement_ratio = replacements / total
    control_ratio = controls / total
    score = max(0.0, 1.0 - replacement_ratio * 4 - control_ratio * 4)
    if total < 20:
        score = min(score, 0.4)
    notes: list[str] = []
    if replacement_ratio > 0.01:
        notes.append("OCR contains replacement characters; misrecognition is possible")
    if total < 20:
        notes.append("OCR text is very short")
    usable = total >= 20 and replacement_ratio <= 0.05 and control_ratio <= 0.05
    if not usable and not notes:
        notes.append("OCR quality below the evidence threshold")
    return {
        "chars": total,
        "replacement_ratio": round(replacement_ratio, 4),
        "control_ratio": round(control_ratio, 4),
        "score": round(score, 3),
        "usable": usable,
        "notes": notes,
    }


_FRONT_MATTER_RE = re.compile(r"(目次|標題紙|凡例|緒言|序文|奥付|刊行|発行者|印刷者)")
_PLATE_RE = re.compile(r"(写真|図版|口絵|挿絵|附図)")


def classify_page_kind(text: str | None) -> str:
    """Classify an OCR page for selection and reporting.

    Front matter (title page, table of contents, colophon) and
    photo plates are labelled, never excluded outright: a title
    page can be exactly what a bibliographic question needs. The
    label only orders selection and keeps heading-only pages out
    of document-level coverage unions.
    """
    body = (text or "").strip()
    if not body:
        return "empty"
    compact = re.sub(r"\s+", "", body)
    digits = sum(ch.isdigit() for ch in compact)
    if len(compact) >= 200 and digits / len(compact) > 0.25:
        return "table"
    # OCR-damaged pages (Phase 7-D): replacement glyphs throughout,
    # or text shattered into single characters by column noise.
    if len(compact) >= 200:
        glyphs = sum(compact.count(g) for g in ("〓", "□", "�"))
        if glyphs / len(compact) > 0.01:
            return "damaged"
    tokens = [t for t in re.split(r"\s+", body) if t]
    if len(body) >= 300 and tokens and compact.count("。") <= 2:
        single = sum(1 for t in tokens if len(t) == 1)
        if single / len(tokens) > 0.5:
            return "damaged"
    # Colophon (奥付): a tight cluster of publication statements.
    colophon_hits = sum(k in compact for k in ("発行", "印刷", "定価", "発行者", "印刷者", "発行所"))
    if colophon_hits >= 3 and len(compact) < 900:
        return "colophon"
    # Index pages and unsegmented listings (Phase 7-D): almost no
    # sentence breaks over a long page, or an explicit 索引 marker.
    # The Phase 6 q31/h03 pages are this shape - names and headings
    # without a single asserting sentence.
    if "索引" in compact and len(compact) < 2000:
        return "index"
    if len(compact) >= 600 and compact.count("。") / len(compact) < 0.004:
        return "index"
    # Administrative lists (Phase 7-D): dense official-unit tokens
    # (lines, bureaus, stations) or staffing/enumeration rules with
    # almost no prose - they name and count, they do not narrate.
    unit_tokens = sum(compact.count(k) for k in ("線", "局", "署", "課", "駅"))
    enumerations_pre = len(re.findall(r"[一二三四五六七八九十]+、", compact))
    if compact.count("。") <= 3 and (unit_tokens >= 12 or (
        ("定員" in compact or "職員" in compact or "一覧" in compact) and enumerations_pre >= 3
    )):
        return "admin_list"
    # A contents listing can run long: several chapter/section
    # headings with almost no full sentences is enumerative
    # front matter at any length.
    headings = len(re.findall(r"第[一二三四五六七八九十百]+[章節編]", compact))
    enumerations = len(re.findall(r"[一二三四五六七八九十]+、", compact))
    if headings >= 2 and compact.count("。") <= 2:
        return "front_matter"
    if headings >= 1 and enumerations >= 4 and compact.count("。") <= 2:
        return "front_matter"
    if len(compact) < 300 and _FRONT_MATTER_RE.search(compact):
        return "front_matter"
    if len(compact) < 200 and _PLATE_RE.search(compact):
        return "photo_plate"
    # Title page (標題紙): very short, no sentence at all - a title,
    # an author, a publisher and nothing else.
    if len(compact) < 160 and compact.count("。") == 0:
        return "title_page"
    return "body"
