# b7 Final Review — findings, reproduction, fixes, verification

This document records the external final review of PR #18
(v1.0.0b7 candidate, head `3f414af`), the reproduction of every
finding against that code, the fixes applied on
`feat/research-workspace-b7`, and the post-fix verification.
Suite counts and CI results are stated in the release record;
nothing in this document upgrades a fixture result into a live
result or a storage-level result into an HTTP result.

## 1. Findings and reproduction (pre-fix)

All reproductions ran against `3f414af` with a scratch script
driving the real store and web API:

- **R3 rights fail-open (§4).** `classify_rights` returned
  `public_domain` for "not in the public domain", "not released
  under CC0", "public domain status has not been established"
  and "CC0 does not apply to this item"; `CC BY-SA-NC-ND 4.0`
  fell back to `cc_by`; NoC-NC permitted excerpt storage,
  contradicting the candidate report.
- **R1 cross-document citation (§2).** A genuine page token
  for record A saved a `verified_against_fetched_ocr` citation
  onto record B of the same project. Only project membership
  was checked.
- **R2 rights-token reuse (§3).** An unknown-rights document
  stored its excerpt when handed a CC-BY `document_token` of a
  different document.
- **R13 truncation/hash mismatch (§13).** A 2,500-character
  excerpt was stored truncated to 2,000 characters while
  `excerpt_end` and the SHA-256 described the untruncated text.
- **R5 import bypass (§5).** JSON import kept a 5,000-character
  excerpt for an unknown-rights document, kept
  `page_mapping_status: verified` and a claimed `verified_at`;
  comparison excerpts were stored raw.
- **R9 cross-project references (§9).** A note in project B
  linked to project A's document was accepted.

## 2. Fixes

### Rights classification and storage policy (§§3, 4, 6)

- `workspace/policy.py` rewritten fail-closed: structural CC
  URI/name parsing (exact licence combinations only; an
  unrecognised CC combination is `unknown`, never `cc_by`),
  RightsStatements.org URI mapping, a negation veto, and
  contradictions resolved to `unknown`/`restricted`.
  Metadata-only licences are `unknown` for OCR text.
- NoC-NC is a restriction statement, not a grant: excerpt
  storage is **not** permitted for it. NC licence categories
  (CC BY-NC, CC BY-NC-SA) keep excerpt storage permitted with
  a recorded purpose caveat: the system cannot verify the
  user's purpose, so non-commercial use is the user's
  responsibility. The 2,000-character cap is a system limit,
  not a legal quotation allowance. The system does not
  guarantee legal compliance.
- `effective_decision(save_statement, latest_statement)`:
  display, local search and every export re-gate excerpts
  against BOTH the save-time rights and the latest rights
  observation. The stored row is never rewritten; a later,
  more restrictive observation withholds the text in views
  and exports and records an omission with its reason.

### Citation identity (§2)

- Page identity comes from the snapshot payload's own fields
  (`record_id`; NDL's `book_pid` — live-verified 2026-11-26:
  the NDL page payload carries `book_pid` and no `record_id`).
  Page-id strings are never split to guess a document.
- A citation save requires the snapshot's library_id and
  record_id to match the target saved document exactly;
  a genuine token spent on another document, another
  library, another edition or another volume is rejected
  (400). A snapshot that cannot name its document is
  rejected (422).
- The `document_token` rights fallback is honoured only when
  that snapshot is a document snapshot for the identical
  library and record.

### Excerpt integrity (§13)

Option A adopted: excerpts over the 2,000-character storage
limit are rejected (422) with a request to shorten the
selection, for snapshot and manual citations alike. Stored
text, offsets and SHA-256 therefore always describe the same
string. Reference-only citations (no stored text) never
display a text-verification state.

### Re-verification (§14)

Re-verification keeps a per-check ledger (page fetch, page
identity, OCR presence, excerpt presence, excerpt hash,
image reachability via `verify_page`, rights, metadata).
`unchanged` is returned only when identity, excerpt,
image and metadata checks all ran and passed. A
reference-only citation returns `partial_verification`
with `excerpt: not_checked_reference_only`; failures map to
`source_unavailable` / `access_restricted` /
`mapping_unverified` / `quotation_not_found` /
`rights_changed` / `metadata_changed` as applicable.

