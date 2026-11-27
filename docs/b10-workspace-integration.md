# b10 Stage 5 — workspace integration, UI, Zotero

Date: 2026-11-28. Brief sections 34–37.

## Workspace (section 34)

b10 artefacts (claim assessments, contradiction candidates,
authority resolutions, ranking explanations, structured
questions, comparisons) are saved through
`workspace/research_artefacts.py` as research notes carrying a
versioned JSON envelope (`{"kind": "b10_<kind>", "version": 1,
"payload": {...}}`). Design choices:

- **No schema change.** The notes table already stores title +
  content, so no migration was needed: existing projects,
  documents, citations, search history and — critically — the
  b8/b9 rights-trust state are untouched (a unit test asserts
  the schema version and integrity are unchanged after saving
  artefacts). The envelope version leaves a clean path if a
  future release gives artefacts dedicated tables.
- Nothing existing is reclassified, deleted or sent anywhere;
  plain notes are never mistaken for artefacts (the reader
  requires the envelope prefix and version).
- `project_research_progress` (section 35) computes counts from
  live state: saved documents/citations/notes/comparisons plus
  b10-specific counters — claims with insufficient evidence,
  contradiction candidates, unverified authority candidates.
- `project_relationship_graph` builds nodes/edges over saved
  documents using the workspace's own candidate fields
  (`work_id_candidate`, `author_id_candidate`): every edge is
  typed `*_candidate` with `certainty: "candidate"`, and
  contradiction-candidate edges link back to their artefact.
  Candidate and confirmed relations are never conflated.

## Web UI (section 37)

- New `GET /api/features` reports what is actually active in
  the process: ResearchRanker on/off (env), semantic search
  availability — true only when a local backend can be
  constructed from `GLM_SEMANTIC_MODEL_DIR` — the model id when
  available, and the expansion allocation. The results header
  shows this line in Japanese/English; on any fetch failure it
  shows nothing rather than guessing.
- Result cards render `ranking_reasons` when the service
  attached them (ResearchRanker opt-in path); otherwise the UI
  is unchanged. Mobile layout, staged display, cancellation and
  search-only mode are untouched.

## Zotero compatibility (section 36)

The Zotero application is **not present** in this environment
(no binary, no profile directory), so real-application import
verification was **not performed** and is reported as such.
What was verified, with synthetic records only
(`eval/b10_zotero_compat.py`, 13/13 checks):

- BibTeX: independent strict parse — entry count, Japanese
  author, German edition statement, French translator, year,
  URL all survive; citation keys are stable across exports.
- RIS: tag grammar (TY first, ER last) and Japanese author.
- CSL JSON: shape (id/type/title/issued), corporate author as
  literal, newspaper material typed as a newspaper article.

No user Zotero library exists here or was touched; no account,
registration or cloud sync was involved.
