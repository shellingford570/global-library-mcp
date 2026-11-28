"""Workspace HTTP layer (b7; final review sections 2, 3, 7,
10, 11, 12, 13, 14, 20).

Security model for the local workspace API:
- workspace mode refuses non-loopback binds at startup, and
  every workspace request additionally requires a loopback
  client address and a strictly parsed Host header naming a
  loopback host on the server's own port (DNS-rebinding
  defence);
- authentication is a per-session cookie issued when the
  server's own page is served: each page load creates a
  session (HttpOnly, SameSite=Strict, 12 h expiry) and the
  page's meta tag carries THAT session's CSRF token. Reads
  require a valid session; mutations additionally require
  the session's CSRF token and an Origin matching the Host.
  This is a local single-user application model: it defends
  against other websites and network attackers, and the
  threat model (including what the same OS user can do) is
  documented in docs/workspace-security.md. It is NOT
  public-web authentication;
- request bodies are size-capped and must be JSON
  (application/json) except the backup-restore upload;
- provenance: clients cannot assert verification. Save
  operations reference short-lived server-side snapshots of
  payloads THIS server returned; the server rebuilds the
  stored record from its own snapshot, binds the citation
  to the snapshot's document identity (library, record,
  page) and re-checks the excerpt verbatim. A genuine token
  minted for one document cannot be spent on another.
- snapshots are deep copies with per-item and total byte
  caps, so later mutation of a response object cannot alter
  what a token will save, and memory stays bounded.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..workspace import policy as rights_policy
from ..workspace.exports import documents_export, project_markdown
from ..workspace.store import (SCHEMA_VERSION, DuplicateError,
                               WorkspaceStore, now_iso)
from ..workspace.transfer import (MAX_IMPORT_BYTES, ImportError_,
                                  dumps_export, export_project,
                                  import_project, parse_import_json)

SNAPSHOT_TTL_S = 7200
SNAPSHOT_CAP = 512
SNAPSHOT_MAX_BYTES = 4 * 1024 * 1024
SNAPSHOT_TOTAL_MAX_BYTES = 64 * 1024 * 1024
SESSION_TTL_S = 12 * 3600
BODY_CAP = 1_048_576
RESTORE_CAP = 209_715_200
BACKUP_CAP = 10
HISTORY_FIELD_CAP = 16_384
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}
SESSION_COOKIE = "glm_ws_session"

_PAGE_SNAPSHOT_KEYS = (
    "page_id", "_page_id", "record_id", "book_pid", "library_id",
    "contents", "ocr_text", "rights", "ocr_state", "verified_mapping",
    "page_identity_verified", "image_url", "canvas_id", "ocr_file",
    "ocr_source", "source", "source_url", "retrieved_at", "title",
    "landing_url", "digital_frame", "printed_page",
)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class WorkspaceWebRuntime:
    def __init__(self, store: WorkspaceStore):
        self.store = store
        self._snapshots: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._snap_lock = threading.Lock()
        self._snap_bytes = 0
        self._sessions: dict[str, dict[str, Any]] = {}
        self._session_lock = threading.Lock()
        self.restoring = False
        self._ops_cond = threading.Condition()
        self._ops_inflight = 0
        self._backups: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._backup_lock = threading.Lock()
        self._scan_backups()

    # -- operation quiescence (b8 section 2) --------------------------------
    def op_begin(self) -> None:
        """Register an in-flight workspace operation. New
        operations are refused while a restore is quiescing or
        swapping the database."""
        with self._ops_cond:
            if self.restoring:
                raise ApiError(503, "a restore is in progress; retry shortly")
            self._ops_inflight += 1

    def op_end(self) -> None:
        with self._ops_cond:
            self._ops_inflight -= 1
            self._ops_cond.notify_all()

    def quiesce(self, timeout: float = 30.0) -> bool:
        """Stop new operations and wait for in-flight ones to
        finish. Ownership is ATOMIC (b8 final review section
        12): if another restore already owns the quiesced
        state, this call returns False immediately instead of
        racing it, and the caller must NOT call unquiesce for
        a quiesce it did not acquire. Returns False also on
        timeout (the caller aborts and clears its own flag)."""
        with self._ops_cond:
            if self.restoring:
                return False
            self.restoring = True
            return self._ops_cond.wait_for(
                lambda: self._ops_inflight == 0, timeout=timeout)

    def acquire_restore(self, timeout: float = 30.0) -> bool:
        """Atomic restore ownership (b8 final review section
        12): returns True only when THIS caller set the
        quiesced flag AND in-flight operations drained. A
        concurrent restore sees the flag already set and is
        refused without touching it; on timeout the caller's
        own flag is released again. Only a caller that got
        True may call unquiesce."""
        with self._ops_cond:
            if self.restoring:
                return False
            self.restoring = True
            ok = self._ops_cond.wait_for(
                lambda: self._ops_inflight == 0, timeout=timeout)
            if not ok:
                self.restoring = False
                self._ops_cond.notify_all()
            return ok

    def unquiesce(self) -> None:
        with self._ops_cond:
            self.restoring = False
            self._ops_cond.notify_all()

    # -- sessions ------------------------------------------------------------
    def issue_session(self) -> tuple[str, str]:
        sid = secrets.token_urlsafe(24)
        token = secrets.token_urlsafe(32)
        with self._session_lock:
            now = time.time()
            self._sessions = {k: v for k, v in self._sessions.items()
                              if now - v["created"] <= SESSION_TTL_S}
            self._sessions[sid] = {"token": token, "created": now}
        return sid, token

    def session_token(self, sid: str | None) -> str | None:
        if not sid:
            return None
        with self._session_lock:
            session = self._sessions.get(sid)
            if session is None:
                return None
            if time.time() - session["created"] > SESSION_TTL_S:
                del self._sessions[sid]
                return None
            return session["token"]

    # -- snapshots ---------------------------------------------------------
    def register_snapshot(self, kind: str, library_id: str,
                          payload: dict[str, Any]) -> str:
        frozen = json.loads(json.dumps(payload, ensure_ascii=False))
        size = len(json.dumps(frozen, ensure_ascii=False).encode("utf-8"))
        if size > SNAPSHOT_MAX_BYTES:
            raise ValueError("response too large to offer for saving")
        token = secrets.token_urlsafe(18)
        with self._snap_lock:
            now = time.time()
            expired = [t for t, s in self._snapshots.items()
                       if now - s["ts"] > SNAPSHOT_TTL_S]
            for old in expired:
                self._snap_bytes -= self._snapshots.pop(old)["size"]
            while self._snapshots and (len(self._snapshots) >= SNAPSHOT_CAP
                                       or self._snap_bytes + size > SNAPSHOT_TOTAL_MAX_BYTES):
                _, evicted = self._snapshots.popitem(last=False)
                self._snap_bytes -= evicted["size"]
            self._snapshots[token] = {"kind": kind, "library_id": library_id,
                                      "payload": frozen, "ts": now, "size": size}
            self._snap_bytes += size
        return token

    def get_snapshot(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._snap_lock:
            snap = self._snapshots.get(token)
            if snap is None:
                return None
            if time.time() - snap["ts"] > SNAPSHOT_TTL_S:
                self._snap_bytes -= snap["size"]
                del self._snapshots[token]
                return None
            return snap

    def annotate_search_results(self, results: list[dict[str, Any]]) -> None:
        for item in results:
            if isinstance(item, dict) and item.get("library_id") and (
                    item.get("record_id") or item.get("id")):
                try:
                    item["save_token"] = self.register_snapshot(
                        "document", item["library_id"], item)
                except ValueError:
                    pass

    def annotate_page(self, library_id: str, page_id: str,
                      payload: dict[str, Any]) -> None:
        trimmed = {k: payload[k] for k in _PAGE_SNAPSHOT_KEYS if k in payload}
        trimmed["_page_id"] = page_id
        try:
            payload["save_token"] = self.register_snapshot("page", library_id, trimmed)
        except ValueError:
            pass

    def annotate_search_response(self, entry: dict[str, Any]) -> str:
        return self.register_snapshot("search", "", entry)

    # -- backups ---------------------------------------------------------------
    def _backup_dir(self) -> Path:
        return self.store.db_path.parent / "backups"

    def _scan_backups(self) -> None:
        directory = self._backup_dir()
        if not directory.exists():
            return
        files = sorted(directory.glob("ws-backup-*.db"),
                       key=lambda p: p.stat().st_mtime)
        for path in files:
            backup_id = path.name[len("ws-backup-"):-len(".db")]
            self._backups[backup_id] = {
                "id": backup_id, "path": str(path),
                "bytes": path.stat().st_size,
                "created_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime))}

    def create_backup(self) -> dict[str, Any]:
        backup_id = secrets.token_urlsafe(9)
        dest = self._backup_dir() / f"ws-backup-{backup_id}.db"
        info = self.store.backup(dest)
        with self._backup_lock:
            self._backups[backup_id] = {"id": backup_id, "path": str(dest),
                                        "bytes": info["bytes"],
                                        "created_at": info["created_at"]}
            while len(self._backups) > BACKUP_CAP:
                _, oldest = self._backups.popitem(last=False)
                Path(oldest["path"]).unlink(missing_ok=True)
        return {"id": backup_id, "bytes": info["bytes"],
                "sha256": info["sha256"], "schema_version": info["schema_version"],
                "created_at": info["created_at"]}

    def list_backups(self) -> list[dict[str, Any]]:
        with self._backup_lock:
            return [{"id": b["id"], "bytes": b["bytes"], "created_at": b["created_at"]}
                    for b in reversed(self._backups.values())]

    def backup_path(self, backup_id: str) -> Path | None:
        with self._backup_lock:
            entry = self._backups.get(backup_id)
        if entry is None:
            return None
        path = Path(entry["path"])
        return path if path.exists() else None

    def delete_backup(self, backup_id: str) -> bool:
        with self._backup_lock:
            entry = self._backups.pop(backup_id, None)
        if entry is None:
            return False
        Path(entry["path"]).unlink(missing_ok=True)
        return True


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


def build_history_entry(query: str, params: dict[str, Any],
                        result: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """A search-history record built from the SERVER's own
    response (final review section 20): variants, scope and
    statistics are what the server actually executed, never
    client assertions."""
    discovery = result.get("discovery") or {}
    scope = result.get("search_scope") or {}
    materials = result.get("materials") or result.get("results") or []
    return {
        "original_query": query,
        "search_parameters": {**params, "kind": kind},
        "planned_variants": discovery.get("planned_variants") or [],
        "executed_variants": discovery.get("executed_variants") or [],
        "searched_libraries": scope.get("searched") or result.get("searched_libraries") or {},
        "skipped_libraries": scope.get("skipped") or result.get("routing_skipped") or {},
        "result_summary": {"count": len(materials),
                           "answerable": result.get("answerable")},
        "http_stats": result.get("http_stats") or {},
        "search_status": result.get("status") or "completed",
    }


def _parse_host(host_header: str) -> tuple[str, int | None] | None:
    """Strict Host parsing: returns (name, port) or None.
    Rejects whitespace, controls, userinfo tricks, bare IPv6
    and non-numeric ports."""
    host = host_header.strip()
    if not host or any(ch.isspace() or ord(ch) < 32 for ch in host):
        return None
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return None
        name, rest = host[1:end], host[end + 1:]
        if rest == "":
            return name.lower(), None
        if rest.startswith(":") and rest[1:].isdigit():
            return name.lower(), int(rest[1:])
        return None
    if host.count(":") > 1:
        return None
    if ":" in host:
        name, _, port = host.partition(":")
        if not port.isdigit():
            return None
        return name.lower(), int(port)
    return host.lower(), None


def _origin_matches(origin: str, host_header: str) -> bool:
    if origin == "null":
        return False
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    return parsed.netloc.lower() == host_header.lower()


def _session_cookie(handler: Any) -> str | None:
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE:
            return value
    return None


class WorkspaceApi:
    """Dispatches /api/workspace/* for one handler instance."""

    def __init__(self, runtime: WorkspaceWebRuntime, service_runtime: Any):
        self.ws = runtime
        self.runtime = service_runtime

    # -- plumbing ------------------------------------------------------------
    def guard(self, handler: Any, *, mutation: bool) -> None:
        if self.ws.restoring:
            raise ApiError(503, "a restore is in progress; retry shortly")
        if handler.client_address[0] not in LOOPBACK_CLIENTS:
            raise ApiError(403, "workspace API is loopback-only")
        hosts = handler.headers.get_all("Host") or []
        if len(hosts) != 1:
            raise ApiError(403, "invalid Host header")
        parsed = _parse_host(hosts[0])
        if parsed is None:
            raise ApiError(403, "invalid Host header")
        name, port = parsed
        if name not in LOOPBACK_HOSTS:
            raise ApiError(403, "invalid Host header")
        server_port = handler.server.server_address[1]
        if port is not None and port != server_port:
            raise ApiError(403, "Host port does not match the server port")
        origin = handler.headers.get("Origin")
        if origin is not None and not _origin_matches(origin, hosts[0]):
            raise ApiError(403, "Origin does not match Host")
        token = self.ws.session_token(_session_cookie(handler))
        if token is None:
            raise ApiError(403, "workspace session required; reload the page")
        if mutation and handler.headers.get("X-GLM-CSRF") != token:
            raise ApiError(403, "missing or invalid CSRF token")

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
        # The restore route quiesces the API itself; every other
        # route registers as an in-flight operation so a restore
        # can wait for it (b8 section 2).
        is_restore = method == "POST" and parsed.path == "/api/workspace/restore"
        try:
            if not is_restore:
                self.ws.op_begin()
            try:
                self._dispatch(handler, method, parsed.path, parse_qs(parsed.query))
            finally:
                if not is_restore:
                    self.ws.op_end()
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
                    handler._send(_json({
                        "error": "deletion requires confirmation",
                        "related_counts": project["counts"],
                        "note": "these records will be deleted with the project; "
                                "backups and exported files are not affected"}),
                        status=409)
                    return
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
            docs = store.list_documents(
                pid, tag=qs.get("tag", [None])[0],
                collection_id=qs.get("collection_id", [None])[0])
            send({"documents": [self._document_view(store, d) for d in docs]})
            return
        if len(parts) == 2 and parts[0] == "documents" and method == "DELETE":
            doc = store.get_document(parts[1])
            if doc is None:
                raise ApiError(404, "document not found")
            counts = store.document_related_counts(parts[1])
            destructive = counts["citations_deleted"] + counts["notes_unlinked"]
            if destructive and qs.get("confirm", [""])[0] != "1":
                handler._send(_json({
                    "error": "deletion affects related records; confirmation required",
                    "related_counts": counts,
                    "note": "citations are deleted with the document; research "
                            "notes survive with their link cleared"}), status=409)
                return
            store.delete_document(parts[1])
            send({"deleted": parts[1], "related_counts": counts})
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
            send({"citations": [self._citation_view(store, c)
                                for c in store.list_citations(qs.get("project_id", [""])[0])]})
            return
        if len(parts) == 3 and parts[0] == "citations" and parts[2] == "reverify" and method == "POST":
            self.read_json(handler)
            send(self._reverify(parts[1]))
            return
        if len(parts) == 2 and parts[0] == "citations" and method == "DELETE":
            cit = store.get_citation(parts[1])
            if cit is None:
                raise ApiError(404, "citation not found")
            counts = store.citation_related_counts(parts[1])
            if counts["notes_unlinked"] and qs.get("confirm", [""])[0] != "1":
                handler._send(_json({
                    "error": "deletion affects related records; confirmation required",
                    "related_counts": counts,
                    "note": "research notes survive with their link cleared"}), status=409)
                return
            store.delete_citation(parts[1])
            send({"deleted": parts[1], "related_counts": counts})
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
                                 saved_document_id=body.get("saved_document_id"),
                                 citation_id=body.get("citation_id"),
                                 note_id=parts[1]))
            return
        if len(parts) == 2 and parts[0] == "notes" and method == "DELETE":
            if not store.delete_note(parts[1]):
                raise ApiError(404, "note not found")
            send({"deleted": parts[1]})
            return
        if parts == ["history"] and method == "POST":
            body = self.read_json(handler)
            send(self._save_history(body), 201)
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
            send({"comparisons": [self._comparison_view(store, c)
                                  for c in store.list_comparisons(qs.get("project_id", [""])[0])]})
            return
        if len(parts) == 2 and parts[0] == "comparisons" and method == "DELETE":
            if not store.delete_comparison(parts[1]):
                raise ApiError(404, "comparison not found")
            send({"deleted": parts[1]})
            return
        if parts == ["search"] and method == "GET":
            result = store.local_search(qs.get("project_id", [""])[0],
                                        qs.get("q", [""])[0])
            # Trust boundary for search itself (b8 final review
            # section 9): a citation whose excerpt is currently
            # withheld must not leak through the search index -
            # neither its text, nor the mere existence of a hit
            # that only the withheld text could produce. Such a
            # citation stays findable only via its non-excerpt
            # fields (page id).
            from ..workspace.store import search_text as _norm
            needle = _norm(qs.get("q", [""])[0]).strip()
            kept = []
            for cit in result["citations"]:
                view = self._citation_view(store, cit)
                if view.get("excerpt_stored"):
                    kept.append(view)
                elif needle and needle in _norm(cit.get("page_id")):
                    kept.append(view)
            result["citations"] = kept
            send(result)
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
                bundle = store.export_bundle(pid)
                latest = {}
                document_decisions = {}
                for doc in bundle["documents"]:
                    obs = bundle["rights_observations"].get(doc["saved_document_id"]) or []
                    latest[doc["saved_document_id"]] = obs[-1]["statement"] if obs else None
                    document_decisions[doc["saved_document_id"]] = (
                        rights_policy.trusted_decision(
                            (doc.get("rights_snapshot") or {}).get("statement"),
                            doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED,
                            obs))
                citation_decisions = {}
                for cit in bundle["citations"]:
                    obs = bundle["rights_observations"].get(cit["saved_document_id"]) or []
                    citation_decisions[cit["citation_id"]] = (
                        rights_policy.trusted_decision(
                            (cit.get("rights_at_save") or {}).get("statement"),
                            self._citation_trust(store, cit), obs))
                text, _omissions = project_markdown(
                    project, bundle["documents"], bundle["citations"],
                    bundle["notes"], bundle["comparisons"], bundle["history"],
                    latest_rights=latest,
                    citation_decisions=citation_decisions,
                    document_decisions=document_decisions)
                handler._send(text.encode("utf-8"), "text/markdown; charset=utf-8")
            else:
                raise ApiError(400, f"unsupported project export format: {fmt}")
            return
        if parts == ["import"] and method == "POST":
            ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype != "application/json":
                raise ApiError(415, "Content-Type must be application/json")
            raw = self.read_body(handler, cap=MAX_IMPORT_BYTES)
            send(import_project(store, parse_import_json(raw)), 201)
            return
        if parts == ["backup"] and method == "POST":
            self.read_json(handler)
            send(self.ws.create_backup(), 201)
            return
        if parts == ["backup"] and method == "GET":
            send({"backups": self.ws.list_backups()})
            return
        if parts == ["backup", "download"] and method == "GET":
            path = self.ws.backup_path(qs.get("id", [""])[0])
            if path is None:
                raise ApiError(404, "unknown backup id; create a backup first")
            handler._send(path.read_bytes(), "application/octet-stream")
            return
        if len(parts) == 2 and parts[0] == "backup" and method == "DELETE":
            if not self.ws.delete_backup(parts[1]):
                raise ApiError(404, "backup not found")
            send({"deleted": parts[1]})
            return
        if parts == ["restore"] and method == "POST":
            ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype not in ("application/octet-stream", "application/x-sqlite3",
                             "application/vnd.sqlite3"):
                raise ApiError(415, "restore expects a raw database file body")
            if qs.get("confirm", [""])[0] != "1":
                raise ApiError(409, "restore requires explicit confirmation")
            data = self.read_body(handler, cap=RESTORE_CAP)
            send(self._restore(data))
            return
        # -- b11 research validation routes (sections 49-54) ---------------
        if len(parts) >= 3 and parts[0] == "projects" and parts[2] == "research":
            pid = parts[1]
            if store.get_project(pid) is None:
                raise ApiError(404, "project not found")
            from global_library_mcp.evidence_graph import (
                build_project_graph)
            from global_library_mcp.research import (
                structure_claim, structure_question)
            from global_library_mcp.synthesis import (
                build_timeline, generate_research_report)
            from global_library_mcp.workspace.research_artefacts import (
                list_artefacts, project_research_progress, save_artefact)
            sub = parts[3] if len(parts) > 3 else ""
            if sub == "progress" and method == "GET":
                send(project_research_progress(store, pid))
                return
            if sub == "artefacts" and method == "GET":
                send({"artefacts": list_artefacts(store, pid)})
                return
            if sub == "graph" and method == "GET":
                try:
                    limit = min(2000, max(1, int(qs.get("limit", ["500"])[0])))
                    offset = max(0, int(qs.get("offset", ["0"])[0]))
                except ValueError:
                    raise ApiError(400, "limit/offset must be integers")
                send(build_project_graph(store, pid, limit=limit,
                                         offset=offset))
                return
            if sub == "timeline" and method == "GET":
                events = []
                for art in list_artefacts(store, pid):
                    if art["kind"] in ("b10_timeline", "timeline"):
                        events += (art.get("payload") or {}).get("events") or []
                send(build_timeline(events))
                return
            if sub == "questions" and method == "POST":
                body = self.read_json(handler)
                question = str(body.get("question") or "").strip()
                if not question:
                    raise ApiError(400, "question is required")
                structured = structure_question(question).to_dict()
                art = save_artefact(store, pid, "research_question",
                                    question[:80],
                                    {"question": structured})
                send({"artefact": art, "structured": structured}, 201)
                return
            if sub == "claims" and method == "POST":
                body = self.read_json(handler)
                statement = str(body.get("statement") or "").strip()
                if not statement:
                    raise ApiError(400, "statement is required")
                claim = structure_claim(statement).to_dict()
                art = save_artefact(store, pid, "claim_assessment",
                                    statement[:80],
                                    {"claim": claim, "assessments": []})
                send({"artefact": art, "claim": claim}, 201)
                return
            if sub == "reports" and method == "POST":
                import subprocess as _sp
                try:
                    commit = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                                     capture_output=True, text=True,
                                     timeout=5).stdout.strip()
                except Exception:
                    commit = ""
                report = generate_research_report(store, pid,
                                                  git_commit=commit)
                sections = [{"name": k} for k in (
                    "summary", "questions", "claim_states", "comparisons",
                    "timeline", "rights", "unresolved_references")]
                save_artefact(store, pid, "research_report",
                              f"Report {report['report_id']}",
                              {"report_id": report["report_id"],
                               "title": f"Research report {report['report_id']}",
                               "sections": sections,
                               "record_refs": report["record_refs"],
                               "citation_refs": report["citation_refs"],
                               "snapshot_id": report["snapshot_id"],
                               "settings": {
                                   "code_version": report["code_version"],
                                   "git_commit": report["git_commit"]},
                               "generated_at": report["generated_at"]})
                send(report, 201)
                return
            if sub == "reports" and method == "GET":
                reps = [a for a in list_artefacts(store, pid)
                        if a["kind"] in ("b10_research_report",
                                         "research_report")]
                send({"reports": reps})
                return
            if sub == "revalidate" and method == "POST":
                graph = build_project_graph(store, pid, limit=1)
                send({"revalidated": True,
                      "graph_nodes": graph["node_count"],
                      "graph_edges": graph["edge_count"],
                      "progress": project_research_progress(store, pid)})
                return
            raise ApiError(404, "research route not found")
        raise ApiError(404, "workspace route not found")

    # -- views with current-rights gating ---------------------------------------
    def _citation_trust(self, store: WorkspaceStore, cit: dict[str, Any]) -> str:
        """Trust state governing a citation's rights (b8
        section 2): server-fetched citations carry this server's
        own observation; imported ones are claims; user-entered
        ones inherit their document's trust."""
        # A citation whose verification state was downgraded
        # by a restore is a restored claim FIRST (b8 final
        # review section 8): its pre-restore provenance does
        # not re-establish trust. Only a fresh re-verification
        # (which replaces the status) restores server trust.
        if cit.get("quotation_verification_status") == "restored_unverified" \
                or cit.get("page_mapping_status") == "restored_unverified":
            return rights_policy.TRUST_RESTORED_CLAIM
        if cit.get("provenance") == "system_fetched":
            return rights_policy.TRUST_SERVER_OBSERVED
        if cit.get("provenance") == "imported":
            return rights_policy.TRUST_IMPORTED_CLAIM
        doc = store.get_document(cit["saved_document_id"]) or {}
        return doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED

    def _document_view(self, store: WorkspaceStore, doc: dict[str, Any]) -> dict[str, Any]:
        observations = store.list_rights_observations(doc["saved_document_id"])
        if observations:
            doc = dict(doc)
            latest = observations[-1]
            decision = rights_policy.trusted_decision(
                (doc.get("rights_snapshot") or {}).get("statement"),
                doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED,
                observations)
            doc["rights_current"] = {
                "latest_statement": latest.get("statement"),
                "latest_category": latest.get("category"),
                "observed_at": latest.get("observed_at"),
                "trust": doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED,
                "excerpt_storage_now": decision["excerpt_storage"],
                "reason": decision["reason"]}
        return doc

    def _citation_view(self, store: WorkspaceStore, cit: dict[str, Any]) -> dict[str, Any]:
        """Display view: the excerpt text is included only if
        the CURRENT trusted rights still permit it (final review
        section 6, b8 section 2). The stored row is never
        mutated."""
        cit = dict(cit)
        cit["excerpt_stored"] = cit.get("original_excerpt") is not None
        if cit["excerpt_stored"]:
            observations = store.list_rights_observations(cit["saved_document_id"])
            decision = rights_policy.trusted_decision(
                (cit.get("rights_at_save") or {}).get("statement"),
                self._citation_trust(store, cit), observations)
            if not decision["excerpt_export"]:
                cit["original_excerpt"] = None
                cit["excerpt_stored"] = False
                cit["excerpt_omitted_reason"] = decision["reason"]
        return cit

    def _comparison_view(self, store: WorkspaceStore, comp: dict[str, Any]) -> dict[str, Any]:
        comp = dict(comp)
        excerpts = {}
        for doc_id, value in (comp.get("original_excerpts") or {}).items():
            if isinstance(value, list):
                doc = store.get_document(doc_id)
                observations = store.list_rights_observations(doc_id) if doc else []
                decision = rights_policy.trusted_decision(
                    (doc.get("rights_snapshot") or {}).get("statement") if doc else None,
                    (doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED) if doc
                    else rights_policy.TRUST_IMPORTED_CLAIM,
                    observations)
                if decision["excerpt_export"]:
                    excerpts[doc_id] = value
                else:
                    excerpts[doc_id] = {"omitted": decision["reason"],
                                        "count": len(value)}
            else:
                excerpts[doc_id] = value
        comp["original_excerpts"] = excerpts
        return comp

    # -- history -------------------------------------------------------------------
    def _save_history(self, body: dict[str, Any]) -> dict[str, Any]:
        store = self.ws.store
        project_id = str(body.get("project_id") or "")
        token = body.get("history_token")
        if token:
            snap = self.ws.get_snapshot(token)
            if snap is None or snap["kind"] != "search":
                raise ApiError(410, "history token expired or unknown; re-run the search")
            entry = copy.deepcopy(snap["payload"])
            entry["provenance"] = "server_recorded"
            return store.save_history(project_id, entry)
        # Manual entries are the user's own record, marked as
        # such, size-capped, and never treated as server proof.
        entry: dict[str, Any] = {"provenance": "user_entered"}
        query = body.get("original_query")
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ApiError(400, "original_query is required (max 2000 chars)")
        entry["original_query"] = query
        secret_keys = {"api_key", "apikey", "token", "password", "secret",
                       "session", "authorization", "cookie"}

        def no_secrets(node: Any) -> bool:
            if isinstance(node, dict):
                return all(k.lower() not in secret_keys and no_secrets(v)
                           for k, v in node.items())
            if isinstance(node, list):
                return all(no_secrets(v) for v in node)
            return True

        for key in ("search_parameters", "planned_variants", "executed_variants",
                    "searched_libraries", "skipped_libraries", "result_summary",
                    "http_stats"):
            value = body.get(key)
            if value is None:
                continue
            if len(json.dumps(value, ensure_ascii=False)) > HISTORY_FIELD_CAP:
                raise ApiError(413, f"{key} is too large for a history record")
            if not no_secrets(value):
                raise ApiError(400, f"{key} contains a secret-like field")
            entry[key] = value
        status = str(body.get("search_status") or "user_recorded")
        if status not in ("completed", "partial", "failed", "cancelled", "user_recorded"):
            raise ApiError(400, f"unknown search_status: {status}")
        entry["search_status"] = status
        return store.save_history(project_id, entry)

    # -- citations -------------------------------------------------------------
    def _page_identity(self, snap: dict[str, Any]) -> tuple[str, str, str]:
        """(library_id, record_id, page_id) of a page snapshot,
        from the payload's own identifier fields - never by
        splitting the page id string (final review section 2).
        Every adapter's page payload carries record_id (NDL:
        book_pid). A snapshot that cannot name its document
        cannot back a verified citation."""
        payload = snap["payload"]
        library_id = snap["library_id"]
        if payload.get("library_id") and payload["library_id"] != library_id:
            raise ApiError(422, "page snapshot library does not match its payload")
        record_id = payload.get("record_id") or payload.get("book_pid")
        if not record_id:
            raise ApiError(422, "the fetched page does not identify its document; "
                                "save the document from the search result first")
        page_id = payload.get("_page_id") or payload.get("page_id")
        if payload.get("_page_id") and payload.get("page_id") \
                and payload["_page_id"] != payload["page_id"]:
            raise ApiError(422, "page snapshot page id does not match its payload")
        if not page_id:
            raise ApiError(422, "page snapshot has no page id")
        return library_id, str(record_id), str(page_id)

    def _document_for_page(self, store: WorkspaceStore, project_id: str,
                           library_id: str, record_id: str,
                           snap: dict[str, Any],
                           saved_document_id: str | None) -> str:
        if saved_document_id:
            doc = store.get_document(saved_document_id)
            if doc is None:
                raise ApiError(404, "saved document not found")
            if doc["project_id"] != project_id:
                raise ApiError(400, "document belongs to another project")
            if doc["library_id"] != library_id or doc["record_id"] != record_id:
                raise ApiError(400, "the page snapshot belongs to a different "
                                    "document than the save target")
            return saved_document_id
        existing = store.find_document(project_id, library_id, record_id)
        if existing is not None:
            return existing["saved_document_id"]
        fields = document_fields({**snap["payload"], "record_id": record_id,
                                  "library_id": library_id})
        try:
            doc = store.save_document(project_id, library_id, record_id, fields)
            return doc["saved_document_id"]
        except DuplicateError as exc:
            return exc.args[0]

    def _gate_new_excerpt(self, store: WorkspaceStore, doc: dict[str, Any],
                          statement: Any, excerpt: str, body: dict[str, Any],
                          *, basis: str) -> tuple[str | None, dict[str, Any]]:
        """Gate a NEW excerpt save (b8 section 2): the latest
        rights observation always applies (an older permissive
        token cannot bypass a newer restriction), stored
        statements count only under the trust model, and
        NonCommercial categories require an explicit per-save
        purpose confirmation (409 so the UI can ask and retry).
        ``basis`` is "live" when the statement was observed by
        this server in this request, "stored" when it comes from
        saved data."""
        observations = store.list_rights_observations(doc["saved_document_id"])
        if basis == "live":
            # The statement carried by this request's snapshot
            # is the SAVE basis (server-observed when the
            # snapshot was fetched); every observation already
            # on record applies AFTER it in order, so a newer
            # restrictive observation - trusted or claim - can
            # never be bypassed by an older permissive token
            # (b8 sections 2/13, final review section 13).
            decision = rights_policy.trusted_decision(
                statement, rights_policy.TRUST_SERVER_OBSERVED,
                observations)
        else:
            decision = rights_policy.trusted_decision(
                statement,
                doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED,
                observations)
        if not decision["excerpt_storage"]:
            return None, decision
        if decision.get("excerpt_requires_confirmation") \
                and body.get("nc_purpose_confirmed") is not True:
            raise ApiError(
                409, "nc_confirmation_required: excerpt storage under a "
                     "NonCommercial licence requires confirming a "
                     "non-commercial research purpose for this save")
        if len(excerpt) > rights_policy.MAX_EXCERPT_CHARS:
            return None, {**decision,
                          "reason": (f"excerpt exceeds the {rights_policy.MAX_EXCERPT_CHARS}-character "
                                     "storage limit; withheld rather than truncated")}
        return excerpt, decision

    def _citation_rights_statement(self, body: dict[str, Any], payload: dict[str, Any],
                                   doc: dict[str, Any], library_id: str,
                                   record_id: str) -> tuple[Any, str]:
        """Rights for a citation, from server-side sources only,
        as (statement, basis). A document-token fallback is
        honoured ONLY when that snapshot names the very same
        document (final review section 3): another document's -
        or another edition's - rights never leak into this
        citation. The saved-document fallback is honoured only
        when the document's rights are server-observed (b8
        section 2): an imported claim is never a fallback basis."""
        rights = payload.get("rights")
        statement = rights.get("statement") if isinstance(rights, dict) else rights
        if rights_policy.classify_rights(statement) != "unknown":
            return statement, "live"
        doc_trust = doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED
        doc_statement = (doc.get("rights_snapshot") or {}).get("statement")
        if doc_trust == rights_policy.TRUST_SERVER_OBSERVED and doc_statement \
                and rights_policy.classify_rights(doc_statement) != "unknown":
            return doc_statement, "stored"
        doc_snap = self.ws.get_snapshot(body.get("document_token"))
        if doc_snap is not None and doc_snap["kind"] == "document" \
                and doc_snap["library_id"] == library_id:
            snap_item = doc_snap["payload"]
            snap_record = snap_item.get("record_id") or snap_item.get("id")
            if snap_record is not None and str(snap_record) == record_id:
                snap_rights = snap_item.get("rights") or {}
                snap_statement = (snap_rights.get("statement")
                                  if isinstance(snap_rights, dict) else snap_rights)
                if snap_statement and rights_policy.classify_rights(snap_statement) != "unknown":
                    return snap_statement, "live"
        return statement, "live"

    def _save_citation_from_snapshot(self, body: dict[str, Any]) -> dict[str, Any]:
        store = self.ws.store
        snap = self.ws.get_snapshot(body.get("save_token"))
        if snap is None or snap["kind"] != "page":
            raise ApiError(410, "page token expired or unknown; fetch the page again")
        payload = snap["payload"]
        library_id, record_id, page_id = self._page_identity(snap)
        text = str(payload.get("contents") or payload.get("ocr_text") or "")
        excerpt = body.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ApiError(400, "excerpt is required")
        if len(excerpt) > rights_policy.MAX_EXCERPT_CHARS:
            raise ApiError(422, f"excerpt exceeds the {rights_policy.MAX_EXCERPT_CHARS}-character "
                                "storage limit; select a shorter passage "
                                "(the limit is a system limit, not a legal quotation limit)")
        start = text.find(excerpt)
        if start < 0:
            raise ApiError(422, "excerpt is not present verbatim in the fetched OCR text")
        project_id = str(body.get("project_id") or "")
        doc_id = self._document_for_page(store, project_id, library_id, record_id,
                                         snap, body.get("saved_document_id"))
        doc = store.get_document(doc_id) or {}
        rights_statement, rights_basis = self._citation_rights_statement(
            body, payload, doc, library_id, record_id)
        stored_excerpt, decision = self._gate_new_excerpt(
            store, doc, rights_statement, excerpt, body, basis=rights_basis)
        state = payload.get("ocr_state") or {}
        identity = bool(state.get("page_identity_verified")
                        or payload.get("verified_mapping"))
        key_base = doc.get("citation_key") or "cit"
        fields = {
            "page_id": page_id,
            "citation_key": f"{key_base}-{page_id.rsplit('/', 1)[-1][:16]}",
            "original_excerpt": stored_excerpt,
            "excerpt_omitted_reason": None if stored_excerpt else decision["reason"],
            "excerpt_start": start,
            "excerpt_end": start + len(excerpt),
            "excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "ocr_source": library_id,
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
        saved["excerpt_stored"] = saved.get("original_excerpt") is not None
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
        if len(excerpt) > rights_policy.MAX_EXCERPT_CHARS:
            raise ApiError(422, f"excerpt exceeds the {rights_policy.MAX_EXCERPT_CHARS}-character "
                                "storage limit; enter a shorter passage")
        statement = (doc.get("rights_snapshot") or {}).get("statement")
        stored_excerpt, decision = self._gate_new_excerpt(
            store, doc, statement, excerpt, body, basis="stored")
        page_id = str(body.get("page_id") or "")
        fields = {
            "page_id": page_id,
            "citation_key": f"{doc.get('citation_key') or 'cit'}-manual",
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
        saved["excerpt_stored"] = saved.get("original_excerpt") is not None
        return saved

    # -- reverify ------------------------------------------------------------------
    def _reverify(self, citation_id: str) -> dict[str, Any]:
        """Re-verification with an honest check ledger (final
        review section 14): `unchanged` is returned only when
        every applicable check actually ran and found no
        change. Reference-only citations (no stored text) can
        never be reported as text-rechecked."""
        store = self.ws.store
        cit = store.get_citation(citation_id)
        if cit is None:
            raise ApiError(404, "citation not found")
        doc = store.get_document(cit["saved_document_id"]) or {}
        library_id = doc.get("library_id", "")
        checks: dict[str, Any] = {}
        try:
            page = self.runtime.run(self.runtime.service.get_page_text(
                library_id, cit["page_id"]))
        except Exception as exc:  # upstream failure is a result, not a 500
            message = str(exc).lower()
            status = ("access_restricted" if ("restrict" in message or "lending" in message)
                      else "source_unavailable")
            checks["page_fetch"] = "failed"
            return store.add_verification_observation(
                citation_id, status, {"checks": checks, "error": str(exc)[:300]})
        checks["page_fetch"] = "ok"
        text = str(page.get("contents") or page.get("ocr_text") or "")
        state = page.get("ocr_state") or {}
        identity = bool(state.get("page_identity_verified") or page.get("verified_mapping"))
        checks["page_identity"] = identity
        # Document identity of the freshly fetched page (b8
        # final review section 11): the payload must name the
        # SAME (library_id, record_id) as the saved document.
        # A page from another document - even with a matching
        # excerpt hash - proves nothing about this citation.
        page_record = page.get("record_id") or page.get("book_pid")
        page_library = page.get("library_id") or library_id
        document_identity = bool(
            page_record and doc.get("record_id")
            and str(page_record) == str(doc.get("record_id"))
            and str(page_library) == str(library_id))
        checks["document_identity"] = document_identity
        if not document_identity:
            identity = False
        checks["ocr_present"] = bool(text.strip())
        # Original-image reachability through the service's own
        # verification path; not performed -> recorded as such.
        image_checked = False
        verify = getattr(self.runtime.service, "verify_page", None)
        if verify is not None:
            try:
                report = self.runtime.run(verify(library_id, cit["page_id"]))
                image_check = (report.get("checks") or {}).get("image_reachable") or {}
                checks["image_reachable"] = bool(image_check.get("ok"))
                image_checked = True
            except Exception:
                checks["image_reachable"] = "check_failed"
        else:
            checks["image_reachable"] = "not_checked"
        current_rights = page.get("rights")
        current_statement = (current_rights.get("statement")
                             if isinstance(current_rights, dict) else current_rights)
        saved_statement = (cit.get("rights_at_save") or {}).get("statement")
        excerpt_state = "not_applicable"
        if cit.get("original_excerpt"):
            present = cit["original_excerpt"] in text
            hash_ok = (hashlib.sha256(cit["original_excerpt"].encode("utf-8")).hexdigest()
                       == cit.get("excerpt_hash"))
            checks["excerpt_present"] = present
            checks["excerpt_hash_matches"] = hash_ok
            excerpt_state = "present" if present and hash_ok else "not_found"
        elif (cit.get("excerpt_hash") and cit.get("excerpt_start") is not None
                and cit.get("excerpt_end") is not None):
            # Re-admission (b8 section 2; final review section
            # 11): a reference-only citation can regain its
            # excerpt ONLY from this fresh server-side fetch,
            # and only when ALL of these hold: the fetched page
            # belongs to the saved document (library + record
            # identity above), its page mapping is verified,
            # the slice at the stored offsets hashes to the
            # stored reference hash, the slice is within the
            # storage cap, and the CURRENT rights - observed by
            # this server just now, never the saved statement as
            # a fallback - permit storage under the trust model
            # including every later observation. NonCommercial
            # categories cannot re-admit here (no
            # purpose-confirmation channel). A hash match proves
            # string equality only, never provenance or
            # permission by itself.
            start = int(cit["excerpt_start"])
            end = int(cit["excerpt_end"])
            readmitted = False
            checks["readmission_blockers"] = []
            if not identity:
                checks["readmission_blockers"].append("page_identity_unverified")
            if not current_statement:
                checks["readmission_blockers"].append("current_rights_unavailable")
            if 0 <= start < end <= len(text):
                candidate = text[start:end]
                if len(candidate) > rights_policy.MAX_EXCERPT_CHARS:
                    checks["readmission_blockers"].append("excerpt_over_limit")
                elif hashlib.sha256(candidate.encode("utf-8")).hexdigest() != cit["excerpt_hash"]:
                    checks["readmission_blockers"].append("hash_mismatch")
                elif identity and current_statement:
                    observations = store.list_rights_observations(
                        cit["saved_document_id"])
                    decision = rights_policy.trusted_decision(
                        current_statement, rights_policy.TRUST_SERVER_OBSERVED,
                        observations + [{"statement": current_statement,
                                          "source": "reverify",
                                          "trust": "server_observed",
                                          "observed_at": now_iso()}])
                    if decision["excerpt_storage"] and not decision.get(
                            "excerpt_requires_confirmation"):
                        store.update_citation_excerpt(citation_id, candidate)
                        readmitted = True
                    else:
                        checks["readmission_blockers"].append(
                            "current_rights_do_not_permit")
            checks["excerpt_readmitted"] = readmitted
            excerpt_state = "present" if readmitted else "reference_only"
            if not readmitted:
                checks["excerpt"] = "not_checked_reference_only"
        else:
            checks["excerpt"] = "not_checked_reference_only"
            excerpt_state = "reference_only"
        rights_changed = False
        if current_statement and current_statement != saved_statement:
            rights_changed = True
            checks["rights_changed"] = {"from": saved_statement, "to": current_statement}
            store.add_rights_observation(
                cit["saved_document_id"], current_statement,
                rights_policy.classify_rights(current_statement),
                "reverify", "rights_changed")
        elif current_statement and (doc.get("rights_trust")
                                    or rights_policy.TRUST_SERVER_OBSERVED) != (
                                        rights_policy.TRUST_SERVER_OBSERVED):
            # A claim-trust document gains a server-side rights
            # observation through re-verification, so the trust
            # model can permit excerpts again afterwards.
            store.add_rights_observation(
                cit["saved_document_id"], current_statement,
                rights_policy.classify_rights(current_statement),
                "reverify", "observed")
        metadata_state = "not_checked"
        try:
            fresh = self.runtime.run(self.runtime.service.get_document(
                library_id, doc.get("record_id", "")))
            fresh_title = (fresh or {}).get("title")
            if fresh_title and doc.get("title") and fresh_title != doc["title"]:
                checks["metadata_changed"] = {"title_from": doc["title"],
                                              "title_to": fresh_title}
                metadata_state = "changed"
            else:
                metadata_state = "checked"
        except Exception:
            checks["metadata_check"] = "failed"
            metadata_state = "failed"
        if not identity:
            status = "mapping_unverified"
        elif excerpt_state == "not_found":
            status = "quotation_not_found"
        elif rights_changed:
            status = "rights_changed"
        elif metadata_state == "changed":
            status = "metadata_changed"
        elif excerpt_state == "reference_only" or not image_checked \
                or metadata_state != "checked":
            status = "partial_verification"
        else:
            status = "unchanged"
        return store.add_verification_observation(
            citation_id, status, {"checks": checks})

    # -- comparisons ------------------------------------------------------------------
    def _save_comparison(self, body: dict[str, Any]) -> dict[str, Any]:
        """Save a comparison against the REAL compare_documents
        response (final review section 19): excerpts live in
        rows[].documents[record_id].excerpts and are matched by
        record identity, never by list position. Each excerpt
        passes its own document's rights gate and the length
        cap; semantic_status stays not_checked."""
        store = self.ws.store
        project_id = str(body.get("project_id") or "")
        doc_ids = [str(d) for d in body.get("saved_document_ids") or []]
        if not 2 <= len(doc_ids) <= 4 or len(set(doc_ids)) != len(doc_ids):
            raise ApiError(400, "comparisons take 2-4 distinct saved documents")
        docs = []
        for doc_id in doc_ids:
            doc = store.get_document(doc_id)
            if doc is None or doc["project_id"] != project_id:
                raise ApiError(400, "comparison documents must belong to the project")
            docs.append(doc)
        result = self.runtime.run(self.runtime.service.compare_documents(
            [{"library_id": d["library_id"], "record_id": d["record_id"]} for d in docs]))
        result_docs = {(d.get("library_id"), d.get("record_id")): d
                       for d in result.get("documents") or []}
        rows = result.get("rows") or []
        lexical: dict[str, Any] = {}
        concepts: dict[str, Any] = {}
        shared_all: list[str] = []
        shared_some: list[str] = []
        # b8 section 2: excerpts are aggregated by the composite
        # (library_id, record_id) identity - never by record_id
        # alone, which mixed up different libraries' documents
        # that happen to share a record_id.
        excerpts_by_record: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            aspect = row.get("aspect") or ""
            lexical[aspect] = {"shared_terms": row.get("shared_terms") or [],
                               "partial_terms": row.get("partial_terms") or [],
                               "unique_terms": row.get("unique_terms") or {}}
            concepts[aspect] = row.get("dictionary_concept_overlap") or []
            for term in row.get("shared_terms") or []:
                if term not in shared_all:
                    shared_all.append(term)
            for term in row.get("partial_terms") or []:
                if term not in shared_some:
                    shared_some.append(term)
            for key, cell in (row.get("documents") or {}).items():
                if "|" in str(key):
                    library_id, _, record_id = str(key).partition("|")
                else:
                    # Legacy plain-record_id key: attribute it
                    # only when exactly one compared document
                    # carries that record_id; an ambiguous key is
                    # dropped rather than guessed.
                    matches = [d for d in docs if d["record_id"] == str(key)]
                    if len(matches) != 1:
                        continue
                    library_id, record_id = matches[0]["library_id"], str(key)
                for entry in cell.get("excerpts") or []:
                    excerpts_by_record.setdefault((library_id, record_id), []).append({
                        "text": entry.get("excerpt") or "",
                        "page_id": entry.get("page_id"),
                        "citation_key": entry.get("citation_key"),
                        "aspect": aspect,
                        "image_url": entry.get("image_url"),
                    })
        excerpts: dict[str, Any] = {}
        insufficient: list[dict[str, Any]] = []
        total_bytes = 0
        for doc in docs:
            entries = excerpts_by_record.get((doc["library_id"], doc["record_id"])) or []
            result_doc = result_docs.get((doc["library_id"], doc["record_id"]))
            if result_doc is not None and result_doc.get("error"):
                insufficient.append({"library_id": doc["library_id"],
                                     "record_id": doc["record_id"],
                                     "reason": str(result_doc["error"])[:300]})
            elif not entries:
                insufficient.append({"library_id": doc["library_id"],
                                     "record_id": doc["record_id"],
                                     "reason": "no verified excerpt pages in the comparison"})
            statement = (doc.get("rights_snapshot") or {}).get("statement")
            decision = rights_policy.trusted_decision(
                statement,
                doc.get("rights_trust") or rights_policy.TRUST_SERVER_OBSERVED,
                store.list_rights_observations(doc["saved_document_id"]))
            if (decision.get("excerpt_requires_confirmation")
                    and body.get("nc_purpose_confirmed") is not True):
                decision = {**decision, "excerpt_storage": False,
                            "reason": ("excerpt withheld: NonCommercial "
                                       "licence and no non-commercial "
                                       "research purpose was confirmed "
                                       "for this save")}
            if not decision["excerpt_storage"]:
                excerpts[doc["saved_document_id"]] = {
                    "omitted": decision["reason"], "count": len(entries)}
                continue
            kept = []
            for entry in entries[:6]:
                if len(entry["text"]) > rights_policy.MAX_EXCERPT_CHARS:
                    continue
                size = len(entry["text"].encode("utf-8"))
                if total_bytes + size > 256_000:
                    break
                total_bytes += size
                kept.append(entry)
            excerpts[doc["saved_document_id"]] = kept
        return store.save_comparison(project_id, {
            "title": str(body.get("title") or ""),
            "saved_document_ids": doc_ids,
            "comparison_aspects": {"aspects": result.get("aspects") or [],
                                   "question": result.get("question"),
                                   "status": result.get("status")},
            "original_excerpts": excerpts,
            "lexical_overlap": lexical,
            "dictionary_concept_overlap": concepts,
            "shared_by_all": shared_all,
            "shared_by_some": shared_some,
            "semantic_status": "not_checked",
            "insufficient_evidence": insufficient,
        })

    # -- restore ------------------------------------------------------------------------
    def _restore(self, data: bytes) -> dict[str, Any]:
        """Restore as ONE managed operation (final review
        sections 7, 8 and 12): candidate validation, atomic
        quiesce ownership, in-flight drain, pre-restore backup
        taken AFTER quiescence, swap, new-store open +
        migration, trust downgrade, integrity check - and a
        rollback to the pre-restore backup on ANY failure
        after the swap, including a failing trust downgrade.
        Structural validation cannot prove a backup file is
        authentic, so restored verification states and rights
        are claims until re-verified against the live sources.
        A concurrent restore is refused atomically (409)."""
        store = self.ws.store
        db_path = store.db_path
        token = secrets.token_urlsafe(6)
        tmp = db_path.parent / f"restore-candidate-{token}.db"
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        info = WorkspaceStore.validate_backup(tmp)
        if not info["ok"]:
            tmp.unlink(missing_ok=True)
            raise ApiError(400, "backup rejected: " + "; ".join(info["problems"][:5]))
        if not self.ws.acquire_restore(timeout=30.0):
            tmp.unlink(missing_ok=True)
            raise ApiError(409, "restore aborted: another restore owns the "
                                "workspace, or operations did not finish in "
                                "time; nothing was changed")
        # From here this call OWNS the quiesced state; only it
        # may unquiesce.
        swapped = False
        pre: dict[str, Any] | None = None
        new_store: WorkspaceStore | None = None
        try:
            pre = store.backup(db_path.parent / "backups" /
                               f"pre-restore-{now_iso().replace(':', '')}-{token}.db")
            store.close()
            for suffix in ("-wal", "-shm"):
                Path(str(db_path) + suffix).unlink(missing_ok=True)
            os.replace(tmp, db_path)
            swapped = True
            new_store = WorkspaceStore(db_path)
            downgrade = new_store.apply_restore_trust_downgrade()
            if new_store.integrity_check() != "ok":
                raise RuntimeError("restored database failed its integrity check")
            # Smoke check: the new store must actually serve reads.
            new_store.list_projects()
        except Exception as exc:
            if new_store is not None:
                try:
                    new_store.close()
                except Exception:
                    pass
            if swapped and pre is not None:
                # Roll back to the pre-restore backup, itself
                # verified by opening it before publishing.
                for suffix in ("-wal", "-shm"):
                    Path(str(db_path) + suffix).unlink(missing_ok=True)
                rollback_tmp = db_path.parent / f"rollback-copy-{token}.db"
                try:
                    rollback_tmp.write_bytes(Path(pre["path"]).read_bytes())
                    try:
                        os.chmod(rollback_tmp, 0o600)
                    except OSError:
                        pass
                    os.replace(rollback_tmp, db_path)
                    self.ws.store = WorkspaceStore(db_path)
                finally:
                    rollback_tmp.unlink(missing_ok=True)
                raise ApiError(500, "restore failed; the previous database "
                                    "was rolled back from the pre-restore "
                                    f"backup ({type(exc).__name__})")
            raise ApiError(500, f"restore failed before replacement; "
                                f"nothing was changed ({type(exc).__name__})")
        finally:
            tmp.unlink(missing_ok=True)
            self.ws.unquiesce()
        self.ws.store = new_store
        return {"restored": True, "schema_version": self.ws.store.schema_version,
                "candidate_sha256": info["sha256"],
                "pre_restore_backup": pre["path"],
                "trust_downgrade": downgrade,
                "note": "the previous database was backed up before replacement; "
                        "a checksum of an uploaded file does not prove the file "
                        "is authentic, so restored verification states were "
                        "downgraded to restored_unverified, every restored "
                        "rights observation was downgraded to a restored claim, "
                        "and restored rights are treated as claims until "
                        "re-verification. NOTE: a workspace backup file contains "
                        "the stored research data itself and is more sensitive "
                        "than a rights-filtered export - keep it private"}


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")
