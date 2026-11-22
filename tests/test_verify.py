import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService

PID = "994120"
PAGE_ID = "994120_50"
IMAGE_URL = "https://dl.ndl.go.jp/api/iiif/994120/R0000050/full/full/0/default.jpg"
PAGE_JSON = {"id": PAGE_ID, "book": PID, "page": 50,
             "contents": "發電水力の開發は明治四十三年に始まり、臨時發電水力調査局が設置された事業である。"}


def _manifest(canvases):
    return {"@context": "http://iiif.io/api/presentation/2/context.json", "@type": "sc:Manifest",
            "sequences": [{"canvases": canvases}]}


def _canvas(frame, image):
    return {"@id": f"https://dl.ndl.go.jp/api/iiif/{PID}/canvas/{frame}",
            "images": [{"resource": {"@id": image}}]}


def _mock_page():
    respx.get(f"https://lab.ndl.go.jp/dl/api/page/{PAGE_ID}").mock(
        return_value=httpx.Response(200, json=PAGE_JSON)
    )


@pytest.mark.asyncio
@respx.mock
async def test_verify_original_all_checks_pass():
    _mock_page()
    respx.get(f"https://dl.ndl.go.jp/api/iiif/{PID}/manifest.json").mock(
        return_value=httpx.Response(200, json=_manifest([_canvas(50, IMAGE_URL)]))
    )
    respx.get(IMAGE_URL).mock(
        return_value=httpx.Response(206, content=b"\xff\xd8\xff\xe0", headers={"content-type": "image/jpeg"})
    )
    async with httpx.AsyncClient() as client:
        report = await LibraryService(client).verify_page("ndl", PAGE_ID)
    assert report["status"] == "verified"
    assert all(check["ok"] for check in report["checks"].values())
    assert report["canvas_id"].endswith("/canvas/50")
    assert report["digital_frame"] == 50


@pytest.mark.asyncio
@respx.mock
async def test_verify_original_missing_canvas_fails():
    _mock_page()
    respx.get(f"https://dl.ndl.go.jp/api/iiif/{PID}/manifest.json").mock(
        return_value=httpx.Response(200, json=_manifest([_canvas(49, IMAGE_URL)]))
    )
    respx.get(IMAGE_URL).mock(
        return_value=httpx.Response(206, content=b"\xff\xd8", headers={"content-type": "image/jpeg"})
    )
    async with httpx.AsyncClient() as client:
        report = await LibraryService(client).verify_page("ndl", PAGE_ID)
    assert report["status"] == "failed"
    assert report["checks"]["canvas"]["ok"] is False
    assert report["checks"]["image_reachable"]["ok"] is True


@pytest.mark.asyncio
@respx.mock
async def test_verify_original_unreachable_image_fails():
    _mock_page()
    respx.get(f"https://dl.ndl.go.jp/api/iiif/{PID}/manifest.json").mock(
        return_value=httpx.Response(200, json=_manifest([_canvas(50, IMAGE_URL)]))
    )
    respx.get(IMAGE_URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        report = await LibraryService(client).verify_page("ndl", PAGE_ID)
    assert report["status"] == "failed"
    assert report["checks"]["image_reachable"]["ok"] is False


@pytest.mark.asyncio
async def test_verify_page_unsupported_adapter():
    async with httpx.AsyncClient() as client:
        report = await LibraryService(client).verify_page("loc", "whatever")
    assert report["status"] == "unsupported"
