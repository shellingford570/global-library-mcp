"""Semantic grounding check: does the page *mean* what the question asks?

The relevance gate (relevance.py) is lexical: it knows a page
mentions the concept and the era. Phase 4's residual false answers
were all pages that mention both while actually saying the topic
did NOT exist / happen / spread in that era, or only that it was
planned. This module reads the concept-bearing sentences of a page
and classifies their stance:

- ``supports``      the page asserts the topic's occurrence /
                    diffusion in the sense the question asks about
- ``contradicts``   the page denies the question's premise
                    (did not exist yet, started later, ...)
- ``mentions_only`` the page talks about the topic (background,
                    plans, other eras) without asserting what the
                    question asks
- ``insufficient``  no sentence bears on the concept at all
- ``uncertain``     mixed or unclassifiable signals
- ``not_checked``   no checker was available; NEVER treated as
                    support by callers

The default checker is deterministic rules over stance cues
(negation / planning / occurrence / diffusion / later-onset), so
the whole pipeline stays reproducible offline. An embedding-based
checker can be plugged in through ``SemanticChecker`` and the
``GLM_SEMANTIC_EMBED_MODEL`` environment variable; when it cannot
load, the factory reports it unavailable and callers fall back to
the rule checker alone. Model output is screening evidence, not
proof of truth.

Scope honesty: the rule checker only has an opinion on
era/existence/diffusion-shaped questions (the Phase 4 failure
class). For other questions it returns ``uncertain`` and the
lexical gate's verdict stands.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from global_library_mcp.question import QuestionAnalysis, find_concept, normalize_text
from global_library_mcp.relevance import concept_families

_SENT_SPLIT = re.compile(r"[。．！？\n]+")

# Stance cues, matched on normalised text. Period orthography writes
# なかった as なかつた, so both spellings are listed.
_NEGATION_CUES = (
    "存在しなかつた", "存在しなかった", "存在しない", "存在せず",
    "まだなかつた", "まだなかった", "未だなかつた", "未だなかった",
    "行われなかつた", "行われなかった", "始まらなかつた", "始まらなかった",
    "実現しなかつた", "実現しなかった", "実用化されなかつた", "実用化されなかった",
    "普及しなかつた", "普及しなかった", "導入されなかつた", "導入されなかった",
    "建設されなかつた", "建設されなかった", "開業しなかつた", "開業しなかった",
    "完成しなかつた", "完成しなかった", "見られなかつた", "見られなかった",
    "皆無", "影も形もな",
)
_LATER_CUES = (
    "後に登場", "後になつて", "後になって", "後年", "やがて", "のちに",
    "遅れて登場", "遅れて現", "大正に入つて", "大正に入って",
    "昭和に入つて", "昭和に入って", "明治も終わり", "時代が下つて", "時代が下って",
)
_PLANNING_CUES = (
    "計画", "構想", "提案", "試み", "企画", "予定", "立案",
)
_OCCURRENCE_CUES = (
    "開業", "営業を開始", "運転を開始", "運行を開始", "放送を開始",
    "建設され", "完成し", "落成", "敷設", "創業", "設立され",
    "始まつた", "始まった", "開始され", "導入され", "実用化され",
    # Institutional vocabulary of the period: telegraph/telephone
    # offices 開局, lines 開通/架設, railways 開通, factories 操業,
    # lighting 点灯, newspapers 創刊, laws 施行/発布, companies 創立.
    "開局", "開通", "架設", "創設", "創立", "開設", "操業", "点灯",
    "創刊", "発刊", "施行", "発布", "制定",
)
_DIFFUSION_CUES = (
    "普及", "広まつた", "広まった", "一般化", "浸透", "全国各地", "家庭にまで",
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if len(s.strip()) >= 4]


def _cue_hits(sentence: str, cues: tuple[str, ...]) -> list[str]:
    return [cue for cue in cues if normalize_text(cue) in sentence]


def question_demand(analysis: QuestionAnalysis) -> str:
    """What the question asks about the topic: diffusion, occurrence,
    or general (no era-premise shape we can check semantically)."""
    raw = analysis.raw
    if "普及" in raw or "広ま" in raw:
        return "diffusion"
    if any(word in raw for word in ("建設", "開始", "導入", "開業", "存在", "行われ", "始ま", "登場")):
        return "occurrence"
    if analysis.era:
        # An era-bound topic question ("the impact of radio in the
        # Meiji era") presupposes the topic existed in that era, so
        # the premise is checkable even without an explicit verb.
        return "occurrence"
    return "general"


class SemanticChecker(Protocol):
    name: str

    def assess(self, analysis: QuestionAnalysis, ocr_text: str, publication_year: int | None = None) -> dict[str, Any]:
        ...


class RuleBasedSemanticChecker:
    """Deterministic stance screening over concept sentences."""

    name = "rules-v1"

    def assess(self, analysis: QuestionAnalysis, ocr_text: str, publication_year: int | None = None) -> dict[str, Any]:
        text = normalize_text(ocr_text or "")
        families = concept_families(analysis.core_concepts)
        demand = question_demand(analysis)
        # Discourse units: period prose states the topic once and
        # continues with zero anaphora ("the offices opened in year
        # 2, four more in year 3" - the second sentence names no
        # topic). Stance and anchors are therefore read over a
        # concept sentence plus the sentence that follows it.
        all_sentences = _sentences(text)
        units: list[tuple[str, str]] = []
        for idx, sentence in enumerate(all_sentences):
            if any(find_concept(sentence, family) for family in families):
                following = all_sentences[idx + 1] if idx + 1 < len(all_sentences) else ""
                units.append((sentence, following))
        if not units:
            return {
                "relation": "insufficient", "checker": self.name, "demand": demand,
                "reasons": ["中心概念に言及する文が本文にない"],
                "stance_sentences": {},
            }
        buckets: dict[str, list[str]] = {"negation": [], "later": [], "planning": [], "occurrence": [], "diffusion": []}
        occurrence_units: list[tuple[str, str]] = []
        diffusion_units: list[tuple[str, str]] = []
        for unit in units:
            sentence = unit[0] + unit[1]
            # Scoped bare negation: a concept-bearing unit that also
            # states something "は/がなかった" negates the premise
            # (大正時代の家庭に冷蔵庫はなかった) even when the
            # negated noun drops the concept's modifier prefix.
            bare_negation = bool(re.search(r"(は|が)(なかつた|なかった)", sentence))
            if _cue_hits(sentence, _NEGATION_CUES) or bare_negation:
                buckets["negation"].append(sentence[:120])
            if _cue_hits(sentence, _LATER_CUES):
                buckets["later"].append(sentence[:120])
            if _cue_hits(sentence, _PLANNING_CUES) and not _cue_hits(sentence, _OCCURRENCE_CUES):
                buckets["planning"].append(sentence[:120])
            if _cue_hits(sentence, _OCCURRENCE_CUES):
                buckets["occurrence"].append(sentence[:120])
                occurrence_units.append(unit)
            if _cue_hits(sentence, _DIFFUSION_CUES):
                buckets["diffusion"].append(sentence[:120])
                diffusion_units.append(unit)

        # Temporal anchoring (temporal.py): an occurrence/diffusion
        # sentence dated AFTER the asked era does not support the
        # era premise, and an onset explicitly dated after the era
        # contradicts it (the topic began later than the question
        # assumes).
        from global_library_mcp.temporal import anchor_class, onset_after_era, sentence_years

        # Onset detection reads sentences individually: in a joined
        # discourse unit, an era name in the *other* sentence (about
        # a different aspect) would mask a later onset year in the
        # onset sentence. The joined unit is added only when the
        # following sentence carries a year and no era name (the
        # zero-anaphora shape: "the service began. It was 1927.").
        onset_inputs: list[str] = []
        for first, following in units:
            onset_inputs.append(first)
            if following:
                onset_inputs.append(following)
                if sentence_years(following) and not any(
                    name in following for name in ("明治", "大正", "昭和", "平成", "江戸", "慶応")
                ):
                    onset_inputs.append(first + following)
        onset_after = onset_after_era(onset_inputs, analysis.era)
        # Retrospective sources (published after the asked era) need
        # stricter anchoring: in a 1934 history, an undated "the
        # subway was built" describes 1927, not the Meiji era it
        # mentions as background. Undated stance sentences in such
        # sources therefore do not count as era support; sentences
        # anchored to the era itself (era name or in-range year) do.
        retrospective = bool(
            analysis.era and publication_year and publication_year > analysis.era["end"]
        )

        def _counts(unit: tuple[str, str]) -> bool:
            first, following = unit
            anchor = anchor_class(first, analysis.era)
            if anchor == "none" and following and sentence_years(following):
                # Anchor inheritance across the discourse window
                # requires a year-bearing following sentence (a
                # western year or an era-year expression). A bare
                # era name there is topical seasoning in
                # retrospective prose and must not anchor a
                # different event to the era (the holdout
                # refrigerator failure).
                anchor = anchor_class(following, analysis.era)
            if anchor == "after_era":
                return False
            if retrospective and anchor == "none":
                return False
            return True

        occurrence_in = [u for u in occurrence_units if _counts(u)]
        diffusion_in = [u for u in diffusion_units if _counts(u)]

        import re as _re

        dated_event = bool(_re.search(r"(1[4-9]\d{2}|20\d{2})\s*年", analysis.raw))
        reasons: list[str] = []
        has_negation = bool(buckets["negation"])
        has_later = bool(buckets["later"])
        has_occurrence = bool(occurrence_in)
        has_diffusion = bool(diffusion_in)
        has_planning_only = bool(buckets["planning"]) and not has_occurrence and not has_diffusion

        if demand == "general":
            relation = "uncertain"
            reasons.append("時代・存在・普及を問う形の質問ではないため、意味判定の対象外（語彙ゲートの判定に従う）")
        elif dated_event and not has_negation:
            relation = "uncertain"
            reasons.append("質問が出来事の年代を明示しているため、前提検証の対象外（語彙ゲートの判定に従う）")
        elif has_negation and (has_occurrence or has_diffusion):
            relation = "uncertain"
            reasons.append("否定の記述と肯定の記述が混在するため、意味関係を自動確定できない")
        elif has_negation or onset_after:
            relation = "contradicts"
            if has_negation:
                reasons.append("中心概念について否定的な記述（存在しなかった等）がある")
            if onset_after:
                reasons.append("中心概念の開始・開業が対象時代より後の年代と明記されている")
        elif has_planning_only:
            relation = "mentions_only"
            reasons.append("計画・構想の段階の記述のみで、実現・普及の記述がない")
        elif demand == "diffusion" and not has_diffusion:
            relation = "mentions_only"
            reasons.append("言及はあるが、普及を示す記述が確認できない")
        elif demand == "diffusion" and has_diffusion:
            relation = "supports"
            reasons.append("普及を示す記述が中心概念と結びついている")
        elif demand == "occurrence" and has_occurrence:
            relation = "supports"
            reasons.append("実現・開始を示す記述が中心概念と結びついている")
        elif demand == "occurrence":
            relation = "mentions_only"
            reasons.append("言及はあるが、実現・開始を示す記述が確認できない")
        else:
            relation = "uncertain"
            reasons.append("立場を示す手がかりが不足している")
        if retrospective and relation == "mentions_only":
            reasons.append("刊行が対象時代より後の回顧的資料であり、対象時代に結びつく実現・普及の記述が確認できない")
        return {
            "relation": relation, "checker": self.name, "demand": demand,
            "reasons": reasons,
            "stance_sentences": {k: v for k, v in buckets.items() if v},
            "onset_after_era": onset_after,
            "retrospective": retrospective,
        }


class EmbeddingSemanticChecker:
    """Optional similarity checker (sentence-transformers).

    Embeddings measure topical closeness only: they cannot detect
    negation or contradiction, so this checker never returns
    ``supports``/``contradicts`` on its own — it reports
    ``uncertain`` with a similarity score, or ``mentions_only``
    when even topical closeness is absent. It exists so a stronger
    model can be attached behind the same interface; treat its
    output as a weak second signal.
    """

    name = "embedding"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # optional dependency

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def assess(self, analysis: QuestionAnalysis, ocr_text: str, publication_year: int | None = None) -> dict[str, Any]:
        try:
            model = self._load()
        except Exception as exc:  # noqa: BLE001 - availability is reported, not hidden
            return {
                "relation": "not_checked", "checker": self.name, "demand": question_demand(analysis),
                "reasons": [f"埋め込みモデルを利用できない: {type(exc).__name__}"],
                "stance_sentences": {},
            }
        import numpy as np

        sentences = [s for s in _sentences(ocr_text or "") if len(s) <= 300][:40]
        if not sentences:
            return {"relation": "insufficient", "checker": self.name, "demand": question_demand(analysis),
                    "reasons": ["判定対象の文がない"], "stance_sentences": {}}
        query_vec = model.encode([analysis.raw], normalize_embeddings=True)
        sent_vecs = model.encode(sentences, normalize_embeddings=True)
        sims = (sent_vecs @ query_vec[0])
        best = float(np.max(sims)) if len(sims) else 0.0
        relation = "uncertain" if best >= 0.35 else "mentions_only"
        return {
            "relation": relation, "checker": self.name, "demand": question_demand(analysis),
            "reasons": [f"質問文との最大類似度 {best:.2f}（埋め込みは話題の近さのみで、否定や矛盾は判定しない）"],
            "stance_sentences": {}, "max_similarity": round(best, 3),
        }


class CompositeSemanticChecker:
    """Rule verdicts stay authoritative; a configured embedding
    checker rides along as an attached signal (never a verdict)."""

    name = "rules+embedding"

    def __init__(self, primary: SemanticChecker, secondary: SemanticChecker) -> None:
        self.primary = primary
        self.secondary = secondary

    def assess(self, analysis: QuestionAnalysis, ocr_text: str, *, publication_year: int | None = None) -> dict[str, Any]:
        verdict = self.primary.assess(analysis, ocr_text, publication_year=publication_year)
        verdict["embedding"] = self.secondary.assess(analysis, ocr_text, publication_year=publication_year)
        return verdict


def get_semantic_checker() -> SemanticChecker:
    """The pipeline's checker: rule-based by default. Set
    GLM_SEMANTIC_EMBED_MODEL to a sentence-transformers model name
    to attach the embedding checker as a second signal; the rule
    checker remains the primary verdict."""
    import os

    model = os.environ.get("GLM_SEMANTIC_EMBED_MODEL")
    if model:
        return CompositeSemanticChecker(RuleBasedSemanticChecker(), EmbeddingSemanticChecker(model))
    return RuleBasedSemanticChecker()
