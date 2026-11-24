"""Claim-level grounding checks.

An answer-level citation is not enough: each important claim in an
answer should be tied to the pages that support it. This module gives
claims a support status using a deliberately simple, mechanical
screening (lexical overlap between the claim text and the cited OCR
text, plus explicit date-token checks).

Statuses:
- supported:   the cited OCR text lexically covers the claim.
- unsupported: no citation, or the cited text does not cover the claim.
- uncertain:   partial coverage, or an unverified date token appears.
- conflicting: only when a provider explicitly flags a conflict
               between cited pages; the mechanical checker never
               invents this status.
- not_checked: the cited evidence text was unavailable to the checker.

This is screening, not proof. A "supported" claim can still be a
misreading of the page; the original image remains the ground truth
and is linked from every evidence record.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

SUPPORTED_THRESHOLD = 0.5
UNCERTAIN_THRESHOLD = 0.25

_PUNCT_RE = re.compile(r"[\s　、。・，,.？?！!「」『』（）()【】\[\]\"'“”‘’|/\\-]+")
_DATE_TOKEN_RE = re.compile(r"(明治|大正|昭和|平成|慶応|文久|元治|安政|嘉永|弘化|天保|文化|文政|享和|寛政|天明|明和|宝暦|享保|正徳|宝永|元禄|延宝|寛文|明暦|承応|慶安|寛永|元和|慶長|文禄|天正|元亀|永禄|弘治|天文|享禄|大永|永正|明応|延徳|長享|文明|応仁|寛正|長禄|康正|享徳|宝徳|文安|嘉吉|永享|正長|応永|明徳|康応|嘉慶|至徳|永徳|康暦|永和|応安|貞治|康安|延文|文和|建武|元弘|元徳|嘉暦|正中|元亨|元応|文保|正和|応長|徳治|嘉元|乾元|嘉禎|仁治|延応|暦仁|嘉禎|貞永|天福|寛喜|安貞|嘉禄|元仁|貞応|承久|建保|建暦|承元|元久|建仁|正治|建久|文治|元暦|寿永|養和|治承|安元|承安|嘉応|仁安|永万|長寛|応保|永暦|久寿|仁平|久安|天養|康治|永治|保延|長承|天承|大治|保安|元永|永久|天仁|嘉承|長治|康和|承徳|永長|嘉保|寛治|応徳|永保|承暦|承保|嘉承|治暦|康平|天喜|永承|寛徳|長久|長暦|長元|万寿|治安|寛仁|長和|寛弘|長保|長徳|長暦|正暦|永祚|永延|寛和|永観|天元|貞元|天延|天禄|安和|康保|応和|天徳|天暦|村上|朱雀|醍醐|昌泰|延喜|寛平|仁和|元慶|貞観|天安|斉衡|嘉祥|承和|天長|弘仁|大同|延暦|宝亀|神護景雲|天平神護|天平宝字|天平勝宝|天平|聖武|養老|霊亀|和銅|慶雲|大宝|朱鳥|白雉|大化)\s?[一二三四五六七八九十百\d]+年|\d{3,4}年")
_YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")


def _bigrams(text: str) -> set[str]:
    cleaned = _PUNCT_RE.sub("", text or "")
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)} if len(cleaned) >= 2 else set()


def _date_tokens(text: str) -> set[str]:
    tokens = {m.group(0).replace(" ", "") for m in _DATE_TOKEN_RE.finditer(text or "")}
    tokens |= {m.group(0) for m in _YEAR_RE.finditer(text or "")}
    return tokens


def _passage_index(evidence_by_key: dict[str, dict[str, Any]]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for item in evidence_by_key.values():
        for passage in item.get("passages") or []:
            if passage.get("passage_id"):
                index[passage["passage_id"]] = (passage, item)
    return index


def verify_claim(claim: dict[str, Any], evidence_by_key: dict[str, dict[str, Any]],
                 analysis: Any = None) -> dict[str, Any]:
    """Screen one claim against the passages it actually cites.

    Phase 10-B: verification runs against the cited passages,
    not the whole page OCR. A claim that names passage IDs is
    checked against those passages only, and the result records
    exactly which passage, excerpt and character span grounded
    the verdict. A claim with citations but no passage IDs is
    checked against the cited pages' passages (binding marked
    "inferred"); a page with no passages falls back to page OCR
    and can reach at most "uncertain", because words scattered
    across a whole page do not establish support.
    """
    text = claim.get("text") or ""
    keys = claim.get("citations") or []
    result = dict(claim)
    if claim.get("conflict"):
        result.update({"support": "conflicting", "support_detail": "provider flagged conflicting sources"})
        return result
    if not keys and not claim.get("evidence_passage_ids"):
        result.update({"support": "unsupported", "support_detail": "claim has no citation"})
        return result
    cited = [evidence_by_key[key] for key in keys if key in evidence_by_key]
    passage_index = _passage_index(evidence_by_key)
    claimed_ids = [p for p in claim.get("evidence_passage_ids") or [] if isinstance(p, str)]
    resolved = [passage_index[p] for p in claimed_ids if p in passage_index]
    verified_against: list[dict[str, Any]] = []
    if claimed_ids and not resolved:
        result.update({"support": "unsupported",
                       "support_detail": "claim cites passage_id(s) not present in the supplied evidence"})
        return result
    if resolved:
        scope = "passage"
        binding = "explicit"
        ocr_text = "\n".join(p.get("text") or "" for p, _ in resolved)
        cited = list({id(item): item for _, item in resolved}.values())
        for passage, item in resolved:
            verified_against.append({
                "passage_id": passage["passage_id"],
                "citation_key": item.get("citation_key"),
                "excerpt": (passage.get("text") or "")[:200],
                "char_start": passage.get("char_start"),
                "char_end": passage.get("char_end"),
            })
    elif cited:
        scoped = [(p, item) for item in cited for p in (item.get("passages") or [])]
        if scoped:
            # Inferred binding: the claim is grounded in the ONE
            # passage of the cited pages that covers it best -
            # not in the union of every passage, and never in
            # words scattered across the whole page.
            scope = "passage"
            binding = "inferred"
            grams = _bigrams(text)
            def _coverage(pair: tuple[dict[str, Any], dict[str, Any]]) -> float:
                pg = _bigrams(pair[0].get("text") or "")
                return len(grams & pg) / len(grams) if grams else 0.0
            passage, item = max(scoped, key=_coverage)
            ocr_text = passage.get("text") or ""
            verified_against.append({
                "passage_id": passage["passage_id"],
                "citation_key": item.get("citation_key"),
                "excerpt": (passage.get("text") or "")[:200],
                "char_start": passage.get("char_start"),
                "char_end": passage.get("char_end"),
            })
        else:
            scope = "page"
            binding = "none"
            ocr_text = "\n".join(item.get("ocr_text") or item.get("text") or "" for item in cited)
    else:
        result.update({"support": "unsupported", "support_detail": "citations do not resolve to supplied evidence"})
        return result
    result["verification_scope"] = scope
    result["passage_binding"] = binding
    if verified_against:
        result["verified_against"] = verified_against
    if not ocr_text.strip():
        result.update({"support": "not_checked", "support_detail": "cited evidence text unavailable to the checker"})
        return result
    claim_grams = _bigrams(text)
    if not claim_grams:
        result.update({"support": "not_checked", "support_detail": "claim text too short to screen"})
        return result
    overlap = len(claim_grams & _bigrams(ocr_text)) / len(claim_grams)
    missing_dates = {tok for tok in _date_tokens(text) if tok not in ocr_text}
    detail = f"lexical overlap {overlap:.2f} over {len(cited)} cited page(s), scope={scope}"
    if scope == "page":
        detail += "; no passage available - page-level screening cannot establish support"
    if missing_dates:
        detail += f"; date token(s) not found in cited OCR: {', '.join(sorted(missing_dates))}"
        status = "uncertain" if overlap >= UNCERTAIN_THRESHOLD else "unsupported"
    elif overlap >= SUPPORTED_THRESHOLD:
        status = "supported"
    elif overlap >= UNCERTAIN_THRESHOLD:
        status = "uncertain"
    else:
        status = "unsupported"
    # Material-condition check: a concrete quantity stated in the claim
    # (a count, a population, a capacity) must literally appear in the
    # cited OCR. Lexical similarity alone never promotes such a claim
    # to supported. Four-digit years are exempt here because era-year
    # conversion (明治四十三年 = 1910) is legitimate; years are handled
    # by the date-token check above instead. Quantities are compared
    # as values across notations (23 == 二十三 == ２３).
    from global_library_mcp.numeric import numeric_values, quantity_binding

    def _is_year(value: float) -> bool:
        return value == int(value) and 1000 <= value <= 2099

    claim_numbers = {v for v in numeric_values(text) if not _is_year(v)}
    ocr_numbers = {v for v in numeric_values(ocr_text) if not _is_year(v)}
    missing_numbers = claim_numbers - ocr_numbers
    if missing_numbers:
        detail += f"; numeric value(s) not found in cited OCR: {', '.join(str(int(v) if v == int(v) else v) for v in sorted(missing_numbers))}"
        status = "unsupported"
    # Numeric-demand binding (Phase 7-C): when the question asks for
    # a quantity, presence is not enough - the value must occur
    # bound to the asked target in a cited page. A page full of
    # staff counts does not answer how many waterfalls there are
    # (Phase 6 q40). Values occurring only on table pages stay
    # unverified: row/column attachment needs the original image.
    def _field(obj: Any, name: str) -> Any:
        # The pipeline hands over the analysis either as the
        # QuestionAnalysis object or as its serialised dict.
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    numeric_intent = bool(
        analysis is not None
        and (_field(analysis, "intent") == "numeric"
             or any(r.get("type") == "numeric" for r in _field(analysis, "requirements") or []))
    )
    if numeric_intent and claim_numbers and not missing_numbers:
        from global_library_mcp.numeric import target_terms

        targets = target_terms(analysis)
        bindings: dict[str, Any] = {}
        unbound: list[float] = []
        table_only: list[float] = []
        for value in sorted(claim_numbers):
            total_occurrences = 0
            total_bound = 0
            non_table_occurrences = 0
            for item in cited:
                page_text = item.get("ocr_text") or item.get("text") or ""
                binding = quantity_binding(page_text, value, targets, page_kind=item.get("page_kind"))
                total_occurrences += binding["occurrences"]
                total_bound += binding["bound"]
                if not binding["on_table_page"]:
                    non_table_occurrences += binding["occurrences"]
            key = str(int(value) if value == int(value) else value)
            bindings[key] = {"occurrences": total_occurrences, "bound": total_bound}
            if total_bound == 0 and non_table_occurrences == 0 and total_occurrences > 0:
                table_only.append(value)
            elif total_bound == 0:
                unbound.append(value)
        if unbound:
            detail += ("; numeric value(s) present but not bound to the asked target: "
                       + ", ".join(str(int(v) if v == int(v) else v) for v in unbound))
            status = "unsupported"
        elif table_only:
            detail += ("; numeric value(s) found only in table layout - attachment unverified, "
                       "original image confirmation required: "
                       + ", ".join(str(int(v) if v == int(v) else v) for v in table_only))
            if status == "supported":
                status = "uncertain"
        result["numeric"] = bindings
    if scope == "page" and status == "supported":
        # Brief 10-B 4.2: words scattered across a whole page do
        # not establish support. Without a passage the strongest
        # honest verdict is uncertain (which never publishes).
        status = "uncertain"
    result.update({"support": status, "support_detail": detail, "overlap": round(overlap, 3)})
    return result


def verify_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]],
                  analysis: Any = None) -> list[dict[str, Any]]:
    by_key = {item.get("citation_key"): item for item in evidence if item.get("citation_key")}
    return [verify_claim(claim, by_key, analysis=analysis) for claim in claims]
