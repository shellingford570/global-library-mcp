"""b5 final-review regression tests.

Every test here pins a defect the external review found in the
first b5 candidate (or a safety property it demanded), so the
defect cannot silently return:

- BSB page mapping must be structural and complete (S2/S3);
- upstream URLs must pass the SSRF policy (S4);
- LoC Chronicling America mapping must be exact (S5/S6);
- BSB in-document results must flow through the shared service
  schema and survive partial failure (S7/S8);
- the Retry-After gate must follow extensions (S10);
- multi-member gzip must survive arbitrary chunking (S11);
- the IIIF parser must not invent OCR links (S12);
- e-rara identity must be checked (S13).

All fixtures are local; no live network is used.
"""

import asyncio
import gzip
import time
import zlib

import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.bsb import BsbAdapter
from global_library_mcp.adapters.erara import EraraAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.http import (
    BudgetedTransport,
    BudgetExceeded,
    HttpBudget,
    _note_retry_after,
    check_dns_public,
    fetch_validated,
    get_within_domain,
    use_budget,
    validate_fetch_url,
)
from global_library_mcp.iiif import alto_to_text, hocr_title, parse_manifest
from global_library_mcp.registry import Registry
from global_library_mcp.service import LibraryService


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        pass


class ScriptedTransport(BudgetedTransport):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    async def _send(self, request):
        return self.handler(request)


# ------------------------------------------------------------ S4 SSRF


@pytest.mark.parametrize(
    "url",
    [
        "https://tile.loc.gov/text-services/x",  # allowed below
        "https://api.digitale-sammlungen.de/ocr/bsb1/1",
        "https://93.184.216.34/image.jpg",  # public IP literal
        "https://example.org:443/x",  # explicit default port
    ],
)
def test_validate_fetch_url_accepts_legitimate(url):
    assert validate_fetch_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://tile.loc.gov/x",  # not https
        "javascript:alert(1)",
        "data:text/html;base64,AAAA",
        "file:///etc/passwd",
        "https://user:pass@tile.loc.gov/x",  # embedded credentials
        "https://tile.loc.gov:8443/x",  # non-standard port
        "https://127.0.0.1/x",
        "https://10.0.0.5/x",
        "https://192.168.1.10/x",
        "https://169.254.169.254/latest/meta-data",  # link-local / metadata
        "https://[::1]/x",
        "https://[fe80::1]/x",
        "https://0.0.0.0/x",
        "https://2130706433/x",  # integer IP form for 127.0.0.1
        "https://0x7f000001/x",  # hex IP form
        "https://localhost/x",
        "https://foo.localhost/x",
    ],
)
def test_validate_fetch_url_refuses_unsafe(url):
    with pytest.raises(AdapterError):
        validate_fetch_url(url)


def test_validate_fetch_url_allowlist_is_exact_not_suffix():
    allowed = {"tile.loc.gov", "www.loc.gov"}
    assert validate_fetch_url("https://tile.loc.gov/x", allowed_hosts=allowed)
    for lookalike in (
        "https://evil-loc.gov/x",
        "https://loc.gov.evil.example/x",
        "https://nottile.loc.gov/x",
        "https://tile.loc.gov.evil.example/x",
    ):
        with pytest.raises(AdapterError):
            validate_fetch_url(lookalike, allowed_hosts=allowed)


def test_check_dns_public(monkeypatch):
    import global_library_mcp.http as http_mod

    monkeypatch.setattr(
        http_mod._socket,
        "getaddrinfo",
        lambda host, port, proto=0: [(2, 1, 6, "", ("93.184.216.34", port))],
    )
    check_dns_public("example.org")  # public: passes
    monkeypatch.setattr(
        http_mod._socket,
        "getaddrinfo",
        lambda host, port, proto=0: [(2, 1, 6, "", ("10.1.2.3", port))],
    )
    with pytest.raises(AdapterError):
        check_dns_public("example.org")
    # A mixed answer (one public, one private) is refused: the
    # connection could pick the private one.
    monkeypatch.setattr(
        http_mod._socket,
        "getaddrinfo",
        lambda host, port, proto=0: [
            (2, 1, 6, "", ("93.184.216.34", port)),
            (2, 1, 6, "", ("192.168.0.1", port)),
        ],
    )
    with pytest.raises(AdapterError):
        check_dns_public("example.org")


