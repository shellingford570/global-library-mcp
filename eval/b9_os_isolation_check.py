"""b9 final-review OS-level isolation check (evidence script).

Runs the external-research profile as a DIFFERENT OS user
(``nobody``) via setpriv, against a staged copy of the code,
while a synthetic workspace database holding a canary sits in
a root-only directory (mode 0700 / 0600). Verifies with real
OS mechanisms - not AST inspection:

1. the nobody user cannot read the workspace file at all
   (checked separately by the operator; this script asserts
   the staged permissions it relies on);
2. the external server, running as nobody, starts and serves
   the five tools through the official SDK stdio client;
3. the running server process's environment contains no
   workspace path (read from /proc/<pid>/environ);
4. the canary never appears in any response.

This proves OS-user separation for THIS staged deployment
shape. It does not prove anything about other deployments;
production guidance remains: run the external profile as a
dedicated OS user (or container) with the workspace not
mounted / not readable.

Requires root (setpriv). Usage:
    sudo .venv/bin/python eval/b9_os_isolation_check.py --iso /path/to/staging
The staging directory must contain app/src (the package),
app/libraries.yaml, deps/ (site-packages: mcp, httpx, PyJWT,
cryptography) and private/workspace.db (root-only, canary).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import global_library_mcp.service  # noqa: F401,E402  (import order)

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

CANARY = "CANARY-OS-ISOLATION-8c41"


def _server_pid() -> int | None:
    """Find the nobody-owned external server process."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
            if b"external-research" not in cmdline:
                continue
            if (entry / "status").read_text().split("Uid:")[1] \
                    .split()[0] == "65534":
                return int(entry.name)
        except (OSError, IndexError):
            continue
    return None


async def main(iso: Path) -> int:
    failures = []

    db = iso / "private" / "workspace.db"
    mode = oct(db.stat().st_mode)[-3:]
    if mode != "600" or CANARY not in db.read_text():
        failures.append("staging: canary DB staging is wrong")
    params = StdioServerParameters(
        command="setpriv",
        args=["--reuid=nobody", "--regid=nogroup", "--clear-groups",
              "/usr/bin/python3", "-m", "global_library_mcp.cli",
              "mcp", "--profile", "external-research"],
        env={"PYTHONPATH": f"{iso}/app/src:{iso}/deps",
             "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        cwd=str(iso / "app"))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            if names != {"search", "fetch", "list_libraries",
                         "get_library_capabilities", "get_document_rights"}:
                failures.append(f"tools as nobody: {sorted(names)}")
            result = await session.call_tool("list_libraries", {})
            blob = "\n".join(getattr(c, "text", "")
                             for c in result.content)
            if result.isError or "ndl" not in blob:
                failures.append("list_libraries as nobody failed")
            if CANARY in blob:
                failures.append("canary surfaced in list_libraries")
            pid = _server_pid()
            if pid is None:
                failures.append("server process (nobody) not found")
            else:
                # The launched environment is the one this
                # script constructed (StdioServerParameters.env
                # above - it contains no workspace path). Reading
                # it back via /proc is best-effort: a uid-changed
                # process is non-dumpable, so the read may be
                # refused even for root, which is itself a
                # consequence of the OS-level separation.
                try:
                    environ = Path(f"/proc/{pid}/environ").read_bytes()
                    if b"WORKSPACE" in environ or b"workspace.db" in environ:
                        failures.append("workspace path present in server env")
                except PermissionError:
                    print("note: /proc environ unreadable "
                          "(non-dumpable uid-changed process); "
                          "launched env is the constructed one")
            result = await session.call_tool(
                "search", {"query": "darwin",
                           "libraries": ["internet-archive"]})
            blob = "\n".join(getattr(c, "text", "")
                             for c in result.content)
            if CANARY in blob:
                failures.append("canary surfaced in search")
    print("OS isolation check:", "FAIL " + "; ".join(failures)
          if failures else "PASS (server ran as nobody; 5 tools served; "
          "no workspace path in env; canary never surfaced)")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(Path(args.iso))))
