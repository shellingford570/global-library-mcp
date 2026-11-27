# b9 — OpenAI / MCP official-specification research

Checked: **2026-11-27**. Sources are the official pages listed
per section; statements below are what those pages said on the
check date. Anything not confirmed there is marked unknown.

## 1. Connecting custom MCP servers in ChatGPT

Source: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

- Custom MCP server connections and **full MCP support** are
  available to **ChatGPT Business** and **Enterprise/Edu**
  customers, on **ChatGPT web**. Admins/owners create, test and
  publish connections for the workspace; Enterprise/Edu admins
  can delegate creation via RBAC.
- **Pro**: users can build apps with the Apps SDK; full MCP is
  Business/Enterprise-Edu only, but **Pro users can connect
  custom MCP servers with read/fetch permissions**.
- **Plus / Go / Free**: the page does **not** list these plans
  as able to connect custom MCP servers. **No official route
  for ChatGPT Plus was confirmed on 2026-11-27** — this is
  stated plainly rather than assumed.
- Connecting on **mobile is not possible (web only)**; using
  an installed app in chats is separate from creating the
  connection.
- A local/private MCP server **cannot be connected directly**;
  use Secure MCP Tunnel.
- `search`/`fetch` tools are **no longer required** for
  connected servers; company knowledge includes only apps with
  search/fetch functionality. Deep research can use custom
  apps for **read/fetch actions only**.
- After an admin approves a connection, ChatGPT uses a
  **frozen snapshot** of the server's tools; later server-side
  changes apply only after an admin reviews and republishes.
- OAuth connections should advertise `offline_access` (or the
  provider equivalent) or ChatGPT may lose access when the
  original authorisation expires.

Source: https://developers.openai.com/api/docs/guides/custom-mcp-server

- Supported MCP protocols: **SSE and Streamable HTTP**.
- Authentication options: **OAuth**, **no authentication**, or
  mixed. OAuth supports static credentials, Client ID Metadata
  Documents (CIMD; `none` and `private_key_jwt`), and DCR.
- **Read-only detection respects `readOnlyHint`**; tools
  without the hint are treated as write actions and require
  confirmation by default. External-profile tools therefore
  all carry `readOnlyHint: true` (an annotation, never a
  substitute for server-side authorisation).
- Server `instructions` field: first 512 characters should be
  self-contained.

## 2. Secure MCP Tunnel

Source: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

- `tunnel-client` runs inside the network that can reach the
  private MCP server and opens an **outbound-only HTTPS** path
  to `api.openai.com:443` (`/v1/tunnel/*`), or
  `mtls.api.openai.com:443` when control-plane mTLS is
  configured. No inbound ports; the MCP server needs no public
  listener. The client long-polls, forwards JSON-RPC to the
  local server (stdio command or HTTP URL) and posts responses
  back.
- Requirements: a **`tunnel_id`** from Platform tunnel
  settings, a **runtime API key** for tunnel-client, and a
  reachable MCP server.
- Permissions (Platform organisation level): creating/editing
  a tunnel requires Tunnels **Read + Manage**; running
  tunnel-client or selecting the tunnel when creating an app
  requires **Read + Use**. Tunnel permissions and ChatGPT
  workspace permissions are separate; a tunnel is associated
  with one or more Platform organisations and/or ChatGPT
  workspaces, and must be associated with the target workspace
  to appear there.
- Default limits: 1,000 tunnels per workspace/organisation;
  **600 MCP requests/minute** per tunnel + calling app;
  **10 MiB** maximum serialised request or response;
  **120-second absolute request deadline** (queue time counts;
  progress notifications do not reset it); 1,000 pending
  requests per tunnel.
- The tunnel does **not** support public plugin submission;
  public plugins require a stable public HTTPS endpoint.
- tunnel-client is distributed from Platform tunnel settings
  or https://github.com/openai/tunnel-client (keep runbooks on
  the latest-release URL). It provides `init`, `doctor
  --explain`, `run`, and a local admin UI at `/ui`.