@pytest.mark.asyncio
async def test_fetch_validated_refuses_before_any_request():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AdapterError):
            await fetch_validated(client, "https://169.254.169.254/latest/meta-data")
        with pytest.raises(AdapterError):
            await fetch_validated(client, "https://tile.loc.gov/x", allowed_hosts={"www.loc.gov"})
    assert calls == []  # nothing was ever sent


@pytest.mark.asyncio
async def test_redirect_downgrade_and_private_target_refused():
    def handler(request):
        url = str(request.url)
        if url.endswith("/downgrade"):
            return httpx.Response(302, headers={"location": "http://archive.org/file"})
        if url.endswith("/private"):
            return httpx.Response(302, headers={"location": "https://192.168.0.9/file"})
        if url.endswith("/ok"):
            return httpx.Response(302, headers={"location": "https://archive.org/other"})
        return httpx.Response(200, text="done")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AdapterError):
            await get_within_domain(client, "https://archive.org/downgrade")
        with pytest.raises(AdapterError):
            await get_within_domain(client, "https://archive.org/private")
        response = await get_within_domain(client, "https://archive.org/ok")
        assert response.text == "done"


@pytest.mark.asyncio
async def test_redirect_strips_credentials_to_a_different_host():
    seen = {}

    def handler(request):
        url = str(request.url)
        if url.endswith("/start"):
            return httpx.Response(302, headers={"location": "https://dl.archive.org/file"})
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, text="done")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await get_within_domain(
            client, "https://archive.org/start", headers={"Authorization": "Bearer secret"}
        )
        assert response.text == "done"
    assert seen["authorization"] is None


# ------------------------------------------------------------ S2/S3 BSB


def _bsb_manifest(object_id="bsb00000001", pages=3, *, manifest_id=None, canvas_object=None, service_object=None, ocr_link=True, ocr_page=None):
    canvas_object = canvas_object or object_id
    service_object = service_object or object_id
    canvases = []
    for n in range(1, pages + 1):
        canvas = {
            "@id": f"https://api.digitale-sammlungen.de/iiif/presentation/v2/{canvas_object}/canvas/{n}",
            "label": f"{n} ({n:04d})",
            "images": [
                {
                    "resource": {
                        "@id": f"https://api.digitale-sammlungen.de/iiif/image/v2/{service_object}_{n:05d}/full/full/0/default.jpg",
                        "service": {"@id": f"https://api.digitale-sammlungen.de/iiif/image/v2/{service_object}_{n:05d}"},
                    }
                }
            ],
        }
        if ocr_link:
            canvas["seeAlso"] = [
                {
                    "@id": f"https://api.digitale-sammlungen.de/ocr/{object_id}/{ocr_page or n}",
                    "format": "text/vnd.hocr+html",
                }
            ]
        canvases.append(canvas)
    return {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": manifest_id or f"https://api.digitale-sammlungen.de/iiif/presentation/v2/{object_id}/manifest",
        "label": "Fixture Book",
        "license": "https://rightsstatements.org/vocab/NoC-NC/1.0/",
        "metadata": [{"label": "Date", "value": "1854"}],
        "sequences": [{"canvases": canvases}],
    }


