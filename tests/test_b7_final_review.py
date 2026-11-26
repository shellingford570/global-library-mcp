"""b7 final review: regression tests for the external-review
findings (identity binding, rights fail-closed, import/restore
safety, cross-project integrity, session security). Each test
names the review section it pins down."""
from __future__ import annotations

import hashlib
import json
from http.cookiejar import CookieJar
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import global_library_mcp.web.server as server_mod
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime
from global_library_mcp.workspace import policy
from global_library_mcp.workspace.exports import (assign_keys, csl_author,
                                                  parse_date_parts,
                                                  project_markdown, to_bibtex,
                                                  to_csl_json, to_ris)
from global_library_mcp.workspace.store import WorkspaceStore
from global_library_mcp.workspace.transfer import (export_project,
                                                    import_project,
                                                    parse_import_json,
                                                    ImportError_)


class _StubService:
    def __init__(self):
        self.page_text = "alpha verbatim passage omega"
        self.page_rights = "Public Domain"

    async def get_page_text(self, library_id, page_id):
        return {"contents": self.page_text, "verified_mapping": True,
                "library_id": library_id, "record_id": "rec",
                "page_id": page_id,
                "image_url": "https://example.org/p.jpg",
                "rights": {"statement": self.page_rights},
                "ocr_state": {"page_identity_verified": True}}

    async def verify_page(self, library_id, page_id):
        return {"status": "verified", "checks": {"image_reachable": {"ok": True}}}

    async def get_document(self, library_id, record_id):
        return {"title": "On the Origin of Species"}


@pytest.fixture()
def http(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    ws = WorkspaceWebRuntime(store)
    old_ws, old_service = server_mod.RUNTIME.ws, server_mod.RUNTIME.service
    server_mod.RUNTIME.ws = ws
    server_mod.RUNTIME.service = _StubService()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(base + "/", timeout=30) as res:
        html = res.read().decode()
    token = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)
    yield base, ws, store, opener, token
    httpd.shutdown()
    server_mod.RUNTIME.ws, server_mod.RUNTIME.service = old_ws, old_service
    store.close()


def _req(http, method, path, body=None, headers=None, raw=None, opener=None):
    base = http[0]
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
    op = opener or http[3]
    try:
        with op.open(req, timeout=30) as res:
            raw_bytes = res.read()
            try:
                return res.status, json.loads(raw_bytes.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return res.status, {"_binary_bytes": len(raw_bytes)}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            return exc.code, {"_binary_bytes": len(payload)}


def _auth(http, extra=None):
    return {"X-GLM-CSRF": http[4], "Content-Type": "application/json", **(extra or {})}


def _project(http):
    status, project = _req(http, "POST", "/api/workspace/projects", {"title": "P"}, _auth(http))
    assert status == 201
    return project


def _save_doc(http, project_id, record, statement="Public Domain", library="internet-archive"):
    token = http[1].register_snapshot("document", library, {
        "record_id": record, "title": f"Title {record}",
        "rights": {"statement": statement}})
    status, doc = _req(http, "POST", "/api/workspace/documents",
                       {"project_id": project_id, "save_token": token}, _auth(http))
    assert status == 201, doc
    return doc


def _page_token(http, record="rec", statement="Public Domain", text="alpha verbatim passage omega",
                library="internet-archive", page_id=None, verified=True):
    return http[1].register_snapshot("page", library, {
        "_page_id": page_id or f"{record}@1", "record_id": record,
        "library_id": library, "contents": text, "verified_mapping": verified,
        "rights": {"statement": statement}})


# ---------------------------------------------------------- section 2: identity
def test_citation_binds_to_snapshot_document(http):
    project = _project(http)
    doc_a = _save_doc(http, project["project_id"], "recA")
    doc_b = _save_doc(http, project["project_id"], "recB")
    token = _page_token(http, record="recA")
    # the genuine token spent on another document of the same project
    status, body = _req(http, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"], "save_token": token,
                         "saved_document_id": doc_b["saved_document_id"],
                         "excerpt": "verbatim passage"}, _auth(http))
    assert status == 400
    # another library's document
    doc_c = _save_doc(http, project["project_id"], "recA", library="bsb")
    status, body = _req(http, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"], "save_token": token,
                         "saved_document_id": doc_c["saved_document_id"],
                         "excerpt": "verbatim passage"}, _auth(http))
    assert status == 400
    # the right document works
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "saved_document_id": doc_a["saved_document_id"],
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201 and cit["quotation_verification_status"] == "verified_against_fetched_ocr"


