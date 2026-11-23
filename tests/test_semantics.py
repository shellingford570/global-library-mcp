from global_library_mcp.question import analyze_question
from global_library_mcp.semantics import RuleBasedSemanticChecker

CHECKER = RuleBasedSemanticChecker()


def assess(question: str, text: str) -> dict:
    return CHECKER.assess(analyze_question(question), text)


def test_negation_is_contradiction():
    result = assess("明治時代のラジオ放送が社会に与えた影響について教えて",
                    "明治時代にはラジオ放送は存在しなかった。当時の通信は電信と電話が中心であった。ラジオ放送の実験はまだ行われていなかった。")
    assert result["relation"] == "contradicts"


def test_telegraph_only_page_is_insufficient_for_radio():
    result = assess("明治時代のラジオ放送が社会に与えた影響について教えて",
                    "明治時代には電信技術が発達した。電信は全国に広がり、通信の要となった。")
    assert result["relation"] == "insufficient"


def test_planning_only_is_mentions_only():
    result = assess("明治時代の地下鉄の建設について教えて",
                    "地下鉄の計画は明治時代に構想され、幾度も提案された。しかし資金の目処は立たなかった。")
    assert result["relation"] == "mentions_only"


def test_diffusion_support():
    result = assess("大正時代の電灯の普及について教えて",
                    "電灯は大正時代に急速に普及した。電灯は都市の家庭にまで広まった。")
    assert result["relation"] == "supports"


def test_occurrence_without_diffusion_does_not_support_diffusion_question():
    result = assess("大正時代の電気洗濯機の普及について教えて",
                    "電気洗濯機は大正時代に輸入され、一部の店舗で実演された。価格は高く、限られた人々の目に触れるのみであった。")
    assert result["relation"] in ("mentions_only", "uncertain")


def test_general_question_is_out_of_scope():
    result = assess("水力発電の仕組みを教えて",
                    "水力発電は水の落差を利用して水車を回し、発電機を駆動する仕組みである。")
    assert result["relation"] == "uncertain"


def test_mixed_signals_are_uncertain():
    result = assess("明治時代の電話の普及について教えて",
                    "電話は明治時代には存在しなかったという説もあるが、実際には電話交換が開始され、電話は次第に普及した。")
    assert result["relation"] == "uncertain"


def test_onset_after_era_is_contradiction():
    result = assess("明治時代の地下鉄の建設について教えて",
                    "地下鉄は昭和二年に開業した。東京の地下鉄は昭和に入ってから建設が進んだ。")
    assert result["relation"] == "contradicts"
    assert result["onset_after_era"]


def test_radio_starting_in_taisho_contradicts_meiji_premise():
    result = assess("明治時代のラジオ放送が社会に与えた影響について教えて",
                    "ラジオ放送は大正十四年に始まった。ラジオ放送の開始は大正時代の出来事である。")
    assert result["relation"] == "contradicts"


def test_in_era_occurrence_still_supports():
    result = assess("明治時代の鉄道の開業について教えて",
                    "鉄道は明治五年に開業した。新橋と横浜の間に鉄道が開業し、旅客の輸送が始まった。")
    assert result["relation"] == "supports"


def test_retrospective_unanchored_occurrence_does_not_support():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("明治時代の地下鉄の建設について教えて"),
        "地下鉄は多くの乗客を運び、建設は困難を極めた。地下鉄の開業は都市の交通を一変させた。",
        publication_year=1934,
    )
    assert result["retrospective"] is True
    assert result["relation"] == "mentions_only"


def test_retrospective_in_era_anchored_occurrence_supports():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("明治時代の鉄道の開業について教えて"),
        "鉄道は明治五年に開業した。新橋と横浜の間に鉄道が開業し、旅客の輸送が始まった。",
        publication_year=1934,
    )
    assert result["relation"] == "supports"


def test_contemporary_source_keeps_unanchored_support():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("明治時代の鉄道の開業について教えて"),
        "鉄道が開業した。新橋と横浜の間に鉄道が開業し、旅客の輸送が始まった。",
        publication_year=1905,
    )
    assert result["relation"] == "supports"


def test_telegraph_office_opening_vocabulary_supports():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("明治時代の電信技術の導入について教えて"),
        "明治政府購入の電信機が届いた。明治二年に開局されたもの五局、三年に開局されたもの四局であった。電信の開通は各地に広がった。",
        publication_year=1934,
    )
    assert result["relation"] == "supports"


def test_later_developments_alone_are_not_a_contradiction():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("明治時代の電信技術の導入について教えて"),
        "本邦電信の将来の動向を確立するに至ったが、明治時代における電信の経緯を総合して見る必要がある。やがて通信機械は印刷機によるを原則とすることになった。",
        publication_year=1934,
    )
    assert result["relation"] != "contradicts"


def test_dated_event_question_is_out_of_scope():
    checker = RuleBasedSemanticChecker()
    result = checker.assess(
        analyze_question("1891年の濃尾地震の被害について教えて"),
        "濃尾地震は各地に大きな被害をもたらした。家屋の倒壊は数万に及んだ。",
        publication_year=1935,
    )
    assert result["relation"] == "uncertain"
