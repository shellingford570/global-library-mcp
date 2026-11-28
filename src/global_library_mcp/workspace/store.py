"""SQLite workspace store (b7, brief sections 7, 8; final
review sections 9, 24).

Design: Python stdlib sqlite3 only. One connection guarded by
a re-entrant lock (the web server is threaded); foreign_keys
ON for every connection; WAL journal; busy_timeout 5s;
synchronous FULL (final review: for long-lived research
data, durability outranks the few-ms write difference of
NORMAL; measured in docs/b7-performance-evaluation.md).
All timestamps are UTC ISO-8601 with a Z suffix. Structured
payloads are JSON text columns; every queryable field is a
real column with constraints and indexes. Migrations are
transactional, recorded, and preceded by an automatic
backup of the pre-migration database; a database from a
NEWER schema is refused untouched (FutureSchemaError).

Referential integrity is enforced beyond bare foreign keys:
a foreign key proves the referenced row EXISTS, not that it
belongs to the same research project. Store methods that
link rows across tables therefore validate project
membership inside the same transaction (final review
section 9).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import policy as _policy

SCHEMA_VERSION = 6

# Verification-status vocabulary a genuine database of this
# application can contain. Restore validation rejects
# anything else (final review sections 7, 8).
KNOWN_QUOTATION_STATUSES = {
    "verified_against_fetched_ocr", "fetched_unverified_mapping",
    "user_entered_unverified", "imported_unverified", "restored_unverified",
    "restored_downgrade", "unchanged",
    "metadata_changed", "ocr_changed", "quotation_not_found",
    "source_unavailable", "mapping_unverified", "access_restricted",
    "rights_changed", "recheck_failed", "not_rechecked",
    "reference_only", "excerpt_not_checked", "metadata_check_failed",
    "image_not_checked", "partial_verification",
}
KNOWN_PROVENANCE = {"system_fetched", "user_entered", "imported"}
KNOWN_HISTORY_PROVENANCE = {"server_recorded", "user_entered", "imported"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return uuid.uuid4().hex


def search_text(*parts: Any) -> str:
    """Normalised substring-search index text: NFKC + casefold.
    The stored originals are never rewritten; this is an index."""
    joined = " ".join(str(p) for p in parts if p)
    return unicodedata.normalize("NFKC", joined).casefold()


class FutureSchemaError(RuntimeError):
    """The database was written by a newer version; refuse to touch it."""


class DuplicateError(RuntimeError):
    """A uniqueness rule rejected the write (e.g. same record saved twice)."""


_SCHEMA_V1 = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE saved_documents (
    saved_document_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    library_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    work_id_candidate TEXT,
    author_id_candidate TEXT,
    resolution_status TEXT,
    title TEXT,
    original_title TEXT,
    translated_title TEXT,
    author TEXT,
    publication_date TEXT,
    publisher TEXT,
    publication_place TEXT,
    edition TEXT,
    translator TEXT,
    volume TEXT,
    language_raw TEXT,
    language_normalized TEXT,
    holding_institution TEXT,
    material_type TEXT,
    landing_url TEXT,
    identifiers TEXT NOT NULL DEFAULT '{}',
    rights_snapshot TEXT NOT NULL DEFAULT '{}',
    discovery_reason TEXT,
    retrieved_at TEXT,
    saved_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, library_id, record_id)
);
CREATE INDEX idx_docs_project ON saved_documents(project_id);
CREATE INDEX idx_docs_search ON saved_documents(search_text);
CREATE TABLE saved_citations (
    citation_id TEXT PRIMARY KEY,
    saved_document_id TEXT NOT NULL REFERENCES saved_documents(saved_document_id) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    citation_key TEXT NOT NULL,
    original_excerpt TEXT,
    excerpt_omitted_reason TEXT,
    excerpt_start INTEGER,
    excerpt_end INTEGER,
    excerpt_hash TEXT,
    ocr_source TEXT,
    ocr_file TEXT,
    source_url TEXT,
    image_url TEXT,
    canvas_id TEXT,
    printed_page TEXT,
    digital_frame TEXT,
    page_mapping_status TEXT,
    image_verification_status TEXT,
    quotation_verification_status TEXT,
    provenance TEXT NOT NULL DEFAULT 'system_fetched',
    user_annotation TEXT,
    rights_at_save TEXT NOT NULL DEFAULT '{}',
    retrieved_at TEXT,
    verified_at TEXT,
    saved_at TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_cit_doc ON saved_citations(saved_document_id);
CREATE TABLE research_notes (
    note_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    saved_document_id TEXT REFERENCES saved_documents(saved_document_id) ON DELETE CASCADE,
    citation_id TEXT REFERENCES saved_citations(citation_id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_notes_project ON research_notes(project_id);
CREATE TABLE search_history (
    search_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    original_query TEXT NOT NULL,
    search_parameters TEXT NOT NULL DEFAULT '{}',
    planned_variants TEXT NOT NULL DEFAULT '[]',
    executed_variants TEXT NOT NULL DEFAULT '[]',
    searched_libraries TEXT NOT NULL DEFAULT '{}',
    skipped_libraries TEXT NOT NULL DEFAULT '{}',
    result_summary TEXT NOT NULL DEFAULT '{}',
    http_stats TEXT NOT NULL DEFAULT '{}',
    search_status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_hist_project ON search_history(project_id);
CREATE TABLE saved_comparisons (
    comparison_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    saved_document_ids TEXT NOT NULL DEFAULT '[]',
    comparison_aspects TEXT NOT NULL DEFAULT '{}',
    original_excerpts TEXT NOT NULL DEFAULT '{}',
    lexical_overlap TEXT NOT NULL DEFAULT '{}',
    dictionary_concept_overlap TEXT NOT NULL DEFAULT '{}',
    shared_by_all TEXT NOT NULL DEFAULT '[]',
    shared_by_some TEXT NOT NULL DEFAULT '[]',
    semantic_status TEXT NOT NULL DEFAULT 'not_checked',
    insufficient_evidence TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE project_tags (
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, tag_id)
);
CREATE TABLE document_tags (
    saved_document_id TEXT NOT NULL REFERENCES saved_documents(saved_document_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (saved_document_id, tag_id)
);
CREATE TABLE collections (
    collection_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, name)
);
CREATE TABLE collection_documents (
    collection_id TEXT NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
    saved_document_id TEXT NOT NULL REFERENCES saved_documents(saved_document_id) ON DELETE CASCADE,
    PRIMARY KEY (collection_id, saved_document_id)
);
CREATE TABLE rights_observations (
    observation_id TEXT PRIMARY KEY,
    saved_document_id TEXT NOT NULL REFERENCES saved_documents(saved_document_id) ON DELETE CASCADE,
    statement TEXT,
    category TEXT,
    source TEXT,
    observed_at TEXT NOT NULL,
    change_status TEXT NOT NULL DEFAULT 'observed'
);
CREATE TABLE verification_observations (
    observation_id TEXT PRIMARY KEY,
    citation_id TEXT NOT NULL REFERENCES saved_citations(citation_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL
);
"""

