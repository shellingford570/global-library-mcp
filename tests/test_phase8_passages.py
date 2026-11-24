"""Phase 8-B/8-C: evidence states and passage extraction."""
from global_library_mcp.passages import extract_passages, verify_quote
from global_library_mcp.question import analyze_question
from global_library_mcp.service import evidence_states, rejection_reasons

PAGE = (
    "本書は電信の歴史を述べるものである。"
    "電信は明治二年に開局した。同年、東京と横浜の間に電信線が架設された。"
    "その後、電信は全国へと広がっていった。天気の話は関係がない。"
)


def test_passages_are_verbatim_and_located():
    analysis = analyze_question("明治時代の電信の開設について教えて")
    passages = extract_passages(analysis, PAGE, "ndl:1:1_10", image_url="https://example.org/img.jpg")
    assert passages
    for passage in passages:
        assert passage["quote_verified"] is True
        assert PAGE[passage["char_start"]:passage["char_end"]] == passage["text"]
        assert passage["image_url"] == "https://example.org/img.jpg"
    opening = next(p for p in passages if "開局" in p["text"])
    assert "occurrence" in opening["stance_cues"]
    assert opening["era_anchor"]["class"] == "in_era"


def test_verify_quote_rejects_fabrication():
    assert verify_quote(PAGE, "電信は明治二年に開局した。") is True
    assert verify_quote(PAGE, "電信は大正二年に開局した。") is False


def test_states_distinguish_discovery_from_certification():
    states = evidence_states(True, "relevant", {"relation": "mentions_only"}, False,
                             rejection_reasons("relevant", {"relation": "mentions_only"}, None, "body"))
    assert states["discovered"] is True
    assert states["source_verified"] is True
    assert states["relevant_candidate"] is True
    assert states["assessed_evidence"] is False
    assert states["rejected_for_answer"] is True
    assert any("主張していない" in r for r in states["rejection_reasons"])
