import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

HYDRO_BOOK = {"id": "994120", "title": "發電水力の開發", "responsibility": "臨時發電水力調査局", "published": 1911, "highlights": ["發電水力"]}
HYDRO_PAGE = "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された。水力發電の適地を全国で調査した記録である。"


def _mock_hydro():
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": [HYDRO_BOOK]})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "994120_50", "book": "994120", "page": 50}], "hit": 1})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/994120_50").mock(
        return_value=httpx.Response(200, json={"id": "994120_50", "book": "994120", "page": 50, "contents": HYDRO_PAGE})
    )


class FabricatingProvider:
    async def answer(self, query, evidence):
        return {"available": True, "answer": "水力発電は明治時代に宇宙人の技術で導入された。",
                "citations": [evidence[0]["citation_key"]],
                "claims": [{"text": "水力発電は明治時代に宇宙人の技術で導入された", "citations": [evidence[0]["citation_key"]]}],
                "limitations": []}


class GroundedProvider:
    async def answer(self, query, evidence):
        return {"available": True, "answer": HYDRO_PAGE,
                "citations": [evidence[0]["citation_key"]],
                "claims": [{"text": HYDRO_PAGE.split("。")[0], "citations": [evidence[0]["citation_key"]]}],
                "limitations": []}


@pytest.mark.asyncio
@respx.mock
async def test_answer_withheld_when_claim_unsupported():
    _mock_hydro()
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer(
            "明治時代の水力発電技術の発達について教えて", libraries=["ndl"], provider=FabricatingProvider()
        )
    assert result["status"] == "answer_withheld"
    assert result["answer"] is None
    assert result["claims"][0]["support"] == "unsupported"


@pytest.mark.asyncio
@respx.mock
async def test_grounded_answer_still_published():
    _mock_hydro()
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer(
            "明治時代の水力発電技術の発達について教えて", libraries=["ndl"], provider=GroundedProvider()
        )
    assert result["status"] == "answered"
    assert result["claims"][0]["support"] == "supported"


@pytest.mark.asyncio
@respx.mock
async def test_insufficient_reason_names_missing_concept_and_related():
    book = {"id": "111", "title": "電信沿革史", "responsibility": "逓信省", "published": 1905, "highlights": ["通信"]}
    text = ("明治時代の通信手段として電信が普及し、東京と横浜の間に電信線が架設された。"
            "通信の歴史において電信は重要な役割を果たし、やがて電話へと発展した記録が残る。")
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(return_value=httpx.Response(200, json={"list": [book]}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "111_10", "book": "111", "page": 10}], "hit": 1}))
    respx.get("https://lab.ndl.go.jp/dl/api/page/111_10").mock(
        return_value=httpx.Response(200, json={"id": "111_10", "book": "111", "page": 10, "contents": text}))
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer("明治時代のスマートフォンの普及について教えて", libraries=["ndl"])
    assert result["status"] == "insufficient_evidence"
    assert "スマートフォン" in result["reason"]
    assert result["related_documents"]
    assert result["related_documents"][0]["relevance_status"] == "irrelevant"
