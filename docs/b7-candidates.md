# b7: Research Workspace & Citation Management (plan only — not started)

Roadmap position (provisional): b7 Research Workspace &
Citation Management; b8 Global Coverage II; b9 External MCP
Readiness; AI Experimental separate; then v1.0.0.

Direction: from a one-shot library search service to a
research environment where a researcher accumulates,
organises and reuses materials, originals, citations,
comparisons and notes across sessions. Local-first:
everything below is designed for local storage; cloud sync
and writing into external services (Zotero) are plan-only
and are NOT part of any b7 implementation step without
separate approval.

## Candidate features

- Research projects; per-project search history.
- Saved documents (bookmarks) and collections, organised
  by theme / period / author, with tags and folders.
- Saved citations: original excerpt + page identity + image
  URL + OCR source + rights at save time.
- Research notes attached to projects, documents, citations.
- Saved comparisons (lexical / dictionary-concept overlap;
  semantic status stays explicit).
- Re-search of saved documents (has the upstream record
  changed? is the OCR still available?).
- Exports: BibTeX, RIS, CSL JSON, Markdown.
- Local backup; project import/export.
- Zotero compatibility as an export format decision only —
  no writes to a Zotero library in b7 planning.

## Design

Entity model, storage comparison (SQLite vs local JSON vs
other lightweight local stores) and the rights-handling
rules are specified in docs/b7-research-workspace-design.md.

Key separations the design keeps from day one:

- The researcher's own writing (notes) vs system-fetched
  OCR vs AI inference vs bibliographic metadata vs
  verification results — stored and displayed distinctly.
- Bibliographic metadata (freely storable) vs copyrighted
  OCR full text (store excerpts/citations under the
  record's rights; full-text retention is a per-record
  rights decision, not a default).
- Rights at save time vs later access-condition changes:
  a saved citation keeps `rights_at_save`; re-checks record
  the current state separately instead of rewriting history.

Recommendation (unchanged in substance from the candidate
comparison): begin with the workspace core — projects,
history, saved documents/citations/comparisons, notes —
plus BibTeX/RIS/CSL JSON/Markdown export, all local and
deterministic. Defer any external write integration.
