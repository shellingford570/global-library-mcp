# b9 — External transfer rights policy

Module: `src/global_library_mcp/external/rights_policy.py`,
data: `src/global_library_mcp/external/transfer_matrix.py`,
per-library table: docs/b9-library-transfer-matrix.md.

## Independence

This policy is **independent of the workspace storage
policy**. A statement that permits local storage does not
permit transfer to an external AI service; saved workspace
rights observations are never inputs here. A decision uses
only (1) the per-library transfer matrix (official API/terms
level), (2) the item's own rights statement from a fresh
fetch, classified from its structured rights URI where one
exists, and (3) the deployment's excerpt switch.

## Decision categories (brief section 12)

`metadata_allowed`, `reference_only`, `excerpt_allowed`,
`attribution_required`, `purpose_restricted`,
`redistribution_restricted`, `access_restricted`,
`terms_unconfirmed`, `rights_unknown`,
`external_transfer_denied` — returned with every rights/fetch
response so the client can see WHY, not just what.

## Defaults

- Minimal metadata transfers only where the matrix allows it
  and the item is not access-restricted.
- Unknown rights → reference-only (external id, library, and
  the reference URL where the matrix allows it).
- In-copyright items → no text transfer.
- CC BY-NC / NoC-NC → **not** assumed to satisfy the
  NonCommercial condition for transfer to an AI service.
- Public Domain Mark / RightsStatements labels alone never
  settle transfer: the matrix must also allow the content kind.
- OCR full text: **never**. Original-image binaries: **never**.
- Local research data (workspace): **never** — structurally
  unreachable from the external profile.
- Access-restricted items (e.g. lending) keep their
  restrictions; nothing here relaxes them.

## Excerpts (brief section 15)

External excerpt transfer is **disabled by default**
(`GLM_EXTERNAL_EXCERPTS` unset). Even when enabled, an excerpt
requires ALL of: document identity re-confirmed from the fresh
page payload; page identity verified; the text taken verbatim
from that verified page's OCR; the item's current rights
permitting it; the matrix allowing OCR-excerpt transfer AND
third-party-AI transfer for that library; no access
restriction; the `excerpts:read` scope; server-side consent
for the excerpts data class; and the cumulative caps — 500
Unicode characters per excerpt, 1,000 per document, 2,000 per
response, 5,000 per user session, enforced from a server-side
per-user ledger so splitting across calls, tools or sessions
of the same user cannot reassemble a text. These caps are
system limits, not a statement of what copyright law permits
as quotation.

With the shipped matrix, **no real library currently
qualifies** (no library's checked terms confirm OCR-excerpt
transfer to a third-party AI service), so the excerpt tool
always denies on real libraries; the allow path is verified
only against synthetic fixtures. Enabling it for a real
library requires confirming that library's terms for this use,
updating the matrix with the source, and a separate
deployment approval.
