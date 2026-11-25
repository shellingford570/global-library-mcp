# ChatGPT接続準備ガイド / ChatGPT Connectivity Preparation

Status as of 2026-11-25: **prepared, NOT connected.** No tunnel has
been created, no ChatGPT workspace has been configured, and no
credentials have been issued. Starting any of those requires a
separate approval.

Sources (OpenAI official, checked 2026-11-25):

- Help Center: "Connecting custom MCP servers in ChatGPT"
  https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- Developer docs: "Secure MCP Tunnel"
  https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- Developer docs: "Connect and test your plugin"
  https://developers.openai.com/plugins/deploy/connect-chatgpt

## What ChatGPT requires (verified from the help article)

- Custom MCP connections are created from **ChatGPT web** (not
  mobile), under **Plugins → Add custom MCP server**.
- The connection is either a **public HTTPS MCP endpoint URL** or a
  **Tunnel** (an existing Secure MCP Tunnel chosen by `tunnel_id`).
  A local server cannot be connected directly.
- Plan / permission matrix:
  - **Business**: only workspace admins/owners can create and
    publish custom MCP server plugins.
  - **Enterprise/Edu**: admins/owners create and publish; RBAC can
    grant selected members permission to create connections.
  - **Pro**: full MCP is not available; Pro users can connect
    custom MCP servers with **read/fetch permissions only**, and
    can build apps with the Apps SDK.
- `search`/`fetch` tools are **no longer required** for connected
  servers (company knowledge includes only apps with search/fetch
  functionality, which is a separate consideration).
- OAuth is supported; providers must issue refresh tokens
  (`offline_access`) or users must re-authenticate on expiry.

## Option A — Secure MCP Tunnel (preferred candidate)

How it works (official guide): OpenAI hosts a tunnel endpoint.
`tunnel-client` runs inside your network, long-polls OpenAI over
**outbound HTTPS only** (`api.openai.com:443`, or
`mtls.api.openai.com:443` with control-plane mTLS), forwards each
JSON-RPC request to the private MCP server, and posts responses
back. No inbound ports, no public exposure of the server.

Fit with this project:

- `tunnel-client` can front a server over **stdio or HTTP**. Our
  existing stdio server works unchanged
  (`tunnel-client init --mcp-command "global-library-mcp mcp --profile research"`);
  **no relay server needs to be built.**
- Requirements: a `tunnel_id` from Platform tunnel settings; a
  runtime API key for `tunnel-client`; tunnel permissions
  (create/edit: Tunnels **Read + Manage**; run/select: **Read +
  Use**); the tunnel must be **associated with the target ChatGPT
  workspace** or it will not appear in ChatGPT.
- Default service limits (official): 600 requests/minute per
  tunnel+app; serialized request/response envelope **10 MiB**;
  pending queue 1,000; **request deadline 120 seconds absolute**,
  including queue time.
- **Deadline consequence for this server:** Quick searches and
  single-document tools fit comfortably; Standard investigations
  measured at ~7–64 s fit; Deep investigations can exceed 120 s
  and would be cut off by the tunnel. For ChatGPT use, prefer the
  `research` profile and Quick/Standard modes.
- Data scope: tool-call arguments and tool results traverse
  OpenAI's hosted tunnel endpoint and are processed by ChatGPT.
  That means **the user's search terms and the fetched material
  (bibliographic records and OCR excerpts) are sent to OpenAI**.
  The Research Beta itself calls no external LLM. App-level
  compliance logging still applies on the ChatGPT side; tunnel
  transport events are not emitted as ChatGPT app events (per
  the official guide).
- **Rights warning:** library materials are NOT all public
  domain or openly licensed. Rights are per item (public domain,
  CC variants, in-copyright, unknown). An external-facing
  profile must apply rights-based transmission limits - for
  example, full text only for public-domain/CC0 items, short
  excerpts for other openly licensed items, and bibliographic
  data only when rights are unknown. It must never be assumed
  that rights-unknown material may be transmitted freely.
- Cost: the tunnel is an OpenAI Platform feature and runtime API
  keys are involved. **No claim is made that it is free**; any
  Platform or API charges must be confirmed in the Platform
  console before creation. Nothing here has been purchased.

Prepared connection procedure (NOT executed):

1. In Platform tunnel settings, create a tunnel and associate it
   with the target ChatGPT workspace (requires Tunnels
   Read + Manage).
2. Issue a restricted runtime API key (Tunnels Read + Use).
3. On the host that runs this server, install `tunnel-client`
   from the Platform download link / `openai/tunnel-client`
   releases; `tunnel-client init --sample sample_mcp_stdio_local
   --profile glm-local --tunnel-id <tunnel_id> --mcp-command
   "global-library-mcp mcp --profile research"`.
4. `tunnel-client doctor --profile glm-local --explain`, then
   `tunnel-client run --profile glm-local` and confirm readiness
   in its local `/ui`.
5. In ChatGPT (web) → Plugins → Add custom MCP server →
   Connection: **Tunnel** → select the tunnel → review the risk
   warning → Create as a plugin.
6. Make one safe representative tool call (e.g.
   `research_materials` in quick mode) and confirm the result
   before calling the setup complete.

## Option B — Authenticated public HTTPS endpoint

Run the Streamable HTTP transport behind a public HTTPS reverse
proxy with authentication (OAuth or equivalent). ChatGPT connects
to the public URL directly.

- Pros: no Platform tunnel dependency; also the required shape
  for any future public plugin submission.
- Cons: the server becomes internet-facing — it needs the full
  remote hardening this project has deliberately not taken on yet
  (authentication in front of the endpoint, per-user budgets and
  authorization, TLS, rate limiting, abuse controls). The built-in
  Streamable HTTP transport is bound to localhost with
  DNS-rebinding protection and has **no built-in authentication**;
  it must not be exposed directly.
- This option is a deployment project of its own and is out of
  scope until separately approved.

## Before any real connection (separate approval required)

Connecting for real is a separate task. Before it starts, each
of the following must be verified, not assumed:

1. **Permissions**: the target ChatGPT account/workspace plan
   and the creator's role satisfy the matrix above; Platform
   tunnel permissions (Read + Manage to create, Read + Use to
   run) are granted by the organization owner/RBAC admin.
2. **Rights policy**: per-rights transmission limits for OCR
   excerpts and full text are implemented in the external
   profile (see the rights warning above) and tested.
3. **Response size**: tool responses stay within the tunnel's
   10 MiB serialized envelope, including for large OCR fetches.
4. **Deadline**: the tunnel's 120-second absolute request
   deadline also requires a matching **server-side per-tool
   execution limit** for the external profile, so a tool call
   fails cleanly on our side instead of being cut off mid-flight
   (Quick/Standard modes, capped investigation budgets).
5. **Authentication**: the tunnel's runtime key handling and
   the ChatGPT-side app authentication are configured and
   reviewed; the local HTTP transport remains loopback-only and
   is never exposed directly.
6. **Cost**: Platform/tunnel billing is confirmed in the
   console; nothing is assumed free.

## Recommendation

Option A (tunnel) with the `research` profile: the server stays
private, the existing stdio entry point is reused as-is, and the
read-only tool surface matches what Pro/Business/Edu connections
can consume. Execution awaits separate approval (tunnel creation,
API key issuance, and workspace configuration are all outside the
current approval scope).