### Import, export, migration (§§5, 15–18, 26)

- Import applies the same storage policy and length cap to
  citation and comparison excerpts; omissions are counted
  and reported. Imported rights are recorded as
  `imported_claim` with their source; verification status,
  page-mapping status, image status are all downgraded to
  `imported_unverified`, `verified_at` is cleared, and the
  claimed values are preserved as a historical observation.
  Rights and verification observation histories are exported
  and restored as history, never as current verification.
  Original timestamps are preserved; migration time is
  recorded separately.
- **Interpretation recorded:** an imported excerpt is kept
  when the file's own stated rights pass the same storage
  policy (the policy is applied to the claim as data; the
  claim is never treated as verified). Dropping every
  imported excerpt would make project migration lose the
  researcher's lawfully saved quotations, and import-time
  upstream verification is prohibited (no automatic external
  fetches during import). Current-rights gating still
  applies to imported material on display and export.
- Per-type ID maps (documents, citations, notes, …); every
  reference is pre-validated — an unknown reference rejects
  the whole file with a single-transaction rollback; nothing
  is silently dropped or nulled. Comparison excerpts are
  remapped to the new document IDs.
- Strict JSON parsing: duplicate keys and non-finite numbers
  are rejected. Limits aligned between export and import
  (64 MB, 250,000 JSON objects, 60,000 research records);
  exports that exceed the import limits carry
  `export_warnings` naming the SQLite backup as the migration
  path for very large projects.
- Exports read one consistent store snapshot
  (`export_bundle` under the store lock).

### Backup and restore (§§7, 8, 11)

- Backup creation is an explicit POST returning an ID;
  downloads serve only an existing backup and never create
  one. At most 10 backups are kept; files are 0600.
- Restore requires `?confirm=1`. The candidate passes deep
  validation (`validate_backup`): integrity check, foreign
  keys, required tables/columns (including the schema-v2
  columns when the candidate claims v2), no unexpected
  triggers/views, schema version range, and the value
  vocabularies for quotation status, provenance, history
  provenance, rights categories, excerpt length and
  comparison `semantic_status`. A pre-restore backup is
  taken, the API is quiesced (503) during the swap, the
  swapped database is opened and checked, and any failure
  rolls back automatically to the pre-restore backup.
- Trust boundary: a checksum computed from an uploaded file
  proves nothing about its authenticity and is reported as a
  fact only. An uploaded database is never auto-certified as
  "one of my backups"; verification states inside a restored
  database are historical records of that database, subject
  to the same current-rights gating.

### Cross-project integrity (§9)

`save_note`, `collection_add` and `save_comparison` validate
project membership of every referenced document/citation
inside the transaction; a note's citation must belong to the
note's document when both are given. Deleting a project
cannot touch another project's data (foreign keys plus
membership checks; tested).

### Web session security (§10) and threat model

- Each page load issues a session: an HttpOnly
  `glm_ws_session` cookie (SameSite=Strict) and that
  session's own CSRF token in a meta tag (12 h expiry).
  Reads require the session; mutations additionally require
  the session's CSRF token.
- Host is parsed strictly (exactly one Host header, no
  whitespace/controls, no bare IPv6) and its port must equal
  the server's port. Origin is checked on ALL requests
  (scheme/host/port must match; `Origin: null` rejected).
- **Threat model:** the workspace is a local, single-user
  application. It defends against other web sites driving
  the user's browser (CSRF, DNS rebinding) and against
  malformed requests. It does NOT provide authentication or
  authorisation for public-web deployment, and another
  process running as the same OS user can read the database
  file directly — file permissions (0600) are the boundary
  there. The database is not encrypted.

### Snapshots (§12)

Snapshots are deep-copied on registration (later mutation of
the source dict cannot alter them), capped per snapshot
(2 MB serialised) and in total (64 MB), TTL 2 h with lazy
expiry, and hold only the fields citation binding needs.

### History (§20)

Search history saved from a server-issued `history_token`
is `server_recorded` and built from the server's own
response. Manual entries are `user_entered`, size-capped,
status-whitelisted, and scanned recursively for
secret-looking keys (`api_key`, `token`, `password`, …),
which are rejected. The system cannot detect secrets a user
types into free-text note bodies; that is documented, not
claimed.

