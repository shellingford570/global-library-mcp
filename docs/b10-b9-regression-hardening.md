# b10 Stage 0 — b9 external-profile regression hardening

This document records the Stage 0 work of v1.0.0b10: the
residual external-connection risks listed in section 4 of the
b10 brief, each **reproduced against the released b9 code
(master `66f2867`) before being fixed**, the fix applied on
`feat/advanced-research-intelligence-b10`, and the regression
tests that now pin the behaviour (`tests/test_b10_stage0.py`,
29 tests). The b9 tag and Release are unchanged. External
connection remains prohibited; section 4.12 blockers (DNS
pinning, production IdP, outbound network isolation) are
untouched by this stage and still stand.

Reproduction harness: `b10-stage0-repro.py` (kept with the
project's evaluation scratch records). Initial result against
b9 code: 6 of 7 scripted findings reproduced directly; §4.1 was
confirmed in a follow-up run with the documented import order
(the first attempt masked it behind the known http circular
import).

## 4.1 Consent / token expiry — REPRODUCED, FIXED

Reproduction: grant consent with a 0.25 s TTL, create a send
guard, wait past expiry. `ConsentStore.has()` correctly
returned False, but `guard.reserve()` still SENT (attempts=1)
and `guard.stale()` returned False — both checked only the
consent generation, which natural expiry never changes. The
access token's expiry was not tracked by the guard at all.

Fix (`external/control.py`, `external/server.py`):
`ConsentStore.current(user, generation)` is now the single
authorisation-currency check — record present (or consistently
absent for generation 0), not revoked, generation unchanged,
and **not expired**. `UserHttpGuard` snapshots the token expiry
(`Principal.expires_at`, passed in `_run_tool`) and
`token_expired()` joins `stale()`. `_guard_reserve` refuses
sends when consent expired/changed, when the token expired, or
when the guard holds no consent snapshot at all. All three
checkpoints (post-queue stale check, pre-send reserve,
pre-return stale check) now evaluate expiry.

## 4.2 Per-data-class consent — CONFIRMED BY INSPECTION, FIXED

`search` required only `bibliographic` + `search_terms_upstream`
consent, yet its projection always included the rights block
and the reference URL; `fetch` required only `bibliographic`
yet projected rights, reference and image URLs.

Fix: a new `images` data class joins the consent vocabulary.
Projections take the caller's granted classes for the item's
library (`ConsentStore.granted_classes`) and gate each field on
its own class — rights block on `rights`, reference URL on
`references`, image URL on `images` — independently of the
bibliographic gate and of the transfer-policy decision. The
search response cache key now includes the granted-class
signature (entries were already consent-generation bound).

## 4.3 Send-level library binding — CONFIRMED BY INSPECTION, FIXED

The send guard received only a host name; nothing bound a wire
send to the library whose operation it belonged to.

Fix: `http.current_library` contextvar (set by
`LibraryService` around every per-library search and document
fetch) is passed by `BudgetedTransport` to
`guard.reserve(host, library_id=...)`. The guard refuses a
send whose library is outside the consent record's library
set, whatever host it targets — shared hosts and future
routing changes cannot reach an unconsented library. Redirect
hops re-enter the transport and are re-reserved and re-checked
individually. Host-level allowlists remain the adapters'
responsibility, as before.

## 4.4 User-state capacity and budget history — REPRODUCED, FIXED

Reproductions: (a) with every tracked user "in-flight",
`_state()` added a 1001st user over the 1000 cap; (b) evicting
a user's state erased their `http_times`, silently refunding
their hourly budget; `revoke_user` likewise dropped counters.

Fix: budget history lives in a separate `_BudgetLedger` that
eviction and revocation never touch inside its measurement
window (entries are dropped only once fully aged out). The
tracked-user cap is strict: at capacity with nobody evictable,
new users are refused with `BudgetExceeded("user_capacity")`
(mapped to a denial in `_run_tool`), for both runtime state
and the ledger. Revocation records are kept (in-memory set;
durable revocations persist in the consent file). The
per-process nature of all counters — and the consequence that
multi-process deployments need a single process or an external
coordinator — is stated in the `control.py` module docstring
as a production constraint.

## 4.5 MCP session capacity — CONFIRMED BY INSPECTION, FIXED

The b9 middleware capped only the binding table (per token
hash): at capacity the SDK still created sessions (they then
failed on first use), one user with several tokens multiplied
the cap, and bindings never expired.

Fix (`_SessionBindingMiddleware` rework): bindings carry a
last-seen timestamp with an 1800 s idle TTL and are swept on
traffic; a session-less POST is refused with 429
`session_capacity` **before** the SDK runs when the global cap
is reached, so session creation itself is refused, not merely
left unbound; caps are enforced per user (resolved from the
bearer token via the validator) as well as per token. Stated
limit: this layer cannot see a session the SDK creates through
a path that never returns an id to it — the pre-creation
refusal is the control, and it is documented as such in the
class docstring. Binding mismatches and capacity refusals are
audited (§4.11).

## 4.6 External response type safety — REPRODUCED, FIXED

Reproductions: `clean_text({"note": "CANARY"})` returned the
stringified dict, canary included; the capabilities projection
copied allowlisted keys raw (a nested dict under `rights`
crossed verbatim) — and its key list did not match the
registry's real field names at all, so the tool returned
almost nothing.

Fix: `clean_text` accepts only strings and finite numbers;
containers and booleans are dropped. A new typed
`models.project_capabilities` projects the registry's real
shape field by field (cleaned strings, cleaned string lists,
boolean-only capability map, string-only status map); unknown
and nested fields are dropped. Nested-canary tests cover both.

## 4.7 External reference URLs — REPRODUCED, FIXED

Reproductions: `clean_url` accepted
`https://evil.example.com/doc?api_key=...` and the decimal-IP
host `https://2130706433/doc`.

Fix: when the owning library is known, the host must be in
`models.REFERENCE_HOSTS` for that library (unknown library →
no outbound reference); credential-shaped query parameters
(token/api_key/signature/session/… names, or JWT-shaped
values) refuse the URL; digit/hex-only hosts that do not parse
as IP literals are refused as disguised numeric addresses.
Reference URLs and image URLs remain separate fields, now
also separated by consent class (§4.2).

## 4.8 Document identity — CONFIRMED BY INSPECTION, FIXED

`get_document` in the adapters writes the sanitised **request**
id back as `record_id` (audited in NDL, Internet Archive and
LoC), so the b9 "identity verified" flag certified an echo;
and a payload with no identifier at all still received a
rights decision from `get_document_rights`.

Fix: `_fetch_document` classifies identity as
`upstream_confirmed` (payload identifiers match AND the
adapter marked them `identity_source == "upstream"`),
`request_echo` (match, unmarked) or `missing` (no identifier).
Only `upstream_confirmed` sets `document_identity_verified`;
the state itself is exposed in fetch and rights responses.
`get_document_rights` refuses with
`document_identity_unverified` when the state is `missing`.
The Internet Archive adapter now genuinely earns the upstream
mark: it compares the metadata payload's own `identifier`
field with the requested one. Other adapters remain
`request_echo` until their payloads are audited the same way —
reported honestly, not papered over.

## 4.9 Consent file and revocation handling — REPRODUCED, FIXED

Reproduction: a persisted row with `expires_at: NaN` loaded as
permanent consent (`has()` True), because Python's `json`
accepts NaN and NaN comparisons never expire. The file was
also written with umask-default permissions and no type
validation.

Fix: strict per-row validation on load (types, data classes ⊆
known set, library-id grammar, finite expiry, boolean revoked,
non-negative integer generation) — a malformed row drops only
that user's consent, never creates any; unknown policy
versions fail closed; symlinked consent paths are refused for
load and save; the file is written with a `version` field and
owner-only (0600) permissions via an atomic replace, under a
lock. Revocations persist in the file as before. The stdio
12-hour self-consent is documented in `run_external` as a
LOCAL-use grant only, never an external-transfer permission
(b10 4.9); it remains process-bound and unpersisted.

## 4.10 Startup validation — CONFIRMED BY INSPECTION, FIXED

`validate_startup` ran on the CLI path, and
`external_http_app` gated parts of it, but
`build_external_server` itself applied none of it.

Fix: `build_external_server` now applies the
transport-agnostic gates (kill switch, DNS-check refusal) and
raises on violation, so direct construction fails closed under
the same incomplete configuration the CLI refuses. The HTTP
app's own gates (auth required, key source present) are
unchanged.

## 4.11 Audit and final response size — CONFIRMED, FIXED

The audit `response_bytes` was the projected payload's JSON
size; SDK-auth-layer and session-layer rejections were not
audited at all.

Fix: audit events now carry `response_bytes_basis`
(`"projected_json"` for tool calls) so the measured quantity
is never conflated with the SDK-serialised response (the
256 KiB cap continues to be enforced on the projected payload
with the factor-of-two margin from the b9 final review).
Token-validation failures are recorded by `_SdkTokenVerifier`
(tool `(auth)`) and session-binding/capacity rejections by the
session middleware (tool `(session)`), pseudonymously and
without content.

## Verification (Stage 0)

- `tests/test_b10_stage0.py`: 29 new tests, all passing.
- Full pytest: **599 passed, 0 failed, 0 skipped** (b9
  baseline 570 + 29).
- b9 synthetic security evaluation: **164/164** re-run against
  the fixed code.
- b9 test files (external, integration, HTTP security): 45
  passed, including the real-path integration suite — the IA
  fetch still certifies identity, now via the genuine upstream
  identifier comparison.
- Paid API calls: 0. External connections attempted: none.

## Still standing (unchanged by this stage)

- DNS pinning unimplemented; no production IdP; Plus route
  unconfirmed; real-library text transfer disabled by
  construction (§4.12 production blockers).
- Adapters other than Internet Archive still return
  `request_echo` document identity.
- All external-profile counters are per-process (§4.4 note).

---

## Final-review addendum (2026-11-28)

This document describes the b10 candidate as submitted in
PR #21 (head `dc8d794`). The external final review reproduced
defects in several of the areas covered here; the fixes,
re-measurements and corrected claims are recorded in
`docs/b10-final-review.md`, which supersedes this document
wherever the two disagree (notably: semantic search is now
wired into the real service path as an opt-in ranking mode;
`authority_verified` can no longer be reached from the local
lexicon alone; editions are candidates; independent-source
counting was replaced; the Docker CI job is fixture-mandatory
with the live smoke separated as an informational job).
