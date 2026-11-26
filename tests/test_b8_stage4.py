"""b8 Stage 4 fixture tests: DPLA (authentication-pending),
KB/Delpher (SRU + resolver OCR) and Japan Search (SPARQL +
JSON-LD), plus the fi/sv/nl lexicon additions.

Fixtures reproduce shapes confirmed live on 2026-11-26
(KB SRU record, KB resolver OCR XML, Japan Search SPARQL
bindings and item JSON-LD). Fixture success is not live
verification; the live runs are recorded separately in
docs/b8-live-verification.md.
"""

import json

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.dpla import DplaAdapter
from global_library_mcp.adapters.japan_search import JapanSearchAdapter, _sparql_literal
from global_library_mcp.adapters.kb import KbDelpherAdapter
from global_library_mcp import lexicon as lexicon_mod
from global_library_mcp.discovery import analyze_discovery_query
from global_library_mcp.expansion import QueryExpansionEngine


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- DPLA

DPLA_SEARCH = {
    "count": 1,
    "start": 0,
    "limit": 10,
    "docs": [
        {
            "id": "abc123def456",
            "sourceResource": {
                "title": ["Hydroelectric power in Finland"],
                "creator": ["Example, A."],
                "date": {"displayDate": "1912", "begin": "1912", "end": "1912"},
                "language": [{"name": "English", "iso639_3": "eng"}],
                "rights": ["http://rightsstatements.org/vocab/InC/1.0/"],
                "subject": [{"name": "Hydroelectric power"}],
                "type": ["text"],
            },
            "provider": {"@id": "https://dp.la/provider/hub", "name": "Example Hub"},
            "dataProvider": "Example State Library",
            "isShownAt": "https://example.org/item/42",
            "object": "https://example.org/thumb/42.jpg",
        }
    ],
}


@pytest.mark.asyncio
async def test_dpla_without_key_is_authentication_required(monkeypatch):
    monkeypatch.delenv("DPLA_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call may be attempted without a key")

    async with _client(handler) as client:
        adapter = DplaAdapter(client)
        assert adapter.authentication_status() == "authentication_required"
        with pytest.raises(AdapterError) as info:
            await adapter.search("hydroelectric", 5)
    assert "authentication_required" in str(info.value)
    assert info.value.retryable is False


@pytest.mark.asyncio
async def test_dpla_with_key_parses_and_separates_providers(monkeypatch):
    monkeypatch.setenv("DPLA_API_KEY", "x" * 32)
    capture: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        return httpx.Response(200, json=DPLA_SEARCH)

    async with _client(handler) as client:
        adapter = DplaAdapter(client)
        assert adapter.authentication_status() == "configured"
        results = await adapter.search("hydroelectric", 5)
        doc = await adapter.get_document("abc123def456")
    assert capture[0].url.params["api_key"] == "x" * 32
    assert results[0].title == "Hydroelectric power in Finland"
    assert results[0].rights.classification == "rightsstatements-in-copyright"
    # Hub and originating institution are never collapsed.
    assert doc["aggregation_provider"] == "Example Hub"
    assert doc["data_provider"] == "Example State Library"
    assert doc["landing_url"] == "https://example.org/item/42"


# ---------------------------------------------------------------- KB / Delpher