def test_citation_snapshot_without_record_identity_rejected(http):
    project = _project(http)
    token = http[1].register_snapshot("page", "internet-archive", {
        "_page_id": "whatever@1", "contents": "alpha verbatim passage omega",
        "verified_mapping": True, "rights": {"statement": "Public Domain"}})
    status, body = _req(http, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"], "save_token": token,
                         "excerpt": "verbatim passage"}, _auth(http))
    assert status == 422


def test_citation_oversize_excerpt_rejected_not_truncated(http):
    project = _project(http)
    long_text = "y" * 2500
    token = _page_token(http, text=long_text)
    status, body = _req(http, "POST", "/api/workspace/citations",
                        {"project_id": project["project_id"], "save_token": token,
                         "excerpt": long_text}, _auth(http))
    assert status == 422 and "storage limit" in body["error"]
    # a within-limit excerpt stores text, offsets and hash in agreement
    token = _page_token(http)
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201
    assert cit["excerpt_end"] - cit["excerpt_start"] == len("verbatim passage")
    assert cit["excerpt_hash"] == hashlib.sha256(b"verbatim passage").hexdigest()
    assert cit["excerpt_stored"] is True


# ---------------------------------------------------------- section 3: rights token
def test_rights_token_from_other_document_rejected(http):
    project = _project(http)
    doc_a = _save_doc(http, project["project_id"], "recA", statement="item-specific; verify")
    _save_doc(http, project["project_id"], "recB",
              statement="https://creativecommons.org/licenses/by/4.0/")
    doc_token_b = http[1].register_snapshot("document", "internet-archive", {
        "record_id": "recB",
        "rights": {"statement": "https://creativecommons.org/licenses/by/4.0/"}})
    token = _page_token(http, record="recA", statement="item-specific; verify")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "saved_document_id": doc_a["saved_document_id"],
                        "document_token": doc_token_b,
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201
    assert cit["original_excerpt"] is None and cit["excerpt_stored"] is False
    assert cit["rights_at_save"]["category"] == "unknown"


# ---------------------------------------------------------- section 4: classification
@pytest.mark.parametrize("statement,want", [
    ("not in the public domain", "unknown"),
    ("not released under CC0", "unknown"),
    ("public domain status has not been established", "unknown"),
    ("CC0 does not apply to this item", "unknown"),
    ("CC BY-SA-NC-ND 4.0", "unknown"),
    ("CC BY 4.0 but also in copyright", "unknown"),
    ("Metadata available under CC0", "unknown"),
    ("No Copyright - Non-Commercial Use Only", "noc_nc"),
    ("https://creativecommons.org/licenses/by-nc-sa/4.0/", "cc_by_nc_sa"),
    ("http://rightsstatements.org/vocab/InC/1.0/", "copyrighted"),
])
def test_rights_classification_fail_closed(statement, want):
    assert policy.classify_rights(statement) == want


def test_noc_nc_does_not_permit_excerpt_storage():
    assert policy.evaluate("No Copyright - Non-Commercial Use Only")["excerpt_storage"] is False
    assert policy.evaluate("CC BY-NC 4.0")["excerpt_storage"] is True  # documented NC default


# ---------------------------------------------------------- sections 5/15/16/17: import
def _import_payload(**overrides):
    payload = {
        "format": "global-library-mcp-project", "format_version": 1,
        "schema_version": 1, "project": {"title": "Imp"},
        "saved_documents": [{"saved_document_id": "d1", "library_id": "lib",
                             "record_id": "r1", "title": "T",
                             "rights_snapshot": {"statement": "unknown"}}],
        "saved_citations": [], "research_notes": [], "search_history": [],
        "saved_comparisons": [], "collections": [],
    }
    payload.update(overrides)
    return payload


