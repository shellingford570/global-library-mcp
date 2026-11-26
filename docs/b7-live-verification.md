# b7 live verification record (2026-11-26)

What was exercised against real services and a real local
server during the b7 candidate work, kept separate from
fixture and synthetic results. Environment: the development
VM (1.5 shared vCPU, ~6 GB RAM), server bound to
127.0.0.1, workspace at a temporary `GLM_WORKSPACE_PATH`.

## Server and security behaviour (live HTTP)

- Workspace-enabled server serves the CSRF token in the
  page meta; `/api/workspace/status` reports schema 1 and
  integrity ok.
- A workspace mutation without the CSRF header → 403; a
  non-loopback Host header → 403.
- Starting the web server with the workspace enabled on a
  non-loopback address is refused at startup.
- Project 「ダーウィンの進化論」 created with a tag;
  data persisted across multiple server restarts against
  the same database file.

## Internet Archive save and citation flow (live)

- `/api/document` for `onoriginofspecie1859darw` returned
  the record; saving it to the project returned 201; a
  second save of the same record returned 409
  (`already saved`).
- Page `onoriginofspecie1859darw@20` fetched (1,914 chars,
  page identity verified). A citation over characters
  200–340 was saved with status
  `verified_against_fetched_ocr`, and re-verification
  returned `unchanged`.
- The excerpt **text was withheld by the rights policy**:
  IA's statement for this item is the generic "item-specific;
  verify at the item page", which classifies as unknown.
  The citation reference (offsets, hash) was stored.
- A forged excerpt (text not present in the fetched OCR)
  was rejected with 422.
- Contrast case: an IA record whose document-level
  statement is CC BY 4.0 stored its excerpt text with
  category `cc_by`. Page payloads carry only the generic
  placeholder, so the document-level statement takes
  precedence, with a document-snapshot fallback.
- BibTeX export of the project produced
  `@book{darwin1859the, …}`.

## Not separately re-run live for b7

- Scenarios 3 (DDB→BSB) and 5 (LoC newspaper) workspace
  saves: the save-token path is adapter-agnostic and was
  proven with IA above; discovery, the DDB→BSB handoff and
  the LoC issue→page→OCR chain were live-verified in b6
  (docs/b6-final-review.md).
- A real Zotero import was **not** performed. BibTeX
  output was parsed by the independent bibtexparser
  library (3 records incl. a Japanese record and a LoC
  newspaper; 0 failed blocks) — format compatibility and
  parser verification only.
- Docker workspace mode was not verified; in Docker the
  workspace stays off by default and the search-only mode
  is unchanged.

## Final review round (2026-11-26)

Small live re-checks for the workspace save path (few
calls): IA page `onoriginofspecie1859darw@20` returned
library/record/page IDs with non-empty OCR and a verified
mapping. NDL page `992954_10` returned `book_pid=992954`
with NO `record_id` field, non-empty OCR and a verified
mapping; its rights statement is the per-item Japanese
notice, which classifies `unknown` (reference-only
excerpts). The NDL payload shape is pinned in
`tests/test_b7_scenarios.py` scenario D. BSB/LoC shapes
were re-verified against fixtures only this round.
