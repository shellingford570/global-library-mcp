"""b8 Stage 2 fixture tests: the Finna adapter.

Fixtures reproduce the two response shapes actually observed
from the live API on 2026-11-26 (facet entries as {value,
translated} objects, and as plain strings). Fixture success is
NOT live verification: from the development network
api.finna.fi answers a Cloudflare bot challenge (403), and the
403 test below pins that this surfaces as a normal
non-retryable error with no evasion.
"""

import json

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.finna import FinnaAdapter

# Shape A: facet entries as objects (direct observation,
# 2026-11-26 20:27 JST).
SEARCH_A = {
    "resultCount": 530965,
    "records": [
        {
            "id": "helle.687105",
            "title": "Suomen historia",
            "usageRights": [],
            "languages": ["fin"],
            "formats": [
                {"value": "0/Book/", "translated": "Kirja"},
                {"value": "1/Book/Book/", "translated": "Kirja"},
            ],
            "buildings": [
                {"value": "0/Helle/", "translated": "Helle-kirjastot"},
                {"value": "1/Helle/PNK/", "translated": "Pornainen"},
                {"value": "2/Helle/PNK/PK/", "translated": "Pornaisten kunnankirjasto"},
            ],
            "authors": {"primary": {"Historiankirjoittaja, Esimerkki": {"role": "kirjoittaja"}}},
            "year": 2020,
        },
        {
            "id": "helka.997595663506253",
            "title": "Suomen historia",
            "usageRights": [],
            "languages": ["fin"],
            "formats": [{"value": "0/Book/", "translated": "Kirja"}],
            "buildings": [{"value": "0/Helka/", "translated": "Helsingin yliopiston kirjasto"}],
        },
    ],
    "status": "OK",
}

# Shape B: facet entries as plain strings (specialist
# observation, 2026-11-26 20:26 JST).
SEARCH_B = {
    "resultCount": 530965,
    "records": [
        {
            "id": "helle.687105",
            "title": "Suomen historia",
            "usageRights": ["0/Paikalliskokoelma"],
            "languages": ["fin"],
            "formats": ["0/Book/"],
            "buildings": [{"value": "1/HelMet/", "translated": "HelMet-kirjastot"}],
        }
    ],
    "status": "OK",
}

