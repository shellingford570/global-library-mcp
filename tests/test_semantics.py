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
