"""b10 Stage 3: lexical scorer, ResearchRanker, semantic backend
fallback (brief sections 17-22). No network; the model backend
tests use only the unavailable/fallback paths plus a synthetic
vector check."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.discovery import analyze_discovery_query  # noqa: E402
from global_library_mcp.lexical import LexicalScorer  # noqa: E402
from global_library_mcp.research_ranker import ResearchRanker  # noqa: E402
from global_library_mcp.semantic_local import (  # noqa: E402
    LocalSemanticBackend, SemanticBackendUnavailable, cosine_scores,
    get_local_backend)


def _item(title, author="", lang="de", ocr=False, rid="x:1", lib="ddb"):
    return SimpleNamespace(title=title, author=author, subjects=[],
                           description="", language=lang, ocr=ocr,
                           record_id=rid, library_id=lib, year=1850,
                           material_type="book", work_id=None)


def test_lexical_scorer_ranks_matching_doc_first():
    docs = ["Die Dampfmaschine und ihre Anwendung",
            "Die Geschichte der Eisenbahn",
            "Traité de la machine à vapeur"]
    scorer = LexicalScorer(docs)
    scores = scorer.score("Dampfmaschine")
    assert scores[0] == max(scores) and scores[0] > 0


def test_lexical_scorer_cjk_bigrams():
    docs = ["蒸気機関の歴史", "鉄道の歴史", "水力発電の仕組み"]
    scorer = LexicalScorer(docs)
    scores = scorer.score("蒸気機関")
    assert scores[0] == max(scores)


def test_research_ranker_strict_tier_beats_ocr():
    analysis = analyze_discovery_query("Kritik der reinen Vernunft Kant")
    strict = _item("Kritik der reinen Vernunft", "Immanuel Kant",
                   rid="x:strict", ocr=False)
    noisy = _item("Kant und die Folgen der Kritik", "Someone Else",
                  rid="x:noisy", ocr=True)
    _rr = ResearchRanker()
    ranked = _rr.rank(analysis, [noisy, strict], {})
    assert ranked[0].record_id == "x:strict"
    assert _rr._meta[("ddb", "x:strict")]["subscores"]["strict_title_tier"] is True
    # OCR is usability only: it must not appear as relevance points
    assert _rr._meta[("ddb", "x:noisy")]["subscores"]["ocr_usability"] is True


def test_research_ranker_reasons_only_from_fired_signals():
    analysis = analyze_discovery_query("Dampfmaschine")
    item = _item("Die Dampfmaschine", "Friedrich Müller")
    _rr = ResearchRanker()
    ranked = _rr.rank(analysis, [item], {})
    reasons = _rr.reasons_for(ranked[0])
    assert all(isinstance(r, str) for r in reasons)
    assert not any("semantic" in r for r in reasons)  # no model ran


def test_semantic_backend_missing_dir_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("GLM_SEMANTIC_MODEL_DIR", str(tmp_path / "nope"))
    assert get_local_backend() is None
    try:
        LocalSemanticBackend(tmp_path / "nope")
        raise AssertionError("should have raised")
    except SemanticBackendUnavailable:
        pass


def test_semantic_backend_unset_env_is_none(monkeypatch):
    monkeypatch.delenv("GLM_SEMANTIC_MODEL_DIR", raising=False)
    assert get_local_backend() is None


def test_cosine_scores_normalised():
    scores = cosine_scores([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    assert scores[0] == 1.0 and scores[1] == 0.0
