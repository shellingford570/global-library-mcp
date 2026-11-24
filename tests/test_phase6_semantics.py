"""Phase 6-F regression cases named in the brief, plus the anchor
inheritance guard and the embedding activation switch."""
import os

from global_library_mcp.question import analyze_question
from global_library_mcp.semantics import (
    CompositeSemanticChecker,
    EmbeddingSemanticChecker,
    RuleBasedSemanticChecker,
    get_semantic_checker,
)

CHECKER = RuleBasedSemanticChecker()


def relation(question: str, text: str, year: int | None = None) -> str:
    return CHECKER.assess(analyze_question(question), text, publication_year=year)["relation"]


def test_false_premises_still_contradict():
    assert relation("明治時代の地下鉄の建設について教えて",
                    "日本で最初の地下鉄は、1927年に東京の上野・浅草間で開通した。") == "contradicts"
    assert relation("明治時代のラジオ放送について教えて",
                    "日本でラジオ放送が始まったのは1925年のことである。") == "contradicts"
    assert relation("大正時代のテレビ放送について教えて",
                    "テレビ放送は昭和二十八年（1953年）に始まった。") == "contradicts"
    assert relation("大正時代の電気冷蔵庫の普及について教えて",
                    "電気冷蔵庫が一般家庭に普及したのは昭和四十年以降である。大正時代の家庭に冷蔵庫はなかった。") == "contradicts"
    assert relation("明治時代の宇宙飛行について教えて",
                    "宇宙飛行が実現したのは1961年のことである。明治時代には空想の域を出なかった。") == "contradicts"


def test_contemporary_hydro_source_still_supports():
    text = "明治四十三年に発電水力調査会が設立され、水力発電の開発が始まった。"
    assert relation("明治時代末期の水力発電技術について当時の資料の記述を教えて", text, 1911) == "supports"


def test_bare_era_name_is_not_inherited():
    # The diffusion sentence is undated; the next sentence only
    # names the era as the record's provenance. Inheriting that
    # bare name would anchor the diffusion to the era.
    text = "電信は全国に普及した。この記録は大正時代のものである。"
    assert relation("大正時代の電信の普及について教えて", text, 1930) != "supports"


def test_year_bearing_neighbour_still_anchors():
    text = "各地に電信局が開局した。明治二年、東京・横浜間に電信線が架設された。"
    assert relation("明治時代の電信の導入について教えて", text, 1909) == "supports"


def test_embedding_activation_switch():
    os.environ.pop("GLM_SEMANTIC_EMBED_MODEL", None)
    assert isinstance(get_semantic_checker(), RuleBasedSemanticChecker)
    os.environ["GLM_SEMANTIC_EMBED_MODEL"] = "some/model"
    try:
        checker = get_semantic_checker()
        assert isinstance(checker, CompositeSemanticChecker)
        verdict = checker.assess(analyze_question("明治時代の電信について教えて"), "電信が導入された。")
        # rules stay authoritative; the embedding signal is attached
        # (not_checked here: no model is actually loaded in tests
        # because the fake embedder path is not exercised)
        assert verdict["relation"] in ("supports", "mentions_only", "insufficient", "uncertain", "not_checked")
        assert "embedding" in verdict
    finally:
        os.environ.pop("GLM_SEMANTIC_EMBED_MODEL", None)


def test_embedding_unavailable_is_not_checked_not_support():
    checker = EmbeddingSemanticChecker("nonexistent/model")

    def _boom() -> None:
        raise RuntimeError("no weights")

    checker._load = _boom  # type: ignore[method-assign]
    verdict = checker.assess(analyze_question("明治時代の電信について教えて"), "電信が導入された。")
    assert verdict["relation"] == "not_checked"
