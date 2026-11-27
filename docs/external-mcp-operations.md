# External MCP — operations

## Running

```sh
global-library-mcp doctor            # no-network diagnostics
global-library-mcp mcp --profile external-research \
  --transport streamable-http --host 127.0.0.1 --port 8002
global-library-mcp mcp --profile external-research --transport stdio
```

Configuration is by environment (presence only is ever
reported): `GLM_EXTERNAL_ISSUER`, `GLM_EXTERNAL_AUDIENCE`,
`GLM_EXTERNAL_JWKS_URL`, `GLM_EXTERNAL_CONTINUATION_SECRET`,
`GLM_EXTERNAL_EXCERPTS` (=1 enables the excerpt path — the
transfer policy still gates every item),
`GLM_EXTERNAL_AUDIT_LOG`, `GLM_EXTERNAL_DISABLED` (=1 kill
switch), `GLM_EXTERNAL_LOCAL_TEST` + `GLM_EXTERNAL_TEST_HS_SECRET`
(synthetic signer; local test mode only).

## Budgets (provisional, brief section 20)

Per user: 2 concurrent operations; 20 tool calls/minute; 200
upstream HTTP attempts/hour; 90-second tool deadline;
256 KiB response cap; excerpt caps 500/1,000/2,000/5,000
chars (single/document/response/session). Stricter upstream
limits (per-library deadlines, HttpBudget, the tunnel's
600 req/min and 120 s) take precedence wherever they are
lower. Users cannot raise any limit via tool arguments.

## Stopping and revocation (brief section 28)

- Stop everything external: `GLM_EXTERNAL_DISABLED=1` and
  restart the external process; local full/research profiles
  are separate processes/profiles and keep running.
- One user: `ExternalRuntime.revoke_user(user_id)` (drops
  consent, budgets, caches, ledgers; their tokens stop
  working at the verifier).
- Consent only: `ConsentStore.revoke(user_id)`.
- Continuation tokens: they expire within 30 minutes and are
  bound to user/scopes/parameters; rotating
  `GLM_EXTERNAL_CONTINUATION_SECRET` invalidates all of them
  at once.
- Tunnel (when one exists): docs/secure-mcp-tunnel.md
  "Stopping and revocation".

## Monitoring

Watch the audit log for: denial spikes (possible probing),
`deadline_exceeded` (upstream slowness or tunnel queueing),
`budget_exceeded` kinds, and error classes. The log format
and privacy rules are in docs/b9-audit-logging.md.
