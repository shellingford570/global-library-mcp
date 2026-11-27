# b9 final review — fixes, verification, release record

Date: 2026-11-27. Scope: the final security review of the
v1.0.0b9 candidate (PR #20, candidate head
`1b16f2d34b5c113178a0965dd7b73335cef064f4`). This document
records what was reproduced, what was changed, how the fixed
build was verified, and what remains blocked. It supersedes
the candidate report where they differ. Nothing in this round
created a tunnel, connected ChatGPT, issued an API key, or
sent any real library text to an external AI.

## 1. Findings reproduced against the candidate head

All reproduced in-process against `1b16f2d` before fixing:

1. **Rights negation treated as allowance.**
   `classify_item_rights("This work is not in the public
   domain")` returned `public_domain`; `"Not public domain;
   all rights reserved"` also returned `public_domain`.
2. **Per-user HTTP budget not on the send path.**
   `BudgetedTransport.handle_async_request` contained no
   reference to the external runtime or any per-user guard;
   the only enforcement was the post-hoc `note_http()`, which
   cannot prevent an overrun.
3. **Guard denials bypassed the audit log.** `_run_tool`
   invoked `_guard` before its `try` block, so consent /
   budget / revocation denials raised before any audit event
   was written.
4. **Search consent never checked a library.** The search
   guard was invoked with an empty library id
   (`_run_tool(ctx, "search", "", go)`), so per-library
   consent could not apply to the search path at all.
5. **stdio blanket consent.** The stdio self-consent was
   granted with a 10-year TTL across all data classes.

## 2. What changed (commits on `feat/external-mcp-readiness-b9`)

- `e331f01` fix(b9): final review - 5-tool profile, send-path
  budget, session binding. (http.py send guard; control.py
  rewrite; server.py rewrite; grammars.py; auth JWKS loader
  and RS256/ES256-only outside local test mode; rights
  negation + OCR-rights separation; audit HMAC + rotation;
  doctor additions.)
- `b55c008` test(b9): real-path integration suite, OS
  isolation check, eval rework. (tests/test_b9_integration.py
  + fixtures; eval/b9_os_isolation_check.py;
  eval/b9_security_eval.py 164-case edition;
  ExternalRuntime.untrack per-call fix; CI external-mcp job
  runs the integration suite; `more_available` rename.)
- This document's commit: docs corrections (5 tools, 164
  cases, continuation removal) across the b9 doc set,
  CHANGELOG and implementation status.

### 2.1 Profile reduction (permitted by the review)

The external profile now exposes exactly **5 tools**, all
readOnlyHint: `search`, `fetch`, `list_libraries`,
`get_library_capabilities`, `get_document_rights`. Removed:
`verify_original_reference`, `get_allowed_excerpt`,
`research_materials_external`, `compare_documents_external`.
Scopes reduced to 4 (`catalog:search`, `metadata:read`,
`libraries:read`, `references:read`). The local full (15)
and research (14) profiles are unchanged. Continuation
tokens were **deleted**; search pagination is a plain
`offset` bound to nothing but the query.

### 2.2 Real HTTP budget on the send path

`BudgetedTransport` now consults a per-user `UserHttpGuard`
(via a contextvar installed by the external runtime)
immediately before each send — after semaphore acquisition,
inside the transport. The guard atomically reserves one
attempt under a lock: **200 upstream attempts/hour per user,
100/hour per host**, counted for retries, redirects,
failures and cancellations, never refunded, and never
charged for cache hits (the transport is below the cache).
Received bytes are noted after buffering. A stale guard
(user revoked, or consent generation changed since the call
started) refuses the send. The old post-hoc
`check_http_budget` / `note_http` API is gone.

### 2.3 Consent

