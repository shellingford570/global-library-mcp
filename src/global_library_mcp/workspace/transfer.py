"""Project JSON export / import (b7, brief sections 26, 27).

Export is policy-gated: excerpts that may not be exported are
omitted and counted with reasons. Import treats the file as
untrusted input: size/record/string/depth limits, structural
validation, URL scheme checks, duplicate-id rejection,
foreign-key resolution inside the file, and a single
transaction (any error rolls the whole import back).
Imported verification claims are preserved as historical
claims only - they never become current verified state.
"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    from importlib.metadata import version as _pkg_version
    APP_VERSION = _pkg_version("global-library-mcp")
except Exception:  # pragma: no cover - source checkout without install
    APP_VERSION = "unknown"
from .policy import evaluate as evaluate_rights
from .store import SCHEMA_VERSION, WorkspaceStore, new_id, now_iso, search_text

FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_RECORDS = 20_000
MAX_STRING = 100_000
MAX_DEPTH = 32

_URL_OK = re.compile(r"^https?://", re.IGNORECASE)
_SECRET_KEYS = {"api_key", "apikey", "token", "password", "secret",
                "session", "authorization", "cookie"}


class ImportError_(ValueError):
    pass


def export_project(store: WorkspaceStore, project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    documents = store.list_documents(project_id)
    citations = store.list_citations(project_id)
    notes = store.list_notes(project_id)
    history = store.list_history(project_id)
    comparisons = store.list_comparisons(project_id)
    collections = store.list_collections(project_id)
    omissions: list[dict[str, Any]] = []
    export_citations = []
    for cit in citations:
        item = dict(cit)
        statement = (cit.get("rights_at_save") or {}).get("statement")
        if item.get("original_excerpt") and not evaluate_rights(statement)["excerpt_export"]:
            item["original_excerpt"] = None
            item["excerpt_omitted_reason"] = (
                "omitted at export: " + evaluate_rights(statement)["reason"])
            omissions.append({"kind": "citation_excerpt",
                              "citation_id": cit["citation_id"],
                              "reason": item["excerpt_omitted_reason"]})
        item.pop("observations", None)
        export_citations.append(item)
    collection_docs: dict[str, list[str]] = {}
    for coll in collections:
        members = store.list_documents(project_id, collection_id=coll["collection_id"])
        collection_docs[coll["collection_id"]] = [d["saved_document_id"] for d in members]
    return {
        "format": "global-library-mcp-project",
        "format_version": FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "application_version": APP_VERSION,
        "exported_at": now_iso(),
        "project": {k: project.get(k) for k in
                    ("title", "description", "created_at", "updated_at", "tags")},
        "saved_documents": documents,
        "saved_citations": export_citations,
        "research_notes": notes,
        "search_history": history,
        "saved_comparisons": comparisons,
        "collections": [{**c, "saved_document_ids": collection_docs.get(c["collection_id"], [])}
                        for c in collections],
        "rights_observations": {d["saved_document_id"]: store.list_rights_observations(d["saved_document_id"])
                                for d in documents},
        "export_omissions": omissions,
    }


def _walk_limits(node: Any, depth: int, counters: dict[str, int]) -> None:
    if depth > MAX_DEPTH:
        raise ImportError_("JSON nesting too deep")
    if isinstance(node, str):
        if len(node) > MAX_STRING:
            raise ImportError_("string too long")
        counters["strings"] += 1
    elif isinstance(node, dict):
        counters["records"] += 1
        for key, value in node.items():
            if key.lower() in _SECRET_KEYS:
                raise ImportError_(f"secret-like field is not importable: {key}")
            _walk_limits(value, depth + 1, counters)
    elif isinstance(node, list):
        for value in node:
            _walk_limits(value, depth + 1, counters)
    if counters["records"] > MAX_RECORDS:
        raise ImportError_("too many records")


def _check_url(value: Any, field: str) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str) or not _URL_OK.match(value):
        raise ImportError_(f"invalid URL in {field}")


def _require_list(payload: dict[str, Any], key: str) -> list:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ImportError_(f"{key} must be a list")
    return value


def import_project(store: WorkspaceStore, payload: Any) -> dict[str, Any]:
    """Validate everything first, then insert in ONE transaction
    with fresh internal ids. Returns the new project summary."""
    if not isinstance(payload, dict):
        raise ImportError_("top level must be an object")
    if payload.get("format") != "global-library-mcp-project":
        raise ImportError_("unsupported format")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ImportError_(f"unsupported format_version: {payload.get('format_version')}")
    if int(payload.get("schema_version") or 0) > SCHEMA_VERSION:
        raise ImportError_("file schema is newer than this build")
    counters = {"records": 0, "strings": 0}
    _walk_limits(payload, 0, counters)

    project_in = payload.get("project")
    if not isinstance(project_in, dict) or not str(project_in.get("title") or "").strip():
        raise ImportError_("project.title is required")
    documents = _require_list(payload, "saved_documents")
    citations = _require_list(payload, "saved_citations")
    notes = _require_list(payload, "research_notes")
    history = _require_list(payload, "search_history")
    comparisons = _require_list(payload, "saved_comparisons")
    collections = _require_list(payload, "collections")

    doc_ids: set[str] = set()
    for doc in documents:
        if not isinstance(doc, dict):
            raise ImportError_("saved_documents entries must be objects")
        did = doc.get("saved_document_id")
        if not isinstance(did, str) or not did or len(did) > 200 or did in doc_ids:
            raise ImportError_("duplicate or invalid saved_document_id")
        doc_ids.add(did)
        if not doc.get("library_id") or not doc.get("record_id"):
            raise ImportError_("document requires library_id and record_id")
        _check_url(doc.get("landing_url"), "landing_url")
    cit_ids: set[str] = set()
    for cit in citations:
        if not isinstance(cit, dict):
            raise ImportError_("saved_citations entries must be objects")
        cid = cit.get("citation_id")
        if not isinstance(cid, str) or not cid or cid in cit_ids:
            raise ImportError_("duplicate or invalid citation_id")
        cit_ids.add(cid)
        if cit.get("saved_document_id") not in doc_ids:
            raise ImportError_("citation references an unknown document")
        _check_url(cit.get("source_url"), "source_url")
        _check_url(cit.get("image_url"), "image_url")

    ts = now_iso()
    id_map: dict[str, str] = {}
    conn = store._conn  # single-transaction import on the store connection
    with store._lock, conn:
        new_project_id = new_id()
        conn.execute(
            "INSERT INTO projects (project_id, title, description, created_at, updated_at, schema_version)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (new_project_id, str(project_in["title"])[:500],
             str(project_in.get("description") or "")[:20000], ts, ts, SCHEMA_VERSION))
        for name in project_in.get("tags") or []:
            if isinstance(name, str):
                store._attach_project_tag(new_project_id, name)
        for doc in documents:
            new_doc_id = new_id()
            id_map[doc["saved_document_id"]] = new_doc_id
            values = {k: doc.get(k) for k in WorkspaceStore._DOC_FIELDS}
            conn.execute(
                "INSERT INTO saved_documents (saved_document_id, project_id, library_id, record_id,"
                " identifiers, rights_snapshot, saved_at, updated_at, search_text, "
                + ", ".join(WorkspaceStore._DOC_FIELDS) + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                + ", ".join("?" for _ in WorkspaceStore._DOC_FIELDS) + ")",
                (new_doc_id, new_project_id, str(doc["library_id"])[:100],
                 str(doc["record_id"])[:500],
                 json.dumps(doc.get("identifiers") or {}, ensure_ascii=False),
                 json.dumps(doc.get("rights_snapshot") or {}, ensure_ascii=False),
                 ts, ts,
                 search_text(values.get("title"), values.get("author"),
                             values.get("publication_date"), doc.get("library_id")),
                 *[values[k] for k in WorkspaceStore._DOC_FIELDS]))
            for name in doc.get("tags") or []:
                if isinstance(name, str):
                    row = conn.execute("SELECT tag_id FROM tags WHERE name = ?", (name,)).fetchone()
                    tag_id = row["tag_id"] if row else new_id()
                    if not row:
                        conn.execute("INSERT INTO tags (tag_id, name) VALUES (?, ?)", (tag_id, name))
                    conn.execute(
                        "INSERT OR IGNORE INTO document_tags (saved_document_id, tag_id) VALUES (?, ?)",
                        (new_doc_id, tag_id))
        imported_claims = 0
        for cit in citations:
            new_cit_id = new_id()
            id_map[cit["citation_id"]] = new_cit_id
            values = {k: cit.get(k) for k in WorkspaceStore._CIT_FIELDS}
            claimed = values.get("quotation_verification_status")
            values["provenance"] = "imported"
            values["quotation_verification_status"] = "imported_unverified"
            rights = values.get("rights_at_save")
            if isinstance(rights, (dict, list)):
                values["rights_at_save"] = json.dumps(rights, ensure_ascii=False)
            elif rights is None:
                values["rights_at_save"] = "{}"
            conn.execute(
                "INSERT INTO saved_citations (citation_id, saved_document_id, saved_at, search_text, "
                + ", ".join(WorkspaceStore._CIT_FIELDS) + ") VALUES (?, ?, ?, ?, "
                + ", ".join("?" for _ in WorkspaceStore._CIT_FIELDS) + ")",
                (new_cit_id, id_map[cit["saved_document_id"]], ts,
                 search_text(values.get("original_excerpt"), values.get("page_id")),
                 *[values[k] for k in WorkspaceStore._CIT_FIELDS]))
            if claimed:
                imported_claims += 1
                conn.execute(
                    "INSERT INTO verification_observations (observation_id, citation_id, status, detail, observed_at)"
                    " VALUES (?, ?, 'imported_claim', ?, ?)",
                    (new_id(), new_cit_id,
                     json.dumps({"claimed_status": claimed}, ensure_ascii=False), ts))
        for note in notes:
            if not isinstance(note, dict):
                raise ImportError_("research_notes entries must be objects")
            doc_ref = note.get("saved_document_id")
            cit_ref = note.get("citation_id")
            conn.execute(
                "INSERT INTO research_notes (note_id, project_id, saved_document_id, citation_id,"
                " title, content, created_at, updated_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), new_project_id,
                 id_map.get(doc_ref) if doc_ref else None,
                 id_map.get(cit_ref) if cit_ref else None,
                 str(note.get("title") or "")[:500], str(note.get("content") or ""),
                 ts, ts, search_text(note.get("title"), note.get("content"))))
        for entry in history:
            if not isinstance(entry, dict):
                raise ImportError_("search_history entries must be objects")
            conn.execute(
                "INSERT INTO search_history (search_id, project_id, original_query, search_parameters,"
                " planned_variants, executed_variants, searched_libraries, skipped_libraries,"
                " result_summary, http_stats, search_status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), new_project_id, str(entry.get("original_query") or "")[:2000],
                 json.dumps(entry.get("search_parameters") or {}, ensure_ascii=False),
                 json.dumps(entry.get("planned_variants") or [], ensure_ascii=False),
                 json.dumps(entry.get("executed_variants") or [], ensure_ascii=False),
                 json.dumps(entry.get("searched_libraries") or {}, ensure_ascii=False),
                 json.dumps(entry.get("skipped_libraries") or {}, ensure_ascii=False),
                 json.dumps(entry.get("result_summary") or {}, ensure_ascii=False),
                 json.dumps(entry.get("http_stats") or {}, ensure_ascii=False),
                 str(entry.get("search_status") or "completed")[:50], ts))
        for comp in comparisons:
            if not isinstance(comp, dict):
                raise ImportError_("saved_comparisons entries must be objects")
            mapped = [id_map[d] for d in comp.get("saved_document_ids") or [] if d in id_map]
            conn.execute(
                "INSERT INTO saved_comparisons (comparison_id, project_id, title, saved_document_ids,"
                " comparison_aspects, original_excerpts, lexical_overlap, dictionary_concept_overlap,"
                " shared_by_all, shared_by_some, semantic_status, insufficient_evidence, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), new_project_id, str(comp.get("title") or "")[:500],
                 json.dumps(mapped), json.dumps(comp.get("comparison_aspects") or {}, ensure_ascii=False),
                 json.dumps(comp.get("original_excerpts") or {}, ensure_ascii=False),
                 json.dumps(comp.get("lexical_overlap") or {}, ensure_ascii=False),
                 json.dumps(comp.get("dictionary_concept_overlap") or {}, ensure_ascii=False),
                 json.dumps(comp.get("shared_by_all") or [], ensure_ascii=False),
                 json.dumps(comp.get("shared_by_some") or [], ensure_ascii=False),
                 "not_checked", json.dumps(comp.get("insufficient_evidence") or [], ensure_ascii=False), ts))
        for coll in collections:
            if not isinstance(coll, dict) or not coll.get("name"):
                raise ImportError_("collections entries require a name")
            new_coll_id = new_id()
            conn.execute(
                "INSERT INTO collections (collection_id, project_id, name, created_at) VALUES (?, ?, ?, ?)",
                (new_coll_id, new_project_id, str(coll["name"])[:200], ts))
            for did in coll.get("saved_document_ids") or []:
                if did in id_map:
                    conn.execute(
                        "INSERT OR IGNORE INTO collection_documents (collection_id, saved_document_id)"
                        " VALUES (?, ?)", (new_coll_id, id_map[did]))
    project = store.get_project(new_project_id)
    return {"project": project, "id_map_size": len(id_map),
            "imported_verification_claims": imported_claims,
            "note": "imported verification states are historical claims, not current verification"}


def dumps_export(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