def _bsb_client(manifest, *, image_body=b"\xff\xd8\xff\xe0jpeg", image_status=200, image_type="image/jpeg", fail_ocr_pages=()):
    def handler(request):
        url = str(request.url)
        if url.endswith("/manifest"):
            return httpx.Response(200, json=manifest)
        if "/ocr/" in url:
            n = int(url.rsplit("/", 1)[1])
            if n in fail_ocr_pages:
                return httpx.Response(500, text="boom")
            hocr = (
                f"<html><head><title>bsb00000001_{n:05d}</title></head><body>"
                f'<div class="ocr_page"><span class="ocr_line">'
                f'<span class="ocrx_word">Wasserwerk</span> <span class="ocrx_word">Text</span>'
                f"</span></div></body></html>"
            )
            return httpx.Response(200, text=hocr, headers={"content-type": "text/vnd.hocr+html"})
        if "/iiif/image/" in url:
            return httpx.Response(image_status, content=image_body, headers={"content-type": image_type})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_bsb_mapping_rejects_other_objects_canvas():
    async with _bsb_client(_bsb_manifest(canvas_object="bsb99999999")) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["canvas_belongs_to_object"] is False
    assert page["contents"]  # still usable as research material


@pytest.mark.asyncio
async def test_bsb_mapping_rejects_other_objects_image_service():
    async with _bsb_client(_bsb_manifest(service_object="bsb99999999")) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["image_service_belongs"] is False


@pytest.mark.asyncio
async def test_bsb_mapping_rejects_wrong_manifest_identity():
    manifest = _bsb_manifest(manifest_id="https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb99999999/manifest")
    async with _bsb_client(manifest) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["manifest_object_matches"] is False


@pytest.mark.asyncio
async def test_bsb_mapping_requires_the_manifest_ocr_link():
    async with _bsb_client(_bsb_manifest(ocr_link=False)) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["ocr_link_in_manifest_matches"] is False
    # The documented URL was still fetched - constructibility is
    # not proof, so the text arrives unverified.
    assert page["ocr_fetched"] is True


@pytest.mark.asyncio
async def test_bsb_mapping_rejects_ocr_link_for_another_page():
    async with _bsb_client(_bsb_manifest(ocr_page=2)) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["ocr_link_in_manifest_matches"] is False


@pytest.mark.asyncio
async def test_bsb_verify_agrees_with_page_text_and_checks_the_image():
    # Mapping is fine but the "image" is an HTML error page:
    # verify must not call that an original image.
    async with _bsb_client(
        _bsb_manifest(), image_body=b"<html><body>error</body></html>", image_type="text/html"
    ) as client:
        adapter = BsbAdapter(client)
        page = await adapter.get_page_text("bsb00000001@1")
        assert page["verified_mapping"] is True
        verified = await adapter.verify_original("bsb00000001@1")
    assert verified["checks"]["image_reachable"]["ok"] is False
    assert verified["status"] == "unverified"


@pytest.mark.asyncio
async def test_bsb_verify_never_verified_when_mapping_is_not():
    async with _bsb_client(_bsb_manifest(canvas_object="bsb99999999")) as client:
        adapter = BsbAdapter(client)
        page = await adapter.get_page_text("bsb00000001@1")
        assert page["verified_mapping"] is False
        verified = await adapter.verify_original("bsb00000001@1")
    assert verified["checks"]["image_reachable"]["ok"] is True  # image itself fine
    assert verified["status"] == "unverified"  # but the verdict follows the mapping


@pytest.mark.asyncio
async def test_bsb_search_schema_and_partial_results():
    async with _bsb_client(_bsb_manifest(pages=5), fail_ocr_pages=(3,)) as client:
        adapter = BsbAdapter(client)
        result = await adapter.search_in_document("bsb00000001", "Wasserwerk")
    entries = result["matches"]["list"]
    assert entries and entries[0]["id"] == "bsb00000001@1"
    assert entries[0]["page_id"] == "bsb00000001@1"
    assert entries[0]["mapping_status"] == "verified"
    assert result["partial_failures"], "the failed page must be reported"
    assert result["complete"] is False


@pytest.mark.asyncio
async def test_bsb_search_window_parameters():
    async with _bsb_client(_bsb_manifest(pages=10)) as client:
        result = await BsbAdapter(client).search_in_document("bsb00000001", "Wasserwerk", start_page=4, end_page=6)
    assert result["searched_range"] == [4, 6]
    assert result["pages_searched"] == 3
    assert result["complete"] is False  # a window is never the whole book


