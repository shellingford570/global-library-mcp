"""Workspace HTTP layer (b7, brief sections 12, 29).

Security model for the state-changing local API:
- workspace mode refuses non-loopback binds at startup, and
  every workspace request additionally requires a loopback
  client address and a Host header naming a loopback host
  (DNS-rebinding defence);
- every mutation requires the per-process CSRF token in the
  X-GLM-CSRF header (delivered only inside the served page's
  meta tag, never in URLs, logs or exports) and, when an
  Origin header is present, it must match the Host;
- request bodies are size-capped and must be JSON
  (application/json) except the backup-restore upload;
- provenance: clients cannot assert verification. Save
  operations reference short-lived server-side snapshots of
  payloads THIS server returned; the server rebuilds the
  stored record from its own snapshot and re-checks the
  excerpt against the fetched OCR text verbatim.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..workspace import policy as rights_policy
from ..workspace.exports import (assign_keys, base_citation_key,
                                 documents_export, project_markdown)
from ..workspace.store import (SCHEMA_VERSION, DuplicateError,
                               WorkspaceStore, now_iso)
from ..workspace.transfer import (MAX_IMPORT_BYTES, ImportError_,
                                  dumps_export, export_project,
                                  import_project)

SNAPSHOT_TTL_S = 7200
SNAPSHOT_CAP = 512
BODY_CAP = 1_048_576
RESTORE_CAP = 209_715_200
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class WorkspaceWebRuntime:
    def __init__(self, store: WorkspaceStore):
        self.store = store
        self.csrf_token = secrets.token_urlsafe(32)
        self._snapshots: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._snap_lock = threading.Lock()

    # -- snapshots ---------------------------------------------------------
    def register_snapshot(self, kind: str, library_id: str,
                          payload: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(18)
        with self._snap_lock:
            self._snapshots[token] = {"kind": kind, "library_id": library_id,
                                      "payload": payload, "ts": time.time()}
            while len(self._snapshots) > SNAPSHOT_CAP:
                self._snapshots.popitem(last=False)
        return token

    def get_snapshot(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._snap_lock:
            snap = self._snapshots.get(token)
            if snap is None:
                return None
            if time.time() - snap["ts"] > SNAPSHOT_TTL_S:
                del self._snapshots[token]
                return None
            return snap

    def annotate_search_results(self, results: list[dict[str, Any]]) -> None:
        for item in results:
            if isinstance(item, dict) and item.get("library_id") and (
                    item.get("record_id") or item.get("id")):
                item["save_token"] = self.register_snapshot(
                    "document", item["library_id"], item)

    def annotate_page(self, library_id: str, page_id: str,
                      payload: dict[str, Any]) -> None:
        payload["save_token"] = self.register_snapshot(
            "page", library_id, {**payload, "_page_id": page_id})


# --------------------------------------------------------------------------
# field mapping from service payloads to stored records

def _scalar(value: Any) -> Any:
    """Service payloads carry some fields as lists (e.g. b6's
    language_normalized); stored columns are scalar text."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def document_fields(item: dict[str, Any]) -> dict[str, Any]:
    rights = item.get("rights")
    rights_snapshot = rights if isinstance(rights, dict) else {"statement": rights}
    work_link = item.get("work_link") or {}
    fields = {
        "work_id_candidate": item.get("work_id_candidate") or work_link.get("work_id"),
        "author_id_candidate": item.get("author_id_candidate"),
        "resolution_status": item.get("resolution_status") or work_link.get("status"),
        "title": item.get("title"),
        "original_title": item.get("original_title"),
        "translated_title": item.get("translated_title"),
        "author": item.get("author") or item.get("creator"),
        "publication_date": item.get("publication_date") or item.get("date"),
        "publisher": item.get("publisher"),
        "publication_place": item.get("publication_place") or item.get("place"),
        "edition": item.get("edition"),
        "translator": item.get("translator"),
        "volume": item.get("volume"),
        "language_raw": item.get("language_raw") or item.get("language"),
        "language_normalized": item.get("language_normalized"),
        "holding_institution": item.get("holding_institution") or item.get("institution"),
        "material_type": item.get("material_type") or item.get("type"),
        "landing_url": item.get("landing_url") or item.get("url"),
        "identifiers": item.get("identifiers") or {},
        "rights_snapshot": rights_snapshot,
        "discovery_reason": item.get("discovery_reason"),
        "retrieved_at": item.get("retrieved_at") or now_iso(),
    }
    for key, value in list(fields.items()):
        if key not in ("identifiers", "rights_snapshot"):
            fields[key] = _scalar(value)
    return fields


