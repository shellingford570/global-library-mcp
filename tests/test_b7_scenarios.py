"""b7 final review section 30: end-to-end research scenarios
over real HTTP with a fixture upstream.

A: rights-permitted material keeps its excerpt through save,
   restart, reverify, Markdown and JSON migration.
B: unknown-rights material stays reference-only everywhere.
C: a later rights change is reflected in views, local search
   and exports while the observation history is preserved.
D: the NDL / IA / BSB / LoC document and page identifier shapes
   bind correctly through the workspace save path.
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

TEXT = ("variation under domestication and variation under nature "
        "species struggle for existence natural selection")


class _ScenarioAdapter(LibraryAdapter):
    library_id = "fixture-lib"
    library_name = "Fixture Library"
    supports_in_document_search = True

    def __init__(self):
        self.rights = {
            "fx-permitted": "Public Domain",
            "fx-unknown": "item-specific; verify before use",
        }
        self.titles = {
            "fx-permitted": "Permitted Research Material",
            "fx-unknown": "Unknown Rights Material",
        }

    async def search(self, query, limit=10):
        return [SearchResult(library_id=self.library_id, library_name=self.library_name,
                             record_id=rid, title=self.titles[rid],
                             author="Author, A.", date="1900", language="en",
                             landing_url=f"https://example.org/{rid}",
                             rights=Rights(statement=self.rights[rid]))
                for rid in self.titles]

    async def get_document(self, record_id):
        return {"library_id": self.library_id, "record_id": record_id,
                "title": self.titles[record_id],
                "landing_url": f"https://example.org/{record_id}",
                "rights": {"statement": self.rights[record_id]},
                "pages": [{"page_id": f"{record_id}@1"}]}

    async def search_in_document(self, record_id, query, limit=20):
        return {"matches": {"list": [{"id": f"{record_id}@1"}]}}

    async def get_page_text(self, page_id):
        record_id = page_id.split("@")[0]
        return {"page_id": page_id, "record_id": record_id,
                "library_id": self.library_id, "contents": TEXT,
                "verified_mapping": True,
                "image_url": "https://example.org/img.jpg",
                "rights": {"statement": self.rights[record_id]}}

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
    adapter = _ScenarioAdapter()
    server_mod.RUNTIME.ws = ws
    service.adapters = {"fixture-lib": adapter}
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
           "adapter": adapter, "db_path": tmp_path / "w.db"}
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


def _setup_doc(env, record_id):
    status, payload = _call(env, "GET", "/api/search?" + urllib.parse.urlencode(
        {"q": "research", "libraries": "fixture-lib"}))
    assert status == 200
    token = {r["record_id"]: r for r in payload["results"]}[record_id]["save_token"]
    status, project = _call(env, "POST", "/api/workspace/projects",
                            {"title": f"P-{record_id}"})
    assert status == 201
    status, doc = _call(env, "POST", "/api/workspace/documents",
                        {"project_id": project["project_id"], "save_token": token})
    assert status == 201, doc
    status, page = _call(env, "GET", "/api/page?" + urllib.parse.urlencode(
        {"library": "fixture-lib", "id": f"{record_id}@1"}))
    assert status == 200 and page["save_token"]
    return project, doc, page


def _save_citation(env, project, doc, page):
    status, cit = _call(env, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"],
                         "save_token": page["save_token"],
                         "saved_document_id": doc["saved_document_id"],
                         "excerpt": "variation under domestication"})
    assert status == 201, cit
    return cit


def test_scenario_a_permitted_material_full_journey(env):
    project, doc, page = _setup_doc(env, "fx-permitted")
    cit = _save_citation(env, project, doc, page)
    assert cit["original_excerpt"] == "variation under domestication"
    # restart: a fresh store on the same file still holds the text
    reopened = WorkspaceStore(env["db_path"])
    try:
        stored = reopened.get_citation(cit["citation_id"])
        assert stored["original_excerpt"] == "variation under domestication"
    finally:
        reopened.close()
    # reverify
    status, obs = _call(env, "POST",
                        f"/api/workspace/citations/{cit['citation_id']}/reverify", {})
    assert status == 200 and obs["status"] == "unchanged", obs
    # Markdown export contains the excerpt
    status, md = _call(env, "GET", "/api/workspace/export/project?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "format": "markdown"}))
    assert status == 200 and "variation under domestication" in md["_text"]
    # JSON migration keeps the relationship (verification downgraded)
    status, exported = _call(env, "GET", "/api/workspace/export/project?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "format": "json"}))
    status, imported = _call(env, "POST", "/api/workspace/import", exported)
    assert status == 201, imported
    new_cits = env["store"].list_citations(imported["project"]["project_id"])
    assert len(new_cits) == 1
    assert new_cits[0]["quotation_verification_status"] == "imported_unverified"
    assert new_cits[0]["original_excerpt"] == "variation under domestication"


def test_scenario_b_unknown_rights_reference_only(env):
    project, doc, page = _setup_doc(env, "fx-unknown")
    cit = _save_citation(env, project, doc, page)
    assert cit["original_excerpt"] is None and cit["excerpt_stored"] is False
    # nothing in the database holds the text
    stored = env["store"].get_citation(cit["citation_id"])
    assert stored["original_excerpt"] is None
    # exports contain no excerpt text
    status, exported = _call(env, "GET", "/api/workspace/export/project?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "format": "json"}))
    assert "variation under domestication" not in json.dumps(exported)
    status, md = _call(env, "GET", "/api/workspace/export/project?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "format": "markdown"}))
    assert "variation under domestication" not in md["_text"]
    # reverify reports the reference-only state honestly
    status, obs = _call(env, "POST",
                        f"/api/workspace/citations/{cit['citation_id']}/reverify", {})
    assert status == 200 and obs["status"] == "partial_verification", obs
    assert obs["detail"]["checks"]["excerpt"] == "not_checked_reference_only"


def test_scenario_c_rights_change_reflected(env):
    project, doc, page = _setup_doc(env, "fx-permitted")
    cit = _save_citation(env, project, doc, page)
    assert cit["original_excerpt"]
    # upstream now reports the item as in copyright
    env["adapter"].rights["fx-permitted"] = "In Copyright"
    status, obs = _call(env, "POST",
                        f"/api/workspace/citations/{cit['citation_id']}/reverify", {})
    assert status == 200 and obs["status"] == "rights_changed", obs
    # views withhold the text now
    status, listing = _call(env, "GET", "/api/workspace/citations?" + urllib.parse.urlencode(
        {"project_id": project["project_id"]}))
    view = listing["citations"][0]
    assert view["original_excerpt"] is None and view["excerpt_stored"] is False
    # local search withholds it too
    status, found = _call(env, "GET", "/api/workspace/search?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "q": "Permitted"}))
    assert all(c["original_excerpt"] is None for c in found["citations"])
    # exports withhold it, with an omission recorded
    status, exported = _call(env, "GET", "/api/workspace/export/project?" + urllib.parse.urlencode(
        {"project_id": project["project_id"], "format": "json"}))
    assert exported["saved_citations"][0]["original_excerpt"] is None
    assert exported["export_omissions"]
    # the observation history keeps both statements
    statements = [o["statement"] for o in
                  env["store"].list_rights_observations(doc["saved_document_id"])]
    assert "In Copyright" in statements
    # the stored row itself is not rewritten
    assert env["store"].get_citation(cit["citation_id"])["original_excerpt"]


def test_scenario_d_adapter_identifier_shapes(env):
    from test_b7_final_review import _auth, _project, _req, _save_doc
    http = _d_http(env)
    project = _project(http)
    shapes = [
        ("ndl", "992954", "992954_12"),
        ("internet-archive", "onoriginofspecie1859darw", "onoriginofspecie1859darw@20"),
        ("bsb", "bsb11650472", "bsb11650472_0005"),
        ("loc", "sn83030214/1917-09-02/ed-1", "sn83030214/1917-09-02/ed-1/seq-3"),
    ]
    for library, record, page_id in shapes:
        doc = _save_doc(http, project["project_id"], record, library=library)
        payload = {"_page_id": page_id, "record_id": record, "library_id": library,
                   "contents": "shape check verbatim text", "verified_mapping": True,
                   "rights": {"statement": "Public Domain"}}
        if library == "ndl":
            # live-verified NDL shape (2026-11-26): the page
            # payload carries book_pid and NO record_id field
            del payload["record_id"]
            payload["book_pid"] = record
        token = http[1].register_snapshot("page", library, payload)
        status, cit = _req(http, "POST", "/api/workspace/citations",
                           {"project_id": project["project_id"], "save_token": token,
                            "saved_document_id": doc["saved_document_id"],
                            "excerpt": "verbatim text"}, _auth(http))
        assert status == 201, (library, cit)
        assert cit["page_id"] == page_id
    # a LoC page from edition 1 must not bind to the edition-2 document
    doc_ed2 = _save_doc(http, project["project_id"], "sn83030214/1917-09-02/ed-2",
                        library="loc")
    token = http[1].register_snapshot("page", "loc", {
        "_page_id": "sn83030214/1917-09-02/ed-1/seq-3",
        "record_id": "sn83030214/1917-09-02/ed-1", "library_id": "loc",
        "contents": "shape check verbatim text", "verified_mapping": True,
        "rights": {"statement": "Public Domain"}})
    status, body = _req(http, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"], "save_token": token,
                         "saved_document_id": doc_ed2["saved_document_id"],
                         "excerpt": "verbatim text"}, _auth(http))
    assert status == 400


def _d_http(env):
    """Adapt the scenarios env to the (base, ws, store, opener,
    csrf) tuple the final-review helpers expect. The runtime's
    store is swapped for a scratch one so scenario D does not
    touch the fixture-adapter service."""
    return (env["base"], server_mod.RUNTIME.ws, env["store"],
            env["opener"], env["csrf"])