KB_SRU = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcx="http://krait.kb.nl/coop/tel/handbook/telterms.html">
<srw:version>1.2</srw:version>
<srw:numberOfRecords>32487</srw:numberOfRecords>
<srw:records>
<srw:record>
<srw:recordPacking>xml</srw:recordPacking>
<srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
<srw:recordData><dc:date>1937/08/28 00:00:00</dc:date><dc:identifier>http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr</dc:identifier><dc:publisher>[ s.n.]</dc:publisher><dc:source>KB C 248</dc:source><dc:title>Waterkracht-centrale.</dc:title><dc:type>artikel</dc:type><dcx:issued>1921</dcx:issued></srw:recordData>
<srw:recordPosition>1</srw:recordPosition>
</srw:record>
<srw:record>
<srw:recordPacking>xml</srw:recordPacking>
<srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
<srw:recordData><dc:date>1926/02/26 00:00:00</dc:date><dc:identifier>http://resolver.kb.nl/resolve?urn=MMKB27:017890102:mpeg21:a00018:ocr</dc:identifier><dc:publisher>De Avondpost</dc:publisher><dc:rights>Koninklijke Bibliotheek Den Haag</dc:rights><dc:source>Koninklijke Bibliotheek</dc:source><dc:title>Uitvoer van waterkracht.</dc:title><dc:type>artikel</dc:type><dcx:issued>1885-1940</dcx:issued></srw:recordData>
<srw:recordPosition>2</srw:recordPosition>
</srw:record>
</srw:records>
</srw:searchRetrieveResponse>
"""

KB_OCR = """<?xml version="1.0" encoding="UTF-8"?>
<text>
<title>Waterkracht-centrale.</title>
<p>Deze centrale werkt met waterkracht.</p>
<p>Tweede alinea over irrigatie.</p>
</text>
"""

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _kb_handler(ocr=KB_OCR, image_body=JPEG, image_type="image/jpeg"):
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "jsru.kb.nl":
            return httpx.Response(200, text=KB_SRU, headers={"content-type": "text/xml"})
        if host == "resolver.kb.nl":
            urn_param = request.url.params.get("urn", "")
            if urn_param.endswith(":ocr"):
                return httpx.Response(200, text=ocr, headers={"content-type": "text/xml"})
            if urn_param.endswith(":image"):
                return httpx.Response(200, content=image_body, headers={"content-type": image_type})
        return httpx.Response(404, text="not found")

    return handler


@pytest.mark.asyncio
async def test_kb_search_parses_sru_records():
    async with _client(_kb_handler()) as client:
        results = await KbDelpherAdapter(client).search("waterkracht", 10)
    assert [r.record_id for r in results] == [
        "ddd:010286065:mpeg21:a0141",
        "MMKB27:017890102:mpeg21:a00018",
    ]
    assert results[0].title == "Waterkracht-centrale."
    assert results[0].date == "1937-08-28"
    assert results[0].rights.statement == "unknown"  # no dc:rights on this record
    assert results[1].rights.statement == "Koninklijke Bibliotheek Den Haag"
    assert results[0].landing_url == "https://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141"


@pytest.mark.asyncio
async def test_kb_page_text_verified_by_title_correspondence():
    async with _client(_kb_handler()) as client:
        page = await KbDelpherAdapter(client).get_page_text("ddd:010286065:mpeg21:a0141")
    assert "waterkracht" in (page["contents"] or "")
    assert page["verified_mapping"] is True
    assert page["mapping_checks"]["title_matches"] is True
    assert page["record_id"] == "ddd:010286065:mpeg21:a0141"
    assert page["issue_urn"] == "ddd:010286065:mpeg21"


@pytest.mark.asyncio
async def test_kb_page_text_title_mismatch_unverified():
    bad = KB_OCR.replace("Waterkracht-centrale.", "Geheel andere titel.")
    async with _client(_kb_handler(ocr=bad)) as client:
        page = await KbDelpherAdapter(client).get_page_text("ddd:010286065:mpeg21:a0141")
    assert page["ocr_fetched"] is True
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_kb_verify_original():
    async with _client(_kb_handler()) as client:
        result = await KbDelpherAdapter(client).verify_original("ddd:010286065:mpeg21:a0141")
    assert result["status"] == "verified"
    async with _client(_kb_handler(image_body=b"<html>blocked</html>", image_type="text/html")) as client:
        result = await KbDelpherAdapter(client).verify_original("ddd:010286065:mpeg21:a0141")
    assert result["status"] == "unverified"


@pytest.mark.asyncio
async def test_kb_document_and_invalid_urn():
    async with _client(_kb_handler()) as client:
        adapter = KbDelpherAdapter(client)
        doc = await adapter.get_document("MMKB27:017890102:mpeg21:a00018")
        assert doc["publisher"] == "De Avondpost"
        assert doc["rights"]["metadata_licence"].startswith("CC0")
        with pytest.raises(AdapterError):
            await adapter.get_document("not-a-urn")


# ---------------------------------------------------------------- Japan Search

JPS_SPARQL = {
    "head": {"vars": ["s", "name"]},
    "results": {
        "bindings": [
            {"s": {"type": "uri", "value": "https://jpsearch.go.jp/data/dignl-12676713"},
             "name": {"type": "literal", "value": "浮世絵", "xml:lang": "ja"}},
            {"s": {"type": "uri", "value": "https://jpsearch.go.jp/data/dignl-12676713"},
             "name": {"type": "literal", "value": "Ukiyo-e", "xml:lang": "en-jp"}},
            {"s": {"type": "uri", "value": "https://jpsearch.go.jp/data/bibnl-75043510"},
             "name": {"type": "literal", "value": "浮世絵", "xml:lang": "ja"}},
        ]
    },
}

JPS_ITEM = {
    "@context": {},
    "@graph": [
        {
            "@id": "https://jpsearch.go.jp/data/dignl-12676713",
            "@type": "https://jpsearch.go.jp/term/type/図書",
            "label": "原色日本の美術 第18巻",
            "name": [{"@value": "原色日本の美術 第18巻", "@language": "ja"}],
            "creator": ["https://jpsearch.go.jp/entity/ncname/大久保純一"],
            "datePublished": "1994",
            "inLanguage": "http://id.loc.gov/vocabulary/iso639-2/jpn",
            "identifier": ["ISBN:4-09-663318-6", "info:ndljp/pid/12676713"],
        },
        {
            "@id": "https://jpsearch.go.jp/data/dignl-12676713#sourceinfo",
            "provider": "https://jpsearch.go.jp/entity/chname/NDLデジタルコレクション",
        },
        {
            "@id": "https://jpsearch.go.jp/data/dignl-12676713#accessinfo",
            "license": "http://rightsstatements.org/vocab/InC/1.0/",
            "provider": "https://jpsearch.go.jp/entity/chname/NDLデジタルコレクション",
            "description": ["アクセス制限: 国立国会図書館内限定公開"],
            "url": ["https://dl.ndl.go.jp/pid/12676713"],
        },
    ],
}


def _jps_handler(capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        if request.url.path == "/rdf/sparql":
            return httpx.Response(200, json=JPS_SPARQL)
        if request.url.path == "/data/dignl-12676713.json":
            return httpx.Response(200, json=JPS_ITEM)
        return httpx.Response(404, text="not found")

    return handler


def test_sparql_literal_escaping():
    assert _sparql_literal('a"b\\c') == 'a\\"b\\\\c'
    with pytest.raises(ValueError):
        _sparql_literal("bad\nterm")


@pytest.mark.asyncio
async def test_japan_search_search_dedupes_and_prefers_japanese():
    capture: list[httpx.Request] = []
    async with _client(_jps_handler(capture)) as client:
        results = await JapanSearchAdapter(client).search("浮世絵", 10)
    assert [r.record_id for r in results] == ["dignl-12676713", "bibnl-75043510"]
    assert results[0].title == "浮世絵"
    assert results[0].landing_url == "https://jpsearch.go.jp/item/dignl-12676713"
    query_sent = capture[0].url.params["query"]
    assert "schema.org/name" in query_sent
    assert 'CONTAINS(LCASE(STR(?name)), LCASE("浮世絵"))' in query_sent


@pytest.mark.asyncio
async def test_japan_search_document_rights_restrictions_and_handoff():
    async with _client(_jps_handler()) as client:
        doc = await JapanSearchAdapter(client).get_document("dignl-12676713")
    assert doc["title"] == "原色日本の美術 第18巻"
    assert doc["language"] == "ja"
    assert doc["provider"] == "NDLデジタルコレクション"
    assert doc["rights"]["classification"] == "rightsstatements-in-copyright"
    assert doc["access_restrictions"] == ["アクセス制限: 国立国会図書館内限定公開"]
    assert doc["ndl_pid"] == "12676713"
    assert doc["handoff_candidates"] == [
        {"library_id": "ndl", "record_id": "12676713", "basis": "info:ndljp/pid identifier in the Japan Search record"}
    ]
    # Provider URLs are data, not fetched by the adapter.
    assert doc["provider_urls"] == ["https://dl.ndl.go.jp/pid/12676713"]


@pytest.mark.asyncio
async def test_japan_search_document_identity_refused_for_wrong_id():
    async with _client(_jps_handler()) as client:
        with pytest.raises(AdapterError):
            await JapanSearchAdapter(client).get_document("dignl-99999999")


# ---------------------------------------------------------------- compare (section 15)

DIGI_OAI = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <responseDate>2026-11-26T00:00:00Z</responseDate>
 <GetRecord><record>
  <header><identifier>oai:digi.kansalliskirjasto.fi:123456</identifier><datestamp>2024-01-01</datestamp></header>
  <metadata><qdc xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:kk="http://www.kansalliskirjasto.fi/kk">
   <dc:title>Uusi Suometar 1900-01-02</dc:title><dc:date>1900-01-02</dc:date>
   <dc:language>fin</dc:language><dc:rights>Tekijänoikeuden alainen</dc:rights>
   <kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/pdf" type="application/pdf" />
   <kk:checksum filetype="application/xml+alto" pagenumber="1" value="abc123" />
  </qdc></metadata>
 </record></GetRecord>
</OAI-PMH>
"""

