# Workspace schema and migrations (b7)

- Engine: SQLite via the Python standard library only.
- Current schema version: **1** (`SCHEMA_VERSION` in
  `workspace/store.py`).
- Migrations are an ordered list applied inside a single
  transaction each; every applied migration is recorded in
  the `schema_migrations` table with its version and
  timestamp (UTC, ISO-8601 `Z`).
- On open, the store compares the database's recorded
  schema version with the build's:
  - older → pending migrations are applied in order;
  - equal → no change;
  - **newer (a database written by a future version) → the
    store refuses to open it (`FutureSchemaError`) and does
    not modify, downgrade or reinitialise it.** Restore a
    backup taken with a compatible version, or use the
    newer build.
- Pragmas per connection: `foreign_keys = ON`,
  `journal_mode = WAL`, `busy_timeout = 5000`,
  `synchronous = NORMAL`. WAL is chosen for concurrent
  read/write behaviour of the local web server; NORMAL is
  the documented WAL pairing (a power loss can lose the
  last committed transactions but cannot corrupt the
  database). Because of WAL, never copy the bare `.db`
  file as a backup — use the built-in backup, which uses
  SQLite's online backup API (see
  docs/workspace-backup-restore.md).
- The database file is created with mode 0600 and its
  directory with 0700.
- Table-by-table detail: docs/workspace-database-schema.md.

## v1 → v2 (v1.0.0b7 final review)

Adds `saved_documents.citation_key` (with backfill),
`search_history.provenance`, and rebuilds `research_notes`
with `ON DELETE SET NULL` links. A 0600 pre-migration
backup (`<db>.pre-migration-v1.bak`) is written before any
change; a failed migration leaves the original database
and its backup in place. Verified by the migration tests
in `tests/test_b7_final_review.py` and the store smoke
checks recorded in `docs/b7-final-review.md`.