### Comparisons (§19)

Saving a comparison runs the real `compare_documents` and
matches excerpts from `rows[].documents[record_id]` by
(library_id, record_id) identity — never by list position.
Per-document rights gates, the 2,000-character cap and a
256 KB total cap apply; duplicate documents are rejected;
gaps are recorded in `insufficient_evidence`;
`semantic_status` stays `not_checked`.

### Exports (§§21–23)

- Citation keys are stored per document at save time
  (deterministic base key; collisions get a stable
  hash suffix from library/record identity). Stored keys
  always win at export; adding or removing documents never
  renames an existing key; keys survive JSON migration.
- Material types are classified per format: unknown types
  stay generic (BibTeX `@misc`, RIS `GEN`, CSL `document`)
  and are never forced to `book`; newspapers map to BibTeX
  misc / RIS NEWS / CSL article-newspaper. Full dates
  (year/month/day) are kept; pre-1500 years are kept; BCE
  and unparseable dates are not fabricated into years.
  Organisation authors stay CSL literal; a two-token split
  is used only for plainly personal Latin names.
- Markdown reports escape stored text (headings, links,
  images, code fences, raw HTML), print URLs only when
  https and link-safe, and carry full provenance per
  citation (record/page IDs, OCR source, citation key,
  image/landing URLs, saved/retrieved times, text-stored
  flag, current rights restriction). User notes are escaped
  the same way: the report's structure cannot be altered by
  stored content, and no external fetch is triggered.

### Durability and deletion (§§24, 25)

- `synchronous = FULL` (was NORMAL): durability of the
  researcher's data outranks the small write cost.
- The database path must not be a symlink. DB, WAL, backup
  and pre-migration files are created 0600. Schema v2
  migration takes a pre-migration backup first and refuses
  future schemas; a v1 database migrates with citation-key
  backfill.
- Notes survive document/citation deletion: the v2 schema
  uses `ON DELETE SET NULL` for the note links, so the
  researcher's own writing is unlinked, never deleted.
  Deletes report real related counts and require
  confirmation when related records are affected. Data in
  existing backups/exports is not retroactively deleted;
  the UI says so.

## 3. Tests added

- `tests/test_b7_final_review.py` (§34): citation identity
  (cross-document/cross-library/edition, missing record
  identity, oversize rejection with hash/offset agreement),
  rights-token reuse, fail-closed classification
  (negations, unknown CC combinations, NoC-NC, metadata-only
  licences), import policy/downgrade/history round-trip,
  unknown references and duplicate keys, current-rights
  gating of views/exports, restore validation (wrong-schema
  SQLite, tampered status, rollback on unopenable
  candidate, quiesce), session security (no cookie,
  wrong-port Host, `Origin: null`, foreign Origin on reads),
  backup GET-never-creates, reverify state honesty,
  citation-key stability, export types/dates, Markdown
  hardening, snapshot immutability and size cap.
  **This suite found a real bug the candidate suites
  missed:** `latest_rights_observation` passed a cursor to
  `_row()` without `fetchone()`, so any citation list after
  a rights observation raised. Fixed.
- `tests/test_b7_http_integration.py` (§28): real HTTP
  server + real WorkspaceApi + real LibraryService + real
  SQLite; only the upstream library is a fixture adapter.
  Full journey: search, materials, project, document save,
  history token, document/page fetch, citation, reverify,
  note, compare, comparison save, local search, BibTeX,
  JSON export/import, backup, restore, reopen.
- `tests/test_b7_scenarios.py` (§30): scenarios A–D over
  real HTTP (see §4).
- Playwright workspace journeys extended from 3 to 5 with
  token-independent journeys for backup create/list/
  download/delete and project rename/archive.
- CI gained a dedicated workspace job (§29): workspace
  pytest suites, a workspace-enabled server, the workspace
  journeys with a not-all-skipped assertion (JSON stats,
  at least 3 passed), and a restart persistence check.

## 4. Scenarios (§30) and live verification scope

- **A (permitted):** excerpt stored, survives a store
  reopen, reverify `unchanged`, appears in Markdown, and
  migrates through JSON export/import (as
  `imported_unverified`).
- **B (unknown rights):** reference-only citation; no text
  in the database, in JSON export or in Markdown; reverify
  reports `partial_verification` with the reference-only
  check state.
