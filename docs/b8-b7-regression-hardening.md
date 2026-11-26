# b8 Stage 0 — b7 residual-problem hardening

Date: 2026-11-26. Base: v1.0.0b7 (`ab1274b`). All five problems
from the b8 brief section 2 were reproduced against b7 before
fixing; the reproductions and fixes are covered by
`tests/test_b8_stage0.py` plus updated b7 suites.

## 1. Reproductions (against b7)

1. **Imported rights claims permitted excerpt storage.** A
   project JSON whose citation claimed "Public Domain" was
   imported with the excerpt text stored, although the
   verification state was correctly downgraded to
   `imported_unverified`. The file's claim alone decided.
2. **Latest rights observation ignored on new saves.** After a
   re-verification recorded "In Copyright" for a document, a
   new citation saved from a fresh page token claiming
   "Public Domain" still stored its excerpt.
3. **Imported document claim usable as a citation fallback.**
   `_citation_rights_statement` fell back to the saved
   document's rights statement without any trust distinction.
4. **Cross-library record_id collision.** Comparing an
   Internet Archive document and an LoC document that share
   the record_id `rec` saved the LoC excerpt ("passage from
   loc") onto BOTH documents: `compare_documents` keyed its
   per-aspect texts and row cells by record_id only, and the
   workspace save aggregated by record_id only.
5. **NonCommercial default.** CC BY-NC / CC BY-NC-SA excerpt
   storage was permitted by default with no purpose
   confirmation anywhere in the system.
6. **Restore.** The restore path set its `restoring` flag only
   after taking the pre-restore backup, never waited for
   in-flight operations, and a structurally valid uploaded
   database kept its `verified` citation states and rights
   untouched — structural validation cannot prove authenticity.

## 2. The trust model

Rights information now carries a trust state:

- `server_observed` — this server fetched the statement from
  the upstream source (live page/document fetch, reverify).
- `imported_claim` — the statement arrived inside an imported
  project file.
- `restored_claim` — the statement arrived inside a restored
  backup database.

Only `server_observed` statements can PERMIT excerpt storage,
display or export (`workspace/policy.py: trusted_decision`).
Claims are preserved as history and can only restrict. A
server-side observation recorded later (for example by
re-verification) can restore permission.

## 3. Fixes

- **Import (transfer.py).** Citation and comparison excerpt
  texts are never stored on import, whatever the file claims.
  Reference information (page id, offsets, SHA-256) is kept,
  omissions are reported, imported documents are marked
  `rights_trust = imported_claim`, and imported citations keep
  `imported_unverified`. No upstream access happens at import.
- **Re-verification re-admission (workspace_api.py).** A
  reference-only citation regains its excerpt only from a
  fresh server-side fetch: the OCR slice at the stored offsets
  must hash to the stored reference hash and the freshly
  observed rights must permit storage. NC categories cannot
  re-admit through re-verification (no confirmation channel).
- **New saves (workspace_api.py `_gate_new_excerpt`).** The
  latest rights observation always applies to new citation and
  comparison saves; the saved-document fallback is honoured
  only for server-observed documents; imported claims are
  never a fallback basis.
- **NonCommercial.** `evaluate()` now reports
  `excerpt_requires_confirmation` for CC BY-NC / CC BY-NC-SA.
  Citation saves return `409 nc_confirmation_required` until
  the request carries `nc_purpose_confirmed: true` (the Web UI
  asks and retries once); comparison saves withhold NC
  excerpts unless the same flag is present.
- **Composite identity.** `compare_documents` keys per-aspect
  texts, row cells and unique terms by `library_id|record_id`;
  the workspace save aggregates by the `(library_id,
  record_id)` tuple (a legacy plain-record_id key is attributed
  only when exactly one compared document carries it); the Web
  UI reads the composite key with a legacy fallback.
- **Restore quiescence.** Every workspace route except restore
  registers as an in-flight operation. Restore validates the
  candidate, then quiesces: new operations get 503, in-flight
  operations are awaited (30 s timeout → 409, nothing
  changed), the pre-restore backup is taken only after
  quiescence, then the swap, open check and rollback run as
  before. A concurrent restore is refused by the same 503.
- **Backup trust boundary.** After every successful restore,
  `apply_restore_trust_downgrade()` runs: citation
  verification states become `restored_unverified` (prior
  values preserved as a `restored_downgrade` observation,
  `verified_at` cleared) and every document's rights become
  `restored_claim` with a `restored_backup` rights
  observation. Excerpt texts stay in the database but are
  withheld from views and exports until re-verification.
  This applies to the application's own backups too: the file
  format carries no signature, so the application cannot
  distinguish them from foreign files, and it does not pretend
  otherwise.

## 4. Schema v3

`saved_documents.rights_trust TEXT NOT NULL DEFAULT
'server_observed'`. The v2→v3 migration keeps the existing
pre-migration backup behaviour and marks documents
`imported_claim` when any of their citations carries a b7
import marker. `validate_backup` requires the v3 column for
candidates claiming schema ≥ 3; v1/v2 candidates remain
restorable and are migrated on open.

## 5. Impact on existing b7 workspaces

- Workspaces created and used locally under b7 are unaffected
  except for the schema migration: their documents keep
  `server_observed` trust.
- Projects imported under b7 keep their stored excerpts in the
  database, but from b8 those documents are claim-trust: the
  excerpts are withheld from views and exports until a
  re-verification records a server-side rights observation
  (and, for citations, re-admits the text by hash match).
  No data is deleted.
- Restoring any backup (including one created by b7) now
  downgrades verification states and rights trust as above.
  Users who restore a backup should re-verify citations they
  rely on; the previous states remain visible in each
  citation's observation history. A maintenance release of b7
  was NOT made: the b7 tag is unchanged per the brief, and
  this document plus the b8 release notes serve as the user
  notice.

## 6. What did not change

Evidence admission and the other frozen conditions (b8 brief
section 22) are untouched. MCP tool profiles are unchanged.
The b7 tag and Release are unchanged.