DIGI_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description><sourceImageInformation><fileName>123456_0001.jp2</fileName></sourceImageInformation></Description>
 <Layout><Page ID="Page1" PHYSICAL_IMG_NR="1"><PrintSpace>
 <TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="Suomen" /><String CONTENT="historia" /></TextLine></TextBlock>
 <TextBlock ID="b2"><TextLine ID="l2"><String CONTENT="vesivoima" /><String CONTENT="ja" /><String CONTENT="teollisuus" /></TextLine></TextBlock>
 </PrintSpace></Page></Layout>
</alto>
"""


@pytest.mark.asyncio
async def test_compare_kb_and_digi_cross_language():
    kb_handler = _kb_handler()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "digi.kansalliskirjasto.fi":
            path = request.url.path
            if path == "/interfaces/OAI-PMH":
                return httpx.Response(200, text=DIGI_OAI, headers={"content-type": "text/xml"})
            if path.endswith("/page-1.xml"):
                return httpx.Response(200, text=DIGI_ALTO, headers={"content-type": "text/xml"})
            return httpx.Response(404, text="not found")
        return kb_handler(request)

    async with _client(handler) as client:
        service = _LS(client)
        result = await service.compare_documents(
            [
                {"library_id": "kb-delpher", "record_id": "ddd:010286065:mpeg21:a0141"},
                {"library_id": "finland-nl-digi", "record_id": "123456"},
            ],
            aspects=["waterkracht", "vesivoima"],
        )
    assert result["status"] == "compared"
    docs = {(d["library_id"], d["record_id"]): d for d in result["documents"]}
    assert docs[("kb-delpher", "ddd:010286065:mpeg21:a0141")]["verified_pages"] >= 1
    assert docs[("finland-nl-digi", "123456")]["verified_pages"] >= 1
    rows = {row["aspect"]: row for row in result["rows"]}
    kb_key = "kb-delpher|ddd:010286065:mpeg21:a0141"
    digi_key = "finland-nl-digi|123456"
    assert rows["waterkracht"]["documents"][kb_key]["found"] is True
    assert rows["waterkracht"]["documents"][digi_key]["found"] is False
    assert rows["vesivoima"]["documents"][digi_key]["found"] is True
    assert rows["vesivoima"]["documents"][kb_key]["found"] is False
    assert all(row["semantic_comparison"] == "not_checked" for row in result["rows"])


@pytest.mark.asyncio
async def test_kb_search_in_document_single_page_unit():
    async with _client(_kb_handler()) as client:
        adapter = KbDelpherAdapter(client)
        hit = await adapter.search_in_document("ddd:010286065:mpeg21:a0141", "waterkracht")
        miss = await adapter.search_in_document("ddd:010286065:mpeg21:a0141", "stoommachine")
    assert hit["matches"]["list"][0]["page_id"] == "ddd:010286065:mpeg21:a0141"
    assert hit["complete"] is True and hit["total_pages"] == 1
    assert miss["matches"]["list"] == []


# ---------------------------------------------------------------- lexicon fi/sv/nl


def test_lexicon_has_fi_sv_nl_labels_with_unverified_status():
    data = lexicon_mod.load_lexicon()
    by_id = {c["concept_id"]: c for c in data["concepts"]}
    hydro = by_id["concept:hydroelectric-power"]
    assert hydro["labels"]["fi"] == ["vesivoima"]
    assert hydro["labels"]["sv"] == ["vattenkraft"]
    assert hydro["labels"]["nl"] == ["waterkracht"]
    assert hydro["verification_status"] == "unverified"
    assert "concept:independence" in by_id
    assert by_id["concept:independence"]["labels"]["fi"] == ["itsenäisyys"]


def test_expansion_generates_finnish_variant_for_japanese_query():
    plan = QueryExpansionEngine().expand(
        analyze_discovery_query("水力発電の歴史"), mode="deep"
    )
    texts = {(v["language"], v["text"]) for v in plan["variants"]}
    assert ("fi", "vesivoima") in texts
    assert ("sv", "vattenkraft") in texts
    # This query matches THREE concepts (hydroelectric power,
    # water power, history), so under the deep cap of 14 the
    # last language in the interleave (nl) is the one that
    # drops; with two matched concepts it fits, as the railway
    # query shows. The cap is a real budget, not raised to hide
    # this (brief section 12); the behaviour is recorded in
    # docs/b8-evaluation.md.
    plan2 = QueryExpansionEngine().expand(
        analyze_discovery_query("鉄道の歴史"), mode="deep"
    )
    texts2 = {(v["language"], v["text"]) for v in plan2["variants"]}
    assert ("nl", "spoorweg") in texts2
    assert ("fi", "rautatie") in texts2