def _host_ok(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        name = host[1:].split("]", 1)[0]
    else:
        name = host.rsplit(":", 1)[0] if ":" in host else host
    return name in LOOPBACK_HOSTS


def _origin_ok(origin: str | None, host_header: str | None) -> bool:
    if not origin:
        return True  # absence alone is not trust: the CSRF token still gates
    parsed = urlparse(origin)
    return parsed.netloc.lower() == (host_header or "").lower()


class WorkspaceApi:
    """Dispatches /api/workspace/* for one handler instance."""

    def __init__(self, runtime: WorkspaceWebRuntime, service_runtime: Any):
        self.ws = runtime
        self.runtime = service_runtime

    # -- plumbing ------------------------------------------------------------
    def guard(self, handler: Any, *, mutation: bool) -> None:
        if handler.client_address[0] not in LOOPBACK_CLIENTS:
            raise ApiError(403, "workspace API is loopback-only")
        host = handler.headers.get("Host")
        if not _host_ok(host):
            raise ApiError(403, "invalid Host header")
        if mutation:
            if handler.headers.get("X-GLM-CSRF") != self.ws.csrf_token:
                raise ApiError(403, "missing or invalid CSRF token")
            if not _origin_ok(handler.headers.get("Origin"), host):
                raise ApiError(403, "Origin does not match Host")

    def read_body(self, handler: Any, cap: int = BODY_CAP) -> bytes:
        length = handler.headers.get("Content-Length")
        if length is None:
            raise ApiError(411, "Content-Length required")
        try:
            size = int(length)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if size < 0 or size > cap:
            raise ApiError(413, "request body too large")
        return handler.rfile.read(size)

    def read_json(self, handler: Any, cap: int = BODY_CAP) -> dict[str, Any]:
        ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype != "application/json":
            raise ApiError(415, "Content-Type must be application/json")
        raw = self.read_body(handler, cap)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid JSON body")
        if not isinstance(value, dict):
            raise ApiError(400, "JSON body must be an object")
        return value

    # -- dispatch ---------------------------------------------------------------
    def handle(self, handler: Any, method: str) -> bool:
        parsed = urlparse(handler.path)
        if not parsed.path.startswith("/api/workspace"):
            return False
        try:
            self._dispatch(handler, method, parsed.path, parse_qs(parsed.query))
        except ApiError as exc:
            handler._send(_json({"error": exc.message}), status=exc.status)
        except DuplicateError as exc:
            handler._send(_json({"error": "already saved", "existing_id": exc.args[0]}), status=409)
        except KeyError as exc:
            handler._send(_json({"error": f"not found: {exc.args[0]}"}), status=404)
        except ImportError_ as exc:
            handler._send(_json({"error": f"import rejected: {exc}"}), status=400)
        except ValueError as exc:
            handler._send(_json({"error": str(exc)}), status=400)
        except Exception:
            # The client gets a safe message; the detail stays in
            # the server's own log (never in the response).
            import traceback
            traceback.print_exc()
            handler._send(_json({"error": "workspace operation failed"}), status=500)
        return True

    def _dispatch(self, handler: Any, method: str, path: str, qs: dict) -> None:
        store = self.ws.store
        parts = [p for p in path.split("/") if p][2:]  # after api/workspace
        mutation = method in ("POST", "PUT", "DELETE")
        self.guard(handler, mutation=mutation)
        send = lambda value, status=200: handler._send(_json(value), status=status)

        if parts == ["status"] and method == "GET":
            send({"enabled": True, "db_path": str(store.db_path),
                  "schema_version": store.schema_version,
                  "integrity": store.integrity_check()})
            return
        if parts == ["projects"] and method == "GET":
            send({"projects": store.list_projects(
                include_archived=qs.get("archived", ["1"])[0] != "0")})
            return
        if parts == ["projects"] and method == "POST":
            body = self.read_json(handler)
            title = str(body.get("title") or "").strip()
            if not title:
                raise ApiError(400, "title is required")
            send(store.create_project(title, str(body.get("description") or ""),
                                      [str(t) for t in body.get("tags") or []][:20]), 201)
            return
        if len(parts) == 2 and parts[0] == "projects":
            pid = parts[1]
            if method == "GET":
                project = store.get_project(pid)
                if project is None:
                    raise ApiError(404, "project not found")
                send(project)
                return
            if method == "PUT":
                body = self.read_json(handler)
                updated = store.update_project(
                    pid, title=body.get("title"), description=body.get("description"),
                    archived=body.get("archived"), tags=body.get("tags"))
                if updated is None:
                    raise ApiError(404, "project not found")
                send(updated)
                return
            if method == "DELETE":
                project = store.get_project(pid)
                if project is None:
                    raise ApiError(404, "project not found")
                if qs.get("confirm", [""])[0] != "1":
                    raise ApiError(409, "deletion requires confirmation; "
                                        "related record counts are attached")
                counts = store.delete_project(pid)
                send({"deleted": pid, "related_counts": counts,
                      "note": "backups and exported files may still contain this data"})
                return
        if parts == ["documents"] and method == "POST":
            body = self.read_json(handler)
            snap = self.ws.get_snapshot(body.get("save_token"))
            if snap is None or snap["kind"] != "document":
                raise ApiError(410, "save token expired or unknown; re-run the search")
            item = snap["payload"]
            doc = store.save_document(str(body.get("project_id") or ""),
                                      snap["library_id"],
                                      str(item.get("record_id") or item.get("id") or ""),
                                      document_fields(item))
            send(doc, 201)
            return
        if parts == ["documents"] and method == "GET":
            pid = qs.get("project_id", [""])[0]
            send({"documents": store.list_documents(
                pid, tag=qs.get("tag", [None])[0],
                collection_id=qs.get("collection_id", [None])[0])})
            return
        if len(parts) == 2 and parts[0] == "documents" and method == "DELETE":
            if not store.delete_document(parts[1]):
                raise ApiError(404, "document not found")
            send({"deleted": parts[1]})
            return
        if len(parts) == 3 and parts[0] == "documents" and parts[2] == "tags" and method == "PUT":
            body = self.read_json(handler)
            send({"tags": store.set_document_tags(
                parts[1], [str(t) for t in body.get("tags") or []][:30])})
            return
        if parts == ["collections"] and method == "POST":
            body = self.read_json(handler)
            send(store.create_collection(str(body.get("project_id") or ""),
                                         str(body.get("name") or "").strip()), 201)
            return
        if parts == ["collections"] and method == "GET":
            send({"collections": store.list_collections(qs.get("project_id", [""])[0])})
            return
        if len(parts) == 3 and parts[0] == "collections" and parts[2] == "documents" and method == "POST":
            body = self.read_json(handler)
            store.collection_add(parts[1], str(body.get("saved_document_id") or ""))
            send({"ok": True})
            return
        if len(parts) == 3 and parts[0] == "collections" and parts[2] == "documents" and method == "DELETE":
            body = self.read_json(handler)
            store.collection_remove(parts[1], str(body.get("saved_document_id") or ""))
            send({"ok": True})
            return
        if len(parts) == 2 and parts[0] == "collections" and method == "DELETE":
            if not store.delete_collection(parts[1]):
                raise ApiError(404, "collection not found")
            send({"deleted": parts[1]})
            return
        if parts == ["citations"] and method == "POST":
            body = self.read_json(handler)
            send(self._save_citation_from_snapshot(body), 201)
            return
        if parts == ["citations", "manual"] and method == "POST":
            body = self.read_json(handler)
            send(self._save_manual_citation(body), 201)
            return
        if parts == ["citations"] and method == "GET":
            send({"citations": store.list_citations(qs.get("project_id", [""])[0])})
            return
        if len(parts) == 3 and parts[0] == "citations" and parts[2] == "reverify" and method == "POST":
            self.read_json(handler)
            send(self._reverify(parts[1]))
            return
        if len(parts) == 2 and parts[0] == "citations" and method == "DELETE":
            if not store.delete_citation(parts[1]):
                raise ApiError(404, "citation not found")
            send({"deleted": parts[1]})
            return
        if parts == ["notes"] and method == "POST":
            body = self.read_json(handler)
            send(store.save_note(str(body.get("project_id") or ""),
                                 str(body.get("content") or ""),
                                 title=str(body.get("title") or ""),
                                 saved_document_id=body.get("saved_document_id"),
                                 citation_id=body.get("citation_id")), 201)
            return
        if parts == ["notes"] and method == "GET":
            send({"notes": store.list_notes(qs.get("project_id", [""])[0])})
            return
        if len(parts) == 2 and parts[0] == "notes" and method == "PUT":
            body = self.read_json(handler)
            note = store.get_note(parts[1])
            if note is None:
                raise ApiError(404, "note not found")
            send(store.save_note(note["project_id"], str(body.get("content") or ""),
                                 title=str(body.get("title") or ""),
                                 note_id=parts[1]))
            return
        if len(parts) == 2 and parts[0] == "notes" and method == "DELETE":
            if not store.delete_note(parts[1]):
                raise ApiError(404, "note not found")
            send({"deleted": parts[1]})
            return
        if parts == ["history"] and method == "POST":
            body = self.read_json(handler)
            entry = {k: body.get(k) for k in
                     ("original_query", "search_parameters", "planned_variants",
                      "executed_variants", "searched_libraries", "skipped_libraries",
                      "result_summary", "http_stats", "search_status")}
            send(store.save_history(str(body.get("project_id") or ""), entry), 201)
            return
        if parts == ["history"] and method == "GET":
            send({"history": store.list_history(qs.get("project_id", [""])[0])})
            return
        if len(parts) == 2 and parts[0] == "history" and method == "DELETE":
            if not store.delete_history(parts[1]):
                raise ApiError(404, "history entry not found")
            send({"deleted": parts[1]})
            return
        if parts == ["comparisons"] and method == "POST":
            body = self.read_json(handler)
            send(self._save_comparison(body), 201)
            return
        if parts == ["comparisons"] and method == "GET":
            send({"comparisons": store.list_comparisons(qs.get("project_id", [""])[0])})
            return
        if len(parts) == 2 and parts[0] == "comparisons" and method == "DELETE":
            if not store.delete_comparison(parts[1]):
                raise ApiError(404, "comparison not found")
            send({"deleted": parts[1]})
            return
        if parts == ["search"] and method == "GET":
            send(store.local_search(qs.get("project_id", [""])[0],
                                    qs.get("q", [""])[0]))
            return
        if parts == ["export", "documents"] and method == "GET":
            fmt = qs.get("format", ["bibtex"])[0]
            docs = store.list_documents(qs.get("project_id", [""])[0])
            content, ctype = documents_export(fmt, docs)
            handler._send(content.encode("utf-8"), ctype)
            return
        if parts == ["export", "project"] and method == "GET":
            pid = qs.get("project_id", [""])[0]
            fmt = qs.get("format", ["json"])[0]
            if fmt == "json":
                handler._send(dumps_export(export_project(store, pid)).encode("utf-8"),
                              "application/json; charset=utf-8")
            elif fmt == "markdown":
                project = store.get_project(pid)
                if project is None:
                    raise ApiError(404, "project not found")
                text, _omissions = project_markdown(
                    project, store.list_documents(pid), store.list_citations(pid),
                    store.list_notes(pid), store.list_comparisons(pid),
                    store.list_history(pid))
                handler._send(text.encode("utf-8"), "text/markdown; charset=utf-8")
            else:
                raise ApiError(400, f"unsupported project export format: {fmt}")
            return
        if parts == ["import"] and method == "POST":
            body = self.read_json(handler, cap=MAX_IMPORT_BYTES)
            send(import_project(store, body), 201)
            return
        if parts == ["backup"] and method == "POST":
            self.read_json(handler)
            dest = store.db_path.parent / "backups" / f"workspace-backup-{now_iso().replace(':', '')}.db"
            send(store.backup(dest))
            return
        if parts == ["backup", "download"] and method == "GET":
            dest = store.db_path.parent / "backups" / "workspace-backup-download.db"
            store.backup(dest)
            handler._send(dest.read_bytes(), "application/octet-stream")
            return
        if parts == ["restore"] and method == "POST":
            ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype not in ("application/octet-stream", "application/x-sqlite3",
                             "application/vnd.sqlite3"):
                raise ApiError(415, "restore expects a raw database file body")
            data = self.read_body(handler, cap=RESTORE_CAP)
            send(self._restore(data))
            return
        raise ApiError(404, "workspace route not found")

    # -- citations -------------------------------------------------------------
    def _document_for_page(self, store: WorkspaceStore, project_id: str,
                           snap: dict[str, Any],
                           saved_document_id: str | None) -> str:
        if saved_document_id:
            doc = store.get_document(saved_document_id)
            if doc is None:
                raise ApiError(404, "saved document not found")
            if doc["project_id"] != project_id:
                raise ApiError(400, "document belongs to another project")
            return saved_document_id
        payload = snap["payload"]
        record_id = (payload.get("record_id") or payload.get("document_id")
                     or str(payload.get("_page_id", "")).split("/")[0])
        if not record_id:
            raise ApiError(400, "save the document first, then the citation")
        fields = document_fields({**payload, "record_id": record_id,
                                  "library_id": snap["library_id"]})
        try:
            doc = store.save_document(project_id, snap["library_id"], str(record_id), fields)
            return doc["saved_document_id"]
        except DuplicateError as exc:
            return exc.args[0]

    def _save_citation_from_snapshot(self, body: dict[str, Any]) -> dict[str, Any]:
        store = self.ws.store
        snap = self.ws.get_snapshot(body.get("save_token"))
        if snap is None or snap["kind"] != "page":
            raise ApiError(410, "page token expired or unknown; fetch the page again")
        payload = snap["payload"]
        text = str(payload.get("contents") or payload.get("ocr_text") or "")
        excerpt = body.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ApiError(400, "excerpt is required")
        start = text.find(excerpt)
        if start < 0:
            raise ApiError(422, "excerpt is not present verbatim in the fetched OCR text")
        project_id = str(body.get("project_id") or "")
        doc_id = self._document_for_page(store, project_id, snap,
                                         body.get("saved_document_id"))
        doc = store.get_document(doc_id) or {}
        rights_statement = (payload.get("rights")
                            or (doc.get("rights_snapshot") or {}).get("statement"))
        # A generic page-level placeholder ("item-specific;
        # verify at the item page") must not shadow a specific
        # statement recorded for the document itself - or, when
        # the client passes the document result's own token, in
        # that server-side snapshot. Client-supplied rights text
        # is never accepted; only server snapshots count.
        doc_statement = (doc.get("rights_snapshot") or {}).get("statement")
        if (rights_policy.classify_rights(rights_statement) == "unknown"
                and doc_statement
                and rights_policy.classify_rights(doc_statement) != "unknown"):
            rights_statement = doc_statement
        if rights_policy.classify_rights(rights_statement) == "unknown":
            doc_snap = self.ws.get_snapshot(body.get("document_token"))
            if doc_snap is not None and doc_snap["kind"] == "document":
                snap_rights = (doc_snap["payload"].get("rights") or {})
                snap_statement = (snap_rights.get("statement")
                                  if isinstance(snap_rights, dict) else snap_rights)
                if (snap_statement
                        and rights_policy.classify_rights(snap_statement) != "unknown"):
                    rights_statement = snap_statement
        stored_excerpt, decision = rights_policy.gate_excerpt(excerpt, rights_statement)
        state = payload.get("ocr_state") or {}
        identity = bool(state.get("page_identity_verified")
                        or payload.get("verified_mapping"))
        page_id = str(payload.get("_page_id") or payload.get("page_id") or "")
        key_base = base_citation_key(doc) if doc else "cit"
        fields = {
            "page_id": page_id,
            "citation_key": f"{key_base}-{page_id.rsplit('/', 1)[-1][:16]}",
            "original_excerpt": stored_excerpt,
            "excerpt_omitted_reason": None if stored_excerpt else decision["reason"],
            "excerpt_start": start,
            "excerpt_end": start + len(excerpt),
            "excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "ocr_source": snap["library_id"],
            "ocr_file": payload.get("ocr_file") or payload.get("source"),
            "source_url": payload.get("source_url") or doc.get("landing_url"),
            "image_url": payload.get("image_url"),
            "canvas_id": payload.get("canvas_id"),
            "page_mapping_status": "verified" if identity else "unverified",
            "image_verification_status": "present" if payload.get("image_url") else "absent",
            "quotation_verification_status": (
                "verified_against_fetched_ocr" if identity
                else "fetched_unverified_mapping"),
            "provenance": "system_fetched",
            "rights_at_save": {"statement": rights_statement,
                               "category": decision["category"],
                               "policy": decision["reason"]},
            "retrieved_at": payload.get("retrieved_at") or now_iso(),
            "verified_at": now_iso() if identity else None,
        }
        saved = store.save_citation(doc_id, fields)
        saved["rights_decision"] = decision
        return saved

    def _save_manual_citation(self, body: dict[str, Any]) -> dict[str, Any]:
        store = self.ws.store
        doc_id = str(body.get("saved_document_id") or "")
        doc = store.get_document(doc_id)
        if doc is None:
            raise ApiError(404, "saved document not found")
        excerpt = body.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ApiError(400, "excerpt is required")
        statement = (doc.get("rights_snapshot") or {}).get("statement")
        stored_excerpt, decision = rights_policy.gate_excerpt(excerpt, statement)
        page_id = str(body.get("page_id") or "")
        fields = {
            "page_id": page_id,
            "citation_key": f"{base_citation_key(doc)}-manual",
            "original_excerpt": stored_excerpt,
            "excerpt_omitted_reason": None if stored_excerpt else decision["reason"],
            "excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "page_mapping_status": "unknown",
            "image_verification_status": "not_checked",
            "quotation_verification_status": "user_entered_unverified",
            "provenance": "user_entered",
            "user_annotation": body.get("annotation"),
            "rights_at_save": {"statement": statement, "category": decision["category"]},
            "retrieved_at": now_iso(),
        }
        saved = store.save_citation(doc_id, fields)
        saved["rights_decision"] = decision
        return saved

    # -- reverify ------------------------------------------------------------------
    def _reverify(self, citation_id: str) -> dict[str, Any]:
        store = self.ws.store
        cit = store.get_citation(citation_id)
        if cit is None:
            raise ApiError(404, "citation not found")
        doc = store.get_document(cit["saved_document_id"]) or {}
        detail: dict[str, Any] = {}
        try:
            page = self.runtime.run(self.runtime.service.get_page_text(
                doc.get("library_id", ""), cit["page_id"]))
        except Exception as exc:  # upstream failure is a result, not a 500
            message = str(exc).lower()
            status = ("access_restricted" if ("restrict" in message or "lending" in message)
                      else "source_unavailable")
            return store.add_verification_observation(
                citation_id, status, {"error": str(exc)[:300]})
        text = str(page.get("contents") or page.get("ocr_text") or "")
        state = page.get("ocr_state") or {}
        if cit.get("original_excerpt"):
            present = cit["original_excerpt"] in text
            detail["excerpt_present"] = present
            detail["excerpt_hash_matches"] = (
                hashlib.sha256(cit["original_excerpt"].encode("utf-8")).hexdigest()
                == cit.get("excerpt_hash"))
        else:
            detail["excerpt_present"] = None
            detail["note"] = "no stored excerpt (rights policy); presence not checked"
        current_rights = page.get("rights")
        saved_rights = (cit.get("rights_at_save") or {}).get("statement")
        if current_rights and saved_rights and current_rights != saved_rights:
            detail["rights_changed"] = {"from": saved_rights, "to": current_rights}
            store.add_rights_observation(
                cit["saved_document_id"], current_rights,
                rights_policy.classify_rights(current_rights),
                "reverify", "rights_changed")
        if not (state.get("page_identity_verified") or page.get("verified_mapping")):
            status = "mapping_unverified"
        elif detail.get("excerpt_present") is False:
            status = "quotation_not_found"
        elif detail.get("rights_changed"):
            status = "rights_changed"
        else:
            try:
                fresh = self.runtime.run(self.runtime.service.get_document(
                    doc.get("library_id", ""), doc.get("record_id", "")))
                fresh_title = (fresh or {}).get("title")
                if fresh_title and doc.get("title") and fresh_title != doc["title"]:
                    detail["metadata_changed"] = {"title_from": doc["title"],
                                                  "title_to": fresh_title}
                    status = "metadata_changed"
                else:
                    status = "unchanged"
            except Exception:
                status = "unchanged"
                detail["metadata_check"] = "unavailable"
        return store.add_verification_observation(citation_id, status, detail)

    # -- comparisons ------------------------------------------------------------------
    def _save_comparison(self, body: dict[str, Any]) -> dict[str, Any]:
        store = self.ws.store
        project_id = str(body.get("project_id") or "")
        doc_ids = [str(d) for d in body.get("saved_document_ids") or []]
        if not 2 <= len(doc_ids) <= 4:
            raise ApiError(400, "comparisons take 2-4 saved documents")
        docs = []
        for doc_id in doc_ids:
            doc = store.get_document(doc_id)
            if doc is None or doc["project_id"] != project_id:
                raise ApiError(400, "comparison documents must belong to the project")
            docs.append(doc)
        result = self.runtime.run(self.runtime.service.compare_documents(
            [{"library_id": d["library_id"], "record_id": d["record_id"]} for d in docs]))
        overlap = result.get("concept_overlap") or {}
        excerpts: dict[str, Any] = {}
        for doc, comp_doc in zip(docs, result.get("documents") or []):
            statement = (doc.get("rights_snapshot") or {}).get("statement")
            decision = rights_policy.evaluate(statement)
            samples = comp_doc.get("sample_excerpts") or comp_doc.get("excerpts") or []
            texts = [s.get("text", "") if isinstance(s, dict) else str(s) for s in samples]
            if decision["excerpt_storage"]:
                excerpts[doc["saved_document_id"]] = texts[:3]
            else:
                excerpts[doc["saved_document_id"]] = {
                    "omitted": decision["reason"], "count": len(texts)}
        return store.save_comparison(project_id, {
            "title": str(body.get("title") or ""),
            "saved_document_ids": doc_ids,
            "comparison_aspects": {"aspects": result.get("aspects") or [],
                                   "question": result.get("question")},
            "original_excerpts": excerpts,
            "lexical_overlap": overlap.get("lexical") or {},
            "dictionary_concept_overlap": overlap.get("dictionary_concept_overlap") or {},
            "shared_by_all": overlap.get("shared_by_all_documents") or [],
            "shared_by_some": overlap.get("shared_by_some_documents") or [],
            "semantic_status": "not_checked",
            "insufficient_evidence": result.get("insufficient_evidence") or [],
        })

    # -- restore ------------------------------------------------------------------------
    def _restore(self, data: bytes) -> dict[str, Any]:
        store = self.ws.store
        db_path = store.db_path
        tmp = db_path.parent / f"restore-candidate-{now_iso().replace(':', '')}.db"
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        try:
            info = WorkspaceStore.inspect_backup(tmp)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise ApiError(400, f"not a readable SQLite database: {exc}")
        if info["integrity"] != "ok":
            tmp.unlink(missing_ok=True)
            raise ApiError(400, "backup integrity check failed; current database untouched")
        if info["schema_version"] > SCHEMA_VERSION:
            tmp.unlink(missing_ok=True)
            raise ApiError(400, "backup schema is newer than this build; refused")
        pre = store.backup(db_path.parent / "backups" /
                           f"pre-restore-{now_iso().replace(':', '')}.db")
        store.close()
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        os.replace(tmp, db_path)
        self.ws.store = WorkspaceStore(db_path)
        return {"restored": True, "schema_version": self.ws.store.schema_version,
                "pre_restore_backup": pre["path"],
                "note": "the previous database was backed up before replacement"}


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")
