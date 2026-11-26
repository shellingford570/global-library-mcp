"""b7 final review section 28: real-HTTP integration tests.

The REAL web server, REAL WorkspaceApi, REAL LibraryService and
REAL SQLite store run together; only the upstream library is a
fixed fixture adapter. Nothing in the HTTP/workspace/service
path is mocked, so route-level defects (like the b6
/api/materials NameError that mocked Playwright routes hid)
cannot slip through.
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

import pytest

import global_library_mcp.web.server as server_mod
from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.models import Rights, SearchResult
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime
from global_library_mcp.workspace.store import WorkspaceStore

PAGE_TEXT = ("Natural selection is the differential survival and "
             "reproduction of individuals due to differences in "
             "phenotype. species species variation inheritance")


class _FixtureAdapter(LibraryAdapter):
    library_id = "fixture-lib"
    library_name = "Fixture Library"
    supports_in_document_search = True

    RECORDS = {
        "fx-origin": ("On the Origin of Species", "Darwin, Charles", "1859"),
        "fx-voyage": ("The Voyage of the Beagle", "Darwin, Charles", "1839"),
    }

    def __init__(self):
        pass  # no upstream client: fixed data only

    async def search(self, query, limit=10):
        return [SearchResult(library_id=self.library_id, library_name=self.library_name,
                             record_id=rid, title=title, author=author, date=date,
                             language="en",
                             landing_url=f"https://example.org/{rid}",
                             rights=Rights(statement="Public Domain"))
                for rid, (title, author, date) in self.RECORDS.items()]

    async def get_document(self, record_id):
        title, author, date = self.RECORDS[record_id]
        return {"library_id": self.library_id, "record_id": record_id,
                "title": title, "author": author, "date": date,
                "landing_url": f"https://example.org/{record_id}",
                "rights": {"statement": "Public Domain"},
                "pages": [{"page_id": f"{record_id}@1"}]}

    async def search_in_document(self, record_id, query, limit=20):
        return {"matches": {"list": [{"id": f"{record_id}@1"}]}}

    async def get_page_text(self, page_id):
        record_id = page_id.split("@")[0]
        return {"page_id": page_id, "record_id": record_id,
                "library_id": self.library_id, "contents": PAGE_TEXT,
                "verified_mapping": True,
                "image_url": "https://example.org/img.jpg",
                "rights": {"statement": "Public Domain"}}

    async def verify_original(self, page_id):
        return {"status": "verified",
                "checks": {"image_reachable": {"ok": True}}}


@pytest.fixture()
def env(tmp_path):
    server_mod.RATE_LIMITER._hits.clear()
    store = WorkspaceStore(tmp_path / "w.db")
    ws = WorkspaceWebRuntime(store)
    service = server_mod.RUNTIME.service
    old_ws = server_mod.RUNTIME.ws
    old_adapters, old_defaults = service.adapters, service.default_libraries
    server_mod.RUNTIME.ws = ws
    service.adapters = {"fixture-lib": _FixtureAdapter()}
    service.default_libraries = ["fixture-lib"]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(base + "/", timeout=30) as res:
        html = res.read().decode()
    csrf = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)
    yield {"base": base, "opener": opener, "csrf": csrf, "store": store,
           "ws": ws, "db_path": tmp_path / "w.db"}
    httpd.shutdown()
    server_mod.RUNTIME.ws = old_ws
    service.adapters, service.default_libraries = old_adapters, old_defaults
    store.close()


def _call(env, method, path, body=None, raw=None, ctype=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = {}
    if method in ("POST", "PUT", "DELETE"):
        headers["X-GLM-CSRF"] = env["csrf"]
    if data is not None:
        headers["Content-Type"] = ctype or "application/json"
    req = urllib.request.Request(env["base"] + path, data=data, method=method, headers=headers)
    try:
        with env["opener"].open(req, timeout=60) as res:
            payload = res.read()
            try:
                return res.status, json.loads(payload.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return res.status, {"_text": payload.decode("utf-8", "replace"),
                                    "_bytes": payload}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            return exc.code, {"_text": payload.decode("utf-8", "replace"),
                              "_bytes": payload}


def _q(**params):
    return urllib.parse.urlencode(params)


def test_full_research_journey_over_real_http(env):
    # -- /api/search (real service + fixture adapter) -----------
    status, payload = _call(env, "GET", "/api/search?" + _q(q="Darwin", libraries="fixture-lib"))
    assert status == 200, payload
    results = {r["record_id"]: r for r in payload["results"]}
    assert "fx-origin" in results and results["fx-origin"]["save_token"]
    assert payload["history_token"]

    # -- /api/materials (the route that hid the b6 NameError) ---
    status, payload_m = _call(env, "GET", "/api/materials?" + _q(
        q="Darwin", libraries="fixture-lib", mode="quick"))
    assert status == 200, payload_m
    assert payload_m["materials"], "quick materials must not be empty"

    # -- project + document save --------------------------------
    status, project = _call(env, "POST", "/api/workspace/projects", {"title": "統合"})
    assert status == 201
    pid = project["project_id"]
    status, doc = _call(env, "POST", "/api/workspace/documents",
                        {"project_id": pid,
                         "save_token": results["fx-origin"]["save_token"]})
    assert status == 201, doc
    assert doc["title"] == "On the Origin of Species"

    # -- history from the server-issued token --------------------
    status, entry = _call(env, "POST", "/api/workspace/history",
                          {"project_id": pid,
                           "history_token": payload["history_token"]})
    assert status == 201, entry
    assert entry["provenance"] == "server_recorded"
    assert entry["original_query"] == "Darwin"

    # -- document + page over real HTTP ---------------------------
    status, detail = _call(env, "GET", "/api/document?" + _q(
        library="fixture-lib", id="fx-origin"))
    assert status == 200 and detail["pages"][0]["page_id"] == "fx-origin@1"
    status, page = _call(env, "GET", "/api/page?" + _q(
        library="fixture-lib", id="fx-origin@1"))
    assert status == 200 and page["save_token"] and "Natural selection" in page["contents"]

    # -- citation save + reverify ---------------------------------
    status, cit = _call(env, "POST", "/api/workspace/citations",
                        {"project_id": pid, "save_token": page["save_token"],
                         "saved_document_id": doc["saved_document_id"],
                         "excerpt": "Natural selection is the differential survival"})
    assert status == 201, cit
    assert cit["quotation_verification_status"] == "verified_against_fetched_ocr"
    assert cit["original_excerpt"] == "Natural selection is the differential survival"
    status, obs = _call(env, "POST",
                        f"/api/workspace/citations/{cit['citation_id']}/reverify", {})
    assert status == 200 and obs["status"] == "unchanged", obs

    # -- note ------------------------------------------------------
    status, note = _call(env, "POST", "/api/workspace/notes",
                         {"project_id": pid, "title": "n", "content": "memo",
                          "saved_document_id": doc["saved_document_id"],
                          "citation_id": cit["citation_id"]})
    assert status == 201, note

    # -- second document, comparison -------------------------------
    status, doc2 = _call(env, "POST", "/api/workspace/documents",
                         {"project_id": pid,
                          "save_token": results["fx-voyage"]["save_token"]})
    assert status == 201, doc2
    status, compared = _call(env, "GET", "/api/compare?" + _q(
        docs="fixture-lib:fx-origin;fixture-lib:fx-voyage", aspects="species"))
    assert status == 200 and compared["status"] == "compared", compared
    status, comp = _call(env, "POST", "/api/workspace/comparisons",
                         {"project_id": pid, "title": "比較",
                          "saved_document_ids": [doc["saved_document_id"],
                                                 doc2["saved_document_id"]]})
    assert status == 201, comp
    assert comp["semantic_status"] == "not_checked"
    assert comp["original_excerpts"][doc["saved_document_id"]], "PD excerpts stored"

    # -- local search ------------------------------------------------
    status, found = _call(env, "GET", "/api/workspace/search?" + _q(
        project_id=pid, q="Origin"))
    assert status == 200 and found["documents"], found

    # -- exports ------------------------------------------------------
    status, bib = _call(env, "GET", "/api/workspace/export/documents?" + _q(
        project_id=pid, format="bibtex"))
    assert status == 200 and "On the Origin of Species" in bib["_text"]
    status, exported = _call(env, "GET", "/api/workspace/export/project?" + _q(
        project_id=pid, format="json"))
    assert status == 200 and exported["format"] == "global-library-mcp-project"
    assert exported["project"]["title"] == "統合"

    # -- import --------------------------------------------------------
    status, imported = _call(env, "POST", "/api/workspace/import", exported)
    assert status == 201, imported
    assert imported["project"]["project_id"] != pid

    # -- backup + restore ----------------------------------------------
    status, backup = _call(env, "POST", "/api/workspace/backup", {})
    assert status == 201 and backup["id"]
    status, blob = _call(env, "GET", f"/api/workspace/backup/download?id={backup['id']}")
    assert status == 200 and blob["_bytes"][:6] == b"SQLite"
    status, restored = _call(env, "POST", "/api/workspace/restore?confirm=1",
                             raw=blob["_bytes"], ctype="application/octet-stream")
    assert status == 200, restored
    status, listing = _call(env, "GET", "/api/workspace/projects")
    assert any(p["project_id"] == pid for p in listing["projects"])

    # -- persistence across a reopen ------------------------------------
    reopened = WorkspaceStore(env["db_path"])
    try:
        assert reopened.get_project(pid) is not None
        assert reopened.list_citations(pid)
    finally:
        reopened.close()


def test_materials_with_structured_options_over_real_http(env):
    status, payload = _call(env, "GET", "/api/search?" + _q(
        q="Darwin", libraries="fixture-lib", author="Charles Darwin"))
    assert status == 200, payload
    assert payload["search_kind"] == "structured_bibliographic"
    assert payload["options_applied"] is True
    assert payload["results"], "author-matched materials expected"
