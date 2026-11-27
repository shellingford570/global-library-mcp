# MCPセキュリティ監査 (b4) / MCP Security Audit

Scope: the MCP server (stdio + local Streamable HTTP), the shared
HTTP client layer, and the research tool surface. Audited
2026-11-25 for the v1.0.0b4 candidate. This is a local-first
research tool; it is **not** hardened for multi-tenant public
hosting, and this document says so wherever that matters.

## Transport and binding

- stdio: no network surface; the client process owns the server
  process. Suitable for desktop/CLI clients and for
  `tunnel-client --mcp-command`.
- Streamable HTTP: binds **127.0.0.1 by default**; the SDK's
  `TransportSecuritySettings` are configured with
  `enable_dns_rebinding_protection=True` and Host/Origin
  allowlists limited to `127.0.0.1`, `localhost`, `[::1]`. A
  request with a foreign Host or Origin is rejected by the SDK
  before it reaches a tool.
- **No authentication is built into the HTTP transport.** Do not
  bind it to a non-loopback interface or expose it through a
  tunnel other than an authenticated one (e.g. Secure MCP
  Tunnel, which authenticates at the OpenAI control plane). A
  public deployment needs an authenticating reverse proxy — not
  implemented here.

## Sessions, cancellation, timeouts

- Sessions are managed by the official SDK's session manager;
  one client's session id does not grant access to another's
  in-flight tool calls.
- Client disconnects and request cancellations propagate through
  the SDK into the tool coroutine; the shared HTTP layer counts
  cancelled attempts and charges bytes already received.
- The web UI's operation ids are random UUIDs known only to the
  initiating browser session. **That is not multi-user
  authorization** — it is a capability token for a single-user
  local UI. Any future multi-user deployment must add real
  authentication and per-user authorization in front of it.

## Budgets and resource limits

- Every network path runs under an operation budget: request
  counts are reserved atomically before sending (b3.1), response
  bytes are charged incrementally as they stream (b4), per-host
  caps apply, and a process-wide concurrency semaphore (8) is
  shared by the proxy and direct transports.
- A 429 response raises a process-wide per-host Retry-After gate:
  later requests to that host — from any operation — wait the
  full instructed time (seconds or HTTP-date). 403 responses are
  never evaded.
- Response sizes: per-response cap 25 MB (decoded), cumulative
  per-operation cap (mode-dependent, up to 300 MB in Deep),
  enforced while streaming with abort + close.
- Tool inputs: `limit` arguments are clamped to 1–50 and queries
  to 500 characters at the MCP boundary.
- Budgets are **per operation**, not per user: in a shared
  process, one user's operation cannot exhaust another's budget,
  but there is no per-user quota system. Multi-user hosting
  would need one.

## SSRF and redirect safety

- Adapters call only the library endpoints configured in
  `libraries.yaml` / adapter code. User input is placed in query
  parameters or validated path segments, never used as a URL
  base. IA file names from upstream metadata are treated as
  untrusted (path-traversal names are skipped; download URLs are
  percent-encoded).
- The shared client does not follow redirects automatically
  (`follow_redirects=False`); library APIs that answer 3xx
  surface as errors rather than silent cross-host hops.
- Access-restricted (lending) IA items are refused from metadata
  before any content fetch, and the refusal is re-checked before
  cached pages are served (b3.1).

## Data handling and logs

- The Research Beta paths (search, materials, OCR fetch,
  comparison) make **zero LLM calls** — verified by the
  trap-route test and re-verified for the research profile
  (the experimental `research_question` tool is not exposed).
- Errors returned to clients pass through `sanitize_error`,
  which strips internal details; server logs contain no
  credentials (the beta uses no API keys at all).
- Caches are process-local and keyed by library/record/page;
  search results are not shared across different queries, and
  partial-failure searches are cached for only 30 s.

## Prompt injection

- OCR text is third-party content reproduced verbatim. Tool
  responses carry a `data_notice` stating that upstream text is
  untrusted data, not instructions, and the guides instruct
  client operators likewise. The server itself never executes
  instructions found in fetched content.
- Tool descriptions avoid instructing client models to treat
  excerpts as authoritative: "verified" is defined narrowly as
  page↔original-image correspondence (see the quickstart's
  wording), never as OCR correctness or factual truth.

## Known limitations (explicit)

- No authentication/authorization on the local HTTP transport
  (loopback-only by design).
- Operation ids are capability tokens, not an authorization
  system (see above).
- Per-user quotas do not exist; budgets are per operation with a
  process-wide concurrency cap.
- The web UI and MCP server share a process model intended for a
  single user on a local machine.

## b9 addendum (2026-11-27) — external profile

The external-research profile adds: OAuth 2.1 resource-server
validation (JWKS signature, issuer, audience, expiry,
per-tool scopes) with RFC 9728 metadata and a 401 challenge;
fail-closed startup when authentication is unconfigured;
server-side consent per data class; per-user budgets,
concurrency (2), a 90-second tool deadline and HMAC-bound
continuation tokens; per-user session/cache isolation;
typed allowlist projections (no raw payloads cross); a
catch-all that returns only stable error codes so upstream
exceptions cannot leak keys or URLs; an audit log with
pseudonymised users and no research content; a kill switch
(GLM_EXTERNAL_DISABLED=1) and per-user revocation. The DNS
public-address pre-check is ON by default for this profile;
the honest residual risk (no address pinning; proxy
resolution) and the managed-egress precondition for
production are recorded in docs/b9-external-security.md.
The full threat model is docs/b9-threat-model.md.
