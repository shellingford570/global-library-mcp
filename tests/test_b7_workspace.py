"""b7: Research Workspace - storage, policy, exports, transfer,
web API security and provenance. All fixtures are local."""
from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from global_library_mcp.workspace import policy
from global_library_mcp.workspace.exports import (assign_keys, project_markdown,
                                                  to_bibtex, to_csl_json, to_ris)
from global_library_mcp.workspace.store import (SCHEMA_VERSION, DuplicateError,
                                                FutureSchemaError, WorkspaceStore)
from global_library_mcp.workspace.transfer import (ImportError_, export_project,
                                                   import_project)


@pytest.fixture()
def store(tmp_path):
    s = WorkspaceStore(tmp_path / "w.db")
    yield s
    s.close()


def _doc(store, pid, record="rec1", **kw):
    fields = {"title": "On the Origin of Species", "author": "Darwin, Charles",
              "publication_date": "1859", "language_raw": "en",
              "rights_snapshot": {"statement": "Public Domain"}}
    fields.update(kw)
    return store.save_document(pid, "internet-archive", record, fields)


# ---------------------------------------------------------------- storage
def test_schema_and_pragmas(store):
    assert store.schema_version == SCHEMA_VERSION
    assert store.integrity_check() == "ok"
    assert store._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert store._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_future_schema_refused(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    conn.execute("INSERT INTO schema_migrations VALUES (99, '2026-01-01T00:00:00Z')")
    conn.commit(); conn.close()
    with pytest.raises(FutureSchemaError):
        WorkspaceStore(path)


def test_project_crud_archive_and_counts(store):
    p = store.create_project("進化論", "desc", tags=["明治"])
    assert p["counts"]["documents"] == 0
    _doc(store, p["project_id"])
    assert store.get_project(p["project_id"])["counts"]["documents"] == 1
    updated = store.update_project(p["project_id"], archived=True)
    assert updated["archived_at"]
    assert store.list_projects(include_archived=False) == []
    counts = store.delete_project(p["project_id"])
    assert counts["documents"] == 1
    assert store.get_project(p["project_id"]) is None


def test_duplicate_document_rejected_but_editions_kept(store):
    p = store.create_project("x")
    _doc(store, p["project_id"])
    with pytest.raises(DuplicateError):
        _doc(store, p["project_id"])
    # a different record id (another edition/copy) is a different document
    _doc(store, p["project_id"], record="rec2", edition="6th")
    assert len(store.list_documents(p["project_id"])) == 2


def test_foreign_keys_enforced(store):
    with pytest.raises(KeyError):
        store.save_document("no-such-project", "lib", "r", {})
    # and at the SQL level: a child row for a missing parent is refused
    with pytest.raises(sqlite3.IntegrityError):
        with store._conn:
            store._conn.execute(
                "INSERT INTO saved_citations (citation_id, saved_document_id, page_id,"
                " citation_key, saved_at) VALUES ('c', 'missing-doc', 'p', 'k', 't')")


def test_cascade_delete_removes_children(store):
    p = store.create_project("x")
    doc = _doc(store, p["project_id"])
    store.save_citation(doc["saved_document_id"],
                        {"page_id": "rec1@1", "citation_key": "k1"})
    store.delete_project(p["project_id"])
    assert store.get_citation(store.list_citations(p["project_id"]) and "x" or "none") is None
    assert store.list_documents(p["project_id"]) == []


def test_concurrent_document_saves(store):
    p = store.create_project("x")
    errors = []

    def worker(i):
        try:
            _doc(store, p["project_id"], record=f"rec{i}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(store.list_documents(p["project_id"])) == 12


def test_local_search_and_sql_injection(store):
    p = store.create_project("x")
    _doc(store, p["project_id"])
    store.save_note(p["project_id"], "ダーウィンへの考察メモ")
    found = store.local_search(p["project_id"], "ダーウィン")
    assert len(found["notes"]) == 1
    assert store.local_search(p["project_id"], "' OR '1'='1")["documents"] == []
    assert store.local_search(p["project_id"], "%")["documents"] == []


def test_tags_and_collections(store):
    p = store.create_project("x")
    doc = _doc(store, p["project_id"])
    store.set_document_tags(doc["saved_document_id"], ["一次資料", "要確認"])
    assert store.list_documents(p["project_id"], tag="一次資料")
    assert store.list_documents(p["project_id"], tag="存在しない") == []
    coll = store.create_collection(p["project_id"], "進化論")
    store.collection_add(coll["collection_id"], doc["saved_document_id"])
    assert len(store.list_documents(p["project_id"], collection_id=coll["collection_id"])) == 1
    with pytest.raises(DuplicateError):
        store.create_collection(p["project_id"], "進化論")


# ----------------------------------------------------------------- policy
@pytest.mark.parametrize("statement,category", [
    ("Public Domain Mark", "public_domain"),
    ("CC0 1.0", "public_domain"),
    ("https://creativecommons.org/licenses/by/4.0/", "cc_by"),
    ("CC BY-NC-ND 4.0", "cc_by_nc_nd"),
    ("CC BY-SA 3.0", "cc_by_sa"),
    ("In Copyright", "copyrighted"),
    ("Rights unknown", "unknown"),
    (None, "unknown"),
    ("Access restricted - lending", "restricted"),
])
def test_rights_classification(statement, category):
    assert policy.classify_rights(statement) == category


def test_excerpt_gate_withholds_unknown_and_copyrighted():
    excerpt, decision = policy.gate_excerpt("some text", "unknown")
    assert excerpt is None and decision["excerpt_storage"] is False
    excerpt, decision = policy.gate_excerpt("some text", "In Copyright")
    assert excerpt is None
    excerpt, decision = policy.gate_excerpt("some text", "Public Domain")
    assert excerpt == "some text"
    long_text = "x" * (policy.MAX_EXCERPT_CHARS + 10)
    excerpt, decision = policy.gate_excerpt(long_text, "CC BY 4.0")
    # Final review section 13: oversize excerpts are withheld,
    # never silently truncated (stored text, offsets and hash
    # must always agree).
    assert excerpt is None and "storage limit" in decision["reason"]


def test_fulltext_and_images_never_stored():
    for statement in ("Public Domain", "CC BY 4.0", "unknown"):
        decision = policy.evaluate(statement)
        assert decision["fulltext_storage"] is False
        assert decision["image_storage"] is False
        assert decision["external_transfer"] is False


# ---------------------------------------------------------------- exports
def _docs(store):
    p = store.create_project("x")
    a = _doc(store, p["project_id"])
    b = _doc(store, p["project_id"], record="rec2", title="種の起源",
             author="ダーウィン", publication_date=None)
    return p, [store.get_document(a["saved_document_id"]),
               store.get_document(b["saved_document_id"])]


def test_bibtex_stable_keys_and_escaping(store):
    _, docs = _docs(store)
    docs[0]["title"] = "Origin {with} braces " + chr(92) + "cite{x}"
    out = to_bibtex(docs)
    assert (chr(92) + "{with" + chr(92) + "}") in out
    assert (chr(92) + "textbackslash{}") in out
    keys = assign_keys(docs)
    # Final review section 21: the key is the one stored at
    # save time (from the original title "On the origin of
    # species"), stable even if the title is later edited.
    assert keys[docs[0]["saved_document_id"]] == "darwin1859the"
    assert keys[docs[0]["saved_document_id"]] == docs[0]["citation_key"]
    assert to_bibtex(docs) == out  # deterministic


def test_ris_newline_injection_blocked(store):
    _, docs = _docs(store)
    docs[0]["title"] = "Title\nTY  - FAKE\nAU  - Attacker"
    out = to_ris(docs)
    lines = out.splitlines()
    # the injected text stays inside the TI value on one line:
    # no line of its own may start with the forged tag
    assert not any(line.startswith("TY  - FAKE") for line in lines)
    assert sum(1 for line in lines if line.startswith("TY  - ")) == 2


def test_csl_json_cjk_literal_and_missing_year(store):
    _, docs = _docs(store)
    items = {i["id"]: i for i in to_csl_json(docs)}
    cjk = next(i for i in items.values() if i["title"] == "種の起源")
    assert cjk["author"] == [{"literal": "ダーウィン"}]
    assert "issued" not in cjk  # unknown year stays absent, never invented
    darwin = next(i for i in items.values() if i["title"].startswith("On the"))
    assert darwin["author"] == [{"family": "Darwin", "given": "Charles"}]
    assert darwin["issued"] == {"date-parts": [[1859]]}


def test_markdown_report_gates_excerpts(store):
    p, docs = _docs(store)
    cit = store.save_citation(docs[0]["saved_document_id"], {
        "page_id": "rec1@1", "citation_key": "k",
        "original_excerpt": "verbatim text",
        "rights_at_save": {"statement": "In Copyright"},
        "quotation_verification_status": "verified_against_fetched_ocr",
        "provenance": "system_fetched"})
    text, omissions = project_markdown(
        store.get_project(p["project_id"]), docs,
        store.list_citations(p["project_id"]), [], [], [])
    assert "verbatim text" not in text
    assert len(omissions) == 1
    assert "AI生成文は含みません" in text


# ---------------------------------------------------------------- transfer
def test_export_import_roundtrip(store, tmp_path):
    p, docs = _docs(store)
    store.save_citation(docs[0]["saved_document_id"], {
        "page_id": "rec1@1", "citation_key": "k",
        "original_excerpt": "public domain words",
        "rights_at_save": {"statement": "Public Domain"},
        "quotation_verification_status": "verified_against_fetched_ocr",
        "provenance": "system_fetched"})
    payload = export_project(store, p["project_id"])
    other = WorkspaceStore(tmp_path / "other.db")
    result = import_project(other, payload)
    new_pid = result["project"]["project_id"]
    assert new_pid != p["project_id"]
    imported_docs = other.list_documents(new_pid)
    assert len(imported_docs) == 2
    assert imported_docs[0]["saved_document_id"] != docs[0]["saved_document_id"]
    imported_cits = other.list_citations(new_pid)
    assert imported_cits[0]["provenance"] == "imported"
    # the claimed verification is a historical claim, not current state
    assert imported_cits[0]["quotation_verification_status"] == "imported_unverified"
    assert imported_cits[0]["observations"][0]["status"] == "imported_claim"
    other.close()


def test_import_rejects_bad_files(store):
    with pytest.raises(ImportError_):
        import_project(store, {"format": "other"})
    with pytest.raises(ImportError_):
        import_project(store, {"format": "global-library-mcp-project",
                               "format_version": 99, "project": {"title": "x"}})
    payload = {"format": "global-library-mcp-project", "format_version": 1,
               "schema_version": 1, "project": {"title": "x"},
               "saved_documents": [{"saved_document_id": "a", "library_id": "l",
                                    "record_id": "r"},
                                   {"saved_document_id": "a", "library_id": "l",
                                    "record_id": "r2"}]}
    with pytest.raises(ImportError_):
        import_project(store, payload)
    payload["saved_documents"] = [{"saved_document_id": "a", "library_id": "l",
                                   "record_id": "r", "landing_url": "javascript:alert(1)"}]
    with pytest.raises(ImportError_):
        import_project(store, payload)
    payload["saved_documents"] = [{"saved_document_id": "a", "library_id": "l",
                                   "record_id": "r", "api_key": "sk-secret"}]
    with pytest.raises(ImportError_):
        import_project(store, payload)
    assert store.list_projects() == []  # nothing leaked in


def test_import_rolls_back_on_bad_citation(store):
    payload = {"format": "global-library-mcp-project", "format_version": 1,
               "schema_version": 1, "project": {"title": "x"},
               "saved_documents": [{"saved_document_id": "a", "library_id": "l",
                                    "record_id": "r"}],
               "saved_citations": [{"citation_id": "c1",
                                    "saved_document_id": "missing"}]}
    with pytest.raises(ImportError_):
        import_project(store, payload)
    assert store.list_projects() == []


def test_backup_and_inspect(store, tmp_path):
    p = store.create_project("x")
    _doc(store, p["project_id"])
    info = store.backup(tmp_path / "b.db")
    assert info["integrity"] == "ok" and len(info["sha256"]) == 64
    inspected = WorkspaceStore.inspect_backup(tmp_path / "b.db")
    assert inspected["schema_version"] == SCHEMA_VERSION
