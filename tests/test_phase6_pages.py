from global_library_mcp.evidence import classify_page_kind
from global_library_mcp.models import Evidence
from global_library_mcp.question import analyze_question
from global_library_mcp.service import LibraryService


def test_page_kinds():
    assert classify_page_kind("目次 第一章 緒言 本書は…") == "front_matter"
    assert classify_page_kind("第壱図 写真 横浜港の景") == "photo_plate"
    assert classify_page_kind("年 次 人 口 1900 123456 1901 234567 " * 8) == "table"
    assert classify_page_kind("横浜は安政六年に開港し、貿易が始まった。当時の記録によれば、生糸が主要な輸出品であった。" * 3) == "body"
    assert classify_page_kind("") == "empty"


def _evidence(page: str, matched: list[str], kind: str = "body", relation: str = "uncertain") -> Evidence:
    return Evidence(
        library_id="ndl", library_name="NDL", record_id="1", title="横浜開港と貿易",
        page_id=f"1_{page}", relevance={"status": "partially_relevant", "score": 0.4,
                                        "matched_concepts": matched, "reasons": []},
        semantics={"relation": relation}, page_kind=kind,
    )


def _service() -> LibraryService:
    return LibraryService.__new__(LibraryService)


def test_union_promotion_covers_split_concepts():
    analysis = analyze_question("横浜開港と貿易について当時の資料の記述を教えて")
    a = _evidence("10", ["横浜開港"])
    b = _evidence("20", ["貿易"])
    states = {1: {"partial_objects": [a, b], "related_pages": [a.to_dict(), b.to_dict()]}}
    promoted, keys = _service()._union_promote(states, analysis)
    assert len(promoted) == 2
    assert keys == {a.citation_key, b.citation_key}
    assert all(obj.semantics.get("union_promoted") for obj in promoted)


def test_union_blocked_by_contradiction_and_front_matter():
    analysis = analyze_question("横浜開港と貿易について当時の資料の記述を教えて")
    a = _evidence("10", ["横浜開港"])
    b = _evidence("20", ["貿易"])
    contra = _evidence("30", ["貿易"], relation="contradicts")
    states = {1: {"partial_objects": [a, b], "related_pages": [a.to_dict(), b.to_dict(), contra.to_dict()]}}
    promoted, _ = _service()._union_promote(states, analysis)
    assert promoted == []
    # coverage carried only by a front-matter page does not count
    fm = _evidence("2", ["貿易"], kind="front_matter")
    states = {1: {"partial_objects": [a, fm], "related_pages": [a.to_dict(), fm.to_dict()]}}
    promoted, _ = _service()._union_promote(states, analysis)
    assert promoted == []