Per-library, per-data-class, server-side consent, enforced
on every path: search checks **both** `bibliographic` and
`search_terms_upstream` for each target library — targets
without consent are excluded before any query is built,
reported as `excluded_no_consent`, and never contacted;
fetch and rights reads check their classes per document.
Grant / revoke / expiry are implemented in `ConsentStore`
with a per-user **generation counter** (any grant or revoke
invalidates in-flight guards); optional JSON persistence
via `GLM_EXTERNAL_CONSENT_FILE` (atomic replace; an
unreadable file means no consent). The stdio self-consent
is now **12 hours, process-bound**, and excludes excerpts.

### 2.4 Revocation, deadlines, re-authorisation

Every call runs under ONE absolute 90-second deadline that
includes queueing. Per-user concurrency is 2 with at most 4
waiting (`QueueFull` beyond that). In-flight calls are
tracked **per call**; `revoke_user` cancels them, and the
guard is re-checked after queueing, before every HTTP send,
and again before the response is returned — a call that
finishes after revocation returns `access_revoked` with its
payload voided. (The eval caught an early version of this
tracking the host task across calls; tracking is now
registered and unregistered per call.)

### 2.5 Session binding

An ASGI middleware binds each `mcp-session-id` to the
SHA-256 of the Authorization header that created it. A
different principal presenting the same session id gets
**403 `session_binding_mismatch`** on POST, GET (SSE) and
DELETE alike; DELETE by the owner drops the binding. Caps:
200 sessions total, 10 per principal.

### 2.6 Document ids and identity

