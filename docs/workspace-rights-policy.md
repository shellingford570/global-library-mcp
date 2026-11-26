# Workspace rights policy (b7)

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
