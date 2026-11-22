import httpx
import pytest
import respx

from global_library_mcp.question import analyze_question
from global_library_mcp.relevance import assess_relevance
from global_library_mcp.service import LibraryService

TELEGRAPH_TEXT = (
    "明治時代の通信手段として電信が普及し、東京と横浜の間に電信線が架設された。"
    "通信の歴史において電信は重要な役割を果たし、やがて電話へと発展した記録が残る。"
)
HYDRO_TEXT = (
    "發電水力の開發は明治四十三年に始まった。臨時發電水力調査局は全国の河川を調査し、"
    "水力發電の適地を選定した。發電水力は当時の新技術であり、電氣事業の発展に寄与した。"
)


def test_smartphone_page_is_irrelevant():
    analysis = analyze_question("明治時代のスマートフォンの普及について教えて")
    result = assess_relevance(analysis, TELEGRAPH_TEXT, publication_year=1905)
    assert result["status"] == "irrelevant"
    assert "スマートフォン" in result["missing_concepts"]
    assert any("周辺語のみ" in reason for reason in result["reasons"])


def test_hydroelectric_page_is_relevant_with_old_forms():
    analysis = analyze_question("明治時代の水力発電技術の発達について教えて")
    result = assess_relevance(analysis, HYDRO_TEXT, publication_year=1911)
    assert result["status"] == "relevant"
    assert "水力発電" in result["matched_concepts"]


def test_english_hydroelectric_matches_japanese_question():
    analysis = analyze_question("水力発電の仕組みについて教えて")
    result = assess_relevance(analysis, "Hydroelectric power generation uses the energy of falling water.")
    assert result["status"] in {"relevant", "partially_relevant"}
    assert "水力発電" in result["matched_concepts"]


def test_numeric_question_without_numbers_is_capped():
    analysis = analyze_question("ペリー来航時の横浜村の正確な人口を教えて")
    text = "横浜村は小さな漁村であった。ペリー来航により開港場となり、村の様子は大きく変化した。"
    result = assess_relevance(analysis, text)
    assert result["status"] != "relevant"
    assert any("数値" in reason for reason in result["reasons"])


def test_no_core_concept_is_uncertain():
    analysis = analyze_question("当時の様子について教えて")
    result = assess_relevance(analysis, TELEGRAPH_TEXT)
    assert result["status"] == "uncertain"


def test_later_publication_alone_does_not_exclude():
    analysis = analyze_question("明治時代の水力発電について教えて")
    text = "明治時代の水力発電は、発電水力調査から始まった。明治の技術者たちは各地に発電所を建設した。"
    result = assess_relevance(analysis, text, publication_year=1985)
    assert result["status"] == "relevant"


@pytest.mark.asyncio
@respx.mock
async def test_collect_evidence_routes_irrelevant_pages_to_related():
    book = {"id": "111", "title": "電信沿革史", "responsibility": "逓信省", "published": 1905, "highlights": ["通信"]}
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": [book]})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "111_10", "book": "111", "page": 10}], "hit": 1})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/111_10").mock(
        return_value=httpx.Response(200, json={"id": "111_10", "book": "111", "page": 10, "contents": TELEGRAPH_TEXT})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).collect_evidence(
            "明治時代のスマートフォンの普及について教えて", libraries=["ndl"]
        )
    assert result["evidence"] == []
    assert len(result["related"]) == 1
    assert result["related"][0]["relevance"]["status"] == "irrelevant"
    assert result["analysis"]["core_concepts"]


def test_compound_halves_match_split_form():
    analysis = analyze_question("横浜開港について当時の資料の記述を教えて")
    result = assess_relevance(analysis, "横浜の開港は安政六年に行われ、貿易が始まった。開港場の様子が記録されている。")
    assert "横浜開港" in result["matched_concepts"]
    assert result["status"] == "relevant"


def test_anchor_match_with_half_concepts_is_relevant():
    analysis = analyze_question("蒸気機関の導入と工場について教えて")
    result = assess_relevance(analysis, "蒸気機関は工場に導入され、紡績の機械化が進んだ。蒸気機関の発達は産業を変えた。")
    assert result["status"] == "relevant"


def test_era_far_publication_without_era_mention_is_capped():
    analysis = analyze_question("明治時代の原子力発電所の建設について教えて")
    text = "原子力発電所の建設は安全性の検討から始まり、原子力発電所の運転に至るまで多くの工程がある。"
    result = assess_relevance(analysis, text, publication_year=1980)
    assert result["status"] == "partially_relevant"
    assert any("出版年も時代から大きく離れている" in reason for reason in result["reasons"])


def test_era_mention_overrides_publication_distance():
    analysis = analyze_question("明治時代の原子力発電所の建設について教えて")
    text = "明治時代には原子力発電所は存在しなかった。本書は原子力発電所の建設史を明治の電力事情から説き起こす。"
    result = assess_relevance(analysis, text, publication_year=1980)
    assert result["status"] == "relevant"
