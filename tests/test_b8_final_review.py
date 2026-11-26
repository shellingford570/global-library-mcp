"""b8 final review: regression tests for the external-review
findings (strict Digi/KB identity, handoff provider checks,
rights trust model, restore safety, reverify safety, rights
URI parsing). Each test names the review section it pins.
Fixture success is NOT live verification."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.adapters.digi import DigiAdapter
from global_library_mcp.adapters.dpla import DplaAdapter
from global_library_mcp.adapters.japan_search import _rights_classification as js_classify
from global_library_mcp.adapters.kb import (KbDelpherAdapter, _is_urn,
                                            _urn_from_identifier,
                                            cql_keyword_query)
from global_library_mcp.handoff import extract_digi_candidate
from global_library_mcp.rights_uri import parse_rights_uri
from global_library_mcp.workspace import policy
from global_library_mcp.workspace.store import WorkspaceStore
import global_library_mcp.web.server as server_mod
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ================================================================ Digi (sections 3, 4, 6)

OAI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <GetRecord><record>
  <header><identifier>oai:digi.kansalliskirjasto.fi:123456</identifier></header>
  <metadata>
   <qdc xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:kk="http://www.kansalliskirjasto.fi/kk">
    <dc:title>Uusi Suometar 1900-01-02</dc:title><dc:date>1900-01-02</dc:date>
    <dc:rights>Tekijänoikeuden alainen</dc:rights>
    <kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/pdf" type="application/pdf" />
    <kk:checksum filetype="application/xml+alto" pagenumber="1" value="abc" />
    <kk:checksum filetype="application/xml+alto" pagenumber="2" value="def" />
   </qdc>
  </metadata>
 </record></GetRecord>
</OAI-PMH>
"""


def _alto(filename, nr, text="Suomen historia", extra_pages=""):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description><sourceImageInformation><fileName>{filename}</fileName></sourceImageInformation></Description>
 <Layout><Page ID="P1" PHYSICAL_IMG_NR="{nr}"><PrintSpace>
 <TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="{text}" /></TextLine></TextBlock>
 </PrintSpace></Page>{extra_pages}</Layout>
</alto>
"""


def _digi_handler(alto_by_page, oai=OAI_XML):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/interfaces/OAI-PMH":
            return httpx.Response(200, text=oai, headers={"content-type": "text/xml"})
        m = re.search(r"/page-(\d+)\.xml$", path)
        if m and int(m.group(1)) in alto_by_page:
            return httpx.Response(200, text=alto_by_page[int(m.group(1))],
                                  headers={"content-type": "text/xml"})
        if "/image/" in path:
            return httpx.Response(200, content=b"\xff\xd8\xff\xe0" + b"\x00" * 32,
                                  headers={"content-type": "image/jpeg"})
        return httpx.Response(404, text="not found")
    return handler


@pytest.mark.asyncio
async def test_digi_other_binding_same_page_number_unverified():
    # Another binding's ALTO whose PHYSICAL_IMG_NR equals the
    # requested page: page number alone proves nothing.
    handler = _digi_handler({1: _alto("999999_0001.jp2", "1")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["ocr_fetched"] is True
    assert page["verified_mapping"] is False
    assert page["document_identity_confirmed"] is False


@pytest.mark.asyncio
async def test_digi_filename_foreign_binding_unverified():
    handler = _digi_handler({1: _alto("999999_0001.jp2", "1")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["mapping_checks"]["foreign_numeric_tokens"] == ["999999"]
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_digi_same_binding_wrong_page_unverified():
    handler = _digi_handler({1: _alto("123456_0002.jp2", "2")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["verified_mapping"] is False
    assert page["page_identity_confirmed"] is False


@pytest.mark.asyncio
async def test_digi_contradictory_signals_unverified():
    # PHYSICAL_IMG_NR says page 2, the fileName says page 1,
    # the request is page 1: contradiction -> unverified.
    handler = _digi_handler({1: _alto("123456_0001.jp2", "2")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["mapping_checks"]["signals_consistent"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_digi_multiple_page_elements_unverified():
    extra = '<Page ID="P2" PHYSICAL_IMG_NR="1"><PrintSpace/></Page>'
    handler = _digi_handler({1: _alto("123456_0001.jp2", "1", extra_pages=extra)})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["mapping_checks"]["alto_page_count"] == 2
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_digi_missing_identifiers_unverified():
    alto = """<?xml version="1.0"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>
