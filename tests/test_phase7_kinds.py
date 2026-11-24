"""Phase 7-D: page kinds and their usage policy."""
from global_library_mcp.evidence import classify_page_kind
from global_library_mcp.question import analyze_question
from global_library_mcp.service import admission_decision


def test_new_kinds():
    assert classify_page_kind("発行者 東京印刷株式会社 印刷者 山田太郎 定価 金五拾銭 発行所 博文館 大正三年五月一日発行") == "colophon"
    assert classify_page_kind("人名索引 青木 123 赤羽 45 明石 231 " * 8) == "index"
    assert classify_page_kind("發電水力調査要項 第一條 職員定員 一、局長 二、技師 三、書記 一覧表の通り定める" + "、職員" * 3) in ("admin_list", "index", "front_matter")
    assert classify_page_kind("電信事業史 上巻 山田太郎著 東京 博文館") == "title_page"
    assert classify_page_kind("〓〓〓 漢字 〓〓 テスト 〓〓〓〓 文章 〓 " * 12) == "damaged"


def test_bibliographic_question_may_use_title_page():
    analysis = analyze_question("明治時代に出版された電信事業史という本の正式な書名を教えて")
    admitted, record = admission_decision(
        analysis, "relevant", {"relation": "uncertain"}, "title_page", None, True
    )
    assert admitted is True
    assert record["checks"].get("kind_purpose") == "bibliographic"


def test_factual_question_may_not_use_title_page():
    analysis = analyze_question("明治時代の電信の開設について教えて")
    admitted, _ = admission_decision(
        analysis, "relevant", {"relation": "uncertain"}, "title_page", None, True
    )
    assert admitted is False
