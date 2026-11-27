# b9 — External MCP threat model

Scope: the external-research profile and its path to
LibraryService. Assets: the user's research data (workspace —
out of the external path by construction), library content
and its rights constraints, credentials (tokens, keys), the
host's network position, and upstream libraries' availability.

| # | Threat | Control | Residual |
|---|---|---|---|
| T1 | Unauthenticated caller uses tools | OAuth 2.1 validation on every HTTP call; 401 + PRM challenge; stdio is local-only | AS compromise is out of scope; choose a maintained AS |
| T2 | Stolen/forged token | Signature (JWKS), iss/aud/exp binding, non-empty sub; server-side revocation list | Token theft within its lifetime; short expiries + revocation mitigate |
| T3 | Token for another resource/audience | Exact audience check in the validator | — |
| T4 | Privilege escalation via tools/list hiding | Per-tool scope check on every call, server-side | — |
| T5 | Consent manufactured by client arguments | Consent exists only server-side; no tool can grant it | Operator must grant deliberately |
| T6 | Rights-violating transfer (OCR text, images) | Independent transfer policy; matrix + item rights + excerpt switch; cumulative caps; full text/binaries never | Terms change over time; matrix needs periodic re-checks (checked date recorded) |
| T7 | Prompt injection from library content | No write/fetch/file tools; typed fields + data notice; server-side enforcement | The external client's own behaviour is outside our control |
| T8 | SSRF to internal services / cloud metadata | URL validation, exact allowlists, DNS pre-check on | DNS rebinding not fully preventable without pinning; production requires managed egress (documented) |
| T9 | Cross-user data contamination | All state keyed by user id; per-user cache; continuation tokens bound to user/scopes/params | — |
| T10 | Budget/DoS abuse (upstream hammering) | Per-user call/HTTP budgets, concurrency 2, deadlines, existing HttpBudget + circuit breaker | A determined authorised user can still consume their own budget |
| T11 | Secret leakage via errors/logs | Stable error codes; audit log content rules; sanitize_error upstream | New exception types must keep messages out of the surface — covered by the catch-all |
| T12 | Workspace disclosure | External package never imports workspace; no DB path/config reaches it; canary tests | A future feature must preserve the import boundary (doctor + tests check it) |
| T13 | Supply chain (tunnel-client, SDK) | Official distribution points only; pinned project dependencies | Follow vendor updates at connection time |
| T14 | Frozen tool snapshot drift in ChatGPT | Connection guide requires verifying the discovered tool list at approval and after any server change | Admin republishing is a ChatGPT-side manual step |

Out of scope for b9 (not built): public hosting, multi-tenant
operation for unrelated users, billing, and any real ChatGPT
connection.
