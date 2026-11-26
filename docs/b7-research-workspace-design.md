# b7 design: Research Workspace & Citation Management

Status (2026-11-26): IMPLEMENTED in v1.0.0b7 — see
docs/b7-research-workspace.md for the implementation record
and the points where the implementation refines this
design. The text below is the original b6-era design,
kept for reference. Local-first throughout; no cloud sync,
no writes to external services.

## Entities

### ResearchProject
- project_id (uuid)
- title, description
- created_at, updated_at
- tags (list of strings)

### SavedDocument
A bibliographic record the researcher chose to keep. The
bibliographic fields are a snapshot of the upstream record
at save time; the upstream record itself is not copied
beyond metadata.
- saved_document_id, project_id
- library_id, record_id
- work_id_candidate (nullable; candidate-grade only, with
  the resolution status that produced it)
- title, author, publication_date, edition, language
  (raw + normalised)
- holding_institution, landing_url
- rights (statement + source, as reported at save time)
- retrieved_at

### SavedCitation
A page-level citation: the unit a researcher actually
quotes.
- citation_id, saved_document_id
- page_id, citation_key
- original_excerpt (the quoted passage, verbatim)
- ocr_source (adapter + endpoint kind that produced it)
- image_url
- mapping_status (page identity verification state at save)
- verification_status
- rights_at_save
- retrieved_at
- note (researcher's own annotation, kept distinct)

### ResearchNote
- note_id, project_id
- document_id / citation_id (nullable links)
- content (the researcher's writing — never mixed with OCR)
- created_at, updated_at

### SearchHistory
- search_id, project_id
- original_query
- search_parameters (mode, filters, expansion toggles,
  libraries)
- executed_variants (only executed ones, with libraries)
- searched_libraries (queried / with-results / failed /
  skipped, as reported)
- result_summary (counts, top record ids)
- created_at

### SavedComparison
- comparison_id, project_id
- document_ids (2-4 saved documents)
- comparison_aspects
- excerpts (per document, verbatim, with page ids)
- lexical_overlap, dictionary_concept_overlap
  (shared_by_all vs shared_by_some)
- semantic_status (not_checked unless a future approved
  step changes it)
- created_at

## Provenance separation

Five kinds of content are stored in distinct fields and
rendered distinctly in any future UI/export:

1. researcher writing (notes, annotations),
2. system-fetched OCR (excerpts, with ocr_source),
3. AI inference (none in the workspace core; any future
   addition must be labelled and separately stored),
4. bibliographic metadata (upstream snapshots),
5. verification results (mapping/verification states with
   their check time).

## Rights handling

- Bibliographic metadata: storable without restriction
  concerns beyond upstream terms (several sources are CC0;
  the snapshot keeps its source).
- OCR full text: NOT bulk-stored by default. SavedCitation
  stores the excerpt the researcher quoted plus pointers
  (page id, image URL, landing URL). Any fuller retention
  is a per-record decision gated on that record's rights
  statement; unknown rights default to excerpt-only.
- rights_at_save is immutable history. A later re-check
  appends a new observation (checked_at + current state);
  exports state both when they differ.

## Storage comparison (local-first)

| Criterion | SQLite (single file) | Local JSON files | Notes |
|---|---|---|---|
| Integrity | Transactions, foreign keys, constraints | Manual; partial-write risk | SQLite clearly ahead |
| Migration | Schema version + migrations | Ad-hoc per-file upgrades | SQLite ahead |
| Backup | Copy one file (or .backup) | Copy a directory | Both workable |
| Crash durability | WAL/journal, atomic commits | Weak without careful fsync discipline | SQLite ahead |
| Concurrency | One writer, many readers — enough for a local single-user workspace | File locking hazards | SQLite ahead |
| Deletion | Row deletes + VACUUM; per-project purge is explicit | File removal is simple | JSON simpler, SQLite adequate |
| Portability | File is portable; needs a SQLite reader | Human-readable anywhere | JSON ahead for inspection |
| Search performance | Indexes + FTS5 for notes/excerpts | Linear scans | SQLite ahead |
| Rights management | Per-row rights fields + queries (e.g. list all excerpt-only records) | Grep-able but unstructured | SQLite ahead |
| Extensibility | Schema evolution is a known discipline | Free-form drift risk | SQLite ahead |

Recommendation: SQLite (single file in the user's data
directory) as the primary store, with full project
export/import in JSON (and BibTeX/RIS/CSL JSON/Markdown
for citations) so the data is never locked in. This is a
design recommendation for the b7 brief, not an
implementation decision taken here.

## Out of scope for b7 planning

Cloud sync, multi-user sharing, Zotero writes, external
AI over saved corpora, public deployment. Each needs its
own approval and design pass.
