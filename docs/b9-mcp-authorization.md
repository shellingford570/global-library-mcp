# b9 — MCP authorization design

Implements the resource-server side of the MCP authorization
specification (2025-11-25; research in
docs/b9-openai-compatibility.md section 4).

## Model

- The external server is an OAuth 2.1 **resource server**.
  Token issuance stays with an external authorization server;
  this project registers none and issues no real credentials.
- Discovery: RFC 9728 Protected Resource Metadata is served at
  `/.well-known/oauth-protected-resource/mcp`, naming the
  configured authorization server and the real scope set.
  Unauthenticated requests receive **401** with a
  `WWW-Authenticate: Bearer resource_metadata="…", scope="…"`
  challenge.
- Validation (PyJWT, a maintained library — no hand-rolled
  cryptography): signature against the AS JWKS (pinned document
  or JWKS URL), `iss` exact match, `aud` exact match (the
  token must be bound to this resource), `exp` required and
  enforced, non-empty `sub` required. Algorithms: RS256/ES256
  with JWKS; HS256 only for the synthetic local test signer,
  and only when local test mode is explicitly on.
- Fail-closed startup: authenticated HTTP mode refuses to
  start without issuer, audience and a key source; the
  synthetic HS secret outside local test mode is a startup
  error; `GLM_EXTERNAL_DISABLED=1` blocks the profile entirely.

## Scopes (brief section 18)

| Scope | Tools |
|---|---|
| `libraries:read` | list_libraries, get_library_capabilities |
| `catalog:search` | search |
| `metadata:read` | fetch |
| `references:read` | get_document_rights |
| `originals:verify` | REMOVED in the final review (tool dropped) |
| `excerpts:read` | REMOVED in the final review (tool dropped) |
| `comparisons:read` | REMOVED in the final review (tool dropped) |

There is deliberately **no workspace scope**. Scopes are
checked server-side on every tools/call — hiding a tool from
tools/list is never the enforcement mechanism. The SDK
middleware's `required_scopes` is intentionally empty (it
would demand every scope on every request); the PRM document
advertises the full set, and per-tool enforcement happens in
the tool guard. Token audience binding is validated by the
token validator itself, so the SDK's resource check is
explicitly disabled (`validate_token_resource=False`).

## Verified locally (synthetic AS)

Valid token; expired; wrong audience; wrong issuer; forged
signature; `alg=none`; empty subject; missing scope per tool;
revoked user (valid token, server-side revocation wins);
401 challenge and PRM document over real Streamable HTTP
(tests/test_b9_http_security.py, eval/b9_security_eval.py).

## Not production claims

The local synthetic authorization server (HS256 test signer)
is a **test fixture**, not a production IdP. A real deployment
must choose a maintained authorization server, configure its
JWKS URL, use Authorization Code + PKCE with refresh tokens
(`offline_access`) per the AS's discovery document, and treat
client registration (pre-registration / CIMD / DCR) as that
AS's configuration — all separately approved steps.