def test_import_applies_storage_policy_and_downgrades(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    payload = _import_payload(saved_citations=[{
        "citation_id": "c1", "saved_document_id": "d1", "page_id": "r1@1",
        "citation_key": "k", "original_excerpt": "z" * 100,
        "quotation_verification_status": "verified_against_fetched_ocr",
        "page_mapping_status": "verified", "image_verification_status": "verified",
        "verified_at": "2020-01-01T00:00:00Z",
        "rights_at_save": {"statement": "unknown", "category": "unknown"}}])
    result = import_project(store, payload)
    cit = store.list_citations(result["project"]["project_id"])[0]
    assert cit["original_excerpt"] is None  # unknown rights: text not imported
    assert cit["quotation_verification_status"] == "imported_unverified"
    assert cit["page_mapping_status"] == "imported_unverified"
    assert cit["image_verification_status"] == "imported_unverified"
    assert cit["verified_at"] is None
    assert result["excerpt_omissions"]
    claims = [o for o in cit["observations"] if o["status"] == "imported_claim"]
    assert claims and json.loads(claims[0]["detail"])["claimed_verified_at"] == "2020-01-01T00:00:00Z"


def test_import_rejects_unknown_references_and_duplicate_keys(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    bad = _import_payload(research_notes=[{"title": "n", "saved_document_id": "ghost"}])
    with pytest.raises(ImportError_):
        import_project(store, bad)
    bad = _import_payload(saved_documents=[
        {"saved_document_id": "d1", "library_id": "l", "record_id": "r", "citation_key": "same"},
        {"saved_document_id": "d2", "library_id": "l", "record_id": "r2", "citation_key": "same"}])
    with pytest.raises(ImportError_):
        import_project(store, bad)
    with pytest.raises(ImportError_):
        parse_import_json(b'{"a": 1, "a": 2}')
    with pytest.raises(ImportError_):
        parse_import_json(b'{"a": NaN}')


def test_export_import_roundtrip_keeps_histories(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    project = store.create_project("RT")
    doc = store.save_document(project["project_id"], "lib", "r1",
                              {"title": "T", "rights_snapshot": {"statement": "Public Domain"}})
    cit = store.save_citation(doc["saved_document_id"], {
        "page_id": "r1@1", "citation_key": "k1", "original_excerpt": "passage",
        "quotation_verification_status": "verified_against_fetched_ocr",
        "provenance": "system_fetched", "rights_at_save": {"statement": "Public Domain"}})
    store.add_verification_observation(cit["citation_id"], "unchanged", {"checks": {}})
    store.add_rights_observation(doc["saved_document_id"], "Public Domain",
                                 "public_domain", "save", "observed")
    exported = export_project(store, project["project_id"])
    assert exported["saved_citations"][0]["verification_observations"]
    result = import_project(store, exported)
    new_project = result["project"]
    new_cit = store.list_citations(new_project["project_id"])[0]
    statuses = [o["status"] for o in new_cit["observations"]]
    assert "imported_claim" in statuses and "unchanged" in statuses  # history kept as history
    assert new_cit["quotation_verification_status"] == "imported_unverified"
    new_doc = store.list_documents(new_project["project_id"])[0]
    assert store.list_rights_observations(new_doc["saved_document_id"])
    assert new_doc["citation_key"] == doc["citation_key"]  # key survives migration
    assert new_cit["saved_at"] == cit["saved_at"]  # original time preserved


# ---------------------------------------------------------- section 6: current rights
def test_rights_change_gates_views_and_exports(http):
    project = _project(http)
    token = _page_token(http)
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201 and cit["original_excerpt"] == "verbatim passage"
    store = http[2]
    store.add_rights_observation(cit["saved_document_id"], "In Copyright",
                                 "copyrighted", "reverify", "rights_changed")
    status, listing = _req(http, "GET", f"/api/workspace/citations?project_id={project['project_id']}")
    view = listing["citations"][0]
    assert view["original_excerpt"] is None and view["excerpt_stored"] is False
    assert "latest rights observation" in view["excerpt_omitted_reason"]
    exported = export_project(store, project["project_id"])
    assert exported["saved_citations"][0]["original_excerpt"] is None
    assert exported["export_omissions"]
    # the stored row itself is untouched (only views/exports gate)
    assert store.get_citation(cit["citation_id"])["original_excerpt"] == "verbatim passage"


# ---------------------------------------------------------- sections 7/8: restore
def test_restore_rejects_wrong_schema_sqlite(http, tmp_path):
    _project(http)
    other = sqlite3.connect(str(tmp_path / "other.db"))
    other.execute("CREATE TABLE stuff (a TEXT)")
    other.commit()
    other.close()
    data = (tmp_path / "other.db").read_bytes()
    status, body = _req(http, "POST", "/api/workspace/restore?confirm=1", raw=data,
                        headers={"X-GLM-CSRF": http[4],
                                 "Content-Type": "application/octet-stream"})
    assert status == 400 and "missing table" in body["error"]
    status, listing = _req(http, "GET", "/api/workspace/projects")
    assert status == 200 and listing["projects"]  # untouched


def test_restore_rejects_tampered_status_and_rolls_back(http, tmp_path):
    project = _project(http)
    store = http[2]
    good = store.backup(tmp_path / "good.db")
    raw = sqlite3.connect(str(tmp_path / "good.db"))
    raw.execute("INSERT INTO saved_documents (saved_document_id, project_id, library_id,"
                " record_id, saved_at, updated_at) VALUES ('x', ?, 'lib', 'rx', 't', 't')",
                (project["project_id"],))
    raw.execute("INSERT INTO saved_citations (citation_id, saved_document_id, page_id,"
                " citation_key, quotation_verification_status, provenance, saved_at)"
                " VALUES ('c', 'x', 'p', 'k', 'verified_by_admin', 'system_fetched', 't')")
    raw.commit()
    raw.close()
    status, body = _req(http, "POST", "/api/workspace/restore?confirm=1",
                        raw=(tmp_path / "good.db").read_bytes(),
                        headers={"X-GLM-CSRF": http[4],
                                 "Content-Type": "application/octet-stream"})
    assert status == 400 and "quotation status" in body["error"]


def test_restore_rolls_back_when_candidate_cannot_open(http, tmp_path):
    project = _project(http)
    store = http[2]
    # A v1-shaped DB that already has the v2 column: validation
    # passes (v1 columns are a subset), but opening it runs the
    # v2 migration, which fails -> automatic rollback.
    import global_library_mcp.workspace.store as store_mod
    candidate = tmp_path / "cand.db"
    raw = sqlite3.connect(str(candidate))
    raw.executescript(store_mod._SCHEMA_V1)
    raw.execute("ALTER TABLE saved_documents ADD COLUMN citation_key TEXT")
    raw.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z')")
    raw.commit()
    raw.close()
    status, body = _req(http, "POST", "/api/workspace/restore?confirm=1",
                        raw=candidate.read_bytes(),
                        headers={"X-GLM-CSRF": http[4],
                                 "Content-Type": "application/octet-stream"})
    assert status == 500 and "rolled back" in body["error"]
    status, listing = _req(http, "GET", "/api/workspace/projects")
    assert status == 200
    assert any(p["project_id"] == project["project_id"] for p in listing["projects"])


def test_restore_in_progress_blocks_requests(http):
    http[1].restoring = True
    try:
        status, _ = _req(http, "GET", "/api/workspace/projects")
        assert status == 503
    finally:
        http[1].restoring = False


# ---------------------------------------------------------- section 10: session security
def test_reads_require_session(http):
    bare = urllib.request.build_opener()  # no cookies at all
    status, _ = _req(http, "GET", "/api/workspace/projects", opener=bare)
    assert status == 403


def test_host_port_mismatch_and_origin_null_rejected(http):
    port = http[0].rsplit(":", 1)[1]
    status, _ = _req(http, "GET", "/api/workspace/projects",
                     headers={"Host": "127.0.0.1:1"})
    assert status == 403
    status, _ = _req(http, "POST", "/api/workspace/projects", {"title": "X"},
                     _auth(http, {"Origin": "null"}))
    assert status == 403
    status, _ = _req(http, "GET", "/api/workspace/projects",
                     headers={"Origin": "http://evil.example"})
    assert status == 403


def test_backup_get_never_creates(http, tmp_path):
    _project(http)
    status, body = _req(http, "GET", "/api/workspace/backup/download?id=nope")
    assert status == 404
    status, body = _req(http, "POST", "/api/workspace/backup", {}, _auth(http))
    assert status == 201 and body["id"]
    status, body = _req(http, "GET", f"/api/workspace/backup/download?id={body['id']}")
    assert status == 200
    backups_dir = http[2].db_path.parent / "backups"
    files = list(backups_dir.glob("ws-backup-*.db"))
    assert len(files) == 1  # exactly the POST-created one


# ---------------------------------------------------------- section 14: reverify states
def test_reverify_reference_only_is_partial_not_unchanged(http):
    project = _project(http)
    server_mod.RUNTIME.service.page_rights = "item-specific; verify"
    token = _page_token(http, statement="item-specific; verify")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201 and cit["original_excerpt"] is None  # reference only
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert status == 200 and obs["status"] == "partial_verification"
    assert obs["detail"]["checks"]["excerpt"] == "not_checked_reference_only"


def test_reverify_full_checks_can_be_unchanged(http):
    project = _project(http)
    token = _page_token(http)
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"], "save_token": token,
                        "excerpt": "verbatim passage"}, _auth(http))
    assert status == 201
    store = http[2]
    # a saved title that disagrees with the source is reported
    store._conn.execute("UPDATE saved_documents SET title = 'A Different Title'"
                        " WHERE saved_document_id = ?", (cit["saved_document_id"],))
    store._conn.commit()
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert obs["status"] == "metadata_changed"
    # with the title matching the source, every check passes
    store._conn.execute("UPDATE saved_documents SET title = 'On the Origin of Species'"
                        " WHERE saved_document_id = ?", (cit["saved_document_id"],))
    store._conn.commit()
    status, obs = _req(http, "POST", f"/api/workspace/citations/{cit['citation_id']}/reverify",
                       {}, _auth(http))
    assert obs["status"] == "unchanged"


# ---------------------------------------------------------- sections 21/22/23: exports
def test_citation_keys_stable_and_unique(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    project = store.create_project("K")
    docs = []
    for i in range(30):
        docs.append(store.save_document(project["project_id"], "lib", f"r{i}",
                                        {"title": "Same Title", "author": "Anon",
                                         "publication_date": "1900"}))
    keys = assign_keys([store.get_document(d["saved_document_id"]) for d in docs])
    assert len(set(keys.values())) == 30
    first = keys[docs[0]["saved_document_id"]]
    docs.append(store.save_document(project["project_id"], "lib", "rX",
                                    {"title": "Other", "author": "Anon",
                                     "publication_date": "1901"}))
    keys2 = assign_keys([store.get_document(d["saved_document_id"]) for d in docs])
    assert keys2[docs[0]["saved_document_id"]] == first  # adding docs never renames


def test_export_types_and_dates():
    docs = [{"saved_document_id": "1", "title": "Old Print", "material_type": "book",
             "publication_date": "1492", "author": "University Library",
             "citation_key": "k1", "library_id": "l", "record_id": "r"},
            {"saved_document_id": "2", "title": "Daily News", "material_type": "newspaper",
             "publication_date": "1917-09-02", "citation_key": "k2",
             "library_id": "l", "record_id": "r2"},
            {"saved_document_id": "3", "title": "Mystery", "material_type": None,
             "publication_date": "紀元前300年頃", "citation_key": "k3",
             "library_id": "l", "record_id": "r3"}]
    bib = to_bibtex(docs)
    assert "@book{k1" in bib and "year = {1492}" in bib  # pre-1500 kept
    assert "@misc{k2" in bib and "month = {9}" in bib  # newspaper is not a journal article
    assert "year" not in bib.split("@misc{k3")[1].split("}")[0]  # BCE year not fabricated
    ris = to_ris(docs)
    assert "TY  - NEWS" in ris and "Y1  - 1917/09/02" in ris
    csl = to_csl_json(docs)
    assert csl[0]["author"] == [{"literal": "University Library"}]  # org stays literal
    assert csl[1]["type"] == "article-newspaper"
    assert csl[1]["issued"] == {"date-parts": [[1917, 9, 2]]}
    assert "issued" not in csl[2]
    assert parse_date_parts("1859-1861") == (1859, None, None)


def test_markdown_escapes_injected_structure():
    project = {"title": "P", "description": "x"}
    docs = [{"saved_document_id": "1", "title": "# Fake Heading [click](https://evil.example)",
             "author": "A", "publication_date": "1900", "library_id": "l",
             "record_id": "r", "citation_key": "k1", "rights_snapshot": {"statement": "Public Domain"}}]
    notes = [{"title": "n", "content": "text\n# Injected\n```\ncode fence break\n![img](https://evil.example/x.png)"}]
    text, _ = project_markdown(project, docs, [], notes, [], [])
    lines = text.split("\n")
    # no stored string may start a line as a heading or image
    assert not any(line.startswith("# Fake") or line.startswith("# Injected")
                   for line in lines)
    assert "\\# Injected" in text  # heading marker escaped at line start
    assert "![img]" not in text  # image syntax broken by escaping
    prose = text.split("```")[0]  # outside the bibliography code fence
    assert "[click](https" not in prose  # link syntax broken by escaping
    assert text.count("```") == 2  # only the bibliography fence pair


# ---------------------------------------------------------- section 12: snapshots
def test_snapshot_immutability_and_size_cap(http):
    ws = http[1]
    payload = {"record_id": "r", "contents": "original"}
    token = ws.register_snapshot("page", "lib", payload)
    payload["contents"] = "mutated afterwards"
    assert ws.get_snapshot(token)["payload"]["contents"] == "original"
    with pytest.raises(ValueError):
        ws.register_snapshot("page", "lib", {"contents": "x" * (5 * 1024 * 1024)})
