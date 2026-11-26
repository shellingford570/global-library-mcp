# Workspace database schema (b7)

Engine: SQLite via Python's standard `sqlite3`. One database
file (`workspace.db`), schema version **1**, migrations
recorded in `schema_migrations` and applied transactionally.

Connection policy (every connection): `PRAGMA foreign_keys
= ON`, `journal_mode = WAL`, `busy_timeout = 5000`,
`synchronous = NORMAL` (the standard WAL trade-off: durable
across application crashes; an OS crash can lose the last
committed transactions — accepted and documented, backups
are the mitigation). A single connection guarded by a
re-entrant lock serves the threaded web server. A database
whose schema is newer than the build is refused untouched
(`FutureSchemaError`); older schemas migrate forward only.

## Tables

- `projects` (project_id PK, title, description, created_at,
  updated_at, archived_at, schema_version)
- `saved_documents` (saved_document_id PK, project_id FK
  CASCADE, library_id, record_id, candidate work/author ids
  + resolution_status, bibliographic snapshot columns,
  identifiers JSON, rights_snapshot JSON, discovery_reason,
  retrieved_at, saved_at, updated_at, search_text;
  UNIQUE(project_id, library_id, record_id))
- `saved_citations` (citation_id PK, saved_document_id FK
  CASCADE, page_id, citation_key, original_excerpt NULL when
  the rights policy withheld it + excerpt_omitted_reason,
  excerpt_start/end, excerpt_hash, ocr_source, ocr_file,
  source_url, image_url, canvas_id, printed_page,
  digital_frame, page_mapping_status,
  image_verification_status, quotation_verification_status,
  provenance, user_annotation, rights_at_save JSON,
  retrieved_at, verified_at, saved_at, search_text)
- `research_notes` (note_id PK, project_id FK CASCADE,
  saved_document_id/citation_id FK CASCADE nullable, title,
  content, created_at, updated_at, search_text)
- `search_history` (search_id PK, project_id FK CASCADE,
  original_query, search_parameters JSON, planned/executed
  variants JSON, searched/skipped libraries JSON,
  result_summary JSON, http_stats JSON, search_status,
  created_at)
- `saved_comparisons` (comparison_id PK, project_id FK
  CASCADE, title, saved_document_ids JSON,
  comparison_aspects JSON, original_excerpts JSON,
  lexical_overlap JSON, dictionary_concept_overlap JSON,
  shared_by_all/some JSON, semantic_status, 
  insufficient_evidence JSON, created_at)
- `tags` (tag_id PK, name UNIQUE), `project_tags`,
  `document_tags` (join tables, composite PKs)
- `collections` (collection_id PK, project_id FK CASCADE,
  name; UNIQUE(project_id, name)), `collection_documents`
- `rights_observations` (per-document rights history)
- `verification_observations` (per-citation reverify history)
- `schema_migrations` (version PK, applied_at)

All timestamps are UTC ISO-8601 (`Z`). Structured payloads
are JSON text; every queryable field is a real column.

## Local search

FTS5 was evaluated and not adopted for b7: its default
tokeniser segments Japanese/Chinese text poorly, which
would silently degrade exactly the multilingual use case.
Instead, each searchable row carries a `search_text` column
(NFKC + casefold concatenation, an index — originals are
never rewritten) queried with parameterised
`LIKE ... ESCAPE '\'` substring matching. User input is
never interpreted as SQL or as a pattern language. At the
large evaluation scale (10k documents) this answers in
single-digit milliseconds (see b7-performance-evaluation).
A trigram FTS5 index remains a future option.

## Added fields beyond the b6 design doc

- `saved_documents.discovery_reason` — why the record was
  found (matched variant / handoff), needed to audit
  discovery later.
- `saved_citations.excerpt_omitted_reason`, `provenance`,
  `user_annotation` — the policy outcome and the
  system/user/imported distinction the brief requires.
- `search_text` columns — the local-search index above.
- `rights_observations.change_status` — separates the
  observation itself from its change classification.

## Schema v2 (v1.0.0b7 final review)

- `saved_documents.citation_key`: the document's stored,
  stable citation key (backfilled on migration).
- `search_history.provenance`: `server_recorded` or
  `user_entered`.
- `research_notes.saved_document_id` / `citation_id` now
  use `ON DELETE SET NULL`: deleting a document or
  citation unlinks the researcher's notes instead of
  deleting them.
- `synchronous = FULL` (durability over write latency).
- Migration from v1 takes a `0600` pre-migration backup
  (`<db>.pre-migration-v1.bak`) before changing anything;
  databases from a future schema are refused, never
  reinitialised.