- A tunnel is a transport path only: it does not by itself
  grant application-level authorisation or make any content
  safe to send. Our external rights policy and authorisation
  layer remain mandatory behind it.

## 3. Responses API MCP (a separate route)

Source: https://developers.openai.com/api/docs/guides/tools-connectors-mcp

- The Responses API `mcp` tool type takes `server_url` for a
  public remote server or `tunnel_id` for a tunnelled private
  server; an OAuth access token can be passed via
  `authorization`. Transports: Streamable HTTP or SSE.
- Approvals: `require_approval` (`always` / `never` / per-tool
  object) produces `mcp_approval_request` items; approvals are
  per tool call. `allowed_tools` filters which tools are
  imported.
- Pricing: you pay only for tokens used importing tool
  definitions and making tool calls; **no additional per-call
  fee** for the MCP tool itself. Model token prices are the
  Platform's published per-model rates (not reproduced here).
- This route is distinct from connecting a custom MCP server
  inside ChatGPT (§1) and is **not** exercised in b9 (no real
  API calls); it is covered by local mock verification only.

## 4. MCP authorization specification

Source: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization

- HTTP transports: the MCP server is an OAuth 2.1 **resource
  server**. Servers **MUST** implement OAuth 2.0 Protected
  Resource Metadata (RFC 9728) with at least one
  `authorization_servers` entry, discoverable via the
  `WWW-Authenticate` `resource_metadata` parameter on 401
  responses and/or the well-known URI.
- Authorization servers **MUST** implement OAuth 2.1 and
  provide RFC 8414 Authorization Server Metadata or OpenID
  Connect Discovery. Clients **MUST** support both discovery
  mechanisms.
- Client registration: pre-registration, Client ID Metadata
  Documents (SHOULD), or Dynamic Client Registration (MAY,
  backwards compatibility).
- Scope selection follows least privilege; the `scope`
  parameter of the 401 challenge is authoritative for the
  current request.
- stdio transports do **not** use this flow; credentials come
  from the environment.
- b9 implements the resource-server side (metadata document,
  401 challenge, token validation for issuer/audience/expiry/
  scope/signature against the AS's JWKS) and verifies it
  against a local synthetic authorization server. No external
  OAuth service is registered in b9.

## 5. Plans and pricing (checked 2026-11-27)

Source: https://chatgpt.com/pricing/

- Plans: Free, Go, Plus, Pro, Business, Enterprise. Paid
  plans are priced per user per month; monthly plans exist
  for Go/Plus/Business, monthly and annual for
  Business/Enterprise. The page renders prices dynamically;
  exact figures are therefore recorded as **see the official
  page** rather than reproduced from other sources.
- Connection capability by plan (from §1, the authoritative
  source for connections): full MCP — Business,
  Enterprise/Edu; read/fetch custom connections — Pro;
  Plus/Go/Free — not listed (unconfirmed; treated as no
  official route until OpenAI documents one).
- Secure MCP Tunnel pricing: the tunnel guide states no
  separate tunnel fee; Platform usage is the API key's normal
  Platform billing. Recorded as: tunnel-specific fee
  **unknown/not stated** on the checked pages; Responses API
  MCP use costs model tokens only (§3).
- Library APIs used by this project remain free of charge in
  b9 (no keys issued, no paid calls).

## 6. Consequences for the b9 design

- The external profile targets Streamable HTTP (and stdio for
  local clients), all tools `readOnlyHint: true`, with the
  OpenAI `search`/`fetch` names kept for company-knowledge /
  deep-research compatibility even though they are no longer
  mandatory.
- Internal limits are set below the tunnel's: response cap
  256 KiB (tunnel allows 10 MiB) and a 90-second tool deadline
  (tunnel deadline is 120 s including queue time).
- Because Plus has no confirmed custom-MCP route, the
  connection guide (docs/chatgpt-connection*.md) presents
  Business/Enterprise-Edu and Pro read/fetch as the documented
  paths and says so explicitly.
