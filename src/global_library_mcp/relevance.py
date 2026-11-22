"""Relevance gate: does this page actually speak to the question?

Separate from the OCR quality gate on purpose: a page can be a
perfect OCR transcription and still say nothing about what was
asked. Phase 3's evaluation showed the old pipeline accepting any
page that contained one generic extracted term (通信, 歴史, 原理),
which produced grounded-looking answers to unanswerable questions.

The gate is a mechanical screening over the question analysis
(question.py): core-concept presence under orthographic folding and
curated synonyms, era/region signals, and requirement checks
(e.g. a numeric question needs numbers near the concept). It is
NOT semantic verification: `relevant` means the page passed this
screening, not that a human would judge it sufficient.
"""
from __future__ import annotations

import re
from typing import Any

from global_library_mcp.question import ERAS, QuestionAnalysis, find_concept, normalize_text

_YEAR_RE = re.compile(r"(1[4-9]\d{2}|20\d{2})")
_DIGITS_RE = re.compile(r"\d+")
_KANJI_NUM_RE = re.compile(r"[一二三四五六七八九十百千万]+")


def concept_families(core_concepts: list[str]) -> list[str]:
    """Collapse suffix-extension aliases (水力発電技術 -> 水力発電)."""
    families: list[str] = []
    for concept in core_concepts:
        if any(other != concept and concept.startswith(other) for other in core_concepts):
            continue
        if concept not in families:
            families.append(concept)
    return families


def _era_signal(text_normalised: str, era: dict[str, Any]) -> tuple[bool, str | None]:
    name = era.get("era")
    if name and normalize_text(name) in text_normalised:
        return True, f"時代名「{name}」が本文に現れる"
    for match in _YEAR_RE.finditer(text_normalised):
        year = int(match.group(1))
        if era["start"] - 20 <= year <= era["end"] + 30:
            return True, f"対象時代の年（{year}年）が本文に現れる"
    return False, None


def assess_relevance(
    analysis: QuestionAnalysis,
    ocr_text: str,
    *,
    publication_year: int | None = None,
) -> dict[str, Any]:
    """Screen one OCR page against the analysed question."""
    text = normalize_text(ocr_text or "")
    reasons: list[str] = []
    families = concept_families(analysis.core_concepts)
    matched: list[str] = []
    missing: list[str] = []
    for family in families:
        if find_concept(text, family):
            matched.append(family)
        else:
            missing.append(family)
    generic_matched = [g for g in analysis.generic_terms if normalize_text(g) in text]

    if not families:
        return {
            "status": "uncertain", "score": 0.3, "matched_concepts": [], "missing_concepts": [],
            "reasons": ["質問から中心概念を抽出できなかったため、関連性を自動判定できない"],
        }

    fraction = len(matched) / len(families)
    score = 0.7 * fraction
    if matched:
        reasons.append(f"中心概念を確認: {'、'.join(matched)}")
    if missing:
        reasons.append(f"中心概念が本文にない: {'、'.join(missing)}")
    if not matched and generic_matched:
        reasons.append(f"一致したのは周辺語のみ: {'、'.join(generic_matched)}")

    numeric_unmet = False
    for requirement in analysis.requirements:
        rtype = requirement.get("type")
        if rtype == "era":
            found, note = _era_signal(text, requirement)
            if found:
                score += 0.15
                reasons.append(note or "時代の手がかりを確認")
            else:
                other_eras = [name for name in ERAS if name != requirement.get("label")
                              and text.count(normalize_text(name)) >= 3]
                if other_eras:
                    score -= 0.1
                    reasons.append(f"対象時代（{requirement.get('label')}）の言及がなく、別の時代（{'、'.join(other_eras)}）の記述が中心")
                else:
                    reasons.append(f"対象時代（{requirement.get('label')}）への言及は本文で確認できない")
        elif rtype == "region":
            region = requirement["region"]
            if normalize_text(region) in text:
                score += 0.1
                reasons.append(f"地域「{region}」の言及を確認")
            else:
                reasons.append(f"地域「{region}」への言及は本文で確認できない")
        elif rtype == "numeric":
            near = False
            for family in matched:
                for variant in [family]:
                    idx = text.find(normalize_text(variant))
                    if idx >= 0:
                        window = text[max(0, idx - 240): idx + 240]
                        if _DIGITS_RE.search(window) or _KANJI_NUM_RE.search(window):
                            near = True
            if near:
                score += 0.05
                reasons.append("中心概念の近傍に数値表現を確認")
            elif _DIGITS_RE.search(text):
                reasons.append("数値はあるが、中心概念との結びつきは確認できない")
                numeric_unmet = True
            else:
                reasons.append("質問が求める数値表現が本文にない")
                numeric_unmet = True

    if publication_year is not None and analysis.era:
        if analysis.era["start"] <= publication_year <= analysis.era["end"] + 40:
            reasons.append(f"出版年（{publication_year}年）は対象時代またはその近傍")
        else:
            reasons.append(f"出版年（{publication_year}年）は対象時代から離れているが、回顧的記述の可能性は出版年だけでは否定できない")

    score = max(0.0, min(1.0, score))
    if fraction == 0:
        status = "irrelevant"
        score = min(score, 0.2)
    elif numeric_unmet:
        status = "partially_relevant" if fraction >= 0.5 else "irrelevant"
    elif fraction == 1 and score >= 0.6:
        status = "relevant"
    elif fraction >= 0.5:
        status = "partially_relevant" if score < 0.75 else "relevant"
    else:
        status = "partially_relevant" if score >= 0.35 else "irrelevant"
    return {
        "status": status, "score": round(score, 3),
        "matched_concepts": matched, "missing_concepts": missing,
        "reasons": reasons,
    }
