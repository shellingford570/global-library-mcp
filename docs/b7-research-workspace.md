# b7: Research Workspace & Citation Management — implementation record

Status: implemented in v1.0.0b7 (branch `feat/research-workspace-b7`).
Design origin: `docs/b7-research-workspace-design.md`. User guide:
`docs/workspace-user-guide.md`. Schema: `docs/workspace-database-schema.md`.
Security: `docs/workspace-security.md`. Exports:
`docs/citation-export.md`. Backup/restore:
`docs/workspace-backup-restore.md`. Performance:
`docs/b7-performance-evaluation.md`.

## What was built

A local-first research workspace on SQLite (Python stdlib
`sqlite3`, no new dependencies):

- **Projects** with counts, tags, archive, confirmed deletion.
- **Saved documents**: bibliographic snapshots taken from
  server-side result snapshots (see Provenance), deduplicated
  per (project, library, record); different editions/copies
  stay different documents; snapshots are never silently
  refreshed.
- **Saved citations**: page-level, with the verbatim excerpt
  re-checked against the OCR text this server fetched, its
  SHA-256, offsets, page-mapping and image states, rights at
  save, and a re-verification history that appends
  observations (`unchanged`, `metadata_changed`, `ocr_changed`,
  `quotation_not_found`, `source_unavailable`,
  `mapping_unverified`, `access_restricted`, `rights_changed`,
  `recheck_failed`, `not_rechecked`).
- **Research notes** (the researcher's own writing, always
  distinct from OCR text), **search history** (opt-in per
  search; reruns create new entries; cancelled searches are
  recorded as cancelled, never as success; no OCR full text is
  stored in history), **saved comparisons** (2–4 documents,
  `semantic_status: not_checked` retained), **tags**,
  **collections**, **local search** over a normalised
  substring index (parameterised LIKE; user input is never
  interpreted as SQL or FTS syntax).
- **Exports**: BibTeX (classic BibTeX), RIS, CSL JSON,
  plain text, deterministic Markdown project reports, and a
  versioned JSON project format with strict import
  validation, id remapping and full rollback.
- **Backup/restore** via the SQLite online backup API with
  SHA-256 + integrity verification; restore snapshots the
  current database first and refuses corrupt or
  future-schema files.

## Provenance (brief section 12)

Clients cannot assert verification. Search/materials/document/
page responses carry short-lived `save_token`s bound to
server-side snapshots of the payloads this server returned
(2 h TTL, 512-entry bound). Save operations rebuild the
stored record from the snapshot; citation excerpts must be
found verbatim in the fetched OCR text. Manual citations are
stored as `user_entered` / `user_entered_unverified`;
imported citations as `imported` / `imported_unverified`
with the claimed status kept as a historical observation.

## Rights policy (brief sections 3, 19, 20)

See `src/global_library_mcp/workspace/policy.py`. Metadata
and links are always storable. Short excerpts are stored and
exported only for public-domain / permissive-CC categories
by default; unknown, unverified, copyrighted or restricted
material keeps the citation reference without the text, with
the reason recorded. OCR full text and image bytes are never
stored. This is a conservative engineering default, not a
legal guarantee.

## Web security (brief sections 29, 33)

Workspace mode refuses non-loopback binds; every workspace
request requires a loopback client and a loopback Host;
mutations require the per-process CSRF token (meta-tag
delivery only) and a matching Origin when present; bodies
are size-capped and JSON-typed; responses are `no-store`
with the existing CSP. The stateless search-only mode is
unchanged (Docker CI keeps working with 0.0.0.0 + no
workspace). The UI renders all stored content via
`textContent`/DOM APIs (no stored-XSS surface), and dangerous
URL schemes are never rendered as links by the existing
`safeHref()`.

## Also fixed in b7 (brief section 35 follow-through)

- `/api/search` parsed the structured options into a variable
  nothing used. Stage-1 now applies them through the Quick
  research path and the UI builds the parameters once for
  both stages.
- Worse, found while wiring the workspace: `/api/materials`
  referenced that same variable from a scope where it never
  existed, so **every real HTTP materials call failed** with
  a NameError masked as an upstream 502. The mocked
  Playwright route had hidden this since b3. A shared
  `structured_kwargs()` helper now serves both routes, and
  the route was verified live (200, 39 materials).

## Verification summary

- pytest 404 (362 pre-b7 + 42 b7), Playwright 17 + 3
  workspace journeys (the workspace spec skips on a
  search-only server and passes against a workspace server).
- MCP regression: stdio 15 tools; Streamable HTTP research
  profile 14 tools, all read-only, `research_question`
  absent. MCP has no workspace access at all in b7.
