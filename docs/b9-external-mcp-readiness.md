# b9 — External MCP Readiness: design and Stage 0 audit

Version 1.0.0b9. This document records the Stage 0 audit of
the b8 baseline, the architecture b9 implements, and what is
deliberately not done. Companion documents:
`b9-openai-compatibility.md` (official-spec research),
`b9-external-rights-policy.md`, `b9-library-transfer-matrix.md`,
`b9-mcp-authorization.md`, `b9-user-consent.md`,
`b9-audit-logging.md`, `b9-external-security.md`,
`b9-threat-model.md`, `b9-security-evaluation.md`,
`b9-performance-evaluation.md`, `chatgpt-connection.md`,
`chatgpt-connection.ja.md`, `secure-mcp-tunnel.md`,
`external-mcp-operations.md`,
`external-mcp-incident-response.md`.

## Architecture (brief sections 4 and 7)

```text
External AI client (ChatGPT etc.)
  -> Secure MCP Tunnel or authenticated MCP connection
     (NOT created in b9)
  -> external-research MCP server (separate FastMCP instance,
     separate process; allowlist-only tools)
  -> authentication (OAuth 2.1 resource-server validation)
  -> authorisation scopes + server-side user consent
  -> per-user budgets, concurrency, deadlines, session isolation
  -> external transfer rights policy (independent of the
     workspace storage policy)
  -> LibraryService (existing, unchanged admission rules)
  -> library APIs worldwide
```

The Research Workspace is not part of this path: the external
package never imports the workspace package, receives no
workspace path or configuration, and is tested for structural
isolation with canary research data (brief section 29).

## Stage 0 audit

### 5.1 Rights observations and trust state

- `workspace/policy.py::observation_trust` carried a
  compatibility branch: an observation with **no trust value**
  but a server-looking `source` string was treated as
  server-observed. **Fixed in b9**: the schema-v4 migration
  backfills an explicit trust value for every row a real
  database can contain, and `add_rights_observation` always
  writes one, so a trust-less observation has unprovable
  provenance and is now a claim (fail-closed).
- `_observation_is_future` treated a **missing or non-string**
  timestamp as "not future". **Fixed in b9**: missing or
  malformed timestamps cannot establish trust (unparseable
  values were already treated as untrusted).
- Import, restore and migration downgrades from b8 are
  unchanged: imports are claims, restores downgrade every
  observation to `restored_claim`, pre-v3 databases mark every
  document `imported_claim`.
- External transfer decisions **never** read workspace rights
  observations: the external policy (Stage 2) decides from a
  fresh fetch plus the per-library transfer matrix only.

### 5.2 Reverify consistency

`web/workspace_api.py::_reverify` was re-audited:

- The freshly fetched page must re-confirm the saved
  document's `(library_id, record_id)`; a page from another
  document cannot contribute rights or text (b8 fix, kept).
- A citation whose page mapping is unverified gets its
  verification status recorded as such; it cannot re-admit an
  excerpt.
- Re-admission writes happen in a single store call after
  every check has passed; an exception before that point
  records a failed verification observation and writes no
  excerpt. The store serialises writes under its lock, and
  `trusted_decision()` consults **all** observations —
  including a restriction recorded while a reverify was in
  flight — at every later save/display, so a concurrent
  restriction is not lost.
- Past-versus-current contradictions resolve conservatively:
  claims only ever restrict; only later server-trusted
  observations lift a restriction (b8 semantics, unchanged).
- NonCommercial categories cannot re-admit through reverify
  (no purpose-confirmation channel there).
- No workspace rights criterion was relaxed for the external
  features; the external path does not call into the workspace
  at all.

### 5.3 Current MCP responses (all 15 tools)

Audited `mcp_server.py` / `service.py` return shapes:

| Tool | Returns today | External concern |
|---|---|---|
| search_catalog | bibliographic fields, rights, raw provider fields in places | raw must not cross |
| get_document | full document payload incl. provider raw data | raw, long descriptions |
| list_libraries | registry entries | safe after projection |
| get_page_text | **full OCR text**, rights, image URLs | full text must never cross by default |
| verify_original | check details | internal check names need projection |
| research_materials | verified excerpts + evidence chains | excerpts only under external policy |
| research_question | AI Experimental answer | **excluded from external profile** |
| search_in_document | matching snippets from full OCR | snippets are excerpts — policy-gated |
| compare_documents | per-document excerpts | excerpts — policy-gated |
| get_citation | citation incl. excerpt | excerpt — policy-gated |
| list/get comparisons, claims, evidence status | internal research state | excluded or projected |
| server info / health style tools | versions, paths in errors | paths/debug must not cross |

Conclusion (brief section 5.3): existing tool outputs are
**not** reused for the external profile. The external server
builds typed projections with an allowlist of fields per tool
(Stage 1/2).

### 5.4 Multilingual regression (b6 corpus under b8)

Measured at b8 release: fixed F Recall@10 0.8819 and
challenge F 0.8611 on the b6 fixed corpus, below the b6
release measurements (0.9097 / 0.9167), while the real-service
fixture B Standard improved (0.7667 -> 0.8333). Analysis:

- The diagonal interleave allocates variant slots to every
  lexicon language equally; the fi/sv/nl labels added in b8
  compete with ja/en/de/fr variants under the unchanged caps
  in the default (no language specified) mode.
- When the caller specifies languages or libraries, expansion
  is already restricted to those, so user-specified priority
  works today.
- The b8 section-19 experiment showed reordering trades one
  corpus against another; a further reordering in b9 — whose
  subject is the external foundation, not search ranking —
  risks a new regression without a dedicated evaluation
  round. Per brief section 5.4 this is recorded as a **b10
  candidate** (see docs/b10-candidates.md) with the measured
  numbers; no budget or cap was raised and no ranking change
  was made in b9. The expansion plan's
  `languages_not_represented` / `cap_reason` reporting (b8) is
  surfaced by the external `search` tool so external clients
  can see when the cap dropped a language.

## What b9 does not do

No Secure MCP Tunnel is created, no ChatGPT connection is
made, no API key is issued, no public server is deployed, no
research data is sent to any external AI service, and b10
implementation is not started. Those steps need the separate
approvals listed in docs/chatgpt-connection.md.