_SCHEMA_V2 = """
ALTER TABLE saved_documents ADD COLUMN citation_key TEXT;
ALTER TABLE search_history ADD COLUMN provenance TEXT NOT NULL DEFAULT 'server_recorded';
CREATE TABLE research_notes_v2 (
    note_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    saved_document_id TEXT REFERENCES saved_documents(saved_document_id) ON DELETE SET NULL,
    citation_id TEXT REFERENCES saved_citations(citation_id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT ''
);
INSERT INTO research_notes_v2 (note_id, project_id, saved_document_id, citation_id,
    title, content, created_at, updated_at, search_text)
    SELECT note_id, project_id, saved_document_id, citation_id,
    title, content, created_at, updated_at, search_text FROM research_notes;
DROP TABLE research_notes;
ALTER TABLE research_notes_v2 RENAME TO research_notes;
CREATE INDEX idx_notes_project ON research_notes(project_id);
"""

_SCHEMA_V3 = """
ALTER TABLE saved_documents ADD COLUMN rights_trust TEXT NOT NULL DEFAULT 'server_observed';
"""

_SCHEMA_V4 = """
ALTER TABLE rights_observations ADD COLUMN trust TEXT;
"""

_SCHEMA_V5 = """
CREATE TABLE research_artefacts (
    artefact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    trust TEXT NOT NULL DEFAULT 'server_generated',
    provenance TEXT NOT NULL DEFAULT 'server',
    operation_id TEXT NOT NULL DEFAULT '',
    algorithm_version TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_artefacts_project ON research_artefacts(project_id);
"""

_SCHEMA_V6 = """
ALTER TABLE rights_observations ADD COLUMN seq INTEGER;
CREATE TABLE rights_seq_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_seq INTEGER NOT NULL DEFAULT 0
);
INSERT INTO rights_seq_counter (id, next_seq) VALUES (1, 0);
"""

MIGRATIONS: list[tuple[int, str]] = [(1, _SCHEMA_V1), (2, _SCHEMA_V2), (3, _SCHEMA_V3), (4, _SCHEMA_V4), (5, _SCHEMA_V5), (6, _SCHEMA_V6)]


# Categories that RESTRICT excerpt use (b11 final review section
# 11 fail-closed tie-break): anything not known to permit excerpts
# is restrictive; only the excerpt-permitting categories are not.
_PERMISSIVE_RIGHTS_CATEGORIES = {
    "public_domain", "cc_by", "cc_by_sa", "cc_by_nc", "cc_by_nc_sa"}
_RESTRICTIVE_RIGHTS_CATEGORIES = {
    "in_copyright", "in_copyright_eu_orphan", "in_copyright_educational",
    "no_copyright_non_commercial", "no_copyright_other", "copyright_undetermined",
    "undetermined", "unknown", "restricted", "in_copyright_us"}


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


class WorkspaceStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if self.db_path.is_symlink():
            raise ValueError("workspace database path must not be a symlink")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = self._connect()
        try:
            self._migrate()
        except Exception:
            self._conn.close()
            raise
        try:
            import os
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    # -- connection / migration -------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _migrate(self) -> None:
        with self._lock:
            exists = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            current = 0
            if exists:
                row = self._conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
                current = int(row["v"] or 0)
            if current > SCHEMA_VERSION:
                raise FutureSchemaError(
                    f"workspace schema {current} is newer than this build "
                    f"supports ({SCHEMA_VERSION}); the database was left untouched")
            pending = [(v, s) for v, s in MIGRATIONS if v > current]
            if pending and current >= 1 and self.db_path.exists() \
                    and self.db_path.stat().st_size > 0:
                # Never migrate the only copy: keep a backup of
                # the pre-migration database beside it.
                bak = self.db_path.with_name(
                    self.db_path.name + f".pre-migration-v{current}.bak")
                if not bak.exists():
                    target = sqlite3.connect(str(bak))
                    try:
                        self._conn.backup(target)
                    finally:
                        target.close()
                    try:
                        import os
                        os.chmod(bak, 0o600)
                    except OSError:
                        pass
            for version, sql in pending:
                with self._conn:
                    self._conn.executescript(sql)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, now_iso()))
            if pending and any(v == 2 for v, _ in pending):
                self._backfill_citation_keys()
            if pending and any(v == 3 for v, _ in pending):
                self._mark_imported_document_trust()
            if pending and any(v == 4 for v, _ in pending):
                self._backfill_observation_trust(from_version=current)
            if pending and any(v == 6 for v, _ in pending):
                self._backfill_rights_seq()

    def _next_rights_seq(self) -> int:
        """Monotonic rights-observation sequence (b11 final
        review section 11). Assigned inside the caller's
        transaction on this store's single connection, so the
        order is total and matches insertion order - unlike the
        second-precision observed_at or random observation ids."""
        row = self._conn.execute(
            "SELECT next_seq FROM rights_seq_counter WHERE id = 1").fetchone()
        nxt = int(row["next_seq"]) + 1 if row else 1
        self._conn.execute(
            "INSERT INTO rights_seq_counter (id, next_seq) VALUES (1, ?)"
            " ON CONFLICT(id) DO UPDATE SET next_seq = excluded.next_seq",
            (nxt,))
        return nxt

    def backfill_rights_seq(self) -> int:
        """Assign seq to rows that arrived without one (imports
        and restores write rows directly). Existing seq values
        are never renumbered; new assignments continue the
        counter in rowid (insertion) order."""
        with self._lock, self._conn:
            return self._backfill_rights_seq_locked()

    def _backfill_rights_seq_locked(self) -> int:
        rows = self._conn.execute(
            "SELECT observation_id FROM rights_observations"
            " WHERE seq IS NULL ORDER BY rowid").fetchall()
        for r in rows:
            self._conn.execute(
                "UPDATE rights_observations SET seq = ?"
                " WHERE observation_id = ?",
                (self._next_rights_seq(), r["observation_id"]))
        return len(rows)

    def _backfill_rights_seq(self) -> None:
        with self._lock, self._conn:
            self._backfill_rights_seq_locked()

    def _mark_imported_document_trust(self) -> None:
        """b8 migration: documents that arrived via a b7 import
        carry claim-trust rights. Evidence used (final review
        section 10): an imported citation (provenance), a
        citation rights_at_save marked imported_claim, or an
        imported rights observation. A document with none of
        these markers in a pre-b8 database was saved by this
        server and keeps server_observed trust at v3; the v4
        step below handles the residual unprovable-origin
        cases for pre-v3 databases."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE saved_documents SET rights_trust = 'imported_claim'"
                " WHERE saved_document_id IN ("
                " SELECT DISTINCT saved_document_id FROM saved_citations"
                " WHERE rights_at_save LIKE '%\"imported_claim\"%')"
                " OR saved_document_id IN ("
                " SELECT DISTINCT saved_document_id FROM saved_citations"
                " WHERE provenance = 'imported')"
                " OR saved_document_id IN ("
                " SELECT DISTINCT saved_document_id FROM rights_observations"
                " WHERE source LIKE 'imported%')")

    def _backfill_observation_trust(self, from_version: int) -> None:
        """Schema v4 (b8 final review sections 8 and 10):
        rights observations gain an explicit trust column.
        Rows whose source is one of this server's own live
        sources are backfilled server_observed; every other
        row is a claim (restored rows keep restored_claim).
        Additionally, databases created before schema v3
        (all b7 databases) carry NO trustworthy origin marker
        for saved documents - the rights_trust column did not
        exist and imports cannot be distinguished from server
        saves for citation-less or comparison-only documents -
        so every pre-v3 document is marked imported_claim:
        its data, notes, ids and references are preserved, and
        excerpt display resumes after a server-side
        re-verification. Nothing is deleted."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE rights_observations SET trust = 'server_observed'"
                " WHERE source IN ('live_fetch', 'reverify', 'document_save', 'page_fetch')")
            self._conn.execute(
                "UPDATE rights_observations SET trust = 'restored_claim'"
                " WHERE source IN ('restored_backup', 'restored_claim')")
            self._conn.execute(
                "UPDATE rights_observations SET trust = 'imported_claim'"
                " WHERE trust IS NULL")
            if from_version < 3:
                self._conn.execute(
                    "UPDATE saved_documents SET rights_trust = 'imported_claim'")

    def _backfill_citation_keys(self) -> None:
        """Assign stored citation keys to documents saved
        before schema v2 (deterministic, per project)."""
        from .exports import base_citation_key
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT saved_document_id, project_id, library_id, record_id,"
                " author, publication_date, title FROM saved_documents"
                " WHERE citation_key IS NULL").fetchall()
            used: dict[str, set[str]] = {}
            for row in rows:
                used.setdefault(row["project_id"], set())
            for row in self._conn.execute(
                    "SELECT project_id, citation_key FROM saved_documents"
                    " WHERE citation_key IS NOT NULL"):
                used.setdefault(row["project_id"], set()).add(row["citation_key"])
            for row in rows:
                key = self._unique_citation_key(
                    row["project_id"], base_citation_key(dict(row)),
                    row["library_id"], row["record_id"], used[row["project_id"]])
                self._conn.execute(
                    "UPDATE saved_documents SET citation_key = ? WHERE saved_document_id = ?",
                    (key, row["saved_document_id"]))

    @staticmethod
    def _unique_citation_key(project_id: str, base: str, library_id: str,
                             record_id: str, used: set[str]) -> str:
        if base not in used:
            used.add(base)
            return base
        suffix = hashlib.sha256(f"{library_id}/{record_id}".encode("utf-8")).hexdigest()[:6]
        key = f"{base}-{suffix}"
        n = 2
        while key in used:
            key = f"{base}-{suffix}-{n}"
            n += 1
        used.add(key)
        return key

    @property
    def schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def integrity_check(self) -> str:
        return str(self._conn.execute("PRAGMA integrity_check").fetchone()[0])

    # -- projects ----------------------------------------------------------
    def create_project(self, title: str, description: str = "",
                       tags: list[str] | None = None) -> dict[str, Any]:
        pid = new_id()
        ts = now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO projects (project_id, title, description, created_at, updated_at, schema_version)"
                " VALUES (?, ?, ?, ?, ?, ?)", (pid, title, description, ts, ts, SCHEMA_VERSION))
            for name in tags or []:
                self._attach_project_tag(pid, name)
        return self.get_project(pid)  # type: ignore[return-value]

    def _attach_project_tag(self, project_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            return
        row = self._conn.execute("SELECT tag_id FROM tags WHERE name = ?", (name,)).fetchone()
        tag_id = row["tag_id"] if row else new_id()
        if not row:
            self._conn.execute("INSERT INTO tags (tag_id, name) VALUES (?, ?)", (tag_id, name))
        self._conn.execute(
            "INSERT OR IGNORE INTO project_tags (project_id, tag_id) VALUES (?, ?)",
            (project_id, tag_id))

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            project = _row(self._conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone())
            if project is None:
                return None
            project["tags"] = [r["name"] for r in self._conn.execute(
                "SELECT t.name FROM tags t JOIN project_tags pt ON pt.tag_id = t.tag_id"
                " WHERE pt.project_id = ? ORDER BY t.name", (project_id,))]
            project["counts"] = self._project_counts(project_id)
            return project

    def _project_counts(self, project_id: str) -> dict[str, int]:
        q = lambda sql, args: int(self._conn.execute(sql, args).fetchone()[0])
        return {
            "documents": q("SELECT COUNT(*) FROM saved_documents WHERE project_id = ?", (project_id,)),
            "citations": q("SELECT COUNT(*) FROM saved_citations c JOIN saved_documents d"
                           " ON d.saved_document_id = c.saved_document_id WHERE d.project_id = ?", (project_id,)),
            "notes": q("SELECT COUNT(*) FROM research_notes WHERE project_id = ?", (project_id,)),
            "searches": q("SELECT COUNT(*) FROM search_history WHERE project_id = ?", (project_id,)),
            "comparisons": q("SELECT COUNT(*) FROM saved_comparisons WHERE project_id = ?", (project_id,)),
            "collections": q("SELECT COUNT(*) FROM collections WHERE project_id = ?", (project_id,)),
        }

    def list_projects(self, include_archived: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM projects"
            if not include_archived:
                sql += " WHERE archived_at IS NULL"
            sql += " ORDER BY updated_at DESC"
            out = []
            for row in self._conn.execute(sql):
                project = dict(row)
                project["counts"] = self._project_counts(project["project_id"])
                out.append(project)
            return out

    def update_project(self, project_id: str, *, title: str | None = None,
                       description: str | None = None, archived: bool | None = None,
                       tags: list[str] | None = None) -> dict[str, Any] | None:
        with self._lock, self._conn:
            current = self.get_project(project_id)
            if current is None:
                return None
            ts = now_iso()
            self._conn.execute(
                "UPDATE projects SET title = ?, description = ?, archived_at = ?, updated_at = ?"
                " WHERE project_id = ?",
                (title if title is not None else current["title"],
                 description if description is not None else current["description"],
                 (ts if archived else None) if archived is not None else current["archived_at"],
                 ts, project_id))
            if tags is not None:
                self._conn.execute("DELETE FROM project_tags WHERE project_id = ?", (project_id,))
                for name in tags:
                    self._attach_project_tag(project_id, name)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> dict[str, int] | None:
        with self._lock, self._conn:
            if self.get_project(project_id) is None:
                return None
            counts = self._project_counts(project_id)
            self._conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            return counts

    # -- saved documents ----------------------------------------------------
    _DOC_FIELDS = (
        "work_id_candidate", "author_id_candidate", "resolution_status", "title",
        "original_title", "translated_title", "author", "publication_date",
        "publisher", "publication_place", "edition", "translator", "volume",
        "language_raw", "language_normalized", "holding_institution",
        "material_type", "landing_url", "discovery_reason", "retrieved_at",
    )

    def save_document(self, project_id: str, library_id: str, record_id: str,
                      fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.get_project(project_id) is None:
                raise KeyError(f"unknown project {project_id}")
            existing = self._conn.execute(
                "SELECT saved_document_id FROM saved_documents"
                " WHERE project_id = ? AND library_id = ? AND record_id = ?",
                (project_id, library_id, record_id)).fetchone()
            if existing:
                raise DuplicateError(existing["saved_document_id"])
            doc_id = new_id()
            ts = now_iso()
            values = {k: fields.get(k) for k in self._DOC_FIELDS}
            text = search_text(values.get("title"), values.get("original_title"),
                               values.get("author"), values.get("publication_date"),
                               library_id, values.get("holding_institution"))
            from .exports import base_citation_key
            used = {r["citation_key"] for r in self._conn.execute(
                "SELECT citation_key FROM saved_documents"
                " WHERE project_id = ? AND citation_key IS NOT NULL", (project_id,))}
            key = self._unique_citation_key(
                project_id, base_citation_key({**values, "library_id": library_id}),
                library_id, record_id, used)
            with self._conn:
                self._conn.execute(
                    "INSERT INTO saved_documents (saved_document_id, project_id, library_id,"
                    " record_id, identifiers, rights_snapshot, saved_at, updated_at, search_text,"
                    " citation_key, rights_trust, "
                    + ", ".join(self._DOC_FIELDS) + ")"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    + ", ".join("?" for _ in self._DOC_FIELDS) + ")",
                    (doc_id, project_id, library_id, record_id,
                     _json(fields.get("identifiers")), _json(fields.get("rights_snapshot")),
                     ts, ts, text, key,
                     str(fields.get("rights_trust") or "server_observed"),
                     *[values[k] for k in self._DOC_FIELDS]))
                self._conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE project_id = ?", (ts, project_id))
            return self.get_document(doc_id)  # type: ignore[return-value]

    def find_document(self, project_id: str, library_id: str,
                      record_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT saved_document_id FROM saved_documents"
                " WHERE project_id = ? AND library_id = ? AND record_id = ?",
                (project_id, library_id, record_id)).fetchone()
            return self.get_document(row["saved_document_id"]) if row else None

    def get_document(self, saved_document_id: str) -> dict[str, Any] | None:
        with self._lock:
            doc = _row(self._conn.execute(
                "SELECT * FROM saved_documents WHERE saved_document_id = ?",
                (saved_document_id,)).fetchone())
            if doc is None:
                return None
            doc["identifiers"] = json.loads(doc["identifiers"] or "{}")
            doc["rights_snapshot"] = json.loads(doc["rights_snapshot"] or "{}")
            doc["tags"] = [r["name"] for r in self._conn.execute(
                "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id = t.tag_id"
                " WHERE dt.saved_document_id = ? ORDER BY t.name", (saved_document_id,))]
            return doc

    def list_documents(self, project_id: str, *, tag: str | None = None,
                       collection_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT d.* FROM saved_documents d WHERE d.project_id = ?"
            args: list[Any] = [project_id]
            if tag:
                sql += (" AND d.saved_document_id IN (SELECT dt.saved_document_id FROM document_tags dt"
                        " JOIN tags t ON t.tag_id = dt.tag_id WHERE t.name = ?)")
                args.append(tag)
            if collection_id:
                sql += (" AND d.saved_document_id IN (SELECT saved_document_id"
                        " FROM collection_documents WHERE collection_id = ?)")
                args.append(collection_id)
            sql += " ORDER BY d.saved_at DESC"
            return [self.get_document(r["saved_document_id"])  # type: ignore[misc]
                    for r in self._conn.execute(sql, args)]

    def delete_document(self, saved_document_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM saved_documents WHERE saved_document_id = ?", (saved_document_id,))
            return cur.rowcount > 0

    def set_document_tags(self, saved_document_id: str, names: list[str]) -> list[str]:
        with self._lock, self._conn:
            if self.get_document(saved_document_id) is None:
                raise KeyError(saved_document_id)
            self._conn.execute("DELETE FROM document_tags WHERE saved_document_id = ?",
                               (saved_document_id,))
            for name in names:
                name = name.strip()
                if not name:
                    continue
                row = self._conn.execute("SELECT tag_id FROM tags WHERE name = ?", (name,)).fetchone()
                tag_id = row["tag_id"] if row else new_id()
                if not row:
                    self._conn.execute("INSERT INTO tags (tag_id, name) VALUES (?, ?)", (tag_id, name))
                self._conn.execute(
                    "INSERT OR IGNORE INTO document_tags (saved_document_id, tag_id) VALUES (?, ?)",
                    (saved_document_id, tag_id))
        doc = self.get_document(saved_document_id)
        return doc["tags"] if doc else []

    # -- collections ---------------------------------------------------------
    def create_collection(self, project_id: str, name: str) -> dict[str, Any]:
        with self._lock, self._conn:
            if self.get_project(project_id) is None:
                raise KeyError(project_id)
            cid = new_id()
            try:
                self._conn.execute(
                    "INSERT INTO collections (collection_id, project_id, name, created_at)"
                    " VALUES (?, ?, ?, ?)", (cid, project_id, name, now_iso()))
            except sqlite3.IntegrityError as exc:
                raise DuplicateError(name) from exc
        return {"collection_id": cid, "project_id": project_id, "name": name}

    def list_collections(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for row in self._conn.execute(
                    "SELECT * FROM collections WHERE project_id = ? ORDER BY name", (project_id,)):
                item = dict(row)
                item["document_count"] = int(self._conn.execute(
                    "SELECT COUNT(*) FROM collection_documents WHERE collection_id = ?",
                    (item["collection_id"],)).fetchone()[0])
                out.append(item)
            return out

    def collection_add(self, collection_id: str, saved_document_id: str) -> None:
        with self._lock, self._conn:
            coll = self._conn.execute(
                "SELECT project_id FROM collections WHERE collection_id = ?",
                (collection_id,)).fetchone()
            if coll is None:
                raise KeyError(collection_id)
            doc = self.get_document(saved_document_id)
            if doc is None:
                raise KeyError(saved_document_id)
            if doc["project_id"] != coll["project_id"]:
                raise ValueError("document belongs to another project")
            self._conn.execute(
                "INSERT OR IGNORE INTO collection_documents (collection_id, saved_document_id)"
                " VALUES (?, ?)", (collection_id, saved_document_id))

    def collection_remove(self, collection_id: str, saved_document_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM collection_documents WHERE collection_id = ? AND saved_document_id = ?",
                (collection_id, saved_document_id))

    def delete_collection(self, collection_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM collections WHERE collection_id = ?", (collection_id,))
            return cur.rowcount > 0

    # -- citations -----------------------------------------------------------
    _CIT_FIELDS = (
        "page_id", "citation_key", "original_excerpt", "excerpt_omitted_reason",
        "excerpt_start", "excerpt_end", "excerpt_hash", "ocr_source", "ocr_file",
        "source_url", "image_url", "canvas_id", "printed_page", "digital_frame",
        "page_mapping_status", "image_verification_status",
        "quotation_verification_status", "provenance", "user_annotation",
        "rights_at_save", "retrieved_at", "verified_at",
    )

    def save_citation(self, saved_document_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.get_document(saved_document_id) is None:
                raise KeyError(saved_document_id)
            if not fields.get("page_id") or not fields.get("citation_key"):
                raise ValueError("page_id and citation_key are required")
            cid = new_id()
            ts = now_iso()
            values = {k: fields.get(k) for k in self._CIT_FIELDS}
            if isinstance(values.get("rights_at_save"), (dict, list)):
                values["rights_at_save"] = _json(values["rights_at_save"])
            if values.get("rights_at_save") is None:
                values["rights_at_save"] = "{}"
            if values.get("provenance") is None:
                values["provenance"] = "system_fetched"
            text = search_text(values.get("original_excerpt"), values.get("page_id"))
            with self._conn:
                self._conn.execute(
                    "INSERT INTO saved_citations (citation_id, saved_document_id, saved_at, search_text, "
                    + ", ".join(self._CIT_FIELDS) + ") VALUES (?, ?, ?, ?, "
                    + ", ".join("?" for _ in self._CIT_FIELDS) + ")",
                    (cid, saved_document_id, ts, text,
                     *[values[k] for k in self._CIT_FIELDS]))
            return self.get_citation(cid)  # type: ignore[return-value]

    def get_citation(self, citation_id: str) -> dict[str, Any] | None:
        with self._lock:
            cit = _row(self._conn.execute(
                "SELECT * FROM saved_citations WHERE citation_id = ?", (citation_id,)).fetchone())
            if cit is None:
                return None
            try:
                cit["rights_at_save"] = json.loads(cit["rights_at_save"] or "{}")
            except (TypeError, json.JSONDecodeError):
                pass
            cit["observations"] = _rows(self._conn.execute(
                "SELECT * FROM verification_observations WHERE citation_id = ?"
                " ORDER BY observed_at", (citation_id,)))
            return cit

    def list_citations(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            ids = [r["citation_id"] for r in self._conn.execute(
                "SELECT c.citation_id FROM saved_citations c JOIN saved_documents d"
                " ON d.saved_document_id = c.saved_document_id WHERE d.project_id = ?"
                " ORDER BY c.saved_at DESC", (project_id,))]
            return [self.get_citation(i) for i in ids]  # type: ignore[misc]

    def delete_citation(self, citation_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM saved_citations WHERE citation_id = ?", (citation_id,))
            return cur.rowcount > 0

    def add_verification_observation(self, citation_id: str, status: str,
                                     detail: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._conn:
            oid = new_id()
            ts = now_iso()
            self._conn.execute(
                "INSERT INTO verification_observations (observation_id, citation_id, status, detail, observed_at)"
                " VALUES (?, ?, ?, ?, ?)", (oid, citation_id, status, _json(detail), ts))
            self._conn.execute(
                "UPDATE saved_citations SET quotation_verification_status = ?, verified_at = ?"
                " WHERE citation_id = ?", (status, ts, citation_id))
            return {"observation_id": oid, "citation_id": citation_id,
                    "status": status, "detail": detail, "observed_at": ts}

    # -- rights observations ---------------------------------------------------
    def add_rights_observation(self, saved_document_id: str, statement: str | None,
                               category: str | None, source: str,
                               change_status: str) -> dict[str, Any]:
        # The trust column is written HERE, by this server, at
        # insert time (schema v4): only this server's own live
        # sources are server_observed. Rows arriving any other
        # way (import files write their own rows as claims;
        # restored rows are rewritten by the restore downgrade)
        # can never acquire this marker retroactively.
        trust = ("server_observed" if source in _policy.SERVER_SOURCES
                 else "restored_claim" if source in ("restored_backup", "restored_claim")
                 else "imported_claim")
        with self._lock, self._conn:
            oid = new_id()
            ts = now_iso()
            seq = self._next_rights_seq()
            self._conn.execute(
                "INSERT INTO rights_observations (observation_id, saved_document_id, statement,"
                " category, source, observed_at, change_status, trust, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, saved_document_id, statement, category, source, ts, change_status, trust, seq))
            return {"observation_id": oid, "saved_document_id": saved_document_id,
                    "statement": statement, "category": category, "source": source,
                    "observed_at": ts, "change_status": change_status, "trust": trust,
                    "seq": seq}

    def list_rights_observations(self, saved_document_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return _rows(self._conn.execute(
                "SELECT * FROM rights_observations WHERE saved_document_id = ?"
                " ORDER BY COALESCE(seq, 0), observed_at, observation_id",
                (saved_document_id,)))

    def latest_rights_observation(self, saved_document_id: str) -> dict[str, Any] | None:
        """The CURRENT rights observation (section 11): the
        greatest monotonic seq wins - insertion order, not the
        second-precision timestamp or a random UUID. Fail-closed:
        when the two newest observations share the same
        observed_at with different categories and the newest is
        not a server observation, the more restrictive one is
        current (a permission never wins a same-timestamp tie
        against a restriction it cannot outrank)."""
        with self._lock:
            rows = _rows(self._conn.execute(
                "SELECT * FROM rights_observations WHERE saved_document_id = ?"
                " ORDER BY COALESCE(seq, 0) DESC, observed_at DESC,"
                " observation_id DESC LIMIT 2",
                (saved_document_id,)))
            if not rows:
                return None
            top = rows[0]
            if len(rows) == 2:
                other = rows[1]
                if other["observed_at"] == top["observed_at"] \
                        and other.get("category") != top.get("category") \
                        and top.get("trust") != "server_observed":
                    restrictive = _RESTRICTIVE_RIGHTS_CATEGORIES
                    if top.get("category") not in restrictive \
                            and other.get("category") in restrictive:
                        return other
            return top

    def update_citation_excerpt(self, citation_id: str, excerpt: str) -> None:
        """Store an excerpt text for an existing citation. Used
        ONLY by re-verification re-admission (b8 section 2): the
        text comes from a fresh server-side fetch whose slice
        hash matched the stored reference hash, never from a
        client or a file."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT page_id FROM saved_citations WHERE citation_id = ?",
                (citation_id,)).fetchone()
            if row is None:
                raise KeyError(citation_id)
            self._conn.execute(
                "UPDATE saved_citations SET original_excerpt = ?,"
                " excerpt_omitted_reason = NULL, search_text = ?"
                " WHERE citation_id = ?",
                (excerpt, search_text(excerpt, row["page_id"]), citation_id))

    def apply_restore_trust_downgrade(self) -> dict[str, int]:
        """Trust downgrade applied to EVERY restored database
        (b8 section 2; final review section 8): structural
        validation cannot prove a backup file is authentic, so
        verification states become restored_unverified (prior
        values preserved as an observation), all document
        rights become claims, and EVERY pre-existing rights
        observation is rewritten to trust=restored_claim - its
        original source string is preserved as history but can
        no longer establish trust, so a forged source="reverify"
        row inside a restored file grants nothing. Only
        observations this server writes AFTER the restore can
        be server_observed. Stored excerpt texts are kept in
        the database but are withheld from views and exports by
        the trust-aware policy."""
        ts = now_iso()
        downgraded = 0
        with self._lock, self._conn:
            observations_downgraded = self._conn.execute(
                "UPDATE rights_observations SET trust = 'restored_claim'"
            ).rowcount
            artefacts_downgraded = self._conn.execute(
                "UPDATE research_artefacts SET trust = 'restored_unverified'"
                " WHERE trust = 'server_generated'").rowcount
            rows = self._conn.execute(
                "SELECT citation_id, quotation_verification_status,"
                " page_mapping_status, image_verification_status, verified_at"
                " FROM saved_citations").fetchall()
            for row in rows:
                keep = {"imported_unverified", "restored_unverified",
                        "user_entered_unverified"}
                if row["quotation_verification_status"] in keep \
                        and row["page_mapping_status"] != "verified" \
                        and row["verified_at"] is None:
                    continue
                self._conn.execute(
                    "INSERT INTO verification_observations (observation_id,"
                    " citation_id, status, detail, observed_at) VALUES (?, ?,"
                    " 'restored_downgrade', ?, ?)",
                    (new_id(), row["citation_id"], json.dumps({
                        "claimed_status": row["quotation_verification_status"],
                        "claimed_mapping": row["page_mapping_status"],
                        "claimed_image_status": row["image_verification_status"],
                        "claimed_verified_at": row["verified_at"],
                        "restored_at": ts}, ensure_ascii=False), ts))
                self._conn.execute(
                    "UPDATE saved_citations SET"
                    " quotation_verification_status = 'restored_unverified',"
                    " page_mapping_status = 'restored_unverified',"
                    " image_verification_status = 'restored_unverified',"
                    " verified_at = NULL WHERE citation_id = ?",
                    (row["citation_id"],))
                downgraded += 1
            docs = self._conn.execute(
                "SELECT saved_document_id, rights_snapshot FROM saved_documents"
            ).fetchall()
            for doc in docs:
                try:
                    snapshot = json.loads(doc["rights_snapshot"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    snapshot = {}
                statement = snapshot.get("statement") if isinstance(snapshot, dict) else None
                self._conn.execute(
                    "INSERT INTO rights_observations (observation_id,"
                    " saved_document_id, statement, category, source,"
                    " observed_at, change_status, trust) VALUES (?, ?, ?, ?,"
                    " 'restored_backup', ?, 'trust_downgraded', 'restored_claim')",
                    (new_id(), doc["saved_document_id"], statement,
                     _policy.classify_rights(statement), ts))
            self._conn.execute(
                "UPDATE saved_documents SET rights_trust = 'restored_claim'")
            self._backfill_rights_seq_locked()
        return {"citations_downgraded": downgraded,
                "documents_marked": len(docs),
                "rights_observations_downgraded": observations_downgraded}

    # -- delete previews -----------------------------------------------------
    def document_related_counts(self, saved_document_id: str) -> dict[str, int]:
        """What deleting this document would affect (final
        review section 25). Notes are NOT deleted: their link
        is cleared (ON DELETE SET NULL) so the researcher's
        own writing survives."""
        with self._lock:
            q = lambda sql, args: int(self._conn.execute(sql, args).fetchone()[0])
            comparisons = 0
            for row in self._conn.execute("SELECT saved_document_ids FROM saved_comparisons"):
                try:
                    if saved_document_id in json.loads(row["saved_document_ids"] or "[]"):
                        comparisons += 1
                except json.JSONDecodeError:
                    pass
            return {
                "citations_deleted": q(
                    "SELECT COUNT(*) FROM saved_citations WHERE saved_document_id = ?",
                    (saved_document_id,)),
                "notes_unlinked": q(
                    "SELECT COUNT(*) FROM research_notes WHERE saved_document_id = ?",
                    (saved_document_id,)),
                "collection_memberships_removed": q(
                    "SELECT COUNT(*) FROM collection_documents WHERE saved_document_id = ?",
                    (saved_document_id,)),
                "comparisons_kept_as_history": comparisons,
                "rights_observations_deleted": q(
                    "SELECT COUNT(*) FROM rights_observations WHERE saved_document_id = ?",
                    (saved_document_id,)),
            }

    def citation_related_counts(self, citation_id: str) -> dict[str, int]:
        with self._lock:
            q = lambda sql, args: int(self._conn.execute(sql, args).fetchone()[0])
            return {
                "notes_unlinked": q(
                    "SELECT COUNT(*) FROM research_notes WHERE citation_id = ?",
                    (citation_id,)),
                "verification_observations_deleted": q(
                    "SELECT COUNT(*) FROM verification_observations WHERE citation_id = ?",
                    (citation_id,)),
            }

    # -- consistent export bundle ---------------------------------------------
    def export_bundle(self, project_id: str) -> dict[str, Any]:
        """All reads for one project export under a single lock
        acquisition, so the export is one consistent snapshot
        even while other requests write (final review 26)."""
        with self._lock:
            project = self.get_project(project_id)
            if project is None:
                raise KeyError(project_id)
            documents = self.list_documents(project_id)
            return {
                "project": project,
                "documents": documents,
                "citations": self.list_citations(project_id),
                "notes": self.list_notes(project_id),
                "history": self.list_history(project_id),
                "comparisons": self.list_comparisons(project_id),
                "collections": self.list_collections(project_id),
                "collection_members": {
                    c["collection_id"]: [d["saved_document_id"] for d in
                                         self.list_documents(
                                             project_id, collection_id=c["collection_id"])]
                    for c in self.list_collections(project_id)},
                "artefacts": self.list_artefact_rows(project_id),
                "rights_observations": {
                    d["saved_document_id"]: self.list_rights_observations(d["saved_document_id"])
                    for d in documents},
            }

    # -- notes -----------------------------------------------------------------
    # -- research artefacts (schema v5, b11 stage 0) -------------------
    # Artefacts live in their OWN table. The trust column is set
    # only by server-side code paths in this module's callers:
    # save via save_artefact_row (server), import via
    # import_artefact_row (always imported_unverified). Plain
    # notes can never become trusted artefacts, and a payload
    # hash is never used as proof of origin.
    def save_artefact_row(self, project_id: str, kind: str, title: str,
                          payload_json: str, *, trust: str,
                          provenance: str, operation_id: str = "",
                          algorithm_version: str = "",
                          model_json: str = "{}") -> dict[str, Any]:
        if trust not in ("server_generated", "imported_unverified",
                         "restored_unverified"):
            raise ValueError(f"invalid artefact trust: {trust}")
        aid = "art_" + uuid.uuid4().hex[:20]
        ts = now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO research_artefacts (artefact_id, project_id,"
                " kind, title, payload, trust, provenance, operation_id,"
                " algorithm_version, model, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, project_id, kind, title, payload_json, trust,
                 provenance, operation_id, algorithm_version, model_json, ts))
        return {"artefact_id": aid, "project_id": project_id, "kind": kind,
                "title": title, "trust": trust, "created_at": ts}

    def list_artefact_rows(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM research_artefacts WHERE project_id = ?"
                " ORDER BY created_at, artefact_id", (project_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for key in ("payload", "model"):
                if isinstance(d.get(key), str):
                    try:
                        d[key] = json.loads(d[key])
                    except (ValueError, TypeError):
                        d[key] = {}
            out.append(d)
        return out

    def save_note(self, project_id: str, content: str, *, title: str = "",
                  saved_document_id: str | None = None,
                  citation_id: str | None = None,
                  note_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self.get_project(project_id) is None:
                raise KeyError(project_id)
            # Cross-project integrity (final review section 9):
            # a foreign key proves existence, not membership.
            if saved_document_id is not None:
                doc = self.get_document(saved_document_id)
                if doc is None:
                    raise KeyError(saved_document_id)
                if doc["project_id"] != project_id:
                    raise ValueError("document belongs to another project")
            if citation_id is not None:
                cit = self.get_citation(citation_id)
                if cit is None:
                    raise KeyError(citation_id)
                cit_doc = self.get_document(cit["saved_document_id"])
                if cit_doc is None or cit_doc["project_id"] != project_id:
                    raise ValueError("citation belongs to another project")
                if saved_document_id is not None \
                        and cit["saved_document_id"] != saved_document_id:
                    raise ValueError("citation belongs to a different document")
            ts = now_iso()
            with self._conn:
                if note_id:
                    self._conn.execute(
                        "UPDATE research_notes SET title = ?, content = ?, updated_at = ?,"
                        " search_text = ?, saved_document_id = ?, citation_id = ?"
                        " WHERE note_id = ? AND project_id = ?",
                        (title, content, ts, search_text(title, content),
                         saved_document_id, citation_id, note_id, project_id))
                    nid = note_id
                else:
                    nid = new_id()
                    self._conn.execute(
                        "INSERT INTO research_notes (note_id, project_id, saved_document_id, citation_id,"
                        " title, content, created_at, updated_at, search_text)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (nid, project_id, saved_document_id, citation_id, title, content,
                         ts, ts, search_text(title, content)))
            return self.get_note(nid)  # type: ignore[return-value]

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        with self._lock:
            return _row(self._conn.execute(
                "SELECT * FROM research_notes WHERE note_id = ?", (note_id,)).fetchone())

    def list_notes(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return _rows(self._conn.execute(
                "SELECT * FROM research_notes WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,)))

    def delete_note(self, note_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM research_notes WHERE note_id = ?", (note_id,))
            return cur.rowcount > 0

    # -- search history ---------------------------------------------------------
    def save_history(self, project_id: str, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.get_project(project_id) is None:
                raise KeyError(project_id)
            provenance = entry.get("provenance") or "server_recorded"
            if provenance not in KNOWN_HISTORY_PROVENANCE:
                raise ValueError(f"unknown history provenance: {provenance}")
            sid = new_id()
            ts = now_iso()
            with self._conn:
                self._conn.execute(
                    "INSERT INTO search_history (search_id, project_id, original_query,"
                    " search_parameters, planned_variants, executed_variants, searched_libraries,"
                    " skipped_libraries, result_summary, http_stats, search_status, created_at,"
                    " provenance)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (sid, project_id, entry.get("original_query", ""),
                     _json(entry.get("search_parameters")), _json(entry.get("planned_variants")),
                     _json(entry.get("executed_variants")), _json(entry.get("searched_libraries")),
                     _json(entry.get("skipped_libraries")), _json(entry.get("result_summary")),
                     _json(entry.get("http_stats")), entry.get("search_status", "completed"),
                     ts, provenance))
            return self.get_history(sid)  # type: ignore[return-value]

    def get_history(self, search_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = _row(self._conn.execute(
                "SELECT * FROM search_history WHERE search_id = ?", (search_id,)).fetchone())
            if row is None:
                return None
            for key in ("search_parameters", "planned_variants", "executed_variants",
                        "searched_libraries", "skipped_libraries", "result_summary", "http_stats"):
                try:
                    row[key] = json.loads(row[key])
                except (TypeError, json.JSONDecodeError):
                    pass
            return row

    def list_history(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            ids = [r["search_id"] for r in self._conn.execute(
                "SELECT search_id FROM search_history WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,))]
            return [self.get_history(i) for i in ids]  # type: ignore[misc]

    def delete_history(self, search_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM search_history WHERE search_id = ?", (search_id,))
            return cur.rowcount > 0

    # -- comparisons --------------------------------------------------------------
    def save_comparison(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.get_project(project_id) is None:
                raise KeyError(project_id)
            for doc_id in fields.get("saved_document_ids") or []:
                doc = self.get_document(doc_id)
                if doc is None:
                    raise KeyError(doc_id)
                if doc["project_id"] != project_id:
                    raise ValueError("comparison document belongs to another project")
            cid = new_id()
            with self._conn:
                self._conn.execute(
                    "INSERT INTO saved_comparisons (comparison_id, project_id, title,"
                    " saved_document_ids, comparison_aspects, original_excerpts, lexical_overlap,"
                    " dictionary_concept_overlap, shared_by_all, shared_by_some, semantic_status,"
                    " insufficient_evidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (cid, project_id, fields.get("title", ""),
                     _json(fields.get("saved_document_ids")), _json(fields.get("comparison_aspects")),
                     _json(fields.get("original_excerpts")), _json(fields.get("lexical_overlap")),
                     _json(fields.get("dictionary_concept_overlap")), _json(fields.get("shared_by_all")),
                     _json(fields.get("shared_by_some")),
                     fields.get("semantic_status", "not_checked"),
                     _json(fields.get("insufficient_evidence")), now_iso()))
            return self.get_comparison(cid)  # type: ignore[return-value]

    def get_comparison(self, comparison_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = _row(self._conn.execute(
                "SELECT * FROM saved_comparisons WHERE comparison_id = ?", (comparison_id,)).fetchone())
            if row is None:
                return None
            for key in ("saved_document_ids", "comparison_aspects", "original_excerpts",
                        "lexical_overlap", "dictionary_concept_overlap", "shared_by_all",
                        "shared_by_some", "insufficient_evidence"):
                try:
                    row[key] = json.loads(row[key])
                except (TypeError, json.JSONDecodeError):
                    pass
            return row

    def list_comparisons(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            ids = [r["comparison_id"] for r in self._conn.execute(
                "SELECT comparison_id FROM saved_comparisons WHERE project_id = ?"
                " ORDER BY created_at DESC", (project_id,))]
            return [self.get_comparison(i) for i in ids]  # type: ignore[misc]

    def delete_comparison(self, comparison_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM saved_comparisons WHERE comparison_id = ?", (comparison_id,))
            return cur.rowcount > 0

    # -- local search ----------------------------------------------------------------
    def local_search(self, project_id: str, query: str, limit: int = 50) -> dict[str, Any]:
        """Substring search over the normalised search_text index.
        Parameterised LIKE with escaping: user input is never
        interpreted as SQL or as a pattern language."""
        needle = search_text(query).strip()
        if not needle:
            return {"documents": [], "notes": [], "citations": []}
        pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._lock:
            docs = [r["saved_document_id"] for r in self._conn.execute(
                "SELECT saved_document_id FROM saved_documents WHERE project_id = ?"
                " AND search_text LIKE ? ESCAPE '\\' ORDER BY saved_at DESC LIMIT ?",
                (project_id, pattern, limit))]
            notes = _rows(self._conn.execute(
                "SELECT * FROM research_notes WHERE project_id = ?"
                " AND search_text LIKE ? ESCAPE '\\' ORDER BY updated_at DESC LIMIT ?",
                (project_id, pattern, limit)))
            cits = [r["citation_id"] for r in self._conn.execute(
                "SELECT c.citation_id FROM saved_citations c JOIN saved_documents d"
                " ON d.saved_document_id = c.saved_document_id WHERE d.project_id = ?"
                " AND c.search_text LIKE ? ESCAPE '\\' ORDER BY c.saved_at DESC LIMIT ?",
                (project_id, pattern, limit))]
            return {"documents": [self.get_document(i) for i in docs],
                    "notes": notes,
                    "citations": [self.get_citation(i) for i in cits]}

    # -- backup / restore ---------------------------------------------------------------
    def backup(self, dest_path: str | Path) -> dict[str, Any]:
        """Online backup via the sqlite3 backup API (WAL-safe)."""
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._conn.backup(target)
            finally:
                target.close()
        try:
            import os
            os.chmod(dest, 0o600)
        except OSError:
            pass
        data = dest.read_bytes()
        return {"path": str(dest), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "schema_version": self.schema_version,
                "integrity": "ok", "created_at": now_iso()}

    @staticmethod
    def inspect_backup(path: str | Path) -> dict[str, Any]:
        """Read-only basic facts about a backup candidate."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            version = 0
            has = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if has:
                version = int(conn.execute(
                    "SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0)
        finally:
            conn.close()
        data = p.read_bytes()
        return {"path": str(p), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "integrity": integrity, "schema_version": version}

    # Tables and columns a genuine workspace database must
    # have (schema v1 set; v2 additions are optional here
    # because opening the store migrates them in).
    _REQUIRED_SCHEMA = {
        "schema_migrations": {"version", "applied_at"},
        "projects": {"project_id", "title", "created_at", "updated_at"},
        "saved_documents": {"saved_document_id", "project_id", "library_id",
                            "record_id", "rights_snapshot", "saved_at"},
        "saved_citations": {"citation_id", "saved_document_id", "page_id",
                            "citation_key", "quotation_verification_status",
                            "provenance", "rights_at_save", "saved_at"},
        "research_notes": {"note_id", "project_id", "content"},
        "search_history": {"search_id", "project_id", "original_query"},
        "saved_comparisons": {"comparison_id", "project_id", "semantic_status"},
        "tags": {"tag_id", "name"},
        "collections": {"collection_id", "project_id", "name"},
        "rights_observations": {"observation_id", "saved_document_id"},
        "verification_observations": {"observation_id", "citation_id", "status"},
    }

    @staticmethod
    def validate_backup(path: str | Path) -> dict[str, Any]:
        """Deep validation of a restore candidate (final review
        sections 7, 8). integrity_check alone does NOT prove a
        file is one of this application's databases: required
        tables/columns, foreign-key consistency, the absence
        of unexpected schema objects (triggers/views), the
        schema version range, and the value vocabularies for
        verification state, provenance, rights categories and
        excerpt length are all checked. A checksum computed
        from the uploaded file itself proves nothing about
        authenticity and is reported as a fact only."""
        p = Path(path)
        problems: list[str] = []
        integrity = "unreadable"
        version = 0
        if not p.exists():
            raise FileNotFoundError(str(p))
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                problems.append(f"integrity_check: {integrity}")
            fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_violations:
                problems.append(f"foreign_key_check: {len(fk_violations)} violation(s)")
            objects = conn.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for obj in objects:
                if obj["type"] not in ("table", "index"):
                    problems.append(f"unexpected schema object: {obj['type']} {obj['name']}")
            tables = {o["name"] for o in objects if o["type"] == "table"}
            for table, columns in WorkspaceStore._REQUIRED_SCHEMA.items():
                if table not in tables:
                    problems.append(f"missing table: {table}")
                    continue
                actual = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                missing = columns - actual
                if missing:
                    problems.append(f"table {table} missing columns: {sorted(missing)}")
            version = 0
            if "schema_migrations" in tables:
                row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
                version = int(row["v"] or 0)
            if version < 1 or version > SCHEMA_VERSION:
                problems.append(f"schema version {version} outside supported range")
            if version >= 2:
                # A database claiming v2 must actually carry
                # the v2 columns; a v1-shaped file labelled v2
                # would break after the swap.
                for table, columns in (("saved_documents", {"citation_key"}),
                                       ("search_history", {"provenance"})):
                    if table in tables:
                        actual = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                        if not columns <= actual:
                            problems.append(f"schema claims v{version} but {table} lacks v2 columns")
            if version >= 3 and "saved_documents" in tables:
                actual = {r["name"] for r in conn.execute("PRAGMA table_info(saved_documents)")}
                if "rights_trust" not in actual:
                    problems.append(f"schema claims v{version} but saved_documents lacks the v3 rights_trust column")
            if version >= 4 and "rights_observations" in tables:
                actual = {r["name"] for r in conn.execute("PRAGMA table_info(rights_observations)")}
                if "trust" not in actual:
                    problems.append(f"schema claims v{version} but rights_observations lacks the v4 trust column")
            if not problems:
                for row in conn.execute(
                        "SELECT quotation_verification_status AS s, provenance AS p,"
                        " rights_at_save AS r, original_excerpt AS e FROM saved_citations"):
                    if row["s"] is not None and row["s"] not in KNOWN_QUOTATION_STATUSES:
                        problems.append(f"unknown quotation status: {row['s']}")
                        break
                    if row["p"] is not None and row["p"] not in KNOWN_PROVENANCE:
                        problems.append(f"unknown citation provenance: {row['p']}")
                        break
                    if row["e"] is not None and len(row["e"]) > _policy.MAX_EXCERPT_CHARS:
                        problems.append("stored excerpt exceeds the storage limit")
                        break
                    try:
                        rights = json.loads(row["r"] or "{}")
                    except (TypeError, json.JSONDecodeError):
                        problems.append("unparsable rights_at_save")
                        break
                    if isinstance(rights, dict) and rights.get("category") is not None \
                            and rights["category"] not in _policy.CATEGORIES:
                        problems.append(f"unknown rights category: {rights['category']}")
                        break
                bad_semantic = conn.execute(
                    "SELECT COUNT(*) FROM saved_comparisons WHERE semantic_status != 'not_checked'"
                ).fetchone()[0]
                if bad_semantic:
                    problems.append("comparison semantic_status other than not_checked")
        except sqlite3.Error as exc:
            problems.append(f"not a readable SQLite database: {exc}")
        finally:
            conn.close()
        data = p.read_bytes()
        return {"path": str(p), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "integrity": integrity,
                "schema_version": version, "ok": not problems,
                "problems": problems}
