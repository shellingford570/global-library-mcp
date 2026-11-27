# Connecting Global Library MCP to ChatGPT — guide

Status: **preparation complete, connection not performed.**
No tunnel exists, no ChatGPT connection has been made, and no
API key has been issued. Each step that creates something
outside this repository needs the separate approval listed at
the end. Official facts checked 2026-11-27; see
docs/b9-openai-compatibility.md for sources.

## 1. What you need

| Requirement | Detail |
|---|---|
| ChatGPT plan | Business or Enterprise/Edu for full MCP; Pro for read/fetch custom connections. **Plus/Go/Free: no official custom-MCP route documented (2026-11-27).** |
| ChatGPT surface | Web (connections cannot be created on mobile) |
| OpenAI Platform account | An organisation linked to the ChatGPT workspace |
| Platform permissions | Tunnels Read + Manage (create), Read + Use (run/select) |
| Workspace permission | Admin/owner (or RBAC grant on Enterprise/Edu) to add and publish custom MCP servers |
| API keys | A tunnel runtime key (minimum scope) — created only at connection time, never stored in this repo |
| Local machine | Runs `tunnel-client` + the external profile; outbound HTTPS to api.openai.com:443 |

## 2. Costs (checked 2026-11-27; see the research doc)

- ChatGPT subscription: per user per month (official pricing
  page; figures are rendered dynamically there and are not
  reproduced here).
- Secure MCP Tunnel: no separate tunnel fee is stated in the
  official guide; the runtime key is a normal Platform key.
- Responses API route (not used for the ChatGPT connection):
  model tokens only, no per-MCP-call fee.
- Library APIs: free; no keys issued by this project.
- If a hosted (public HTTPS) deployment were ever chosen
  instead of a tunnel, hosting/auth-service costs would be
  additional and are currently **unknown** (not surveyed,
  because b9 builds no public server).

## 3. Start the local external profile

```sh
# Authentication configuration (values entered locally):
export GLM_EXTERNAL_ISSUER="https://<your-authorization-server>"
export GLM_EXTERNAL_AUDIENCE="http://127.0.0.1:8002/mcp"
export GLM_EXTERNAL_JWKS_URL="https://<your-authorization-server>/.well-known/jwks.json"
export GLM_EXTERNAL_CONTINUATION_SECRET="<local random secret>"
# Excerpts stay OFF for the first connection:
# (do not set GLM_EXTERNAL_EXCERPTS)

global-library-mcp doctor
global-library-mcp mcp --profile external-research \
  --transport streamable-http --host 127.0.0.1 --port 8002
```

The server binds loopback only, requires a valid bearer token
on every call, and refuses to start when the authentication
configuration is incomplete (fail-closed). The Research
Workspace is not part of this process and is never exposed.

## 4. Create the tunnel

Follow docs/secure-mcp-tunnel.md steps 1–5 (Platform tunnel
settings → tunnel-client init/doctor/run). The MCP command for
the tunnel profile is the stdio form:

```sh
global-library-mcp mcp --profile external-research --transport stdio
```

## 5. Connect in ChatGPT

ChatGPT web → Plugins → + → Add custom MCP server → name it
(e.g. "Global Library MCP") → Connection: Tunnel → select the
tunnel → configure OAuth authentication for the server →
acknowledge the risk warning → Create as a plugin → install
the plugin.

## 6. Verify before first research use

1. The discovered tools are exactly: search, fetch,
   list_libraries, get_library_capabilities,
   get_document_rights, verify_original_reference,
   get_allowed_excerpt, research_materials_external,
   compare_documents_external. Anything else: disconnect.
2. First call: list_libraries.
3. Safe first search: a public-domain topic (e.g. Darwin).
4. Confirm a rights-restricted item returns reference-only
   output (no text) — that is the policy working, not an error.
5. Confirm the workspace is unreachable: no tool can see
   projects, notes, citations, backups or local history.

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Tunnel not listed in ChatGPT | Tunnel not associated with this ChatGPT workspace, or the app creator lacks Tunnels Read + Use |
| 401 from the MCP server | Token issuer/audience mismatch, expired token, or the AS does not advertise offline_access so refresh failed |
| Tool list differs from §6 | Server profile changed after approval; ChatGPT uses a frozen snapshot — an admin must refresh/republish |
| Calls time out | Tunnel deadline is 120 s including queue time; keep tunnel-client healthy and the local server responsive |
| Everything denied with consent_required | Server-side consent has not been granted for that user/data class (by design; tool arguments cannot grant it) |

## 8. Stopping

See docs/secure-mcp-tunnel.md ("Stopping and revocation") and
docs/external-mcp-incident-response.md. Local full/research
profiles keep working when the external connection is stopped.

## 9. Approvals still required before any real connection

1. Creating a Secure MCP Tunnel (Platform).
2. Issuing the tunnel runtime API key.
3. Choosing/contracting the ChatGPT plan and workspace.
4. Registering an OAuth authorization server (or choosing an
   external IdP) and issuing real user credentials.
5. Connecting the plugin in ChatGPT and publishing it to a
   workspace.
6. Enabling excerpt transfer (`GLM_EXTERNAL_EXCERPTS=1`) —
   separately, per deployment, after the bibliographic phase
   is verified.
7. Any public HTTPS deployment instead of a tunnel.

## 10. OS notes

The tunnel-client and this server run on Windows, macOS and
Linux per the vendors' documentation; **no OS has been
verified by this project yet**. The local server itself is
developed and tested on Linux.
