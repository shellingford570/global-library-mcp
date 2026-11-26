"""b8 Stage 3 fixture tests: the NLF Digi adapter and the
Finna -> Digi handoff.

All fixtures are local. Fixture success is NOT live
verification: digi.kansalliskirjasto.fi was unreachable from
the development network on 2026-11-26, which is recorded in
docs/b8-live-verification.md.
"""

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.digi import DigiAdapter
from global_library_mcp.adapters.finna import FinnaAdapter
from global_library_mcp.handoff import extract_digi_candidate, titles_correspond

OAI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <responseDate>2026-11-26T00:00:00Z</responseDate>
 <request verb="GetRecord">https://digi.kansalliskirjasto.fi/interfaces/OAI-PMH</request>
 <GetRecord>
  <record>
   <header><identifier>oai:digi.kansalliskirjasto.fi:123456</identifier><datestamp>2024-01-01</datestamp></header>
   <metadata>
    <qdc xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:kk="http://www.kansalliskirjasto.fi/kk">
     <dc:title>Uusi Suometar 1900-01-02</dc:title>
     <dc:date>1900-01-02</dc:date>
     <dc:language>fin</dc:language>
     <dc:publisher>Uusi Suometar</dc:publisher>
     <dc:rights>Tekijänoikeuden alainen</dc:rights>
     <kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/pdf" type="application/pdf" />
     <kk:file bundle="THUMBNAIL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/thumbnail/1" type="image/jpeg" />
     <kk:checksum filetype="application/xml+alto" pagenumber="1" value="abc123" />
     <kk:checksum filetype="application/xml+alto" pagenumber="2" value="def456" />
    </qdc>
   </metadata>
  </record>
 </GetRecord>
</OAI-PMH>
"""

ALTO_PAGE1 = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description>
  <sourceImageInformation><fileName>123456_0001.jp2</fileName></sourceImageInformation>
 </Description>
 <Layout>
  <Page ID="Page1" PHYSICAL_IMG_NR="1">
   <PrintSpace>
    <TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="Suomen" /><String CONTENT="historia" /></TextLine></TextBlock>
    <TextBlock ID="b2"><TextLine ID="l2"><String CONTENT="vesivoima" /><String CONTENT="ja" /><String CONTENT="teollisuus" /></TextLine></TextBlock>
   </PrintSpace>
  </Page>
 </Layout>
</alto>
"""

ALTO_PAGE2 = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description>
  <sourceImageInformation><fileName>123456_0002.jp2</fileName></sourceImageInformation>
 </Description>
 <Layout>
  <Page ID="Page2" PHYSICAL_IMG_NR="2">
   <PrintSpace>
    <TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="Toinen" /><String CONTENT="sivu" /></TextLine></TextBlock>
   </PrintSpace>
  </Page>
 </Layout>
