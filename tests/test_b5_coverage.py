"""b5 fixture tests: transport hardening (S12), the shared IIIF
module (S7), the BSB/MDZ adapter (S4), LoC Chronicling America
(S5), the e-rara OAI adapter (S6), registry integrity (S9),
German/French search variants (S10) and 2-4 document comparison
(S15). All fixtures are local; no live network is used, and
fixture success is never presented as live verification."""

import asyncio
import gzip
import json

import httpx
import pytest
import respx

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.bsb import BsbAdapter
from global_library_mcp.adapters.erara import EraraAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.compare import compare_aspect
from global_library_mcp.http import (
    BudgetedTransport,
    HttpBudget,
    get_within_domain,
    make_client,
    use_budget,
)
from global_library_mcp.iiif import alto_to_text, hocr_to_text, parse_manifest
from global_library_mcp.question import latin_variants
from global_library_mcp.registry import Registry


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


# ---------------------------------------------------------------- S12


@pytest.mark.asyncio
async def test_unsupported_content_encoding_refused():
    transport = ScriptedTransport(
        lambda r: httpx.Response(200, headers={"content-encoding": "zstd"}, stream=ChunkStream([b"garbage"]), request=r)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(HttpBudget(10, 10)):
            with pytest.raises(AdapterError) as excinfo:
                await client.get("https://example.org/x")
    assert "unsupported content-encoding" in str(excinfo.value)


@pytest.mark.asyncio
async def test_truncated_gzip_is_an_error_not_partial_text():
    payload = gzip.compress(b"hello world " * 100)[:20]  # cut mid-stream
    transport = ScriptedTransport(
        lambda r: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=ChunkStream([payload]), request=r)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(HttpBudget(10, 10)):
            with pytest.raises(httpx.DecodingError):
                await client.get("https://example.org/x")


@pytest.mark.asyncio
async def test_multi_member_gzip_decodes_fully():
    payload = gzip.compress(b"first ") + gzip.compress(b"second")
    transport = ScriptedTransport(
        lambda r: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=ChunkStream([payload]), request=r)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(HttpBudget(10, 10)):
            resp = await client.get("https://example.org/x")
    assert resp.text == "first second"


def test_client_offers_only_supported_encodings():
    client = make_client()
    assert client.headers["accept-encoding"] == "gzip, deflate"


@pytest.mark.asyncio
async def test_redirect_within_domain_followed_cross_domain_refused():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://dl.example.org/file"})
        if request.url.path == "/escape":
            return httpx.Response(302, headers={"location": "https://evil.example.net/file"})
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await get_within_domain(client, "https://example.org/start")
        assert resp.text == "ok"
        with pytest.raises(AdapterError):
            await get_within_domain(client, "https://example.org/escape")


# ---------------------------------------------------------------- S7


def _manifest_v2():
    return {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": "https://api.example.org/iiif/presentation/v2/bsb00000001/manifest",
        "label": "Test Book",
        "license": "https://creativecommons.org/publicdomain/mark/1.0/",
        "metadata": [{"label": "Date", "value": "1854"}],
        "sequences": [
            {
                "canvases": [
                    {
                        "@id": "https://api.example.org/iiif/presentation/v2/bsb00000001/canvas/1",
                        "label": "1 (0001)",
                        "images": [
                            {
                                "resource": {
                                    "@id": "https://api.example.org/iiif/image/v2/bsb00000001_00001/full/full/0/default.jpg",
                                    "service": {"@id": "https://api.example.org/iiif/image/v2/bsb00000001_00001"},
                                }
                            }
                        ],
                        "seeAlso": [{"@id": "https://api.example.org/ocr/bsb00000001/1", "format": "text/vnd.hocr+html", "profile": "http://kba.github.io/hocr-spec/1.2/"}],
                    }
                ]
            }
        ],
    }


def test_iiif_v2_parse():
    manifest = parse_manifest(_manifest_v2())
    assert manifest.version == 2
    assert manifest.license_url and "publicdomain" in manifest.license_url
    canvas = manifest.canvases[0]
    assert canvas.image_service_id.endswith("_00001")
    assert canvas.ocr_urls == ["https://api.example.org/ocr/bsb00000001/1"]


def test_iiif_v3_parse():
    payload = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": "https://example.org/iiif/3/manifest",
        "type": "Manifest",
        "label": {"en": ["V3 Book"]},
        "rights": "http://creativecommons.org/licenses/by/4.0/",
        "metadata": [{"label": {"en": ["Date"]}, "value": {"en": ["1901"]}}],
        "items": [
            {
                "id": "https://example.org/iiif/3/canvas/1",
                "type": "Canvas",
                "label": {"en": ["p. 1"]},
                "items": [
                    {
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "type": "Annotation",
                                "body": {
                                    "id": "https://example.org/img/1.jpg",
                                    "type": "Image",
                                    "service": [{"id": "https://example.org/iiif/image/1", "type": "ImageService2"}],
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    manifest = parse_manifest(payload)
    assert manifest.version == 3
    assert manifest.label == "V3 Book"
    assert manifest.metadata["Date"] == "1901"
    assert manifest.canvases[0].image_service_id == "https://example.org/iiif/image/1"


def test_alto_and_hocr_parsing():
    alto = (
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout><Page><PrintSpace>'
        '<TextBlock><TextLine><String CONTENT="Hello"/><String CONTENT="world"/></TextLine>'
        '<TextLine><String CONTENT="Second"/></TextLine></TextBlock></PrintSpace></Page></Layout></alto>'
    )
    assert alto_to_text(alto) == "Hello world\nSecond"
    with pytest.raises(Exception):
        alto_to_text("<alto><unclosed>")
    hocr = (
        '<html><body><div class="ocr_page" title="bsb00000001_00001">'
        '<span class="ocr_line"><span class="ocrx_word">Alpha</span> '
        '<span class="ocrx_word">beta</span></span></div></body></html>'
    )
    assert hocr_to_text(hocr) == "Alpha beta"


# ---------------------------------------------------------------- S4 BSB


def _bsb_handler(pages=3, *, bad_title=False, term_page=None):
    canvases = []
    for n in range(1, pages + 1):
        canvases.append(
            {
                "@id": f"https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb00000001/canvas/{n}",
                "label": f"{n} ({n:04d})",
                "images": [
                    {
                        "resource": {
                            "@id": f"https://api.digitale-sammlungen.de/iiif/image/v2/bsb00000001_{n:05d}/full/full/0/default.jpg",
                            "service": {"@id": f"https://api.digitale-sammlungen.de/iiif/image/v2/bsb00000001_{n:05d}"},
                        }
                    }
                ],
                "seeAlso": [{"@id": f"https://api.digitale-sammlungen.de/ocr/bsb00000001/{n}", "format": "text/vnd.hocr+html"}],
            }
        )
    manifest = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": "https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb00000001/manifest",
        "label": "Fixture Book",
        "license": "https://rightsstatements.org/vocab/NoC-NC/1.0/",
        "metadata": [
            {"label": "Creator", "value": "Author, A."},
            {"label": "Date", "value": "1854"},
            {"label": "Language", "value": "German"},
            {"label": "Holding institution", "value": "München, Bayerische Staatsbibliothek"},
        ],
        "sequences": [{"canvases": canvases}],
    }

    def handler(request):
        url = str(request.url)
        if url.endswith("/manifest"):
            return httpx.Response(200, json=manifest)
        if "/ocr/bsb00000001/" in url:
            n = int(url.rsplit("/", 1)[1])
            title = "bsb99999999_00001" if bad_title else f"bsb00000001_{n:05d}"
            word = "Wasserwerk" if term_page == n else "Seite"
            hocr = (
                f'<html><head><title>{title}</title></head><body>'
                f'<div class="ocr_page"><span class="ocr_line">'
                f'<span class="ocrx_word">{word}</span> <span class="ocrx_word">Text</span>'
                f"</span></div></body></html>"
            )
            return httpx.Response(200, text=hocr, headers={"content-type": "text/vnd.hocr+html"})
        if "/iiif/image/" in url:
            return httpx.Response(200, content=b"\xff\xd8\xff")
        return httpx.Response(404)

    return handler


def _bsb_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_bsb_document_page_and_verify():
    async with _bsb_client(_bsb_handler()) as client:
        adapter = BsbAdapter(client)
        doc = await adapter.get_document("bsb00000001")
        assert doc["page_count"] == 3
        assert doc["rights"]["statement"].startswith("NoC-NC")
        page = await adapter.get_page_text("bsb00000001@2")
        assert page["verified_mapping"] is True
        assert page["printed_page"] == "unknown"  # S14: the canvas label is not asserted to be the printed page
        assert page["canvas_label"] == "2 (0002)"
        assert "Seite Text" in page["contents"]
        verified = await adapter.verify_original("bsb00000001@2")
        assert verified["status"] == "verified"
        with pytest.raises(AdapterError):
            await adapter.search("Darwin")


@pytest.mark.asyncio
async def test_bsb_mapping_not_claimed_when_hocr_title_mismatches():
    async with _bsb_client(_bsb_handler(bad_title=True)) as client:
        page = await BsbAdapter(client).get_page_text("bsb00000001@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["hocr_title_matches"] is False


@pytest.mark.asyncio
async def test_bsb_in_document_search_is_bounded_and_reports_coverage():
    async with _bsb_client(_bsb_handler(pages=25, term_page=22)) as client:
        result = await BsbAdapter(client).search_in_document("bsb00000001", "Wasserwerk")
    assert result["pages_searched"] == 20
    assert result["total_pages"] == 25
    assert result["complete"] is False
    assert result["hits"] == []  # the term sits beyond the bounded coverage


# ---------------------------------------------------------------- S5 LoC


_LOC_SEGMENT_ID = "/service/ndnp/dlc/batch_x/data/sn83030214/00175041539/1907010101/0003.xml"
_LOC_SERVICE_ID = "service:ndnp:dlc:batch_x:data:sn83030214:00175041539:1907010101:0003"


def _loc_handler(request):
    url = str(request.url)
    if "tile.loc.gov/text-services" in url:
        return httpx.Response(200, json={_LOC_SEGMENT_ID: {"full_text": "Tribune page text"}})
    if url.endswith("/info.json"):
        return httpx.Response(200, json={"@id": f"https://tile.loc.gov/image-services/iiif/{_LOC_SERVICE_ID}"})
    if "tile.loc.gov/image-services" in url:
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0jpeg", headers={"content-type": "image/jpeg"})
    if "www.loc.gov/resource/" in url:
        payload = {
            "segments": [{"url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=2", "aka": ["http://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/?sp=2"]}],
            "segment_id": _LOC_SEGMENT_ID,
            "resource": {
                "fulltext_file": f"https://tile.loc.gov/text-services/word-coordinates-service?segment={_LOC_SEGMENT_ID}&format=alto_xml&full_text=1",
                "iiif_manifest_url": "https://www.loc.gov/resource/sn83030214/1907-01-01/ed-1/manifest.json",
                "image": f"https://tile.loc.gov/image-services/iiif/{_LOC_SERVICE_ID}/full/pct:3.125/0/default.jpg",
            },
            "page": [{"info": f"https://tile.loc.gov/image-services/iiif/{_LOC_SERVICE_ID}/info.json"}],
            "item": {"id": "http://www.loc.gov/item/sn83030214/1907-01-01/ed-1/", "title": "New-York tribune, January 1, 1907", "date": "1907-01-01", "rights_advisory": ["<p>Public domain.</p>"]},
            "viewer_pagination": {"total": 14},
        }
        return httpx.Response(200, json=payload)
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_loc_chronicling_page_text_and_verify():
    async with httpx.AsyncClient(transport=httpx.MockTransport(_loc_handler)) as client:
        adapter = LocAdapter(client)
        adapter._wait_for_rate_limit = lambda: asyncio.sleep(0)  # fixture speed only
        page = await adapter.get_page_text("sn83030214/1907-01-01/ed-1/seq-2")
        assert page["contents"] == "Tribune page text"
        assert page["verified_mapping"] is True
        verified = await adapter.verify_original("sn83030214/1907-01-01/ed-1/seq-2")
        assert verified["status"] == "verified"
        doc = await adapter.get_document("sn83030214/1907-01-01/ed-1")
        assert doc["page_count"] == 14
        with pytest.raises(AdapterError):
            await adapter.get_page_text("some-general-loc-item")


# ---------------------------------------------------------------- S6 e-rara


_OAI = """<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<GetRecord><record>
<header><identifier>oai:www.e-rara.ch:30815284</identifier><setSpec>zut</setSpec></header>
<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Fixture Map</dc:title><dc:creator>Espeyin, F.</dc:creator>
<dc:date>1885</dc:date><dc:identifier>https://www.e-rara.ch/zut/content/titleinfo/30815284</dc:identifier>
<dc:identifier>10.3931/e-rara-00000</dc:identifier><dc:rights>Public Domain</dc:rights>
</oai_dc:dc></metadata></record></GetRecord></OAI-PMH>"""


@pytest.mark.asyncio
async def test_erara_metadata_by_id_and_search_unsupported():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=_OAI))) as client:
        adapter = EraraAdapter(client)
        doc = await adapter.get_document("30815284")
        assert doc["title"] == "Fixture Map"
        assert doc["doi"] == "10.3931/e-rara-00000"
        assert doc["rights"]["statement"] == "Public Domain"
        with pytest.raises(AdapterError):
            await adapter.search("Karte")
        with pytest.raises(AdapterError):
            await adapter.get_document("not-a-number")


# ---------------------------------------------------------------- S9 registry


_ALLOWED_STATUSES = {
    "research_only", "implemented", "fixture_verified", "live_catalog_verified",
    "live_page_verified", "live_end_to_end_verified", "unavailable",
    "authentication_required", "unsupported", "bounded",
    # b8 final review: article-level OCR fetch (KB) is not page
    # verification, and unverified must be sayable explicitly.
    "live_article_ocr_fetched", "unverified",
}


def test_registry_has_no_duplicate_keys_and_consistent_statuses(tmp_path):
    registry = Registry("libraries.yaml")
    ids = [entry["id"] for entry in registry.list()]
    assert len(ids) == len(set(ids)) >= 25
    for entry in registry.list():
        for status in (entry.get("capability_status") or {}).values():
            assert status in _ALLOWED_STATUSES, (entry["id"], status)
    # implemented adapters and registry implementation_status agree
    service_ids = set(_LS.__init__.__defaults__ or ())  # placeholder, real check below
    import inspect

    src = inspect.getsource(_LS.__init__)
    for library_id in ("loc", "ndl", "gallica", "internet-archive", "ddb", "europeana", "bsb", "e-rara"):
        assert f'"{library_id}"' in src
        assert registry.get(library_id)["implementation_status"] == "implemented"
    # duplicate keys are refused, not silently overridden
    bad = tmp_path / "bad.yaml"
    bad.write_text("libraries:\n  - id: x\n    name: a\n    name: b\n", encoding="utf-8")
    with pytest.raises(Exception):
        Registry(bad)


# ---------------------------------------------------------------- S10 variants


def test_latin_variants_german_and_french():
    assert "Mueller" in latin_variants("Müller")
    assert "Muller" in latin_variants("Müller")
    assert any("ss" in v for v in latin_variants("Straße"))
    assert "Bibliotheque" in latin_variants("Bibliothèque")
    assert latin_variants("Darwin") == []


# ---------------------------------------------------------------- S15 compare


def test_compare_aspect_three_and_four_documents():
    texts = {
        "a": "steam engine water power steam",
        "b": "steam engine railway power",
        "c": "steam water railway factory",
    }
    result = compare_aspect("power", texts)
    assert "steam" in result["shared_terms"]
    assert result["documents_compared"] == 3
    assert set(result["unique_terms"]) == {"a", "b", "c"}
    four = dict(texts)
    four["d"] = "steam engine water power"
    result4 = compare_aspect("power", four)
    assert result4["documents_compared"] == 4
    assert "steam" in result4["shared_terms"]


def _mock_book(book, ocr):
    pid = book["id"]
    respx.get(f"https://lab.ndl.go.jp/dl/api/book/{pid}").mock(return_value=httpx.Response(200, json=book))
    respx.get("https://lab.ndl.go.jp/dl/api/page/search", params={"f-book": pid}).mock(
        return_value=httpx.Response(200, json={"list": [{"id": f"{pid}_10", "book": pid, "page": 10}], "hit": 1}))
    respx.get(f"https://lab.ndl.go.jp/dl/api/page/{pid}_10").mock(
        return_value=httpx.Response(200, json={"id": f"{pid}_10", "book": pid, "page": 10, "contents": ocr}))


@pytest.mark.asyncio
@respx.mock
async def test_compare_three_documents_service_level():
    books = [
        ({"id": "994120", "title": "A", "published": 1911}, "送電では水力發電と蒸氣機關が重要である。送電網が擴がった。"),
        ({"id": "1018770", "title": "B", "published": 1925}, "送電では水力發電と送電線の効率が重要である。送電網が擴がった。"),
        ({"id": "1886468", "title": "C", "published": 1930}, "送電では蒸氣機關と送電線が重要である。送電網が擴がった。"),
    ]
    for book, ocr in books:
        _mock_book(book, ocr)
    async with httpx.AsyncClient() as client:
        result = await _LS(client).compare_documents(
            [{"library_id": "ndl", "record_id": book["id"]} for book, _ in books], aspects=["送電"])
    assert result["status"] == "compared"
    row = result["rows"][0]
    assert row["shared_terms"], "3-document comparison must compute shared terms"
    assert set(row["unique_terms"]) == {"ndl|994120", "ndl|1018770", "ndl|1886468"}
