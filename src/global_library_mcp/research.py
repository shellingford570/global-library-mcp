"""Structured research intelligence (b10 Stage 4, sections 23-31).

Rule-based structuring and comparison layers that sit BESIDE the
frozen evidence pipeline:

- `ResearchQuestion` (section 23): a structured view of a
  research question, derived from the existing question/discovery
  analyses. It adds intent classification and explicit ambiguity
  records; it never loosens any admission condition.
- `ResearchClaim` (section 24): a structured claim parsed from a
  statement with era/quantity/entity extraction. Structuring is
  not truth judgement; fields the text does not contain stay
  empty - nothing is filled in from world knowledge.
- `assess_claim_evidence` (section 25): maps ADMITTED evidence
  candidates to a structured claim by explicit signals (entity,
  year, place, quantity+unit, negation). Statuses are
  candidate-level by design; the final support verdict remains
  the frozen claim verification's alone. Unadmitted candidates
  are reported `not_checked` with the reason, never assessed.
- `compare_facts` (sections 28-29): rule-based cross-source
  comparison of extracted facts - consistent / differing unit,
  time or scope / contradiction CANDIDATE (never confirmed) -
  with document counts kept separate from independent-source
  counts (same work in several libraries is one source).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import lexicon
from .discovery import analyze_discovery_query
from .numeric import extract_quantities
from .question import ERAS, analyze_question, normalize_text
from .temporal import sentence_years

INTENTS = (
    "document_discovery", "historical_fact_check", "work_search",
    "edition_comparison", "concept_history", "chronology",
    "numeric_check", "multi_source_comparison", "citation_check",
    "general",
)

CLAIM_STATUSES = (
    "evidence_reference_only", "supported_candidate", "partially_supported",
    "conflicting_candidate", "contextual_only",
    "insufficient_evidence", "not_checked",
)

# Final review (sections 13-14): a candidate is assessed ONLY when
# it carries a verifiable reference issued by the frozen evidence
# pipeline itself. A bare ``admitted: True`` in an arbitrary dict
# is caller-asserted and is NEVER trusted.
TRUSTED_ADMISSION_SOURCE = "glm_evidence_pipeline"


def build_trusted_candidate(*, library_id: str, record_id: str,
                            page_id: str, text: str,
                            citation_id: str | None = None,
                            excerpt_start: int | None = None,
                            excerpt_end: int | None = None,
                            years: list[int] | None = None,
                            place: str | None = None) -> dict[str, Any]:
    """Construct an assessable candidate from pipeline-admitted
    evidence, with the full reference chain and excerpt hash."""
    import hashlib as _hl
    return {
        "admitted": True,
        "admission_source": TRUSTED_ADMISSION_SOURCE,
        "evidence_ref": {
            "library_id": library_id, "record_id": record_id,
            "page_id": page_id, "citation_id": citation_id,
            "excerpt_start": excerpt_start, "excerpt_end": excerpt_end,
            "excerpt_hash": _hl.sha256((text or "").encode("utf-8")).hexdigest(),
            "admission_state": "admitted",
            "document_identity_state": "upstream_confirmed",
            "page_identity_state": "verified_mapping",
            "source": "original_page_ocr",
        },
        "document_id": f"{library_id}:{record_id}",
        "library_id": library_id, "record_id": record_id,
        "page_id": page_id, "text": text,
        "years": years, "place": place,
    }


def _trusted_ref(cand: dict[str, Any]) -> tuple[bool, str]:
    if not cand.get("admitted"):
        return False, "candidate did not pass the evidence admission gates"
    if cand.get("admission_source") != TRUSTED_ADMISSION_SOURCE:
        return False, ("admission is caller-asserted, not issued by the "
                       "evidence pipeline; refusing to assess")
    ref = cand.get("evidence_ref") or {}
    for field_name in ("library_id", "record_id", "page_id", "excerpt_hash"):
        if not ref.get(field_name):
            return False, f"evidence reference incomplete: {field_name} missing"
    if ref.get("admission_state") != "admitted":
        return False, "evidence reference does not record admitted state"
    return True, ""


# ---------------------------------------------------------------------------
# ResearchQuestion (section 23)
# ---------------------------------------------------------------------------

@dataclass
class ResearchQuestion:
    original_question: str
    detected_language: str = ""
    subject: str = ""
    research_intent: str = "general"
    entities: dict[str, list[str]] = field(default_factory=dict)
    time_range: dict[str, Any] | None = None
    place: str = ""
    requested_document_types: list[str] = field(default_factory=list)
    author_constraints: list[str] = field(default_factory=list)
    work_constraints: list[str] = field(default_factory=list)
    numerical_constraints: list[dict[str, Any]] = field(default_factory=list)
    expected_evidence_type: str = ""
    unresolved_ambiguities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()
                if v not in (None, "", [], {})}


_INTENT_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("edition_comparison", ("版", "edition", "第2版", "初版", "改訂")),
    ("citation_check", ("引用", "出典", "citation", "本当に書")),
    ("numeric_check", ("何人", "何台", "何キロ", "何メートル", "数値", "how many", "how much")),
    ("chronology", ("いつから", "何年", "年代", "変遷", "when did")),
    ("multi_source_comparison", ("比較", "違い", "compare", "comparison")),
    ("concept_history", ("概念", "用語", "意味の変化", "concept")),
    ("work_search", ("著作", "著書", "の作品", "bibliography")),
    ("historical_fact_check", ("本当", "事実", "したか", "あったか", "did ", "was there")),
]


def structure_question(question: str) -> ResearchQuestion:
    qa = analyze_question(question)
    da = analyze_discovery_query(question)
    rq = ResearchQuestion(original_question=question)
    rq.detected_language = (da.query_language or {}).get("language", "")
    rq.subject = ", ".join(c.get("concept_id", "").replace("concept:", "")
                           for c in da.concepts)
    lowered = question.lower()
    for intent, cues in _INTENT_CUES:
        if any(cue in lowered for cue in cues):
            rq.research_intent = intent
            break
    else:
        rq.research_intent = ("document_discovery"
                              if da.concepts or da.authors or da.works
                              else "general")
    rq.entities = {
        "authors": [a["author_id"] for a in da.authors],
        "works": [w["work_id"] for w in da.works],
        "concepts": [c["concept_id"] for c in da.concepts],
    }
    if da.era:
        rq.time_range = {"era": da.era.get("era") or da.era.get("label"),
                         "start": da.era.get("start"), "end": da.era.get("end")}
    for author in da.authors:
        forms = [n for group in (author.get("names") or {}).values() for n in group]
        if forms:
            rq.author_constraints.append(max(forms, key=len))
    for work in da.works:
        rq.work_constraints.append(work["original_title"])
    rq.numerical_constraints = extract_quantities(question)
    if any(w in question for w in ("新聞", "newspaper")):
        rq.requested_document_types.append("newspaper")
    if any(w in question for w in ("統計", "statistics", "年鑑")):
        rq.requested_document_types.append("statistics")
    rq.expected_evidence_type = (
        "primary_source_text" if rq.research_intent in
        ("historical_fact_check", "numeric_check", "citation_check")
        else "bibliographic_discovery")
    for author in getattr(da, "ambiguous_authors", []) or []:
        rq.unresolved_ambiguities.append(
            f"author surname {author.get('surname')} matches multiple persons")
    if da.concepts and not (da.authors or da.works) and rq.time_range is None \
            and rq.research_intent == "general":
        rq.unresolved_ambiguities.append(
            "broad concept question without era or author constraints")
    return rq


# ---------------------------------------------------------------------------
# ResearchClaim (section 24)
# ---------------------------------------------------------------------------

@dataclass
class ResearchClaim:
    claim_id: str
    original_statement: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    time: dict[str, Any] | None = None
    place: str = ""
    quantity: dict[str, Any] | None = None
    named_entities: list[str] = field(default_factory=list)
    qualifiers: list[str] = field(default_factory=list)
    source_type_required: str = "primary_or_contemporary"
    evidence_status: str = "not_checked"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()
                if v not in (None, "", [], {})}


_PLACES = ("日本", "ドイツ", "フランス", "イギリス", "英国", "アメリカ",
           "米国", "中国", "フィンランド", "スウェーデン", "オランダ",
           "東京", "大阪", "京都", "横浜", "神戸", "長崎")
_QUALIFIERS = ("初めて", "最初", "最大", "唯一", "約", "およそ", "推定",
               "とされる", "と見られる")


def structure_claim(statement: str, claim_id: str = "") -> ResearchClaim:
    claim = ResearchClaim(claim_id=claim_id or "claim",
                          original_statement=statement)
    text_n = normalize_text(statement)
    # Time: era names and explicit years (existing temporal layer).
    years = sentence_years(text_n)
    for era_name, era_range in ERAS.items():
        if era_name in statement:
            claim.time = {"era": era_name, "start": era_range[0],
                          "end": era_range[1],
                          "years_mentioned": years}
            break
    if claim.time is None and years:
        claim.time = {"years_mentioned": years,
                      "start": min(years), "end": max(years)}
    # Quantity: first bound quantity, kept with its original unit.
    quantities = extract_quantities(statement)
    if quantities:
        claim.quantity = quantities[0]
    # Place: explicit place names only.
    for place in _PLACES:
        if place in statement:
            claim.place = place
            break
    # Named entities: lexicon authors/works/concepts present in text.
    entities: list[str] = []
    for entry in lexicon.match_entries(statement, "authors"):
        entities.append(entry["author_id"])
    for entry in lexicon.match_entries(statement, "works"):
        entities.append(entry["work_id"])
    claim.named_entities = entities
    concepts = lexicon.match_entries(statement, "concepts")
    if concepts:
        claim.subject = concepts[0]["concept_id"]
    claim.qualifiers = [q for q in _QUALIFIERS if q in statement]
    # Predicate/object stay textual: the span after the subject
    # concept's surface, uninterpreted.
    return claim


# ---------------------------------------------------------------------------
# Claim <-> evidence mapping (section 25)
# ---------------------------------------------------------------------------

_NEGATION_MARKERS = ("なかった", "なかつた", "存在しない", "存在せず",
                     "行われなかった", "建設されなかった", "未だ",
                     "not built", "not constructed", "never", "no such")


def assess_claim_evidence(claim: ResearchClaim,
                          candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map gate-admitted evidence candidates to the claim.

    Each candidate must carry ``admitted: True`` (it passed the
    frozen evidence gates upstream); anything else is reported
    not_checked and never assessed. Candidate fields used:
    text, year (event/publication year stated by the caller),
    place, quantities (numeric.extract_quantities shape),
    document_id, page_id.
    """
    out: list[dict[str, Any]] = []
    for cand in candidates:
        row: dict[str, Any] = {
            "claim_id": claim.claim_id,
            "document_id": cand.get("document_id"),
            "page_id": cand.get("page_id"),
            "evidence_ref": cand.get("evidence_ref"),
            "status": "not_checked", "signals": []}
        _ok, _why = _trusted_ref(cand)
        if not _ok:
            row["reason"] = _why
            out.append(row)
            continue
        text = cand.get("text") or ""
        text_n = normalize_text(text)
        signals: list[str] = []
        score = 0
        # Entity / subject agreement.
        concept_hit = False
        if claim.subject:
            concept_id = claim.subject
            for entry in lexicon.load_lexicon()["concepts"]:
                if entry["concept_id"] == concept_id:
                    labels = [v for group in (entry.get("labels") or {}).values()
                              for v in group]
                    concept_hit = any(normalize_text(v) in text_n for v in labels if v)
                    break
        entity_hit = any(
            eid.split(":", 1)[-1] in text_n or eid in text
            for eid in claim.named_entities)
        if concept_hit or entity_hit:
            signals.append("subject_or_entity_match")
            score += 2
        # Time agreement: candidate years inside the claim's range.
        cand_years = cand.get("years") or sentence_years(text_n)
        year_conflict = False
        if claim.time and cand_years:
            specific = claim.time.get("years_mentioned") or []
            if specific and not (set(specific) & set(cand_years)):
                # A different year alone is not a conflict: the
                # passage may describe a different event (a later
                # line opening, another edition). It is a conflict
                # candidate only when the passage makes the SAME
                # kind of assertion about the same subject - a
                # shared event predicate and no edition shift.
                event_cues = ("完成", "開業", "刊行", "建設", "開始",
                              "創業", "運転", "completed", "opened",
                              "published", "built")
                claim_cues = [c for c in event_cues if c in claim.original_statement]
                same_event = (not claim_cues) or any(c in text for c in claim_cues)
                edition_shift = bool(re.search(r"第\d+版|\d+(st|nd|rd|th) edition", text))
                if same_event and not edition_shift:
                    signals.append("year_conflict")
                    year_conflict = True
                else:
                    signals.append("different_event_or_edition_year")
            start, end = claim.time.get("start"), claim.time.get("end")
            if start is not None and end is not None:
                if any(start <= y <= end for y in cand_years):
                    signals.append("time_match")
                    score += 2
                else:
                    signals.append("time_outside_claim_range")
        # Place agreement.
        if claim.place:
            if claim.place in text:
                signals.append("place_match")
                score += 1
            else:
                signals.append("place_not_mentioned")
        # Quantity + unit agreement: exact value AND unit.
        if claim.quantity:
            want_v = claim.quantity.get("value")
            want_u = claim.quantity.get("unit") or claim.quantity.get("counter")
            matched = False
            for q in extract_quantities(text):
                if q.get("value") == want_v and \
                        (q.get("unit") or q.get("counter")) == want_u:
                    matched = True
                    break
            if matched:
                signals.append("quantity_and_unit_match")
                score += 2
            else:
                signals.append("quantity_not_matched")
        # A negated CLAIM contradicted by an affirmative passage
        # is equally a conflict candidate.
        claim_negated = any(m in claim.original_statement
                            for m in _NEGATION_MARKERS)
        if claim_negated and not any(m in text for m in _NEGATION_MARKERS) \
                and ("subject_or_entity_match" in signals):
            signals.append("claim_negated_passage_affirms")
            row["status"] = "conflicting_candidate"
            row["signals"] = signals
            out.append(row)
            continue
        # Negation flips the reading to a conflicting candidate.
        if any(m in text for m in _NEGATION_MARKERS):
            signals.append("negation_present")
            row["status"] = "conflicting_candidate"
            row["signals"] = signals
            out.append(row)
            continue
        if year_conflict:
            row["status"] = "conflicting_candidate"
            row["signals"] = signals
            out.append(row)
            continue
        if "different_event_or_edition_year" in signals \
                and "subject_or_entity_match" in signals:
            row["status"] = "contextual_only"
            row["signals"] = signals
            out.append(row)
            continue
        if "time_outside_claim_range" in signals:
            # A passage anchored outside the claim's period (e.g.
            # a later retrospective) contextualises; it does not
            # support (section 26). It counts as context when it
            # actually discusses the claimed era or subject.
            era_name = (claim.time or {}).get("era")
            discusses = bool((era_name and era_name in text)
                             or "subject_or_entity_match" in signals)
            row["status"] = ("contextual_only" if discusses
                             else "insufficient_evidence")
            row["signals"] = signals
            out.append(row)
            continue
        # Conditional passages contextualise; they do not support.
        if any(m in text for m in ("場合", "ならば", "if ", "would ")):
            signals.append("conditional_context")
            row["status"] = "contextual_only"
            row["signals"] = signals
            out.append(row)
            continue
        _missing: list[str] = []
        if claim.place and "place_match" not in signals:
            _missing.append("place")
        if claim.quantity and "quantity_and_unit_match" not in signals:
            _missing.append("quantity_or_unit")
        if claim.time and (claim.time.get("years_mentioned")) \
                and "time_match" not in signals \
                and "subject_or_entity_match" not in signals:
            _missing.append("time")
        if "subject_or_entity_match" not in signals:
            _missing.append("subject_or_entity")
        row["unconfirmed_signals"] = _missing
        if score >= 4 and not _missing:
            row["status"] = "supported_candidate"
        elif score >= 2:
            row["status"] = "partially_supported"
        elif score >= 1:
            row["status"] = "contextual_only"
        else:
            row["status"] = "insufficient_evidence"
        row["signals"] = signals
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Cross-source fact comparison (sections 28-29)
# ---------------------------------------------------------------------------