- Live (small, representative): IA Darwin document saved;
  duplicate rejected; page citation saved with verbatim
  check (forged excerpt rejected 422); the same item's
  generic IA rights statement withheld the excerpt text by
  policy while a CC-BY item's excerpt was stored; reverify
  returned `unchanged`; data persisted across server
  restarts; BibTeX/RIS/CSL/Markdown/JSON exports produced.
- BibTeX output parsed cleanly by the independent
  `bibtexparser` 2.1.0 (3 entries, 0 failed blocks). A real
  Zotero import was NOT performed (see citation-export.md).
- Performance (synthetic, this VM): see
  `docs/b7-performance-evaluation.md` — every provisional
  target in brief section 38 is met at all three scales.

## Scenarios (brief section 39)

1. Darwin: live-verified end to end (above).
2. 明治水力発電： history recording, comparison saving and
   Markdown export verified at API/test level with fixtures;
   the NDL search itself was live-verified in b6.
3. German steam engine: DDB discovery and the BSB handoff
   were live-verified in b6; workspace saving uses the same
   token path proven live with IA. A DDB-record workspace
   save was not separately re-run.
4. Kant: the author-filtered stage-1 search was live-verified
   through the fixed `/api/search`; edition separation is
   covered by store tests. The Kritik itself not reaching
   the sampled top ranks remains a b6 ranking limitation.
5. LoC newspapers: the OCR/image/citation chain was
   live-verified in b6; a workspace citation save for a LoC
   page was not separately re-run (the token path is
   adapter-agnostic and IA-proven).
6. Migration: export → clean-DB import round trip verified
   in tests, including verification-claim downgrading.
7. Restart persistence: verified in tests (store reopen) and
   live (workspace data survived repeated server restarts).

## Known limitations

- FTS5 was evaluated and not adopted: the default tokeniser
  segments CJK poorly; the normalised substring index is
  used instead (documented in the schema doc).
- The workspace UI is functional rather than polished;
  citation creation is via the page-fetch form.
- Docker: workspace mode is disabled by default in
  containers (search-only mode unchanged); running the
  workspace inside Docker was not verified.
- Windows/macOS startup steps in the user guide are
  procedures only; this build was verified on Linux.
- P2 items (timeline view, relation graph, progress
  aggregation, bulk organisation, extra citation styles)
  are not implemented.
- No APA/Chicago/MLA styles are claimed; the plain-text
  format is a simple author-title-year rendering.

## b8 library priorities (brief section 52, re-ranked)

Criteria: official API, page OCR, original images, page
mapping verifiability, bibliographic quality, rights
information, auth requirements, cost, rate limits, fit with
multilingual search and with the workspace (stable record
ids + page ids are what make citations durable).

1. **Gallica** — already implemented; the blocker is the
   upstream 403 from some networks. Retry verification from
   other environments; SRU + IIIF fit is excellent.
2. **Finna / National Library of Finland** — open API
   (api.finna.fi), strong metadata, IIIF images; good
   multilingual fit.
3. **DPLA** — free API key, rich aggregation of US holdings,
   rights statements standardised (rightsstatements.org),
   which plugs directly into the workspace rights policy.
4. **KB / Delpher (Netherlands)** — newspapers with OCR;
   Delpher access terms need review.
5. **Japan Search** — national aggregator with IIIF and
   SPARQL/JSON APIs; strong fit for Japanese research and
   for NDL-adjacent material.
6. **HathiTrust** — bibliographic API is open; page OCR is
   constrained by the Data API's terms — evaluate carefully.
7. **Trove (Australia)** — API key required; newspapers with
   OCR are a strong match for the LoC-style adapter.
8. **National Library of Korea / National Library of
   Taiwan** — evaluate API openness and page-level access.
9. **BNE (Spain) / ONB (Austria)** — IIIF presence varies;
   evaluate after the above.

Recommendation: b8 starts with Gallica re-verification and
Finna, then DPLA (its standardised rights statements also
strengthen the workspace policy), keeping the
one-adapter-at-a-time, live-verified discipline of b5.

## Final review addendum (v1.0.0b7 release)

The external final review of this candidate found and the
release round fixed: cross-document citation binding,
rights-token reuse, fail-open rights classification,
import/restore policy bypasses, cross-project references,
session binding, and honest re-verification states. One
further real bug was found by the new regression suite
(`latest_rights_observation` cursor misuse). The full
record is `docs/b7-final-review.md`; where the candidate
report above and the final review disagree, the final
review is authoritative. Workspace Playwright journeys are
now 5 (backup and project-edit journeys added), and CI has
a dedicated workspace job.
