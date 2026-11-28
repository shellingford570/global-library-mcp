"""b8 Stage 0: regression tests for the b7 residual problems
(brief section 2): imported rights claims must never permit
excerpt storage, the latest rights observation governs new
saves, NonCommercial saves need an explicit purpose
confirmation, cross-library record_id collisions, restore
quiescence and the backup trust boundary."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

import pytest

import global_library_mcp.web.server as server_mod
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime
from global_library_mcp.workspace import policy
from global_library_mcp.workspace.store import WorkspaceStore
from global_library_mcp.workspace.transfer import export_project, import_project


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
        return {"status": "verified",
                "checks": {"image_reachable": {"ok": True}}}

    async def get_document(self, library_id, record_id):
        return {"title": "On the Origin of Species"}

    async def compare_documents(self, documents, aspects=None, question=None,
                                pages_per_aspect=2):
        rows = [{
            "aspect": "content",
            "shared_terms": [], "partial_terms": [],
            "unique_terms": {},
            "dictionary_concept_overlap": [],
            "documents": {f"{d['library_id']}|{d['record_id']}": {
                "found": True,
                "excerpts": [{"aspect": "content",
                              "page_id": f"{d['library_id']}:{d['record_id']}@1",
                              "citation_key": "k", "image_url": None,
                              "excerpt": f"passage from {d['library_id']}"}]}
                for d in documents},
        }]
        return {"status": "compared",
                "documents": [{"library_id": d["library_id"],
                               "record_id": d["record_id"], "title": "t",
                               "date": None, "landing_url": None,
                               "error": None, "verified_pages": 1}
                              for d in documents],
                "aspects": ["content"], "question": question, "rows": rows}


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


def _req(http, method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(http[0] + path, data=data, method=method,
                                 headers=headers or {})
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


def _auth(http, extra=None):
    return {"X-GLM-CSRF": http[4], "Content-Type": "application/json",
            **(extra or {})}


def _project(http):
    status, project = _req(http, "POST", "/api/workspace/projects",
                           {"title": "P"}, _auth(http))
    assert status == 201
    return project


def _save_doc(http, project_id, record, statement="Public Domain",
              library="internet-archive"):
    token = http[1].register_snapshot("document", library, {
        "record_id": record, "title": f"Title {record}",
        "rights": {"statement": statement}})
    status, doc = _req(http, "POST", "/api/workspace/documents",
                       {"project_id": project_id, "save_token": token},
                       _auth(http))
    assert status == 201, doc
    return doc


def _page_token(http, record="rec", statement="Public Domain",
                text="alpha verbatim passage omega",
                library="internet-archive"):
    return http[1].register_snapshot("page", library, {
        "_page_id": f"{record}@1", "record_id": record,
        "library_id": library, "contents": text, "verified_mapping": True,
        "rights": {"statement": statement}})


# ------------------------------------------------- imported rights claims

def test_import_claim_never_stores_excerpt(tmp_path):
    src = WorkspaceStore(tmp_path / "src.db")
    project = src.create_project("P")
    doc = src.save_document(project["project_id"], "internet-archive",
                            "recX", {"title": "T",
                                     "rights": {"statement": "Public Domain"}})
    src.save_citation(doc["saved_document_id"], {
        "page_id": "recX@1", "citation_key": "k1",
        "original_excerpt": "verbatim text here", "excerpt_start": 0,
        "excerpt_end": 18, "excerpt_hash": "x",
        "quotation_verification_status": "verified_against_fetched_ocr",
        "page_mapping_status": "verified",
        "rights_at_save": {"statement": "Public Domain"}})
    bundle = export_project(src, project["project_id"])
    dst = WorkspaceStore(tmp_path / "dst.db")
    result = import_project(dst, bundle)
    imported = dst.list_projects()[0]
    citations = dst.list_citations(imported["project_id"])
    assert len(citations) == 1
    cit = citations[0]
    # b8: the file's Public Domain claim grants nothing.
    assert cit["original_excerpt"] is None
    assert "not independently verified" in (cit["excerpt_omitted_reason"] or "")
    assert cit["excerpt_hash"] == "x"  # reference information is kept
    assert cit["quotation_verification_status"] == "imported_unverified"
    docs = dst.list_documents(imported["project_id"])
    assert docs[0]["rights_trust"] == "imported_claim"
    assert any(o["kind"] == "citation_excerpt" for o in result["excerpt_omissions"])


def test_imported_document_claim_not_a_citation_fallback(http):
    # Import a project whose document claims Public Domain.
    store = http[2]
    src_project = _project(http)
    doc = _save_doc(http, src_project["project_id"], "recImp")
    token = _page_token(http, record="recImp")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": src_project["project_id"],
                        "save_token": token,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 201 and cit["excerpt_stored"] is True
    bundle = export_project(store, src_project["project_id"])
    status, imported = _req(http, "POST", "/api/workspace/import", bundle,
                            _auth(http))
    assert status == 201, imported
    new_project = imported["project"]["project_id"]
    new_doc = store.list_documents(new_project)[0]
    assert new_doc["rights_trust"] == "imported_claim"
    # A fresh page fetch whose own rights are unknown must NOT
    # fall back to the imported document claim.
    server_mod.RUNTIME.service.page_rights = "Public Domain"
    token = _page_token(http, record="recImp", statement="some vague wording")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": new_project,
                        "saved_document_id": new_doc["saved_document_id"],
                        "save_token": token,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 201, cit
    assert cit["excerpt_stored"] is False


# ------------------------------------------------- latest rights on new saves

def test_latest_restrictive_observation_blocks_new_save(http):
    project = _project(http)
    doc = _save_doc(http, project["project_id"], "recA")
    http[2].add_rights_observation(doc["saved_document_id"], "In Copyright",
                                   "copyrighted", "reverify", "rights_changed")
    token = _page_token(http, record="recA")  # fresh token claims Public Domain
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"],
                        "save_token": token,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 201, cit
    assert cit["excerpt_stored"] is False
    assert "latest rights observation" in (cit["excerpt_omitted_reason"] or "")


# ------------------------------------------------- NonCommercial confirmation

def test_nc_policy_requires_confirmation():
    decision = policy.evaluate("CC BY-NC 4.0")
    assert decision["excerpt_requires_confirmation"] is True
    stored, decision = policy.gate_excerpt("some text", "CC BY-NC 4.0")
    assert stored is None
    stored, decision = policy.gate_excerpt("some text", "CC BY-NC 4.0",
                                           nc_confirmed=True)
    assert stored == "some text"


def test_nc_citation_save_409_then_confirmed(http):
    project = _project(http)
    doc = _save_doc(http, project["project_id"], "recNC",
                    statement="CC BY-NC 4.0")
    token = _page_token(http, record="recNC", statement="CC BY-NC 4.0")
    status, err = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"],
                        "save_token": token,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 409 and "nc_confirmation_required" in err["error"]
    token = _page_token(http, record="recNC", statement="CC BY-NC 4.0")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"],
                        "save_token": token, "nc_purpose_confirmed": True,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 201 and cit["excerpt_stored"] is True


# ------------------------------------------------- cross-library record_id

def test_comparison_cross_library_same_record_id(http):
    project = _project(http)
    doc_a = _save_doc(http, project["project_id"], "rec",
                      library="internet-archive")
    doc_b = _save_doc(http, project["project_id"], "rec", library="loc")
    status, comp = _req(http, "POST", "/api/workspace/comparisons",
                        {"project_id": project["project_id"],
                         "saved_document_ids": [doc_a["saved_document_id"],
                                                doc_b["saved_document_id"]],
                         "title": "x"}, _auth(http))
    assert status == 201, comp
    excerpts = comp["original_excerpts"]
    a_texts = [e["text"] for e in excerpts[doc_a["saved_document_id"]]]
    b_texts = [e["text"] for e in excerpts[doc_b["saved_document_id"]]]
    assert a_texts == ["passage from internet-archive"]
    assert b_texts == ["passage from loc"]


# ------------------------------------------------- restore trust + quiescence

def test_restore_downgrades_verification_and_rights(http, tmp_path):
    project = _project(http)
    doc = _save_doc(http, project["project_id"], "recA")
    token = _page_token(http, record="recA")
    status, cit = _req(http, "POST", "/api/workspace/citations",
                       {"project_id": project["project_id"],
                        "save_token": token,
                        "excerpt": "alpha verbatim passage omega"}, _auth(http))
    assert status == 201 and cit["excerpt_stored"] is True
    # Build a backup file of the current database and restore it
    # as an upload: structurally valid, authenticity unproven.
    store = http[2]
    backup = store.backup(tmp_path / "upload.db")
    data = open(backup["path"], "rb").read()
    status, result = _req(http, "POST", "/api/workspace/restore?confirm=1",
                          headers=_auth(http, {"Content-Type": "application/octet-stream"}),
                          raw=data)
    assert status == 200, result
    assert result["trust_downgrade"]["citations_downgraded"] >= 1
    new_store = http[1].store
    restored_cit = new_store.get_citation(cit["citation_id"])
    assert restored_cit["quotation_verification_status"] == "restored_unverified"
    assert restored_cit["verified_at"] is None
    statuses = [o["status"] for o in restored_cit["observations"]]
    assert "restored_downgrade" in statuses
    restored_doc = new_store.get_document(doc["saved_document_id"])
    assert restored_doc["rights_trust"] == "restored_claim"
    # The stored excerpt text remains in the DB but the view
    # withholds it until re-verification.
    assert restored_cit["original_excerpt"] is not None


def test_quiesce_waits_for_inflight_operations(http):
    ws = http[1]
    ws.op_begin()
    try:
        assert ws.quiesce(timeout=0.2) is False
        assert ws.restoring is True
    finally:
        ws.op_end()
        ws.unquiesce()
    assert ws.quiesce(timeout=2.0) is True
    ws.unquiesce()
    assert ws.restoring is False


def test_schema_current_and_validate_backup(tmp_path):
    store = WorkspaceStore(tmp_path / "w.db")
    # b11 final review section 11: schema v6 adds the monotonic
    # rights-observation sequence on top of b11's v5.
    assert store.schema_version == 6
    backup = store.backup(tmp_path / "b.db")
    info = WorkspaceStore.validate_backup(backup["path"])
    assert info["ok"], info["problems"]
