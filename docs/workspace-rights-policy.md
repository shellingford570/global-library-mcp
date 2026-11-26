# Workspace rights policy (b7; trust model added in b8)

**b8 trust model (Stage 0).** A rights statement can permit
excerpt storage only when THIS server observed it
(`server_observed`). Statements arriving via project import
(`imported_claim`) or inside a restored backup
(`restored_claim`) can only restrict, never permit: imported
projects store citation/comparison excerpts as references
only (text is never stored on import), and restoring any
backup downgrades every citation's verification state and
every document's rights trust until a fresh server-side
re-verification re-establishes them. A backup file's own
checksum proves integrity of the copy, not the authenticity
of the rights or verification claims inside it. CC BY-NC /
CC BY-NC-SA excerpts additionally require an explicit
non-commercial purpose confirmation at save time. See
docs/b8-b7-regression-hardening.md.

Persistence is different from retrieval: that a text can be
fetched does not mean it may be stored, redistributed or
sent elsewhere. The workspace applies a conservative,
category-based policy (`workspace/policy.py`). A licence
name alone never decides every use; the policy is a
default, not a legal guarantee — whether a quotation is
permissible depends on purpose, jurisdiction, extent and
necessity.

## Categories

public_domain (incl. CC0 and Public Domain Mark), cc_by,
cc_by_sa, cc_by_nc, cc_by_nd, cc_by_nc_sa, cc_by_nc_nd,
noc_nc, copyrighted, restricted, unknown. Statements are
classified from the item's own rights text (per-item
statements from the holding institution take precedence
over generic placeholders).

## Decisions per category

| Decision | Permissive (PD, CC BY/SA/NC/NC-SA) | Others (ND, NC-ND, NoC-NC, copyrighted, restricted, unknown) |
|---|---|---|
| metadata_storage | yes | yes |
| metadata_export | yes | yes |
| excerpt_storage | yes | **no (default)** |
| excerpt_export | yes | **no (default)** |
| fulltext_storage | **never** | **never** |
| image_storage | **never** | **never** |
| external_transfer | **never** | **never** |
| access_recheck_required | no | yes |

When an excerpt is withheld, the citation still stores the
source, page id, character offsets and SHA-256 of the
excerpt, so the passage can be re-located and re-verified
against a fresh fetch. Excerpts are capped at 2,000
characters.

## Snapshots and change history

Rights are snapshotted at save time (`rights_at_save`).
Re-verification appends observations; a changed statement
is reported as `rights_changed` and recorded in
`rights_observations`. Snapshots are never overwritten.
If access to an item is later restricted, stored data is
not used to circumvent that restriction; exports re-apply
the policy at export time and list omissions with reasons.

## Final review corrections (v1.0.0b7 release)

The external final review found the original classification
fail-open and corrected it; `docs/b7-final-review.md` §2 is
authoritative where this document and the code disagree.

- Classification is structural and fail-closed: exact CC
  URI/name combinations only; negation vetoes a grant;
  unknown combinations are `unknown`, never CC BY.
- NoC-NC does NOT permit excerpt storage (it is a
  restriction statement, not a grant). CC BY-NC / BY-NC-SA
  permit storage with a recorded non-commercial purpose
  caveat; the system cannot verify the user's purpose and
  does not guarantee legal compliance.
- Metadata licences never license OCR text.
- Display, local search and export re-gate excerpts against
  the save-time AND the latest observed rights
  (`effective_decision`); the stored row is never rewritten.
- Another document's rights information can never be reused:
  the document-token fallback requires identical library and
  record identity.
- The 2,000-character excerpt cap is a system limit, not a
  legal quotation allowance.