@pytest.mark.asyncio
async def test_bsb_search_keeps_partial_results_when_budget_runs_out():
    manifest = _bsb_manifest(pages=6)

    def handler(request):
        url = str(request.url)
        if url.endswith("/manifest"):
            return httpx.Response(200, json=manifest, request=request)
        n = int(url.rsplit("/", 1)[1])
        hocr = (
            f"<html><head><title>bsb00000001_{n:05d}</title></head><body>"
            '<div class="ocr_page"><span class="ocr_line">'
            '<span class="ocrx_word">Wasserwerk</span></span></div></body></html>'
        )
        return httpx.Response(200, text=hocr, request=request)

    async with httpx.AsyncClient(transport=ScriptedTransport(handler)) as client:
        adapter = BsbAdapter(client)
        with use_budget(HttpBudget(30, 3)):  # manifest + 2 OCR pages only
            result = await adapter.search_in_document("bsb00000001", "Wasserwerk")
    assert result["matches"]["list"], "hits found before the budget ran out are kept"
    assert result["complete"] is False
    assert result["partial_failures"]


@pytest.mark.asyncio
async def test_bsb_flows_through_the_service_schema():
    async with _bsb_client(_bsb_manifest(pages=3)) as client:
        service = LibraryService(client)
        result = await service.search_in_document("bsb", "bsb00000001", "Wasserwerk")
    entries = result["matches"]["list"]
    assert entries and entries[0]["id"] == "bsb00000001@1"
    assert entries[0]["mapping_status"] == "verified"
    assert "http_stats" in result


# ------------------------------------------------------------ S5/S6 LoC


_SEG = "/service/ndnp/dlc/batch_x/data/sn83030214/00175041539/1907010101/0003.xml"
_SVC = "service:ndnp:dlc:batch_x:data:sn83030214:00175041539:1907010101:0003"


def _loc_payload(**overrides):
    payload = {
        "segments": [{"url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=2"}],
        "segment_id": _SEG,
        "resource": {
            "fulltext_file": f"https://tile.loc.gov/text-services/word-coordinates-service?segment={_SEG}&format=alto_xml&full_text=1",
        },
        "page": [{"info": f"https://tile.loc.gov/image-services/iiif/{_SVC}/info.json"}],
        "item": {"id": "http://www.loc.gov/item/sn83030214/1907-01-01/ed-1/", "rights_advisory": ["<p>Public domain.</p>"]},
    }
    payload.update(overrides)
    return payload


def _loc_client(payload, *, text_map=None, info_id=None, image_status=200, image_body=b"\xff\xd8\xff\xe0jpeg"):
    def handler(request):
        url = str(request.url)
        if "tile.loc.gov/text-services" in url:
            return httpx.Response(200, json=text_map if text_map is not None else {_SEG: {"full_text": "Tribune page text"}})
        if url.endswith("/info.json"):
            return httpx.Response(200, json={"@id": info_id or f"https://tile.loc.gov/image-services/iiif/{_SVC}"})
        if "tile.loc.gov/image-services" in url:
            return httpx.Response(image_status, content=image_body, headers={"content-type": "image/jpeg"})
        if "www.loc.gov/resource/" in url:
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _loc_adapter(client):
    adapter = LocAdapter(client)
    adapter._wait_for_rate_limit = lambda: asyncio.sleep(0)
    return adapter