<Page ID="P1" PHYSICAL_IMG_NR="1"><PrintSpace>
<TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="teksti" /></TextLine></TextBlock>
</PrintSpace></Page></Layout></alto>"""
    handler = _digi_handler({1: alto})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["verified_mapping"] is False
    assert page["document_identity_confirmed"] is False


@pytest.mark.asyncio
async def test_digi_empty_ocr_and_malformed_alto():
    handler = _digi_handler({1: _alto("123456_0001.jp2", "1", text="")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["ocr_nonempty"] is False
    handler = _digi_handler({1: "<alto><broken"})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@1")
    assert page["verified_mapping"] is False
    assert page["mapping_checks"]["alto_parsed"] is False


@pytest.mark.asyncio
async def test_digi_page_not_in_oai_set_unverified():
    # Page 9 is not in the OAI kk:checksum page set {1, 2}:
    # even a self-consistent ALTO for page 9 is unverified.
    handler = _digi_handler({9: _alto("123456_0009.jp2", "9")})
    async with _client(handler) as client:
        page = await DigiAdapter(client).get_page_text("123456@9")
    assert page["mapping_checks"]["oai_page_listed"] is False
    assert page["verified_mapping"] is False


@pytest.mark.asyncio
async def test_digi_genre_unknown_no_landing_no_guess():
    oai = OAI_XML.replace(
        '<kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/pdf" type="application/pdf" />', "")
    handler = _digi_handler({}, oai=oai)
    async with _client(handler) as client:
        adapter = DigiAdapter(client)
        doc = await adapter.get_document("123456")
        assert doc["genre"] is None
        assert doc["genre_status"] == "unknown"
        assert doc["landing_url"] is None
        with pytest.raises(AdapterError):
            await adapter.get_page_text("123456@1")


@pytest.mark.asyncio
async def test_digi_genre_ambiguous():
    oai = OAI_XML.replace(
        "</qdc>",
        '<kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/teos/binding/123456/pdf" type="application/pdf" /></qdc>')
    handler = _digi_handler({}, oai=oai)
    async with _client(handler) as client:
        doc = await DigiAdapter(client).get_document("123456")
    assert doc["genre"] is None
    assert doc["genre_status"] == "ambiguous"
    assert doc["landing_url"] is None


@pytest.mark.asyncio
async def test_digi_verify_original_other_image_not_verified():
    # The image endpoint serves a perfectly valid JPEG, but
    # the OCR page identity failed -> not verified.
    handler = _digi_handler({1: _alto("999999_0001.jp2", "1")})
    async with _client(handler) as client:
        result = await DigiAdapter(client).verify_original("123456@1")
    assert result["status"] == "unverified"
    assert result["checks"]["image_reachable"]["ok"] is True
    assert result["checks"]["image_page_correspondence"]["ok"] is False
    assert result["checks"]["human_visual_check"]["ok"] is False


# ================================================================ KB (sections 5, 16)

KB_SRU = """<?xml version="1.0"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<srw:records><srw:record><srw:recordData>
<dc:date>1937/08/28</dc:date>
<dc:identifier>http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr</dc:identifier>
<dc:title>Waterkracht-centrale.</dc:title><dc:type>artikel</dc:type>
</srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>
"""

KB_OCR = """<?xml version="1.0"?>
<text><title>Waterkracht-centrale.</title><p>Deze centrale werkt met waterkracht.</p></text>
"""


def _kb_handler(ocr=KB_OCR):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jsru.kb.nl":
            return httpx.Response(200, text=KB_SRU, headers={"content-type": "text/xml"})
        if request.url.host == "resolver.kb.nl":
            return httpx.Response(200, text=ocr, headers={"content-type": "text/xml"})
        return httpx.Response(404, text="not found")
    return handler


@pytest.mark.asyncio
async def test_kb_same_title_is_not_article_identity():
    async with _client(_kb_handler()) as client:
        page = await KbDelpherAdapter(client).get_page_text("ddd:010286065:mpeg21:a0141")
    assert page["article_title_matches"] is True
    assert page["article_identity_confirmed"] is False
    assert page["verified_mapping"] is False
    assert page["ocr_unit"] == "article"
    assert page["page_urn"] is None


def test_kb_cql_literal_safety():
    q = cql_keyword_query('waterkracht" or dc.title all "stoom')
    assert q.startswith('"') and q.endswith('"')
    assert '\\"' in q  # embedded quotes are escaped, not syntax
    with pytest.raises(ValueError):
        cql_keyword_query("bad\x01query")


def test_kb_urn_parsing_strict():
    assert _urn_from_identifier(
        "http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr") == "ddd:010286065:mpeg21:a0141"
    # duplicated urn parameter -> refused
    assert _urn_from_identifier(
        "http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr&urn=ddd:010286065:mpeg21:a9999:ocr") is None
    # userinfo / abnormal port -> refused
    assert _urn_from_identifier(
        "http://user@resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr") is None
    assert _urn_from_identifier(
        "http://resolver.kb.nl:8080/resolve?urn=ddd:010286065:mpeg21:a0141:ocr") is None
    # trailing newline must not sneak past the grammar
    assert _is_urn("ddd:010286065:mpeg21:a0141\n") is False
    assert _is_urn("ddd:010286065:mpeg21:a0141") is True


# ================================================================ handoff (section 7)

def test_handoff_genre_conflict_refused():
    doc = {"data_source": "kansalliskirjasto", "provider_links": [
        {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123"},
        {"url": "https://digi.kansalliskirjasto.fi/teos/binding/123"},
    ]}
    result = extract_digi_candidate(doc)
    assert result["status"] == "refused_ambiguous"
    assert result["binding_id"] is None


def test_handoff_without_provider_is_display_only():
    doc = {"provider_links": [
        {"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123"}]}
    result = extract_digi_candidate(doc)
    assert result["status"] == "candidate_provider_unverified"
    assert result["binding_id"] == "123"


def test_handoff_userinfo_and_port_rejected():
    doc = {"data_source": "kansalliskirjasto", "provider_links": [
        {"url": "https://user@digi.kansalliskirjasto.fi/sanomalehti/binding/123"},
        {"url": "https://digi.kansalliskirjasto.fi:8443/sanomalehti/binding/123"},
    ]}
    assert extract_digi_candidate(doc)["status"] == "no_candidate"


# ================================================================ rights URI (section 15)

def test_rights_uri_strict_parsing():
    assert parse_rights_uri("https://creativecommons.org/licenses/by/4.0/")["label"] == "cc-by"
    assert parse_rights_uri("https://creativecommons.org/licenses/by/4/") is None
    assert parse_rights_uri("https://creativecommons.org.evil.example/licenses/by/4.0/") is None
    assert parse_rights_uri("https://evil.example/?u=https://creativecommons.org/licenses/by/4.0/") is None
    assert parse_rights_uri("https://rightsstatements.org/vocab/InC/1.0/")["label"] == "InC"
    assert js_classify("https://evil.example/?u=creativecommons.org/licenses/by/4.0") == "other"
    assert js_classify("https://creativecommons.org/licenses/by-nc/4.0/") == "creative-commons-licence"


# ================================================================ DPLA key hygiene (section 17)

@pytest.mark.asyncio
async def test_dpla_key_never_leaks_and_id_cannot_change_path(monkeypatch):
    monkeypatch.setenv("DPLA_API_KEY", "SECRETKEY1234567890")
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)
    async with _client(handler) as client:
        adapter = DplaAdapter(client)
        with pytest.raises(AdapterError) as info:
            await adapter.search("water", 5)
        assert "SECRETKEY1234567890" not in str(info.value)
        with pytest.raises(AdapterError):
            await adapter.get_document("../items?api_key=x")
        with pytest.raises(AdapterError):
            await adapter.get_document("abc/def")


# ================================================================ policy trust (sections 8, 13, 14)

def test_policy_forged_source_string_grants_nothing():
    # An observation row as it could appear inside a restored
    # or imported file: trust column absent, source forged.
    # The restore downgrade rewrites trust explicitly; a claim
    # document whose rows were downgraded is denied even when
    # a row's source string claims "reverify":
    forged_after_restore = {"statement": "CC BY 4.0", "source": "reverify",
                            "trust": "restored_claim"}
    decision = policy.trusted_decision("CC BY 4.0", "restored_claim", [forged_after_restore])
    assert decision["excerpt_storage"] is False


def test_policy_unknown_trust_state_fail_closed():
    decision = policy.trusted_decision("CC BY 4.0", "totally_unknown_state", [])
    assert decision["excerpt_storage"] is False


def test_policy_future_observation_is_a_claim():
    future = {"statement": "CC BY 4.0", "source": "reverify",
              "trust": "server_observed", "observed_at": "2999-01-01T00:00:00Z"}
    assert policy.observation_trust(future) != policy.TRUST_SERVER_OBSERVED
    decision = policy.trusted_decision("CC BY 4.0", "imported_claim", [future])
    assert decision["excerpt_storage"] is False


def test_policy_claim_restricts_and_only_server_lifts():
    server_ok = {"statement": "CC BY 4.0", "source": "reverify",
                 "trust": "server_observed", "observed_at": "2026-01-01T00:00:00Z"}
    claim_bad = {"statement": "In Copyright", "source": "imported:x",
                 "trust": "imported_claim", "observed_at": "2026-01-02T00:00:00Z"}
    decision = policy.trusted_decision("Public Domain", "server_observed",
                                       [server_ok, claim_bad])
    assert decision["excerpt_storage"] is False
    lifted = policy.trusted_decision("Public Domain", "server_observed",
                                     [server_ok, claim_bad, dict(server_ok)])
    assert lifted["excerpt_storage"] is True


def test_policy_nc_gate_is_central():
    stored, decision = policy.gate_excerpt("some text", "CC BY-NC 4.0")
    assert stored is None and decision["excerpt_requires_confirmation"]
    stored, decision = policy.gate_excerpt("some text", "CC BY-NC 4.0", nc_confirmed=True)
    assert stored == "some text"
    assert "not an independent legal verification" in decision["reason"]


# ================================================================ store: restore + migration (sections 8, 10, 12)

def test_restore_downgrade_rewrites_forged_observations(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    project = store.create_project("P")
    doc = store.save_document(project["project_id"], "lib", "rec1",
                              {"title": "T", "rights": {"statement": "CC BY 4.0"}})
    # Forge a server-looking observation directly in SQL, as
    # a crafted backup file could contain it.
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO rights_observations (observation_id, saved_document_id,"
            " statement, category, source, observed_at, change_status, trust)"
            " VALUES ('forged', ?, 'CC BY 4.0', 'cc_by', 'reverify',"
            " '2026-01-01T00:00:00Z', 'observed', 'server_observed')",
            (doc["saved_document_id"],))
    store.apply_restore_trust_downgrade()
    observations = store.list_rights_observations(doc["saved_document_id"])
    assert all(policy.observation_trust(o) != policy.TRUST_SERVER_OBSERVED
               for o in observations)
    decision = policy.trusted_decision(
        "CC BY 4.0", store.get_document(doc["saved_document_id"])["rights_trust"],
        observations)
    assert decision["excerpt_storage"] is False
    store.close()


def test_v4_backfill_marks_pre_v3_documents_as_claims(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    project = store.create_project("P")
    doc = store.save_document(project["project_id"], "lib", "rec1", {"title": "T"})
    assert doc["rights_trust"] == "server_observed"
    # Simulate a pre-v3 (b7) database arriving at the v4
    # migration: origin is unprovable, so the document becomes
    # a claim (data preserved, reverify restores display).
    store._backfill_observation_trust(from_version=2)
    assert store.get_document(doc["saved_document_id"])["rights_trust"] == "imported_claim"
    store.close()


def test_acquire_restore_is_atomic(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    ws = WorkspaceWebRuntime(store)
    assert ws.acquire_restore(timeout=0.5) is True
    assert ws.acquire_restore(timeout=0.5) is False  # concurrent restore refused
    ws.unquiesce()
    assert ws.acquire_restore(timeout=0.5) is True
    ws.unquiesce()
    store.close()


# ================================================================ HTTP: markdown/search/restore/reverify (sections 9, 11, 12)

class _StubService:
    """Configurable page/document source for reverify tests."""
    def __init__(self):
        self.page = {
            "contents": "alpha verbatim passage omega",
            "verified_mapping": True,
            "library_id": "internet-archive",
            "record_id": "rec",
            "page_id": "rec@1",
            "image_url": "https://example.org/p.jpg",
            "rights": {"statement": "Public Domain"},
            "ocr_state": {"page_identity_verified": True},
        }

    async def get_page_text(self, library_id, page_id):
        return dict(self.page)

    async def verify_page(self, library_id, page_id):
        return {"status": "verified", "checks": {"image_reachable": {"ok": True}}}

    async def get_document(self, library_id, record_id):
        return {"title": "Title rec"}


@pytest.fixture()
def http(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    ws = WorkspaceWebRuntime(store)
    old_ws, old_service = server_mod.RUNTIME.ws, server_mod.RUNTIME.service
    server_mod.RUNTIME.ws = ws
    stub = _StubService()
    server_mod.RUNTIME.service = stub
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(base + "/", timeout=30) as res:
        html = res.read().decode()
    token = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)
    yield base, ws, store, opener, token, stub
    httpd.shutdown()
    server_mod.RUNTIME.ws, server_mod.RUNTIME.service = old_ws, old_service
    store.close()


def _req(http, method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(http[0] + path, data=data, method=method, headers=headers or {})
    try:
        with http[3].open(req, timeout=30) as res:
            payload = res.read()
            try:
                return res.status, json.loads(payload.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return res.status, {"_binary_bytes": len(payload)}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            return exc.code, {"_binary_bytes": len(payload)}


def _auth(http):
    return {"X-GLM-CSRF": http[4], "Content-Type": "application/json"}


def _project(http):
    status, project = _req(http, "POST", "/api/workspace/projects", {"title": "P"}, _auth(http))
    assert status == 201
    return project


def _save_doc(http, project_id, record="rec", statement="Public Domain"):
    token = http[1].register_snapshot("document", "internet-archive", {
        "record_id": record, "title": f"Title {record}",
        "rights": {"statement": statement}})
    status, doc = _req(http, "POST", "/api/workspace/documents",
                       {"project_id": project_id, "save_token": token}, _auth(http))
    assert status == 201, doc
    return doc


def _save_citation(http, project_id, doc_id, statement="Public Domain",
                   text="alpha verbatim passage omega", excerpt="verbatim passage"):
    token = http[1].register_snapshot("page", "internet-archive", {
        "_page_id": "rec@1", "record_id": "rec", "library_id": "internet-archive",
        "contents": text, "verified_mapping": True,
        "rights": {"statement": statement}})
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project_id, "save_token": token,
                        "saved_document_id": doc_id, "excerpt": excerpt}, _auth(http))
    assert status == 201, cit
    return cit


def test_markdown_and_search_respect_restored_trust(http, tmp_path):
    project = _project(http)
    doc = _save_doc(http, project["project_id"])
    cit = _save_citation(http, project["project_id"], doc["saved_document_id"])
    assert cit["original_excerpt"] == "verbatim passage"
    # Back up, then restore into the same server: restored
    # data is claim-trust, so the excerpt must vanish from
    # Markdown AND from local search hits.
    status, backup = _req(http, "POST", "/api/workspace/backup", {}, _auth(http))
    assert status == 201, backup
    path = http[1].backup_path(backup["id"])
    data = path.read_bytes()
    status, result = _req(http, "POST", "/api/workspace/restore?confirm=1", None,
                          {**_auth(http), "Content-Type": "application/octet-stream"},
                          raw=data)
    assert status == 200, result
    status, listing = _req(http, "GET", f"/api/workspace/citations?project_id={project['project_id']}")
    assert listing["citations"][0]["original_excerpt"] is None
    req = urllib.request.Request(
        http[0] + f"/api/workspace/export/project?project_id={project['project_id']}&format=markdown")
    with http[3].open(req, timeout=30) as res:
        markdown = res.read().decode()
    assert "verbatim passage" not in markdown
    status, found = _req(http, "GET",
                         f"/api/workspace/search?project_id={project['project_id']}&q=verbatim")
    assert found["citations"] == []  # no existence leak from withheld text


def test_restore_failure_in_downgrade_rolls_back(http, monkeypatch):
    project = _project(http)
    doc = _save_doc(http, project["project_id"])
    status, backup = _req(http, "POST", "/api/workspace/backup", {}, _auth(http))
    data = http[1].backup_path(backup["id"]).read_bytes()

    def boom(self):
        raise RuntimeError("injected downgrade failure")
    monkeypatch.setattr(WorkspaceStore, "apply_restore_trust_downgrade", boom)
    status, result = _req(http, "POST", "/api/workspace/restore?confirm=1", None,
                          {**_auth(http), "Content-Type": "application/octet-stream"},
                          raw=data)
    assert status == 500, result
    # The previous database is back and fully usable.
    status, projects = _req(http, "GET", "/api/workspace/projects")
    assert [p["title"] for p in projects["projects"]] == ["P"]
    status, project2 = _req(http, "POST", "/api/workspace/projects", {"title": "P2"}, _auth(http))
    assert status == 201


def _reference_only_citation(http, project_id, doc_id):
    cit = _save_citation(http, project_id, doc_id, statement="item-specific; verify")
    assert cit["original_excerpt"] is None and cit["excerpt_hash"], cit
    return cit


def _unknown_rights_doc_and_citation(http, project_id):
    doc = _save_doc(http, project_id, statement="item-specific; verify")
    cit = _reference_only_citation(http, project_id, doc["saved_document_id"])
    return doc, cit


def test_reverify_readmits_only_with_identity_and_current_rights(http):
    project = _project(http)
    doc, cit = _unknown_rights_doc_and_citation(http, project["project_id"])
    # Happy path: verified page, same document, current
    # rights permit -> the excerpt is re-stored.
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert status == 200, obs
    stored = http[2].get_citation(cit["citation_id"])
    assert stored["original_excerpt"] == "verbatim passage"


def test_reverify_blocks_wrong_document_and_unverified_and_unknown_rights(http):
    project = _project(http)
    doc, cit = _unknown_rights_doc_and_citation(http, project["project_id"])
    stub = http[5]
    # (a) page belongs to another document
    stub.page = {**stub.page, "record_id": "someone-else"}
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert http[2].get_citation(cit["citation_id"])["original_excerpt"] is None
    assert obs["detail"]["checks"]["document_identity"] is False
    # (b) page identity unverified
    stub.page = {**stub.page, "record_id": "rec", "verified_mapping": False,
                 "ocr_state": {"page_identity_verified": False}}
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert http[2].get_citation(cit["citation_id"])["original_excerpt"] is None
    assert "page_identity_unverified" in obs["detail"]["checks"]["readmission_blockers"]
    # (c) current rights unavailable: the saved statement must
    # NOT be used as a fallback.
    stub.page = {**stub.page, "verified_mapping": True,
                 "ocr_state": {"page_identity_verified": True}, "rights": None}
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert http[2].get_citation(cit["citation_id"])["original_excerpt"] is None
    assert "current_rights_unavailable" in obs["detail"]["checks"]["readmission_blockers"]


def test_reverify_oversize_candidate_not_readmitted(http):
    project = _project(http)
    doc, cit = _unknown_rights_doc_and_citation(http, project["project_id"])
    big = "A" * 2100
    store = http[2]
    with store._lock, store._conn:
        store._conn.execute(
            "UPDATE saved_citations SET excerpt_start = 0, excerpt_end = 2100,"
            " excerpt_hash = ? WHERE citation_id = ?",
            (hashlib.sha256(big.encode()).hexdigest(), cit["citation_id"]))
    http[5].page = {**http[5].page, "contents": big}
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert store.get_citation(cit["citation_id"])["original_excerpt"] is None
    assert "excerpt_over_limit" in obs["detail"]["checks"]["readmission_blockers"]


# ================================================================ CI fixtures (section 18)

def test_fixture_transport_serves_only_recorded_routes(tmp_path):
    import asyncio
    from global_library_mcp.http import FixtureTransport
    fixture_dir = "tests/e2e/fixtures/upstream"
    transport = FixtureTransport(fixture_dir)

    async def go():
        req = httpx.Request("GET", "https://jsru.kb.nl/sru/sru?operation=searchRetrieve")
        res = await transport.handle_async_request(req)
        assert res.status_code == 200 and b"Waterkracht" in res.content
        req = httpx.Request("GET", "https://example.org/anything")
        res = await transport.handle_async_request(req)
        assert res.status_code == 404  # never falls through to live network
    asyncio.run(go())


def test_ci_workspace_job_is_fixture_based_and_skip_intolerant():
    workflow = open(".github/workflows/test.yml", encoding="utf-8").read()
    assert "GLM_UPSTREAM_FIXTURE_DIR" in workflow
    assert "skipped == 0" in workflow
    assert "passed == 6" in workflow
    assert "workspace-live" in workflow  # live checks are a separate job
    spec = open("tests/e2e/workspace.spec.js", encoding="utf-8").read()
    assert "upstream unreachable" not in spec  # no upstream-based skips remain
