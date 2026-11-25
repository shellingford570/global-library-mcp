from __future__ import annotations

import argparse

from global_library_mcp.mcp_server import run as run_mcp
from global_library_mcp.web.server import run as run_web


def main() -> None:
    parser = argparse.ArgumentParser(description="Global Library MCP")
    sub = parser.add_subparsers(dest="command", required=True)
    mcp_cmd = sub.add_parser("mcp", help="Run the MCP server (stdio or Streamable HTTP)")
    mcp_cmd.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    mcp_cmd.add_argument("--host", default="127.0.0.1")
    mcp_cmd.add_argument("--port", type=int, default=8001)
    mcp_cmd.add_argument("--profile", choices=["full", "research"], default="full")
    web = sub.add_parser("web", help="Run the API and Web UI")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "mcp":
        run_mcp(transport=args.transport, host=args.host, port=args.port, profile=args.profile)
    else:
        run_web(args.host, args.port)


if __name__ == "__main__":
    main()