# Unit spellings that denote the same unit across languages and
# notations (translation is not a unit difference, section 28).
_UNIT_ALIASES = {
    "馬力": "hp", "horsepower": "hp", "ps": "hp", "hp": "hp",
    "キロワット": "kw", "kw": "kw",
    "キロメートル": "km", "km": "km",
    "メートル": "m", "m": "m", "メーター": "m",
    "トン": "t", "t": "t", "ton": "t", "tons": "t",
}


def _unit_norm(unit: Any) -> str:
    if not unit:
        return ""
    key = str(unit).strip().lower()
    return _UNIT_ALIASES.get(key, key)


# Convertible unit families (SI): value in the family base unit.
_UNIT_FAMILIES: dict[str, tuple[str, float]] = {
    "w": ("power", 1.0), "kw": ("power", 1_000.0),
    "mw": ("power", 1_000_000.0), "gw": ("power", 1_000_000_000.0),
    "キロワット": ("power", 1_000.0),
    "m": ("length", 1.0), "km": ("length", 1_000.0),
    "キロメートル": ("length", 1_000.0), "メートル": ("length", 1.0),
    "kg": ("mass", 1.0), "t": ("mass", 1_000.0), "トン": ("mass", 1_000.0),
    "ton": ("mass", 1_000.0), "tons": ("mass", 1_000.0),
}


