"""b8 Stage 5: Research Workspace integration for the new
libraries, over REAL HTTP (section 23 composition: real web
server, real WorkspaceApi, real LibraryService, real adapters,
real SQLite; only the upstream library APIs are fixed
fixtures).

Journey: KB/Delpher search -> save document -> page -> citation
save (rights unknown, so the excerpt is withheld and only the
reference is stored) -> Finna document save -> comparison of
the two -> BibTeX export -> project JSON export.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

import httpx
import pytest

import global_library_mcp.web.server as server_mod
from global_library_mcp.adapters.finna import FinnaAdapter
from global_library_mcp.adapters.kb import KbDelpherAdapter
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime
from global_library_mcp.workspace.store import WorkspaceStore

KB_SRU = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcx="http://krait.kb.nl/coop/tel/handbook/telterms.html">
<srw:version>1.2</srw:version>
<srw:numberOfRecords>1</srw:numberOfRecords>
<srw:records>
<srw:record>
<srw:recordPacking>xml</srw:recordPacking>
<srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
<srw:recordData><dc:date>1937/08/28 00:00:00</dc:date><dc:identifier>http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr</dc:identifier><dc:publisher>[ s.n.]</dc:publisher><dc:source>KB C 248</dc:source><dc:title>Waterkracht-centrale.</dc:title><dc:type>artikel</dc:type><dcx:issued>1921</dcx:issued></srw:recordData>
<srw:recordPosition>1</srw:recordPosition>
</srw:record>
</srw:records>
</srw:searchRetrieveResponse>
"""

KB_OCR = """<?xml version="1.0" encoding="UTF-8"?>
<text>
<title>Waterkracht-centrale.</title>
<p>Deze centrale werkt met waterkracht en irrigatie.</p>
</text>
"""

FINNA_SEARCH = {
    "resultCount": 1,
    "records": [
        {
            "id": "helle.687105",
            "title": "Suomen historia",
            "usageRights": [],
            "languages": ["fin"],
            "formats": [{"value": "0/Book/", "translated": "Kirja"}],
            "buildings": [
                {"value": "0/Helle/", "translated": "Helle-kirjastot"},
                {"value": "2/Helle/PNK/PK/", "translated": "Pornaisten kunnankirjasto"},
            ],
            "authors": {"primary": {"Historiankirjoittaja, Esimerkki": {}}},
            "year": 2020,
        }
    ],
    "status": "OK",
}


def _upstream_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "jsru.kb.nl":
        return httpx.Response(200, text=KB_SRU, headers={"content-type": "text/xml"})
    if host == "resolver.kb.nl":
        if request.url.params.get("urn", "").endswith(":ocr"):
            return httpx.Response(200, text=KB_OCR, headers={"content-type": "text/xml"})
        return httpx.Response(404, text="no")
    if host == "api.finna.fi":
        return httpx.Response(200, json=FINNA_SEARCH)
    return httpx.Response(404, text="not found")


@pytest.fixture()
def env(tmp_path):
    server_mod.RATE_LIMITER._hits.clear()
    store = WorkspaceStore(tmp_path / "w.db")
    ws = WorkspaceWebRuntime(store)
    service = server_mod.RUNTIME.service
    old_ws = server_mod.RUNTIME.ws
    old_adapters, old_defaults = service.adapters, service.default_libraries
    client = httpx.AsyncClient(transport=httpx.MockTransport(_upstream_handler))
    server_mod.RUNTIME.ws = ws
    service.adapters = {
        "kb-delpher": KbDelpherAdapter(client),
        "finna": FinnaAdapter(client),
    }
    service.default_libraries = ["kb-delpher", "finna"]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(base + "/", timeout=30) as res:
        html = res.read().decode()
    csrf = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)
    yield {"base": base, "opener": opener, "csrf": csrf, "store": store}
    httpd.shutdown()
    server_mod.RUNTIME.ws = old_ws
    service.adapters, service.default_libraries = old_adapters, old_defaults
    store.close()


