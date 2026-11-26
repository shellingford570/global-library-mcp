# Workspace security (b7)

Threat model: the workspace turns a stateless search page
into a stateful local application holding unpublished
research. Attackers considered: malicious web pages in the
user's browser (CSRF, DNS rebinding), malicious imported
files, malicious stored content (bibliographic data, OCR,
notes — all untrusted), and local data theft via accidental
publication (git, exports).

Controls:

- **Bind**: workspace mode refuses non-loopback binds at
  startup (`run()` raises SystemExit). The search-only mode
  keeps its previous behaviour for Docker.
- **Per-request**: loopback client address required; Host
  header must name a loopback host (rebinding defence);
  mutations require the per-process CSRF token
  (`X-GLM-CSRF`, delivered only in the served page's meta
  tag — never in URLs, logs, or exports) and a matching
  Origin when one is sent. Origin absence is not treated as
  trust; the token always gates.
- **Methods/semantics**: mutations are POST/PUT/DELETE only.
  GET never changes research data. Project deletion needs an
  explicit `confirm=1` after a 409 that reports related
  counts. (The pre-existing `/api/cancel` remains GET: it
  cancels an in-flight search operation, writes nothing
  persistent, and is idempotent.)
- **Bodies**: Content-Length required, per-route caps
  (1 MiB JSON, 25 MiB import, 200 MiB restore), JSON
  Content-Type enforced for JSON routes.
- **Responses**: `Cache-Control: no-store` (already global),
  CSP `default-src 'self'; connect-src 'self'`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  no-referrer`, `X-Frame-Options: DENY`.
- **Provenance**: verification states are computed from
  server-side snapshots, never accepted from clients
  (dedicated forgery tests in tests/test_b7_web_api.py).
- **SQL**: parameterised queries everywhere; the local
  search escapes LIKE wildcards.
- **XSS**: the workspace UI writes stored strings with
  `textContent`/DOM APIs only; a Playwright test stores an
  `<img onerror>`/`<script>` note and asserts nothing
  executes and no elements are created. Existing UI paths
  escape via `esc()` and `safeHref()` (https only).
- **Files**: data directory 0700, database file 0600.
  `.gitignore` covers `*.db*`, WAL/SHM, backups and export
  directories. Exports never contain tokens, API keys or
  absolute server paths; import rejects secret-like fields.
- **Privacy**: no telemetry, no external calls from the
  workspace layer except user-initiated re-verification and
  comparisons, which reuse the existing budgeted HTTP
  stack. Note text is never logged.
- **Restore**: integrity + schema checks before touching
  the live database; the current database is backed up
  first; corrupt candidates leave the live DB untouched.

Residual risks (documented, accepted for a local tool):
the CSRF token is readable by any script running on the
legitimate page itself (same-origin trust); the database is
not encrypted at rest — the backup/restore doc says so
plainly.

## Final review corrections (v1.0.0b7 release)

- CSRF protection is session-bound, not a single
  per-process token: each page load issues an HttpOnly
  session cookie (SameSite=Strict, 12 h) and that session's
  own CSRF token. Reads require the session; mutations
  require the session token.
- Host is parsed strictly and its port must equal the
  server port; Origin is checked on all requests including
  reads; `Origin: null` is rejected.
- Threat model: a local single-user application. Defended:
  cross-site request forgery and DNS rebinding against the
  user's browser, malformed requests. NOT provided:
  authentication/authorisation for public deployment.
  Another process running as the same OS user can read the
  database file; 0600 file permissions are the boundary.
  The database is not encrypted.
