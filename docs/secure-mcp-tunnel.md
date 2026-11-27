# Secure MCP Tunnel — connection runbook (preparation only)

Status: **prepared, not executed.** No tunnel has been created,
no runtime API key has been issued, and ChatGPT has not been
connected. Creating a tunnel is a separately approved step.
Facts below are from the official guide checked 2026-11-27:
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
(see docs/b9-openai-compatibility.md for the full research).

## What the tunnel is (and is not)

`tunnel-client` runs on a host inside the network that can
already reach the private MCP server. It opens an outbound-only
HTTPS connection to OpenAI (`api.openai.com:443`, path
`/v1/tunnel/*`; `mtls.api.openai.com:443` when control-plane
mTLS is configured), long-polls for queued MCP work, forwards
each JSON-RPC request to the local MCP server (stdio command or
HTTP URL), and posts the response back. The MCP server needs no
public listener and no inbound firewall ports.

The tunnel is a **transport path only**. It does not authorise
users, does not decide what content may be sent, and does not
make an unsafe server safe. Global Library MCP's own layers —
OAuth validation, per-tool scopes, server-side consent,
per-user budgets, and the external transfer rights policy —
remain mandatory behind it.

Service limits (defaults, checked 2026-11-27): 1,000 tunnels
per ChatGPT workspace / Platform organisation; 600 MCP
requests/minute per tunnel + calling application; 10 MiB
maximum serialised request or response; **120-second absolute
request deadline including queue time**; 1,000 pending
requests per tunnel. Our internal caps are stricter (256 KiB
responses, 90-second tool deadline).

## Prerequisites (all require separate approval)

1. A ChatGPT plan with a documented custom-MCP route:
   Business or Enterprise/Edu (full MCP), or Pro (read/fetch
   custom connections). **No official route is documented for
   Plus/Go/Free** as of 2026-11-27.
2. An OpenAI Platform organisation linked to the target
   ChatGPT workspace.
3. Platform permissions: Tunnels **Read + Manage** to create
   or edit the tunnel; Tunnels **Read + Use** to run
   tunnel-client and to select the tunnel when creating the
   app. Granted by the Platform organisation owner / RBAC
   admin at organisation level.
4. ChatGPT workspace permission to add custom MCP servers
   (admin/owner, or RBAC-granted on Enterprise/Edu).
5. A runtime API key for tunnel-client, created with minimum
   scope, stored only in the local environment — never in this
   repository, chat, or command-line arguments.

## Procedure (to execute only after approval)

1. In Platform tunnel settings (platform.openai.com), create a
   tunnel; note its `tunnel_id`. Associate it with the Platform
   organisation AND the target ChatGPT workspace (a tunnel
   associated only with a personal organisation does not
   appear in an Enterprise/Edu workspace).
2. Download `tunnel-client` from the Platform tunnel settings
   page or the latest release at
   https://github.com/openai/tunnel-client (do not pin an old
   release URL in runbooks).
3. Initialise a stdio profile pointing at the external
   profile:

   ```sh
   export CONTROL_PLANE_API_KEY=<entered locally, never pasted into chat>
   tunnel-client init \
     --sample sample_mcp_stdio_local \
     --profile glm-external \
     --tunnel-id tunnel_<id> \
     --mcp-command "global-library-mcp mcp --profile external-research --transport stdio"
   tunnel-client doctor --profile glm-external --explain
   ```

4. Start the local prerequisites first: the external profile
   refuses to start without its authentication configuration
   (see docs/b9-mcp-authorization.md); excerpts stay disabled
   (`GLM_EXTERNAL_EXCERPTS` unset) for the first connection.
5. Run `tunnel-client run --profile glm-external` and confirm
   health in its local admin UI (`/ui`): healthy, ready,
   connected, actively polling.
6. In ChatGPT (web): Plugins → + → Add custom MCP server →
   Connection: **Tunnel** → select the tunnel (or paste the
   `tunnel_id`) → configure the server's OAuth authentication →
   acknowledge the risk warning → Create as a plugin.
7. Verify discovery: the discovered tool list must be exactly
   the 9 external tools (docs/b9-external-mcp-readiness.md).
   If anything else appears, disconnect and investigate —
   ChatGPT freezes the tool snapshot at approval time, so a
   wrong snapshot persists until an admin republishes.
8. First safe call: `list_libraries`, then a bibliographic
   `search` for a public-domain topic. Do not enable excerpt
   transfer for the first connection phase.

## Stopping and revocation (section 28)

- Stop `tunnel-client` (the tunnel stops forwarding
  immediately; queued requests expire).
- Delete or disable the tunnel in Platform tunnel settings;
  remove its workspace association.
- Revoke the runtime API key in Platform settings.
- Remove the plugin in the ChatGPT workspace (admin).
- Locally: set `GLM_EXTERNAL_DISABLED=1` (kill switch),
  revoke users/consents server-side; local full/research
  profiles are unaffected.

## Platform notes

- Windows / macOS / Linux: tunnel-client is distributed for
  all three from the official release page; the vendor's
  onboarding doc is the authoritative per-OS guide. **Not
  verified on any OS by this project yet** — the first
  approved connection attempt must record which OS was used
  and what was observed.
- The tunnel path does not support public plugin submission;
  public plugins require a stable public HTTPS endpoint,
  which this project does not operate.