def _call(env, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if method in ("POST", "PUT", "DELETE"):
        headers["X-GLM-CSRF"] = env["csrf"]
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(env["base"] + path, data=data, method=method, headers=headers)
    try:
        with env["opener"].open(req, timeout=60) as res:
            payload = res.read()
            try:
                return res.status, json.loads(payload.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return res.status, {"_text": payload.decode("utf-8", "replace")}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            return exc.code, {"_text": payload.decode("utf-8", "replace")}


def _q(**params):
    return urllib.parse.urlencode(params)


def test_new_library_research_journey_over_real_http(env):
    # -- KB search via the real service + real adapter ------------
    status, payload = _call(env, "GET", "/api/search?" + _q(q="waterkracht", libraries="kb-delpher"))
    assert status == 200, payload
    kb_result = payload["results"][0]
    assert kb_result["record_id"] == "ddd:010286065:mpeg21:a0141"
    assert kb_result["save_token"]

    # -- Finna search ----------------------------------------------
    status, payload_f = _call(env, "GET", "/api/search?" + _q(q="Suomen historia", libraries="finna"))
    assert status == 200, payload_f
    finna_result = payload_f["results"][0]
    assert finna_result["record_id"] == "helle.687105"

    # -- project + document saves -----------------------------------
    status, project = _call(env, "POST", "/api/workspace/projects", {"title": "北欧・オランダ水力史"})
    assert status == 201
    pid = project["project_id"]
    status, kb_doc = _call(env, "POST", "/api/workspace/documents",
                           {"project_id": pid, "save_token": kb_result["save_token"]})
    assert status == 201, kb_doc
    assert kb_doc["title"] == "Waterkracht-centrale."
    assert kb_doc["library_id"] == "kb-delpher"
    status, finna_doc = _call(env, "POST", "/api/workspace/documents",
                              {"project_id": pid, "save_token": finna_result["save_token"]})
    assert status == 201, finna_doc
    assert finna_doc["library_id"] == "finna"

    # -- KB page + citation: rights unknown -> reference only -------
    status, page = _call(env, "GET", "/api/page?" + _q(
        library="kb-delpher", id="ddd:010286065:mpeg21:a0141"))
    assert status == 200 and page["save_token"], page
    # b8 final review section 5: KB article OCR is
    # title-correspondence only - fetched, never verified.
    assert page["verified_mapping"] is False
    assert page["article_title_matches"] is True
    status, cit = _call(env, "POST", "/api/workspace/citations",
                        {"project_id": pid, "save_token": page["save_token"],
                         "saved_document_id": kb_doc["saved_document_id"],
                         "excerpt": "Deze centrale werkt met waterkracht"})
    assert status == 201, cit
    # The KB record carries no rights statement: the excerpt text
    # must NOT be stored; the reference (hash + offsets) is kept.
    assert not cit.get("original_excerpt")
    assert cit.get("excerpt_stored") is False
    assert cit.get("excerpt_hash")
    stored = env["store"].get_citation(cit["citation_id"])
    assert stored["original_excerpt"] is None
    assert stored["excerpt_hash"]

    # -- comparison across the two new libraries ---------------------
    status, compared = _call(env, "GET", "/api/compare?" + _q(
        docs="kb-delpher:ddd:010286065:mpeg21:a0141;finna:helle.687105",
        aspects="waterkracht"))
    assert status == 200, compared
    status, comp = _call(env, "POST", "/api/workspace/comparisons",
                         {"project_id": pid, "title": "水力比較",
                          "saved_document_ids": [kb_doc["saved_document_id"],
                                                 finna_doc["saved_document_id"]]})
    assert status == 201, comp
    assert comp["semantic_status"] == "not_checked"

    # -- exports -------------------------------------------------------
    status, bib = _call(env, "GET", "/api/workspace/export/documents?" + _q(
        project_id=pid, format="bibtex"))
    assert status == 200 and "Waterkracht-centrale" in bib["_text"]
    assert "Suomen historia" in bib["_text"]
    status, exported = _call(env, "GET", "/api/workspace/export/project?" + _q(
        project_id=pid, format="json"))
    assert status == 200 and exported["format"] == "global-library-mcp-project"
    libraries = {d["library_id"] for d in exported["saved_documents"]}
    assert libraries == {"kb-delpher", "finna"}
