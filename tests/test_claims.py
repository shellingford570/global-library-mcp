import httpx
import pytest
import respx

from global_library_mcp.answer import MockProvider
from global_library_mcp.claims import verify_claim, verify_claims
from global_library_mcp.service import LibraryService

OCR = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"
EVIDENCE = [{"citation_key": "ndl:994120:994120_50", "ocr_text": OCR}]


def test_verbatim_claim_is_supported():
    claim = {"text": "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された", "citations": ["ndl:994120:994120_50"]}
    result = verify_claim(claim, {"ndl:994120:994120_50": EVIDENCE[0]})
    assert result["support"] == "supported"
    assert result["overlap"] > 0.9


def test_claim_without_citation_is_unsupported():
    result = verify_claim({"text": "何らかの主張", "citations": []}, {})
    assert result["support"] == "unsupported"


def test_unrelated_claim_is_unsupported():
    claim = {"text": "量子コンピュータは重ね合わせの原理を利用して計算を行う装置である", "citations": ["ndl:994120:994120_50"]}
    result = verify_claim(claim, {"ndl:994120:994120_50": EVIDENCE[0]})
    assert result["support"] == "unsupported"


def test_unverified_date_token_downgrades_claim():
    claim = {"text": "發電水力の開發は大正五年に始まり、臨時發電水力調査局が設置された", "citations": ["ndl:994120:994120_50"]}
    result = verify_claim(claim, {"ndl:994120:994120_50": EVIDENCE[0]})
    assert result["support"] in {"uncertain", "unsupported"}
    assert "大正五年" in result["support_detail"]


def test_conflict_flag_is_conflicting():
    claim = {"text": "設置年は資料により異なる", "citations": ["ndl:994120:994120_50"], "conflict": True}
    result = verify_claim(claim, {"ndl:994120:994120_50": EVIDENCE[0]})
    assert result["support"] == "conflicting"


def test_empty_cited_text_is_not_checked():
    claim = {"text": "主張", "citations": ["k"]}
    result = verify_claim(claim, {"k": {"citation_key": "k", "ocr_text": ""}})
    assert result["support"] == "not_checked"


def test_verify_claims_maps_evidence():
    claims = [{"text": "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された", "citations": ["ndl:994120:994120_50"]}]
    results = verify_claims(claims, EVIDENCE)
    assert results[0]["support"] == "supported"


BOOK = {"id": "994120", "title": "發電水力の開發", "responsibility": "臨時發電水力調査局", "published": 1911, "highlights": ["發電水力"]}


@pytest.mark.asyncio
@respx.mock
async def test_answer_includes_verified_claims():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [BOOK]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": OCR}))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("発電水力の開発", libraries=["ndl"], provider=MockProvider())
    assert result["status"] == "answered"
    assert result["claims"]
    assert result["claims"][0]["support"] == "supported"
    assert result["claims"][0]["citations"] == ["ndl:994120:994120_50"]
