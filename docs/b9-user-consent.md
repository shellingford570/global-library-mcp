# b9 — External user consent model

Module: `ConsentStore` in
`src/global_library_mcp/external/control.py`.

## Principles (brief section 19)

- Consent is **server-side state**, bound to a user, a set of
  data classes, optionally a set of libraries, and an expiry.
- A tool argument can never create consent: there is no
  `consent=true` parameter anywhere, and text inside library
  data claiming consent is treated as data.
- Without consent, a tool call is refused with
  `consent_required:<data class>` — or, for the least-sensitive
  tools (library listing/capabilities), no consent is needed.
- Consent never overrides library terms or copyright: it is
  one necessary condition among several for excerpt transfer,
  never a sufficient one.

## Data classes

| Class | Covers | Needed by |
|---|---|---|
| `bibliographic` | sending bibliographic metadata about the user's queries' results | search, fetch, materials, compare |
| `search_terms_upstream` | the user's search terms being sent to upstream library APIs (inherent to searching) | search, materials, compare |
| `references` | original-reference data in fetch results | fetch |
| `rights` | rights statements/decisions for items the user asks about | get_document_rights |
| `excerpts` | (no tool exposes excerpts after the final-review reduction) | — |

## Lifecycle

- **Grant**: `ConsentStore.grant(user, classes, libraries=None,
  ttl)` — called by the deployment/operator (in local stdio
  mode, the local operator is auto-granted for their own
  server, which is documented behaviour, not a silent default
  for HTTP mode).
- **Expiry**: grants carry an expiry (default 24 h); expired
  consent is treated as absent.
- **Revocation**: `revoke(user)` clears the classes at once;
  `ExternalRuntime.revoke_user` additionally drops budgets,
  caches and ledgers. Revocation takes effect on the next
  call — verified in the security evaluation.
- **Scope of a grant**: the consent screen a deployment shows
  its users should name the libraries, the data classes, the
  fact that search terms go to upstream libraries, the fact
  that the external AI service processes what is sent under
  ITS terms, the budget, and the expiry — the checklist in
  brief section 19. The exact UI belongs to the deployment;
  this repository provides the enforcement, not a consent UI.