def _convert(value: float, unit: Any) -> tuple[str, float] | None:
    fam = _UNIT_FAMILIES.get(_unit_norm(unit))
    if fam is None:
        return None
    return fam[0], value * fam[1]


def compare_facts(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare extracted facts across sources (sections 15-16).

    A pair is a contradiction CANDIDATE only when subject,
    predicate, object, place, scope, time and definition all
    agree and the (unit-normalised) values still differ. Any
    identity mismatch yields differing_* / insufficient_context,
    never a contradiction. Independence is reported honestly:
    distinct documents are NOT independent sources; only facts
    carrying an explicit independence basis count as confirmed
    independent, everything else is unknown.
    """
    pairs: list[dict[str, Any]] = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a, b = facts[i], facts[j]
            pair: dict[str, Any] = {"a": a.get("document_id"),
                                    "b": b.get("document_id")}
            for field_name in ("subject", "predicate", "object"):
                if a.get(field_name) and b.get(field_name) \
                        and a.get(field_name) != b.get(field_name):
                    pair["status"] = "insufficient_context"
                    pair["reason"] = f"{field_name} differs - not the same assertion"
                    pairs.append(pair)
                    break
            else:
                if a.get("place") and b.get("place") and a.get("place") != b.get("place"):
                    pair["status"] = "differing_scope"
                    pair["reason"] = "different place"
                elif a.get("definition") and b.get("definition") \
                        and a.get("definition") != b.get("definition"):
                    pair["status"] = "differing_scope"
                elif a.get("scope") and b.get("scope") and a.get("scope") != b.get("scope"):
                    pair["status"] = "differing_scope"
                elif a.get("value") is None or b.get("value") is None:
                    if a.get("concept") and a.get("concept") == b.get("concept"):
                        pair["status"] = "consistent_candidate"
                    else:
                        pair["status"] = "insufficient_context"
                else:
                    au, bu = _unit_norm(a.get("unit")), _unit_norm(b.get("unit"))
                    ca, cb = _convert(float(a["value"]), a.get("unit")), \
                        _convert(float(b["value"]), b.get("unit"))
                    if au == bu:
                        norm_a, norm_b = float(a["value"]), float(b["value"])
                        comparable = True
                    elif ca and cb and ca[0] == cb[0]:
                        norm_a, norm_b = ca[1], cb[1]
                        comparable = True
                        pair["converted"] = {
                            "a_base": norm_a, "b_base": norm_b, "family": ca[0]}
                    else:
                        comparable = False
                    if not comparable:
                        pair["status"] = "differing_unit"
                    elif a.get("year") and b.get("year") and a.get("year") != b.get("year") \
                            and au not in ("年", "year", "years"):
                        pair["status"] = "differing_time"
                    elif norm_a != norm_b:
                        both_negated = bool(a.get("negated")) and bool(b.get("negated"))
                        if both_negated:
                            pair["status"] = "insufficient_context"
                            pair["reason"] = ("both sources state a negation; "
                                               "differing negated values are not "
                                               "a mutual contradiction")
                        else:
                            pair["status"] = "contradiction_candidate"
                    else:
                        pair["status"] = "consistent_candidate"
                pairs.append(pair)
    doc_keys = {f"{f.get('library_id')}|{f.get('record_id') or f.get('document_id')}"
                for f in facts}
    families = {f.get("work_id") or f"{f.get('library_id')}|{f.get('record_id') or f.get('document_id')}"
                for f in facts}
    libraries = {f.get("library_id") for f in facts if f.get("library_id")}
    confirmed = sum(1 for f in facts if f.get("independence_confirmed"))
    dependent = sum(1 for f in facts if f.get("dependent_on"))
    return {
        "evidence_item_count": len(facts),
        "distinct_document_count": len(doc_keys),
        "distinct_library_record_count": len(doc_keys),
        "distinct_library_count": len(libraries),
        "source_family_candidate_count": len(families),
        "known_dependent_source_count": dependent,
        "independence_unknown_count": len(facts) - confirmed - dependent,
        "independently_confirmed_source_count": confirmed,
        # Legacy keys kept as DOCUMENT counts only (never read as
        # independent corroboration):
        "document_count": len(doc_keys),
        "independent_source_count": None,
        "pairs": pairs,
        "note": ("distinct documents are not independent sources; "
                 "independence is unknown unless explicitly confirmed "
                 "with a basis"),
    }
