"""ResearchRanker (b10 Stage 3, brief sections 20-22).

Independent re-ranking component for discovery candidates. It
fuses, with weights fixed a priori (never tuned per case):

- strict bibliographic signals from the b6 discovery scorer
  (original/translated title match, author match, concept match,
  era, language, material type) — `ranking.score_item`;
- lexical TF-IDF relevance over title/author/subjects
  (`lexical.LexicalScorer`);
- optional semantic scores supplied by a caller (a local model
  backend); absent scores change nothing.

Tier rule (brief section 20): a record with an exact
original/translated-title or full-query title match forms the
top tier and can never be pushed below non-matching records by
lexical/semantic similarity or by OCR availability. OCR
availability is reported as a separate usability subscore and
contributes no points here (the b6 scorer's +0.5 auxiliary bonus
is removed in this component for exactly that reason).

Every ranked item carries the reasons for its position, using
only signals that actually fired (section 22). Ranking is a
discovery aid: it never feeds evidence admission (section 46).
"""
from __future__ import annotations

from typing import Any

from . import ranking as _ranking
from .lexical import LexicalScorer, item_text

LEXICAL_WEIGHT = 4.0
SEMANTIC_WEIGHT = 4.0
_STRICT_MARKERS = ("title matches", "title contains the full query",
                   "record belongs to")


class ResearchRanker:
    def __init__(self, *, lexical_weight: float = LEXICAL_WEIGHT,
                 semantic_weight: float = SEMANTIC_WEIGHT):
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight

    def rank(self, analysis: Any, items: list[Any],
             query_hits: dict[tuple[str, str], int],
             *, semantic_scores: dict[tuple[str, str], float] | None = None,
             ) -> list[Any]:
        if not items:
            return []
        query_text = getattr(analysis, "raw", "") or ""
        concept_labels: list[str] = []
        for concept in getattr(analysis, "concepts", []) or []:
            for lang in ("ja", "en", "de", "fr", "fi", "sv", "nl"):
                concept_labels.extend((concept.get("labels") or {}).get(lang, []))
        scorer = LexicalScorer([item_text(it) for it in items])
        lex = scorer.score(" ".join([query_text, *concept_labels]))
        scored: list[tuple[float, int, Any]] = []
        for idx, item in enumerate(items):
            base, reasons = _ranking.score_item(analysis, item, query_hits)
            # Remove the OCR auxiliary bonus from the base: in
            # this component OCR is usability, not relevance.
            if getattr(item, "ocr", None):
                base -= 0.5
                reasons = [r for r in reasons
                           if not r.startswith("OCR available")]
            strict = any(marker in reason for reason in reasons
                         for marker in _STRICT_MARKERS)
            total = base + self.lexical_weight * lex[idx]
            if lex[idx] >= 0.25:
                reasons = [*reasons,
                           f"lexical relevance {lex[idx]:.2f} (TF-IDF, local)"]
            key = (getattr(item, "library_id", ""),
                   getattr(item, "record_id", ""))
            sem = (semantic_scores or {}).get(key)
            if sem is not None:
                total += self.semantic_weight * sem
                if sem >= 0.25:
                    reasons = [*reasons,
                               f"semantic relevance {sem:.2f} (local model)"]
            item._research_score = round(total, 3)
            item._research_reasons = reasons
            item._research_subscores = {
                "strict_signals": round(base, 3),
                "lexical": round(float(lex[idx]), 3),
                "semantic": (round(float(sem), 3) if sem is not None else None),
                "strict_title_tier": strict,
                "ocr_usability": bool(getattr(item, "ocr", None)),
            }
            scored.append(((1 if strict else 0), total, idx, item))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [t[3] for t in scored]