`external/grammars.py` validates record ids against a
per-library grammar for all 13 adapter libraries (structural
gate, not an existence proof), refusing `..`, URLs (except
Gallica's ark URL form) and control characters. Fetch
re-checks the returned payload's `(library_id, record_id)`
against the request and raises `document_identity_mismatch`
on any difference; `identity_verified` is computed by the
external layer, never trusted from the payload.

### 2.7 Responses and rights

Typed allowlist projections to nested levels (unchanged in
shape, re-verified); original URLs pass structural
validation (https only, no credentials, port 443/None only,
no localhost, non-global IP literals refused). The final
MCP response is capped so that the SDK's duplicated
(text + structured) serialization stays within **256 KiB**.
Rights classification now evaluates **negations first**
("not / never / no longer … public domain", Japanese
negations, "all rights reserved"), and metadata rights are
separated from OCR rights: an excerpt would additionally
require the matrix row's `ocr_rights == "allowed"`, and
every shipped matrix row now carries `ocr_rights: "unknown"`
— so **no real library can pass the text-transfer path even
with the excerpt switch on**, and a single environment
variable cannot enable real-library text sending (the
excerpt tool itself no longer exists).

### 2.8 Authentication, OAuth, JWKS

External HTTP mode **cannot** run without authentication:
both the CLI and direct app construction refuse
`require_auth=False` outside local test mode. HS256 is
accepted only when a test secret AND local test mode are
both set; otherwise only RS256/ES256 via JWKS. The JWKS
loader validates the URL as a fetch destination, uses a
5 s timeout, a 256 KiB cap, a 10-minute cache, and no
redirects or credentials. `resource_url` must equal the
token audience outside local test mode. Real-HTTP tests
cover an RS256 flow with a generated keypair and pinned
JWKS, HS256 rejection under the production-style config,
and expired-token rejection.

### 2.9 SSRF and research-data protection

The external runner refuses to start if the DNS pre-check
is disabled and forces it on otherwise. **DNS pinning is
NOT implemented**; the residual DNS-rebinding window is a
stated production blocker (see §5), not a solved problem.
Workspace isolation was verified at the OS level with
synthetic data: `eval/b9_os_isolation_check.py` runs the
external profile as OS user `nobody` (via setpriv) with a
root-only canary workspace file present on disk; the server
served the 5 tools through the official SDK stdio client,
the OS denied it the canary file, and the canary never
surfaced. AST import checks are reported as code hygiene
only, never as isolation proof.

### 2.10 Audit log

Denials (auth, scope, consent, budget, revocation) are now
recorded, because the guard runs inside the audited region.
Events carry real HTTP attempts and received bytes from the
send guard, the final response size, and terminal status
including `cancelled`. User ids are pseudonymised with
HMAC-SHA256 (operator key via
`GLM_EXTERNAL_AUDIT_HMAC_KEY`; without one, an ephemeral
per-process key is used and the doctor says so). The
in-memory mirror is capped at 1,000 events; the file
rotates at 5 MiB to a single backup (≈10 MiB bound). No
search text, OCR text, tokens or secrets are recorded.

## 3. Verification results (this machine, 2026-11-27)

- **pytest (full suite): 570 tests, 0 failures, 0 errors,
  0 skipped.** (b8 baseline 525 + 39 b9 unit/HTTP + 6
  integration.)
- **Playwright search spec: 17 passed.** **Workspace
  journeys: 6 passed, 0 skipped** (workspace-mode server,
  fixed fixtures).
- **Real-path integration suite**
  (`tests/test_b9_integration.py`): official MCP SDK client
  → real Streamable HTTP server (RS256) → real auth /
  consent / runtime → real LibraryService → real
  BudgetedTransport → fixed upstream fixtures, with
  transport-level request counting. Measured results:
  - upstream requests to a non-consented library: **0**
  - HTTP budget overruns: **0** (sends stop exactly at the
    cap: 5 sends for a cap of 5 across 7 searches)
  - additional sends after revocation: **0** (a revoked
    principal is refused at the auth layer; an in-flight
    call is voided and initiates no later sends)
  - session-reuse successes by another principal: **0**
  - forbidden-text / canary / secret leaks: **0**
  - final responses over 256 KiB: **0**
  - wrongly certified document/page matches: **0**
    (identity certified exactly for the requested document;
    a grammar-valid nonexistent id errors without certifying)
  - 6/6 tests passed in ~25 s.
- **Synthetic security evaluation** (kept distinct from the
  integration suite): **164/164 cases passed**
  (`eval/results-b9-security.json`); all mandatory zero
  metrics are 0 **within that synthetic set**, which is not
  a proof of no vulnerabilities.
- **OS isolation check: PASS** (see §2.9).
- **Official connection conditions re-verified**
  (2026-11-27, official OpenAI pages only, no substantive
  change): full custom MCP = Business / Enterprise-Edu;
  Pro = read/fetch only; **Plus: no documented route —
  unconfirmed**; Secure MCP Tunnel limits 600 req/min,
  10 MiB, 120 s absolute deadline, no separate tunnel fee
  stated; Responses API MCP is a separate developer route.
  Details: docs/b9-openai-compatibility.md.

## 4. CI

(CI results for the final head are recorded here after the
push; the merge gate below requires all mandatory jobs —
test, workspace, docker-playwright, external-mcp,
external-security — to succeed. workspace-live is
informational.)

## 5. Production connection blockers (unchanged honesty)

This release is an external-MCP **readiness** edition. It is
not connected to ChatGPT and is not production-operable.
Blockers, each requiring separate approval or work:

1. **DNS pinning unimplemented** — rebinding window remains;
   production needs pinning or managed egress.
2. **No production identity provider** — only the
   resource-server validation shape exists; no IdP contract.
3. **No documented ChatGPT Plus route** for custom MCP.
4. **Real-library text transfer is disabled by
   construction** (no excerpt tool; matrix OCR rights
   unknown for every library).
5. Finna / Digi live verification status is unchanged from
   b8 (Finna 403 from this network; Digi unverified on real
   material) — nothing here re-verifies them.
6. No Secure MCP Tunnel exists; creating one, connecting
   ChatGPT, issuing keys, or contracting an OAuth service
   each need separate approval.

## 6. Merge / release gate

Per the review instruction, PR #20 may be merged (Merge
Commit) only if the §39 conditions are met and all
mandatory CI jobs succeed on the final head; the annotated
tag `v1.0.0b9` and the bilingual Pre-release follow only
after master CI succeeds. The merge, master SHA, tag target
and Release URL are recorded in an addendum to this file
once they exist.
