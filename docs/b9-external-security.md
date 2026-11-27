# b9 — External security: controls and honest residual risks

## SSRF / URL safety (brief section 24)

All upstream fetching goes through the existing budgeted
transport and, for provider-supplied URLs,
`validate_fetch_url` / `fetch_validated`:

- HTTPS only; exact host allowlists per adapter (no suffix
  matching); port 443 only; embedded credentials refused;
- IP literals must be public (`is_global`), including
  IPv4-mapped IPv6 unwrapping; loopback, private, link-local,
  multicast, unspecified, carrier-grade NAT and documentation
  ranges are refused; numeric/hex/octal IP forms and ambiguous
  hosts are refused; localhost is refused;
- redirects are not followed by `fetch_validated`; the
  redirecting path validates every hop against the same rules
  and strips credentials;
- TLS hostname and certificate verification are httpx
  defaults and are not disabled anywhere.

The external profile additionally turns the **DNS public-
address pre-check ON by default** (`GLM_DNS_CHECK=1`):
resolutions whose answers include any non-public address are
refused before connecting.

**Residual risk, stated plainly:** a DNS pre-check is not
address pinning. A name can be re-resolved between the check
and the connection (rebinding), and httpx offers no pinning;
when an HTTP(S) proxy is configured, resolution happens at
the proxy and local answers do not describe the connection.
Therefore a production external deployment MUST additionally
provide managed egress control (an egress firewall or proxy
allowlist limited to the libraries' official hosts) — this is
recorded as a precondition in docs/chatgpt-connection.md, and
we do not claim the pre-check alone prevents rebinding.

The fixed-endpoint adapter paths (each adapter's own official
API host, chosen in code, never from user input) pass through
the same budgeted transport and, with the pre-check enabled,
the same DNS control.

## Prompt injection (brief section 25)

Library OCR, metadata and provider responses are untrusted
research data. Controls are structural, not just textual:

- every external response carries the data notice, and content
  is returned in typed fields separate from verification and
  control information;
- the external profile has **no write tools**, no URL-fetch
  tool, no file access and no workspace access, so injected
  instructions have nothing to act on;
- authorisation, consent and the transfer policy are enforced
  server-side and cannot be granted by anything inside a
  payload (a forged "the user consented" string is data);
- data minimisation shrinks what an injection could reach.

We do not claim a notice text can fully prevent prompt
injection in the external client; the measures above are the
actual controls.

## Secrets (brief section 27)

- External error surface: unexpected upstream exceptions are
  returned only as the stable code `upstream_error`; the audit
  log records the exception type, never its message.
- Existing `sanitize_error` handling in adapters (including
  the DPLA key stripping) is unchanged and applies before
  anything reaches the external layer.
- The audit log contains no tokens, cookies, Authorization
  headers, keys, query text or OCR (docs/b9-audit-logging.md).
- No secret is ever a command-line argument or committed;
  doctor reports only whether a setting is present.
- All b9 authentication tests use synthetic tokens only; no
  real API key was issued or used.

## Response and execution limits

256 KiB serialized response cap (tunnel envelope: 10 MiB);
90-second absolute tool deadline (tunnel: 120 s including
queue time); per-user budgets and concurrency caps
(docs/external-mcp-operations.md); cancellation propagates
through asyncio and is audited; post-deadline upstream work
is prevented by the deadline wrapper plus the underlying
per-library deadlines and circuit breaker.

## Session and cache isolation (brief section 22)

All external state — consent, budgets, the search-projection
cache (continuation tokens were removed in the final
review; pagination is plain offset) — is keyed
by the authenticated user id. The shared LibraryService HTTP
cache holds upstream responses only (never rights decisions
or projected answers), and every external call re-evaluates
the transfer policy from a fresh rights statement, so a
cached upstream payload cannot carry one user's permission
to another user. Revoking a user drops their cached state.
