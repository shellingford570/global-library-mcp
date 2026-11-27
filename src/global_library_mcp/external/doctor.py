"""`global-library-mcp doctor` (b9 brief section 32).

Configuration and readiness diagnostics for the external
profile. Default mode performs NO network access. Secret
values are never printed - only whether a setting is present.
`--live` performs one real catalogue search through the
standard service and is strictly opt-in.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any


def run_doctor(live: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("python", sys.version_info >= (3, 11),
        f"Python {platform.python_version()}")
    try:
        import mcp

        add("mcp_sdk", True, f"mcp SDK importable ({mcp.__file__.split('/')[-3]})")
    except Exception as exc:  # noqa: BLE001
        add("mcp_sdk", False, f"import failed: {type(exc).__name__}")

    # Profiles and the external allowlist (built in-process).
    try:
        from global_library_mcp.external.server import (
            EXTERNAL_TOOLS,
            build_external_server,
        )

        server, _ctx = build_external_server()
        import asyncio

        names = {t.name for t in asyncio.run(server.list_tools())}
        add("external_allowlist", names == set(EXTERNAL_TOOLS),
            f"{len(names)} tools, exact allowlist match")
    except Exception as exc:  # noqa: BLE001
        add("external_allowlist", False, f"build failed: {type(exc).__name__}")

    try:
        from global_library_mcp import mcp_server

        import asyncio

        full = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        add("local_profiles", len(full) == 15,
            f"full profile exposes {len(full)} tools (research: 14)")
    except Exception as exc:  # noqa: BLE001
        add("local_profiles", False, f"check failed: {type(exc).__name__}")

    # Rights policy posture.
    from global_library_mcp.external.control import ExternalConfig
    from global_library_mcp.external.transfer_matrix import MATRIX

    cfg = ExternalConfig.from_env()
    add("excerpt_switch", True,
        "external excerpt transfer is "
        + ("ENABLED by GLM_EXTERNAL_EXCERPTS=1" if cfg.excerpt_enabled
           else "disabled (default)"))
    add("transfer_matrix", len(MATRIX) == 13,
        f"{len(MATRIX)} libraries with recorded transfer terms")

    # Auth configuration: presence only, never values.
    add("auth_config",
        bool(cfg.issuer and cfg.audience
             and (cfg.jwks_url or cfg.test_hs_secret)),
        "issuer/audience/JWKS configured: "
        f"issuer={'yes' if cfg.issuer else 'no'}, "
        f"audience={'yes' if cfg.audience else 'no'}, "
        f"jwks={'yes' if cfg.jwks_url else 'no'}, "
        f"synthetic_test_secret={'yes' if cfg.test_hs_secret else 'no'}")
    add("kill_switch", True,
        "external profile disabled by GLM_EXTERNAL_DISABLED=1"
        if cfg.disabled else "external profile not disabled")

    # HTTP budget defaults.
    from global_library_mcp import http as http_mod

    budget = http_mod.HttpBudget()
    add("http_budget", True,
        f"max_requests={budget.max_requests}, per_host_max={budget.per_host_max}, "
        f"max_response_bytes={budget.max_response_bytes}")
    add("dns_precheck", True,
        "GLM_DNS_CHECK=" + os.environ.get("GLM_DNS_CHECK", "(unset; "
        "the external profile enables it by default at startup)"))

    # Workspace separation: the external package must not
    # IMPORT the workspace package (AST-level check, so this
    # file's own diagnostic strings are not self-flagged).
    import ast
    import pathlib

    pkg = pathlib.Path(__file__).resolve().parent
    offenders = []
    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = ",".join(a.name for a in node.names)
            if "workspace" in module and "global_library_mcp" in module:
                offenders.append(path.name)
    add("workspace_separation", not offenders,
        "external package has no workspace imports"
        if not offenders else f"offenders: {offenders}")

    # API-key presence (names only) and tunnel configuration.
    add("api_keys", True,
        "EUROPEANA_API_KEY " + ("is set" if os.environ.get("EUROPEANA_API_KEY")
                                else "is not set (Europeana stays unavailable)"))
    add("tunnel", True,
        "no Secure MCP Tunnel is configured by this tool; tunnel "
        "creation is a separately approved step (docs/secure-mcp-tunnel.md)")

    report: dict[str, Any] = {
        "ok": all(c["ok"] for c in checks),
        "network_used": False,
        "checks": checks,
    }
    if live:
        report["live"] = _live_check()
        report["network_used"] = True
    return report


def _live_check() -> dict[str, Any]:
    """One explicit, user-invoked live catalogue search."""
    import asyncio

    async def go():
        from global_library_mcp.http import make_client
        from global_library_mcp.service import LibraryService

        client = make_client(timeout=30)
        try:
            service = LibraryService(client)
            response = await service.search("Darwin", ["loc"], 3)
            return {"ok": True, "results": len(response.results),
                    "errors": len(response.errors or [])}
        finally:
            await client.aclose()

    try:
        return asyncio.run(go())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def main(live: bool = False) -> int:
    import json

    report = run_doctor(live=live)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1
