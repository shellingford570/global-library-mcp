"""Phase 7-C: numeric binding - presence is not an answer."""
from global_library_mcp.claims import verify_claim
from global_library_mcp.numeric import extract_quantities, parse_kanji_number
from global_library_mcp.question import analyze_question


def test_kanji_numerals():
    assert parse_kanji_number("二十三") == 23
    assert parse_kanji_number("一万二千三百") == 12300
    assert parse_kanji_number("參拾") == 30
    assert parse_kanji_number("廿四") == 24
    assert parse_kanji_number("九") == 9
    values = {q["value"] for q in extract_quantities("職員十九人、予算三百円、滝は二十三本を数えた")}
    assert {19.0, 300.0, 23.0} <= values


def _evidence(text: str, kind: str = "body") -> dict:
    return {"ndl:1:1_5": {"citation_key": "ndl:1:1_5", "ocr_text": text, "page_kind": kind}}


def test_unbound_number_is_unsupported_for_numeric_questions():
    # q40's shape: staff numbers exist; the waterfall count does not bind.
    analysis = analyze_question("明治四十三年の発電水力調査で確認された滝の正確な数を教えて")
    assert analysis.intent == "numeric"
    page = "調査には職員十九人が従事し、予算は三百円であった。各地の地形を測量した記録である。"
    claim = {"text": "調査で確認された滝は19であった", "citations": ["ndl:1:1_5"]}
    result = verify_claim(claim, _evidence(page), analysis=analysis)
    assert result["support"] == "unsupported"
    assert "not bound" in result["support_detail"]


def test_bound_number_supports_numeric_claim():
    analysis = analyze_question("明治四十三年の発電水力調査で確認された滝の正確な数を教えて")
    page = "調査の結果、滝は二十三本を数えた。いずれも発電に利用できる落差を持っていた。"
    claim = {"text": "調査で確認された滝は23本であった", "citations": ["ndl:1:1_5"]}
    result = verify_claim(claim, _evidence(page), analysis=analysis)
    assert result["numeric"]["23"]["bound"] >= 1
    assert "not bound" not in result["support_detail"]


def test_table_only_number_stays_unverified():
    analysis = analyze_question("明治四十三年の発電水力調査で確認された滝の正確な数を教えて")
    page = "滝 二十三 職員 十九 予算 三百 " * 3
    claim = {"text": "調査で確認された滝は23本であった", "citations": ["ndl:1:1_5"]}
    result = verify_claim(claim, _evidence(page, kind="table"), analysis=analysis)
    assert result["support"] in ("uncertain", "unsupported")
    assert "table" in result["support_detail"]