- **C (rights change):** after the fixture upstream starts
  reporting "In Copyright", reverify returns
  `rights_changed`; citation views, local search and JSON
  export withhold the text with a recorded omission; both
  rights observations remain in history; the stored row is
  unchanged.
- **D (identifier shapes):** NDL (`book_pid`, no
  `record_id` — the live-verified payload shape), IA
  (`identifier@leaf`), BSB and LoC
  (`<lccn>/<date>/ed-<n>/seq-<s>`) bind through the save
  path; a LoC edition-1 page spent on the edition-2
  document is rejected.
- **Live API (few calls, 2026-11-26):** IA page
  `onoriginofspecie1859darw@20` — library/record/page IDs
  present, OCR non-empty, mapping verified. NDL page
  `992954_10` — `book_pid` present, `record_id` absent,
  OCR non-empty, mapping verified, rights statement is the
  per-item Japanese notice (classifies `unknown`, so NDL
  excerpts stay reference-only unless the item states
  permissive rights). BSB/LoC live journeys were verified
  in b5/b6; this round re-verified their identifier shapes
  against fixtures only. Gallica remains upstream-403 from
  this network (not retried, not evaded).

## 5. Performance (§31, synthetic, this VM)

Full results: `eval/results-b7-perf-final.json`
(medians of 3 runs unless noted; restore measured at store
level as validate + swap + reopen).

| scale | projects/docs/citations/notes (DB total) | DB bytes | WAL bytes | local search warm | backup | restore |
|---|---|---|---|---|---|---|
| small | 1 / 100 / 300 / 100 | 393,216 | 4,124,152 | 0.33 ms | 1.7 ms | 5.5 ms |
| medium | 5 / 1,000 / 3,000 / 1,000 | 2,408,448 | 4,148,872 | 0.95 ms | 11.8 ms | 33.3 ms |
| large | 20 / 10,000 / 30,000 / 10,000 | 23,027,712 | 4,169,472 | 6.41 ms | 89.6 ms | 337.2 ms |

Large scale, measured project: 500 documents, 1,500
citations, 10,000 notes; exported 12,000 records; imported
500/1,500/10,000 (documents/citations/notes). Excerpt size
in the synthetic set: avg = max = 29 chars (uniform fixture
text — a property of the fixture, not of real corpora).
Cold-cache first search at large scale: 10.52 ms. Process
max RSS at large scale: 154,720 KB. Concurrent writes
(4 threads × 25 notes): 107.2 ms total at large scale;
concurrent exports (×4): 791.7 ms. BibTeX for 1,000
documents: 11.9 ms; JSON export of the measured project:
190.2 ms; JSON import: 296.9 ms (single run).
`synchronous = FULL` costs a little write latency
(save_document 1.79 ms, save_note 0.99 ms at large scale)
and is kept deliberately.

## 6. MCP and evidence regression (§§32, 33)

- `mcp_server.py` contains no workspace references; the
  workspace is reachable only through the local web API.
- Full profile: 15 tools. Research profile: 14 tools,
  `research_question` removed, every tool
  `readOnlyHint=True` (verified directly against the
  server object; stdio and Streamable HTTP transports are
  covered by the b4 suites in CI).
- Evidence admission, temporal anchoring, numeric binding,
  page kind, relevance gate, citation/claim verification,
  `insufficient_evidence` and `answer_withheld` are
  unchanged; being saved in a workspace is never treated
  as evidence of correctness, and user notes are never
  treated as sources.

## 7. Unresolved and out of scope (unchanged by this round)

- Zotero real-application import: NOT performed (BibTeX
  parse-checked with bibtexparser only). RIS/CSL are
  validated structurally in tests, not in a reference
  manager.
- Docker workspace mode: not verified (the Docker job runs
  the search-only server).
- macOS/Windows user-data paths: implemented per platform
  conventions, not executed on those systems.
- The database is not encrypted; no public-web
  authentication/authorisation exists.
- P2 items (timeline, relation graph, progress rollups,
  bulk operations, extra citation styles) remain
  unimplemented.
- The b6 ranking limitation (Kant's *Kritik der reinen
  Vernunft* not reaching top ranks) is unchanged.