@pytest.mark.asyncio
async def test_loc_sp_is_compared_exactly_not_by_substring():
    payload = _loc_payload(
        segments=[{"url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=20"}]
    )
    async with _loc_client(payload) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["mapping_checks"]["segment_url_matches_seq"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_loc_multiple_segments_are_not_a_page_proof():
    payload = _loc_payload(
        segments=[
            {"url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=2"},
            {"url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=2"},
        ]
    )
    async with _loc_client(payload) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["mapping_checks"]["single_segment_for_seq"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_loc_missing_or_empty_ocr_is_not_success():
    async with _loc_client(_loc_payload(), text_map={}) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["contents"] is None
    assert page["ocr_available"] is False
    assert page["verified_mapping"] is False
    async with _loc_client(_loc_payload(), text_map={_SEG: {"full_text": "   "}}) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["ocr_available"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_loc_lookalike_fulltext_host_is_never_fetched():
    payload = _loc_payload()
    payload["resource"] = {
        "fulltext_file": f"https://evil-loc.gov/text-services/word-coordinates-service?segment={_SEG}&format=alto_xml&full_text=1"
    }
    fetched = []

    def handler(request):
        fetched.append(str(request.url))
        if "www.loc.gov/resource/" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json={_SEG: {"full_text": "should never be read"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["contents"] is None
    assert page["verified_mapping"] is False
    assert not any("evil-loc.gov" in url for url in fetched)


@pytest.mark.asyncio
async def test_loc_image_info_of_another_segment_fails_identity():
    payload = _loc_payload()
    payload["page"] = [{"info": "https://tile.loc.gov/image-services/iiif/service:ndnp:other:0009/info.json"}]
    async with _loc_client(payload) as client:
        page = await _loc_adapter(client).get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
    assert page["mapping_checks"]["image_info_belongs_to_segment"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_loc_verify_distinguishes_info_from_image():
    # info.json answers but the image itself is gone.
    async with _loc_client(_loc_payload(), image_status=404, image_body=b"not found") as client:
        verified = await _loc_adapter(client).verify_original("sn83030214/1907-01-01/ed-1/seq-2")
    assert verified["checks"]["image_service_reachable"]["ok"] is True
    assert verified["checks"]["image_reachable"]["ok"] is False
    assert verified["status"] == "unverified"
    # The service declares a different @id than the page payload.
    async with _loc_client(_loc_payload(), info_id="https://tile.loc.gov/image-services/iiif/someone-else") as client:
        verified = await _loc_adapter(client).verify_original("sn83030214/1907-01-01/ed-1/seq-2")
    assert verified["checks"]["image_service_identity_verified"]["ok"] is False
    assert verified["status"] == "unverified"


# ------------------------------------------------------------ S10 Retry-After


@pytest.mark.asyncio
async def test_retry_after_extension_is_followed_until_the_absolute_deadline():
    host = "gate-ext.example.org"
    sent_at = []

    def handler(request):
        sent_at.append(time.monotonic())
        return httpx.Response(200, text="ok")

    transport = ScriptedTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        _note_retry_after(host, 0.5)
        started = time.monotonic()

        async def extend_later():
            await asyncio.sleep(0.2)
            _note_retry_after(host, 1.6)  # a concurrent 429 extends the gate

        extender = asyncio.create_task(extend_later())
        await client.get(f"https://{host}/x")
        await extender
    assert sent_at and sent_at[0] - started >= 1.5, "the request must wait for the EXTENDED deadline"


@pytest.mark.asyncio
async def test_retry_after_beyond_the_send_window_is_refused_unsent():
    host = "gate-far.example.org"
    sent = []

    def handler(request):
        sent.append(1)
        return httpx.Response(200, text="ok")

    transport = ScriptedTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        _note_retry_after(host, 3600)
        with pytest.raises(AdapterError):
            await client.get(f"https://{host}/x")
    assert sent == []


# ------------------------------------------------------------ S11 gzip chunking


def _gzip_members(*payloads):
    return b"".join(gzip.compress(p) for p in payloads)


async def _fetch_chunked(chunks, *, budget=None, encoding="gzip"):
    transport = ScriptedTransport(
        lambda r: httpx.Response(200, headers={"content-encoding": encoding}, stream=ChunkStream(chunks), request=r)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(budget or HttpBudget(10, 10)):
            response = await client.get("https://example.org/x")
            return response


@pytest.mark.asyncio
async def test_multi_member_gzip_across_arbitrary_chunk_boundaries():
    payload = _gzip_members(b"Hello ", b"multi-member ", b"world" * 500)
    for size in (1, 3, 7, 64, 4096):
        chunks = [payload[i : i + size] for i in range(0, len(payload), size)]
        response = await _fetch_chunked(chunks)
        assert response.content == b"Hello multi-member " + b"world" * 500


@pytest.mark.asyncio
async def test_truncated_last_gzip_member_is_an_error():
    payload = _gzip_members(b"first member ok", b"second member is cut")[:-6]
    chunks = [payload[i : i + 5] for i in range(0, len(payload), 5)]
    with pytest.raises(httpx.DecodingError):
        await _fetch_chunked(chunks)


@pytest.mark.asyncio
async def test_garbage_after_final_gzip_member_is_an_error():
    payload = _gzip_members(b"clean") + b"trailing-garbage"
    with pytest.raises(httpx.DecodingError):
        await _fetch_chunked([payload])


@pytest.mark.asyncio
async def test_corrupt_gzip_crc_is_an_error():
    payload = bytearray(gzip.compress(b"integrity matters"))
    payload[-6] ^= 0xFF  # damage the CRC/ISIZE trailer area
    with pytest.raises(httpx.DecodingError):
        await _fetch_chunked([bytes(payload)])


@pytest.mark.asyncio
async def test_deflate_raw_and_zlib_forms():
    text = b"deflate payload " * 100
    raw = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    raw_bytes = raw.compress(text) + raw.flush()
    response = await _fetch_chunked([raw_bytes], encoding="deflate")
    assert response.content == text
    response = await _fetch_chunked([zlib.compress(text)], encoding="deflate")
    assert response.content == text


@pytest.mark.asyncio
async def test_cumulative_byte_cap_counts_across_responses():
    budget = HttpBudget(10, 10, max_total_bytes=3000)
    transport = ScriptedTransport(
        lambda r: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=ChunkStream([gzip.compress(b"x" * 2000)]), request=r)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(budget):
            await client.get("https://example.org/a")
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/b")
    assert budget.bytes_received > 3000  # received bytes stay counted


# ------------------------------------------------------------ S12 IIIF


def test_iiif_v2_service_list_and_multiple_images_and_sequences():
    payload = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": "https://example.org/manifest",
        "label": "Multi",
        "license": {"@id": "https://creativecommons.org/publicdomain/mark/1.0/"},
        "sequences": [
            {"canvases": [{"@id": "https://example.org/c/1", "images": [
                {"resource": {"@id": "https://example.org/img-a"}},
                {"resource": {"@id": "https://example.org/img-b", "service": [{"@id": "https://example.org/svc-b"}]}},
            ]}]},
            {"canvases": [{"@id": "https://example.org/c/2", "images": [
                {"resource": {"@id": "https://example.org/img-c", "service": {"@id": "https://example.org/svc-c"}}},
            ]}]},
        ],
    }
    manifest = parse_manifest(payload)
    assert manifest.license_url == "https://creativecommons.org/publicdomain/mark/1.0/"
    assert [c.canvas_id for c in manifest.canvases] == ["https://example.org/c/1", "https://example.org/c/2"]
    assert manifest.canvases[0].image_service_id == "https://example.org/svc-b"  # the image WITH a service wins
    assert manifest.canvases[1].image_service_id == "https://example.org/svc-c"


def test_iiif_v2_other_content_is_not_an_ocr_link():
    payload = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": "https://example.org/manifest",
        "label": "OC",
        "sequences": [{"canvases": [{"@id": "https://example.org/c/1",
                                     "otherContent": [{"@id": "https://example.org/list/1", "@type": "sc:AnnotationList"}]}]}],
    }
    canvas = parse_manifest(payload).canvases[0]
    assert canvas.ocr_urls == []
    assert canvas.other_content_urls == ["https://example.org/list/1"]


def test_iiif_v3_external_annotation_page_and_non_ocr_annotations():
    payload = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": "https://example.org/m3",
        "type": "Manifest",
        "label": {"en": ["V3"]},
        "items": [
            {"type": "AnnotationPage", "id": "https://example.org/not-a-canvas"},
            {
                "type": "Canvas",
                "id": "https://example.org/canvas/1",
                "items": [{"type": "AnnotationPage", "items": [
                    {"type": "Annotation", "motivation": "painting",
                     "body": {"type": "Choice", "items": [{"type": "Image", "id": "https://example.org/img/1",
                                                           "service": [{"type": "ImageService3", "id": "https://example.org/svc/1"}]}]}},
                ]}],
                "annotations": [
                    {"type": "AnnotationPage", "id": "https://example.org/external-page"},  # reference only
                    {"type": "AnnotationPage", "items": [
                        {"type": "Annotation", "motivation": "commenting",
                         "body": {"type": "TextualBody", "id": "https://example.org/note/1", "value": "a note"}},
                        {"type": "Annotation", "motivation": "supplementing",
                         "body": {"type": "TextualBody", "id": "https://example.org/ocr/1", "format": "text/plain"}},
                    ]},
                ],
            },
        ],
    }
    manifest = parse_manifest(payload)
    assert len(manifest.canvases) == 1
    canvas = manifest.canvases[0]
    assert canvas.image_service_id == "https://example.org/svc/1"  # via Choice
    assert canvas.ocr_urls == ["https://example.org/ocr/1"]  # commenting is not OCR


def test_alto_entity_declaration_refused_and_hocr_title_parsed():
    with pytest.raises(ValueError):
        alto_to_text('<?xml version="1.0"?><!DOCTYPE alto [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><alto/>')
    assert hocr_title("<html><head><title>bsb00000001_00005</title></head></html>") == "bsb00000001_00005"
    assert hocr_title("<html><body>no title here</body></html>") is None


# ------------------------------------------------------------ S13 e-rara


_OAI_HEAD = """<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<GetRecord><record>
<header{status}><identifier>{identifier}</identifier><setSpec>zut</setSpec></header>
<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Fixture Map</dc:title><dc:creator>Espeyin, F.</dc:creator>
<dc:date>1885</dc:date><dc:identifier>https://www.e-rara.ch/zut/content/titleinfo/30815284</dc:identifier>
<dc:identifier>https://doi.org/10.3931/e-rara-00000</dc:identifier>
<dc:rights>Public Domain</dc:rights><dc:rights>PDM 1.0</dc:rights>
</oai_dc:dc></metadata></record></GetRecord></OAI-PMH>"""


def _erara_client(body):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)))


@pytest.mark.asyncio
async def test_erara_identity_deleted_and_rights():
    body = _OAI_HEAD.format(status="", identifier="oai:www.e-rara.ch:30815284")
    async with _erara_client(body) as client:
        doc = await EraraAdapter(client).get_document("30815284")
    assert doc["doi"] == "10.3931/e-rara-00000"  # doi.org prefix stripped by the strict pattern
    assert doc["rights"]["values"] == ["Public Domain", "PDM 1.0"]  # nothing lost
    assert doc["holding_institution"] == "unknown"  # setSpec is not an institution name

    wrong = _OAI_HEAD.format(status="", identifier="oai:www.e-rara.ch:99999999")
    async with _erara_client(wrong) as client:
        with pytest.raises(AdapterError):
            await EraraAdapter(client).get_document("30815284")

    deleted = _OAI_HEAD.format(status=' status="deleted"', identifier="oai:www.e-rara.ch:30815284")
    async with _erara_client(deleted) as client:
        with pytest.raises(AdapterError):
            await EraraAdapter(client).get_document("30815284")


# ------------------------------------------------------------ S16 registry consistency


def test_registry_capabilities_match_the_adapters():
    from pathlib import Path

    registry = Registry(Path(__file__).resolve().parents[1] / "libraries.yaml")
    vocabulary = {
        "research_only", "implemented", "fixture_verified", "live_catalog_verified",
        "live_page_verified", "live_end_to_end_verified", "unavailable",
        "authentication_required", "unsupported", "bounded",
    }
    service = LibraryService(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
    for library_id, adapter in service.adapters.items():
        caps = registry.capabilities(library_id)
        statuses = caps.get("capability_status") or {}
        for status in statuses.values():
            assert status in vocabulary, f"{library_id}: unknown status {status}"
        if not adapter.supports_in_document_search:
            assert statuses.get("in_document_search") in (None, "unsupported", "unavailable")
    # ID-addressed adapters must never present as keyword-searchable.
    assert registry.capabilities("bsb")["capability_status"]["catalog_search"] == "unsupported"
    assert registry.capabilities("e-rara")["capability_status"]["catalog_search"] == "unsupported"
    assert registry.capabilities("bsb")["capability_status"]["page_ocr"] == "live_page_verified"
    assert registry.capabilities("e-rara")["capability_status"]["page_ocr"] == "unsupported"


# ------------------------------------------------------------ S17 comparison


def _bsb_two_doc_client():
    manifests = {
        "bsb00000001": _bsb_manifest("bsb00000001", pages=2),
        "bsb00000002": _bsb_manifest("bsb00000002", pages=2),
    }

    def handler(request):
        url = str(request.url)
        for object_id, manifest in manifests.items():
            if url.endswith(f"/{object_id}/manifest"):
                return httpx.Response(200, json=manifest)
        if "/ocr/" in url:
            object_id = url.split("/ocr/")[1].split("/")[0]
            n = int(url.rsplit("/", 1)[1])
            word = "Wasserwerk" if object_id == "bsb00000001" else "Dampfkessel"
            sentence = f"{word} und Betrieb der Anlage im neunzehnten Jahrhundert ausfuehrlich beschrieben"
            words = "".join(f'<span class="ocrx_word">{w}</span> ' for w in sentence.split())
            hocr = (
                f"<html><head><title>{object_id}_{n:05d}</title></head><body>"
                f'<div class="ocr_page"><span class="ocr_line">{words}</span></div></body></html>'
            )
            return httpx.Response(200, text=hocr, headers={"content-type": "text/vnd.hocr+html"})
        if "/iiif/image/" in url:
            return httpx.Response(200, content=b"\xff\xd8\xff\xe0jpeg", headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_compare_documents_with_bsb_via_the_service():
    async with _bsb_two_doc_client() as client:
        service = LibraryService(client)
        result = await service.compare_documents(
            [
                {"library_id": "bsb", "record_id": "bsb00000001"},
                {"library_id": "bsb", "record_id": "bsb00000002"},
            ],
            aspects=["Wasserwerk", "Dampfkessel"],
        )
    docs = result["documents"]
    assert all(doc["verified_pages"] >= 1 for doc in docs), "both BSB documents must contribute verified pages"
    assert result["status"] == "compared"
    assert result["rows"], "aspect comparison rows must be produced"


@pytest.mark.asyncio
async def test_compare_keeps_partial_failure_visible():
    async with _bsb_two_doc_client() as client:
        service = LibraryService(client)
        result = await service.compare_documents(
            [
                {"library_id": "bsb", "record_id": "bsb00000001"},
                {"library_id": "bsb", "record_id": "bsb00009999"},  # manifest 404s
            ],
            aspects=["Wasserwerk"],
        )
    docs = result["documents"]
    assert docs[0]["verified_pages"] >= 1, "the good document still compares"
    assert docs[1]["verified_pages"] == 0, "the failed document contributes nothing"
    assert result["status"] == "insufficient_evidence", "the shortfall is stated, not hidden"


def test_compare_aspect_distinguishes_partial_sharing():
    from global_library_mcp.compare import compare_aspect

    result = compare_aspect(
        "power",
        {
            "a": "Wasserwerk Dampfkessel Betrieb Anlage",
            "b": "Wasserwerk Dampfkessel Betrieb Anlage",
            "c": "Wasserwerk Seilbahn Betrieb Anlage",
        },
    )
    assert "wasserwerk" in result["shared_terms"]  # in all three
    partial_terms = {entry["term"] for entry in result["partial_terms"]}
    assert "dampfkessel" in partial_terms  # in a+b only: NOT shared, NOT unique
    assert "dampfkessel" not in result["shared_terms"]
