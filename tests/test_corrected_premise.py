import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

SUBWAY_TEXT = (
    "明治時代の東京では馬車鉄道が旅客を運んでいた。地下鉄の計画は明治時代にも構想されたが、実現には至らなかった。"
    "地下鉄は昭和二年に開業した。上野と浅草の間に地下鉄が開業し、多くの乗客を運んだ。"
    "地下鉄の建設は昭和に入ってから本格化したのである。"
)


@pytest.mark.asyncio
@respx.mock
async def test_corrected_premise_from_later_onset():
    book = {"id": "222", "title": "東京地下鉄道史", "responsibility": "東京地下鉄道", "published": 1934, "highlights": ["地下鉄"]}
    respx.get("https://lab.ndl.go.jp/dl/api/book/search").mock(
        return_value=httpx.Response(200, json={"list": [book]})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/search").mock(
        return_value=httpx.Response(200, json={"list": [{"id": "222_10", "book": "222", "page": 10}], "hit": 1})
    )
    respx.get("https://lab.ndl.go.jp/dl/api/page/222_10").mock(
        return_value=httpx.Response(200, json={"id": "222_10", "book": "222", "page": 10, "contents": SUBWAY_TEXT})
    )
    async with httpx.AsyncClient() as client:
        result = await LibraryService(client).answer(
            "明治時代の地下鉄の建設について教えて", libraries=["ndl"]
        )
    assert result["status"] == "corrected_premise"
    assert result["available"] is True
    assert result["citations"][0]["title"] == "東京地下鉄道史"
    assert result["correction"]["quotes"]
    assert "昭和二年" in result["correction"]["quotes"][0]
    assert result["evidence"] == []