</alto>
"""

# ALTO whose internal signals belong to a DIFFERENT page and
# binding: the text must still come back, but unverified.
ALTO_WRONG = ALTO_PAGE1.replace('PHYSICAL_IMG_NR="1"', 'PHYSICAL_IMG_NR="7"').replace("123456_0001", "999999_0007")

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _digi_handler(alto1=ALTO_PAGE1, image_body=JPEG, image_type="image/jpeg"):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/interfaces/OAI-PMH":
            return httpx.Response(200, text=OAI_XML, headers={"content-type": "text/xml"})
        if path.endswith("/page-1.xml"):
            return httpx.Response(200, text=alto1, headers={"content-type": "text/xml"})
        if path.endswith("/page-2.xml"):
            return httpx.Response(200, text=ALTO_PAGE2, headers={"content-type": "text/xml"})
        if "/image/" in path:
            return httpx.Response(200, content=image_body, headers={"content-type": image_type})
        return httpx.Response(404, text="not found")

    return handler


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_get_document_identity_genre_and_page_count():
    async with _client(_digi_handler()) as client:
        doc = await DigiAdapter(client).get_document("123456")
    assert doc["record_id"] == "123456"
    assert doc["title"] == "Uusi Suometar 1900-01-02"
    assert doc["genre"] == "sanomalehti"  # from the record's own file links
    assert doc["page_count"] == 2
    assert doc["rights"]["statement"] == "Tekijänoikeuden alainen"
    assert doc["landing_url"] == "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456"


@pytest.mark.asyncio
async def test_get_document_identity_mismatch_refused():
    async with _client(_digi_handler()) as client:
        with pytest.raises(AdapterError) as info:
            await DigiAdapter(client).get_document("999999")
    assert info.value.retryable is False


@pytest.mark.asyncio
async def test_search_is_unsupported_with_reason():
    async with _client(_digi_handler()) as client:
        with pytest.raises(AdapterError) as info:
            await DigiAdapter(client).search("Suomen historia", 5)
    assert "Finna" in str(info.value)


@pytest.mark.asyncio
async def test_page_text_verified_by_alto_signals():
    async with _client(_digi_handler()) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["record_id"] == "123456"
    assert "Suomen" in (page["contents"] or "")
    assert page["ocr_nonempty"] is True
    assert page["verified_mapping"] is True
    assert page["mapping_checks"]["page_nr_matches"] is True
    assert page["mapping_checks"]["filename_mentions_binding"] is True
    assert page["image_url"] == "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/image/1"


@pytest.mark.asyncio
async def test_page_text_wrong_alto_signals_unverified():
    async with _client(_digi_handler(alto1=ALTO_WRONG)) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["ocr_fetched"] is True
    assert page["contents"]  # text still returned as research material
    assert page["verified_mapping"] is False
    assert page["page_identity_verified"] is False


@pytest.mark.asyncio
async def test_verify_original_verified():
    async with _client(_digi_handler()) as client:
        result = await DigiAdapter(client).verify_original("123456@1")
    assert result["status"] == "verified"
    assert result["checks"]["image_reachable"]["ok"] is True


@pytest.mark.asyncio
async def test_verify_original_html_image_is_not_an_original():
    async with _client(_digi_handler(image_body=b"<html>login</html>", image_type="text/html")) as client:
        result = await DigiAdapter(client).verify_original("123456@1")
    assert result["status"] == "unverified"
    assert result["checks"]["image_reachable"]["ok"] is False


@pytest.mark.asyncio
async def test_search_in_document_bounded_with_coverage():
    async with _client(_digi_handler()) as client:
        result = await DigiAdapter(client).search_in_document("123456", "historia")
    assert result["total_pages"] == 2
    assert result["pages_searched"] == 2
    assert result["complete"] is True
    matches = result["matches"]["list"]
    assert [m["page_id"] for m in matches] == ["123456@1"]
    assert matches[0]["mapping_status"] == "verified"
    assert "historia" in matches[0]["snippet"]


# -- Finna -> Digi handoff -------------------------------------------


def _finndoc(links):
    return {"provider_links": links, "data_source": "kansalliskirjasto"}


def test_handoff_candidate_from_digi_link():
    doc = _finndoc(
        [
            {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456?page=1", "host": "digi.kansalliskirjasto.fi"},
            {"url": "https://example.invalid/item/9", "host": "example.invalid"},
        ]
    )
    candidate = extract_digi_candidate(doc)
    assert candidate["status"] == "candidate"
    assert candidate["binding_id"] == "123456"
    assert candidate["genre"] == "sanomalehti"


def test_handoff_ambiguous_bindings_refused():
    doc = _finndoc(
        [
            {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456"},
            {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/789012"},
        ]
    )
    assert extract_digi_candidate(doc)["status"] == "refused_ambiguous"


def test_handoff_lookalike_host_is_not_a_candidate():
    doc = _finndoc(
        [
            {"url": "https://digi.kansalliskirjasto.fi.evil.example/sanomalehti/binding/123456"},
            {"url": "http://digi.kansalliskirjasto.fi/sanomalehti/binding/123456"},
            {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/item/123456"},
        ]
    )
    assert extract_digi_candidate(doc)["status"] == "no_candidate"


@pytest.mark.asyncio
async def test_finna_to_digi_end_to_end_fixture_journey():
    finna_record = {
        "resultCount": 1,
        "records": [
            {
                "id": "kansalliskirjasto.123456",
                "title": "Uusi Suometar",
                "usageRights": [],
                "languages": ["fin"],
                "formats": [{"value": "0/Journal/", "translated": "Lehti"}],
                "buildings": [{"value": "0/Kansalliskirjasto/", "translated": "Kansalliskirjasto"}],
                "onlineUrls": [
                    {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456", "text": "Digi"}
                ],
                "year": 1900,
            }
        ],
        "status": "OK",
    }

    def finna_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=finna_record)

    async with _client(finna_handler) as finna_client:
        finndoc = await FinnaAdapter(finna_client).get_document("kansalliskirjasto.123456")
    candidate = extract_digi_candidate(finndoc)
    assert candidate["status"] == "candidate"
    async with _client(_digi_handler()) as digi_client:
        digidoc = await DigiAdapter(digi_client).get_document(candidate["binding_id"])
        page = await DigiAdapter(digi_client).get_page_text(f"{candidate['binding_id']}@1")
    # Bibliographic correspondence between the platform record
    # and the provider record is checked, not assumed.
    assert titles_correspond(finndoc["title"], digidoc["title"])
    assert digidoc["genre"] == candidate["genre"]
    assert page["verified_mapping"] is True
