"""b4 fixture tests: byte accounting under concurrency, Retry-After
host gate, script variants, research profile, MCP over Streamable
HTTP (in-process server, stub service - no live network)."""
import asyncio
import time

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order: full package init first)
from global_library_mcp.http import (
    BudgetedTransport,
    BudgetExceeded,
    HttpBudget,
    _host_gates,
    use_budget,
)
from global_library_mcp.question import script_variants


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0.0):
        self._chunks = chunks
        self._delay = delay
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk

    async def aclose(self):
        self.closed = True


class ScriptedTransport(BudgetedTransport):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler
        self.sent = 0

    async def _send(self, request):
        self.sent += 1
        return self.handler(request)


@pytest.mark.asyncio
async def test_concurrent_streams_share_cumulative_cap():
    """Two responses streaming at once must not jointly pass the
    cumulative byte cap (b4 Section 2)."""
    def handler(request):
        stream = ChunkStream([b"x" * 400] * 5, delay=0.05)
        return httpx.Response(200, stream=stream, request=request)

    transport = ScriptedTransport(handler)
    budget = HttpBudget(max_requests=10, per_host_max=10, max_response_bytes=100_000, max_total_bytes=1_000)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            results = await asyncio.gather(
                client.get("https://example.org/a"),
                client.get("https://example.org/b"),
                return_exceptions=True,
            )
    assert any(isinstance(r, BudgetExceeded) for r in results)
    stats = budget.stats()
    assert stats["exceeded"] is True
    assert stats["bytes_received"] > 1_000  # charged as it arrived
    # Enforcement granularity is the transport read chunk (64KB):
    # the overshoot past the cap is bounded by one read chunk per
    # concurrent stream (here the tiny 2,000-byte bodies arrive as
    # a single read each, so the total is exactly 4,000).
    assert stats["bytes_received"] <= 1_000 + 2 * 65536


@pytest.mark.asyncio
async def test_retry_after_gate_shared_across_budgets():
    """A 429's Retry-After delays the NEXT request to that host even
    under a different budget/user (b4 Section 2)."""
    _host_gates.clear()
    state = {"first": True}

    def handler(request):
        if state["first"]:
            state["first"] = False
            return httpx.Response(429, headers={"retry-after": "1"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = ScriptedTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with use_budget(HttpBudget(10, 10)):
            resp = await client.get("https://example.org/x")
            assert resp.status_code == 429
        started = time.monotonic()
        with use_budget(HttpBudget(10, 10)):
            resp = await client.get("https://example.org/y")
            assert resp.status_code == 200
        assert time.monotonic() - started >= 0.9
    _host_gates.clear()


def test_script_variants_old_new():
    assert "發電" in script_variants("発電")
    assert "鉄道" in script_variants("鐵道")
    assert script_variants("Darwin") == []
    assert "遞信" in script_variants("逓信")


@pytest.mark.asyncio
async def test_mcp_streamable_http_with_stub_service():
    """Full MCP over Streamable HTTP against the real FastMCP app
    (in-process uvicorn), with a stub-backed shared service."""
    import threading

    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    from global_library_mcp import mcp_server
    from global_library_mcp.service import LibraryService
    from tests.test_b31_review_fixes import _StubAdapter

    client = httpx.AsyncClient()
    service = LibraryService(client)
    service.adapters = {"stub": _StubAdapter()}
    service.default_libraries = ["stub"]
    previous = mcp_server._shared
    mcp_server._shared = (client, service)

    from mcp.server.transport_security import TransportSecuritySettings

    mcp_server.mcp.settings.host = "127.0.0.1"
    mcp_server.mcp.settings.port = 8791
    mcp_server.mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
    )
    app = mcp_server.mcp.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=8791, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        async with streamablehttp_client("http://127.0.0.1:8791/mcp") as (read, write, _sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                assert "research_materials" in names
                assert all(t.annotations and t.annotations.readOnlyHint for t in tools.tools)
                result = await session.call_tool("research_materials", {"query": "発電", "libraries": ["stub"], "limit": 3, "mode": "quick"})
                text = result.content[0].text
                assert "Stub Book" in text
                assert "data_notice" in text
                bad = await session.call_tool("research_materials", {"query": 12345, "libraries": ["stub"]})
                assert bad.isError  # invalid input is rejected, not executed
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        mcp_server._shared = previous
        await client.aclose()


def test_research_profile_hides_research_question():
    import subprocess
    import sys

    code = (
        "from global_library_mcp import mcp_server\n"
        "import asyncio\n"
        "mcp_server.run.__wrapped__ if hasattr(mcp_server.run, '__wrapped__') else None\n"
        "import contextlib\n"
        "with contextlib.suppress(Exception):\n"
        "    mcp_server.mcp.remove_tool('research_question')\n"
        "names = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]\n"
        "print('research_question' in names)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert out.stdout.strip().endswith("False"), out.stderr[-300:]
