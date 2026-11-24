from dataclasses import dataclass

from global_library_mcp.question import analyze_question, normalize_text
from global_library_mcp.service import rank_candidates


@dataclass
class Item:
    library_id: str = "ndl"
    record_id: str = "x"
    title: str = ""
    author: str | None = None
    description: str | None = None


def test_pseudo_concepts_are_not_core():
    assert analyze_question("発電水力調査はどのように行われたか").core_concepts == ["発電水力調査"]
    assert analyze_question("明治時代のコレラの流行と対策について教えて").core_concepts == ["コレラ", "流行"]
    assert analyze_question("脚気の原因をめぐる議論について教えて").core_concepts == ["脚気"]
    assert analyze_question("明治時代の写真術の伝来と広がりについて教えて").core_concepts == ["写真術"]


def test_city_is_a_modifier_not_a_topic():
    assert analyze_question("神戸の外国人居留地について教えて").core_concepts == ["外国人居留地"]
    # a compound containing the city stays a topic
    assert "横浜開港" in analyze_question("横浜開港について教えて").core_concepts


def test_period_spellings_fold():
    assert normalize_text("寫眞") == "写真"
    assert normalize_text("橫濱") == "横浜"


def test_ranking_prefers_specialist_and_multiplicity():
    analysis = analyze_question("明治時代の電信技術の導入について教えて")
    survey = Item(record_id="survey", title="日本通信史")
    specialist = Item(record_id="spec", title="電信沿革史")
    other = Item(record_id="other", title="明治時代")
    hits = {("ndl", "survey"): 2, ("ndl", "spec"): 3, ("ndl", "other"): 1}
    ranked = rank_candidates(analysis, [survey, specialist, other], hits)
    assert ranked[0].record_id == "spec"
    assert ranked[-1].record_id == "other"
