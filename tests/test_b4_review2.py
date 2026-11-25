"""b4 final-review fixture tests: tool descriptions, research
profile safety (incl. the real CLI process), loopback-only HTTP,
Host/Origin rejection, Retry-After gate extension + send window,
wire vs decoded byte accounting."""
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp.http import (
    BudgetedTransport,
    HttpBudget,
    _host_gates,
    _note_retry_after,
    use_budget,
)
from global_library_mcp.adapters.base import AdapterError


@pytest.mark.asyncio
async def test_all_tools_have_descriptions():
    from global_library_mcp import mcp_server

    tools = await mcp_server.mcp.list_tools()
    assert len(tools) == 15
    for tool in tools:
        assert tool.description and len(tool.description) >= 40, tool.name


def test_profile_allowlist_applies_and_fails_loudly():
    from mcp.server.fastmcp import FastMCP

    from global_library_mcp.mcp_server import RESEARCH_PROFILE_TOOLS, _apply_profile

    server = FastMCP("profile-test")
    for name in sorted(RESEARCH_PROFILE_TOOLS | {"research_question"}):
        server.tool(name=name)(lambda: {})
    _apply_profile(server, "research")  # must not raise

    server2 = FastMCP("profile-test-2")
    for name in sorted(RESEARCH_PROFILE_TOOLS | {"research_question", "sneaky_extra"}):
        server2.tool(name=name)(lambda: {})
    with pytest.raises(RuntimeError):
        _apply_profile(server2, "research")


@pytest.mark.asyncio
async def test_answer_guard_under_research_profile(monkeypatch):
    monkeypatch.setenv("GLM_MCP_PROFILE", "research")
    service = _LS(httpx.AsyncClient())
    result = await service.answer("テストの質問", mode="generative")
    assert result["status"] == "disabled_in_research_profile"


@pytest.mark.asyncio
async def test_cli_research_profile_process():
    """The real CLI entry point: 14 tools, research_question calls
    rejected, even with LLM-related env vars present."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    script = Path(sys.executable).with_name("global-library-mcp")
    env = dict(os.environ)
    env["LLM_ENABLED"] = "true"
    env["GLM_LLM_PROVIDER"] = "openai"
    params = StdioServerParameters(command=str(script), args=["mcp", "--profile", "research"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert len(names) == 14
            assert "research_question" not in names
            rejected = await session.call_tool("research_question", {"query": "x"})
            assert rejected.isError


def test_loopback_validation():
    from global_library_mcp.mcp_server import _validate_bind_host

    for ok in ("127.0.0.1", "::1", "localhost"):
        _validate_bind_host(ok)
    for bad in ("0.0.0.0", "192.168.1.10", "example.com", "::"):
        with pytest.raises(SystemExit):
            _validate_bind_host(bad)


def test_cli_refuses_non_loopback():
    import subprocess

    script = Path(sys.executable).with_name("global-library-mcp")
    proc = subprocess.run(
        [str(script), "mcp", "--transport", "streamable-http", "--host", "0.0.0.0"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "non-loopback" in (proc.stderr + proc.stdout)


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_gate_extension_during_wait_is_honoured():
    """While one request waits out a gate, another 429 extends it;
    the waiting request must re-check before sending (b4 S5)."""
    _host_gates.clear()
    sent_at: list[float] = []
    started = time.monotonic()

    class T(BudgetedTransport):
        async def _send(self, request):
            sent_at.append(time.monotonic() - started)
            if len(sent_at) == 1:
                return httpx.Response(429, headers={"retry-after": "1"}, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

    async def extend_gate():
        await asyncio.sleep(0.5)
        _note_retry_after("example.org", 1.0)  # as another 429 would

    async with httpx.AsyncClient(transport=T()) as client:
        with use_budget(HttpBudget(10, 10)):
            first = await client.get("https://example.org/a")
            assert first.status_code == 429
            task = asyncio.create_task(extend_gate())
            second = await client.get("https://example.org/b")
            await task
            assert second.status_code == 200
    # Gate was 1.0s, extended at +0.5s to ~1.5s: the second send must
    # have waited for the EXTENDED deadline, not the original one.
    assert sent_at[1] >= 1.4
    _host_gates.clear()


@pytest.mark.asyncio
async def test_gate_beyond_send_window_refuses_to_send():
    _host_gates.clear()
    _note_retry_after("example.org", 3600)
    calls = {"n": 0}

    class T(BudgetedTransport):
        async def _send(self, request):
            calls["n"] += 1
            return httpx.Response(200, request=request)

    async with httpx.AsyncClient(transport=T()) as client:
        with use_budget(HttpBudget(10, 10)):
            with pytest.raises(AdapterError):
                await client.get("https://example.org/x")
    assert calls["n"] == 0  # never sent
    _host_gates.clear()


@pytest.mark.asyncio
async def test_wire_and_decoded_bytes_are_distinct():
    import gzip

    payload = gzip.compress(b"B" * 100_000)

    class T(BudgetedTransport):
        async def _send(self, request):
            return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=ChunkStream([payload]), request=request)

    budget = HttpBudget(max_requests=10, per_host_max=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=T()) as client:
            resp = await client.get("https://example.org/data")
            assert len(resp.content) == 100_000
    stats = budget.stats()
    assert stats["bytes_received"] == 100_000
    assert stats["bytes_on_wire"] == len(payload)
    assert stats["bytes_on_wire"] < stats["bytes_received"]


@pytest.mark.asyncio
async def test_http_host_origin_rejected():
    """DNS-rebinding protection: foreign Host / Origin are refused
    by the SDK before any tool runs."""
    import threading

    import uvicorn
    from mcp.server.fastmcp import FastMCP

    from global_library_mcp.mcp_server import local_transport_security

    # A fresh FastMCP instance: a streamable-HTTP session manager
    # can only run once per instance, and the connectivity test
    # already consumed the shared server's. The middleware under
    # test is configured by the same helper run() uses.
    probe = FastMCP("security-probe")
    probe.settings.host = "127.0.0.1"
    probe.settings.port = 8792
    probe.settings.transport_security = local_transport_security()

    @probe.tool()
    def ping() -> str:
        """Ping."""
        return "pong"

    app = probe.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=8792, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        async with httpx.AsyncClient(timeout=10) as raw:
            bad_host = await raw.post("http://127.0.0.1:8792/mcp", json=body, headers={"Host": "evil.example.com", "Accept": "application/json, text/event-stream"})
            assert bad_host.status_code == 421  # SDK DNS-rebinding middleware: Misdirected Request
            bad_origin = await raw.post("http://127.0.0.1:8792/mcp", json=body, headers={"Origin": "http://evil.example.com", "Accept": "application/json, text/event-stream"})
            assert bad_origin.status_code == 403
    finally:
        server.should_exit = True
        thread.join(timeout=10)
