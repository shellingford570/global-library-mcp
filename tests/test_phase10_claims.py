"""Phase 10-B: passage-bound verification and the publish rule."""
import httpx
import pytest
import respx

from global_library_mcp.claims import verify_claim
from global_library_mcp.service import LibraryService

KEY = "ndl:1:p1"
SENT = "臨時發電水力調査局は明治四十三年に設置され、全国の河川を調査した"
OTHER = "本書は河川行政の沿革を述べたものである"
PAGE = SENT + "。" + OTHER + "。"


def _evidence(with_passages=True):
    item = {"citation_key": KEY, "ocr_text": PAGE}
    if with_passages:
        start = PAGE.index(SENT)
        item["passages"] = [{
            "passage_id": f"{KEY}#p1", "citation_key": KEY, "text": SENT,
            "char_start": start, "char_end": start + len(SENT)}]
    return {KEY: item}


def test_claim_verified_against_cited_passage():
    claim = {"text": SENT, "citations": [KEY], "evidence_passage_ids": [f"{KEY}#p1"]}
    result = verify_claim(claim, _evidence())
    assert result["support"] == "supported"
    assert result["verification_scope"] == "passage"
    assert result["verified_against"][0]["passage_id"] == f"{KEY}#p1"
    assert result["verified_against"][0]["char_start"] == 0


def test_words_scattered_across_page_do_not_support():
    # The claim's words exist on the page but in different
    # passages - no single cited passage supports it.
    claim = {"text": "河川行政の沿革は明治四十三年に始まった", "citations": [KEY]}
    result = verify_claim(claim, _evidence())
    assert result["support"] != "supported"


def test_no_passages_caps_at_uncertain():
    claim = {"text": SENT, "citations": [KEY]}
    result = verify_claim(claim, _evidence(with_passages=False))
    assert result["support"] == "uncertain"
    assert result["verification_scope"] == "page"


def test_unknown_passage_id_is_unsupported():
    claim = {"text": SENT, "citations": [KEY], "evidence_passage_ids": [f"{KEY}#p99"]}
    result = verify_claim(claim, _evidence())
    assert result["support"] == "unsupported"


class _UncertainProvider:
    async def answer(self, query, evidence):
        key = evidence[0]["citation_key"]
        return {"available": True, "answer": "x", "citations": [key],
                "claims": [{"text": "發電水力の開發は大正五年に始まり、臨時發電水力調査局が設置された", "citations": [key]}],
                "limitations": []}


@pytest.mark.asyncio
@respx.mock
async def test_all_uncertain_claims_are_withheld():
    """The grok-4.3 q18 regression: every claim uncertain must
    NOT publish as answered (Phase 10-B 4.1)."""
    book = {"id": "994120", "title": "発電水力調査書", "responsibility": "逓信省",
            "published": 1911, "highlights": ["発電水力"]}
    text = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [book]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": text}))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer(
            "発電水力の開発はいつ始まったか", libraries=["ndl"], provider=_UncertainProvider())
    assert result["status"] == "answer_withheld"
    assert result["answer"] is None
