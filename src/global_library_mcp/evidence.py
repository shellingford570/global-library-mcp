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


def extract_terms(query: str) -> list[str]:
    """Extract up to MAX_TERMS content terms from a question string."""
    cleaned = _QUESTION_TAIL_RE.sub("", query.strip())
    parts = [part.strip() for part in _SPLIT_RE.split(cleaned)]
    terms: list[str] = []
    for part in parts:
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