RECORD_DIGI = {
    "resultCount": 1,
    "records": [
        {
            "id": "kansalliskirjasto.123456",
            "title": "Uusi Suometar",
            "usageRights": [],
            "languages": ["fin"],
            "formats": [{"value": "0/Journal/", "translated": "Lehti"}],
            "buildings": [
                {"value": "0/Kansalliskirjasto/", "translated": "Kansalliskirjasto"},
            ],
            "institutions": [
                {"value": "0/Kansalliskirjasto/", "translated": "Kansalliskirjasto"}
            ],
            "onlineUrls": [
                {
                    "url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456",
                    "text": "Digi",
                    "source": "Kansalliskirjasto",
                },
                {
                    "url": "https://example.invalid/some-aggregator/item/9",
                    "text": "Aggregator copy",
                },
            ],
            "year": 1900,
        }
    ],
    "status": "OK",
}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_handler(payload, capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(200, json=payload)

    return handler


@pytest.mark.asyncio
async def test_search_object_shape_facets():
    async with _client(_json_handler(SEARCH_A)) as client:
        results = await FinnaAdapter(client).search("Suomen historia", 10)
    assert len(results) == 2
    first = results[0]
    assert first.library_id == "finna"
    assert first.record_id == "helle.687105"
    assert first.title == "Suomen historia"
    assert first.language == "fi"  # "fin" normalised
    assert first.date == "2020"
    assert first.author == "Historiankirjoittaja, Esimerkki"
    assert first.landing_url == "https://www.finna.fi/Record/helle.687105"
    # Empty usageRights means NO statement was made: unknown,
    # never permission (the CC0 metadata licence is not the
    # item's licence).
    assert first.rights.statement == "unknown"
    assert first.rights.classification is None


@pytest.mark.asyncio
async def test_search_string_shape_facets_and_rights_label():
    async with _client(_json_handler(SEARCH_B)) as client:
        results = await FinnaAdapter(client).search("Suomen historia", 10)
    assert len(results) == 1
    rights = results[0].rights
    # Depth prefix stripped; the institutional label is kept
    # verbatim and NOT upgraded into a licence classification.
    assert rights.statement == "Paikalliskokoelma"
    assert rights.classification is None
    assert "not a licence" in (rights.source or "")


@pytest.mark.asyncio
async def test_search_typed_params_and_filters():
    capture: list[httpx.Request] = []
    async with _client(_json_handler(SEARCH_A, capture)) as client:
        await FinnaAdapter(client).search_typed(
            "Kalevala",
            search_type="Author",
            page=3,
            year="1900",
            language="swe",
            format_value="0/Book/",
        )
    url = capture[0].url
    assert url.params["lookfor"] == "Kalevala"
    assert url.params["type"] == "Author"
    assert url.params["page"] == "3"
    filters = url.params.get_list("filter[]")
    assert "search_daterange_mv:1900" in filters
    assert "language:sv" in filters  # "swe" normalised to ISO 639-1
    assert "format:0/Book/" in filters
    assert "id" in url.params.get_list("field[]")
    assert "usageRights" in url.params.get_list("field[]")


@pytest.mark.asyncio
async def test_search_page_reports_total_count():
    async with _client(_json_handler(SEARCH_A)) as client:
        page = await FinnaAdapter(client).search_page("Suomen historia", limit=2, page=1)
    assert page["result_count"] == 530965
    assert len(page["results"]) == 2


@pytest.mark.asyncio
async def test_get_document_holding_provider_and_handoff_candidates():
    async with _client(_json_handler(RECORD_DIGI)) as client:
        doc = await FinnaAdapter(client).get_document("kansalliskirjasto.123456")
    assert doc["record_id"] == "kansalliskirjasto.123456"
    assert doc["platform"] == "finna"
    assert doc["data_source"] == "kansalliskirjasto"
    assert doc["holding_institution"] == "Kansalliskirjasto"
    assert doc["provider_institutions"] == ["Kansalliskirjasto"]
    assert doc["rights"]["metadata_licence"].startswith("CC0")
    assert doc["rights"]["statement"] == "unknown"
    # The Digi link is a structural handoff candidate; the
    # arbitrary aggregator host is data only, never a candidate,
    # and neither URL was fetched by the adapter.
    candidates = doc["handoff_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["host"] == "digi.kansalliskirjasto.fi"
    assert candidates[0]["handoff_library_id"] == "finland-nl-digi"
    assert len(doc["provider_links"]) == 2


@pytest.mark.asyncio
async def test_get_document_buildings_hierarchy_deepest_is_holder():
    async with _client(_json_handler(SEARCH_A)) as client:
        doc = await FinnaAdapter(client).get_document("helle.687105")
    assert doc["holding_institution"] == "Pornaisten kunnankirjasto"
    assert doc["holding_consortium"] == "Helle-kirjastot"


@pytest.mark.asyncio
async def test_get_document_identity_mismatch_refused():
    async with _client(_json_handler(SEARCH_A)) as client:
        with pytest.raises(AdapterError) as info:
            await FinnaAdapter(client).get_document("helle.999999")
    assert info.value.retryable is False


@pytest.mark.asyncio
async def test_bot_challenge_403_is_plain_non_retryable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Just a moment...")

    async with _client(handler) as client:
        with pytest.raises(AdapterError) as info:
            await FinnaAdapter(client).search("Suomen historia", 5)
    assert info.value.retryable is False


@pytest.mark.asyncio
async def test_service_integration_opt_in_only():
    async with _client(_json_handler(SEARCH_A)) as client:
        service = _LS(client)
        response = await service.search("Suomen historia", ["finna"], 10)
        assert [r.record_id for r in response.results] == [
            "helle.687105",
            "helka.997595663506253",
        ]
        assert response.queried_libraries == ["finna"]
        # Opt-in: a default search must not query Finna at all.
        default_response = await service.search("Suomen historia", None, 10)
        assert "finna" not in default_response.queried_libraries
