"""b3.1 regression tests for the external review findings:
atomic HTTP budget under concurrency, streaming response caps,
Retry-After handling, MCP tool execution, server-side cancel,
IA restriction re-check. All fixture-based; no live network."""
import asyncio
import gzip
import time

import httpx
import pytest

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import (
    BudgetedTransport,
    BudgetExceeded,
    HttpBudget,
    _retry_after_seconds,
    current_http_budget,
    get_json,
    use_budget,
)
from global_library_mcp.models import SearchResult


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False
        self.iterated = False

    async def __aiter__(self):
        self.iterated = True
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class ScriptedTransport(BudgetedTransport):
    """_send replays a script: each entry is a callable(request)->Response
    or an exception instance to raise."""

    def __init__(self, script):
        super().__init__()
        self.script = list(script)
        self.sent = 0

    async def _send(self, request):
        self.sent += 1
        step = self.script.pop(0) if self.script else (lambda r: httpx.Response(200, json={"ok": True}, request=r))
        if isinstance(step, BaseException):
            raise step
        result = step(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result


def ok(request):
    return httpx.Response(200, json={"ok": True}, request=request)


@pytest.mark.asyncio
async def test_atomic_budget_under_concurrency():
    """Remaining budget 1, eight concurrent requests: exactly one
    is sent; the rest are refused BEFORE sending."""
    transport = ScriptedTransport([ok] * 20)
    budget = HttpBudget(max_requests=1, per_host_max=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            async def one():
                try:
                    await client.get("https://example.org/x")
                    return "sent"
                except BudgetExceeded:
                    return "refused"
            results = await asyncio.gather(*(one() for _ in range(8)))
    assert results.count("sent") == 1
    assert results.count("refused") == 7
    assert transport.sent == 1
    assert budget.stats()["requests"] == 1


@pytest.mark.asyncio
async def test_atomic_per_host_cap_under_concurrency():
    transport = ScriptedTransport([ok] * 20)
    budget = HttpBudget(max_requests=100, per_host_max=1)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            async def one(url):
                try:
                    await client.get(url)
                    return "sent"
                except BudgetExceeded:
                    return "refused"
            results = await asyncio.gather(
                one("https://a.example/1"), one("https://a.example/2"), one("https://b.example/1")
            )
    assert results.count("sent") == 2
    assert transport.sent == 2


@pytest.mark.asyncio
async def test_timeout_and_connect_failure_are_counted():
    transport = ScriptedTransport([httpx.TimeoutException("slow"), httpx.ConnectError("down")])
    budget = HttpBudget(max_requests=10, per_host_max=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.TimeoutException):
                await client.get("https://example.org/slow")
            with pytest.raises(httpx.ConnectError):
                await client.get("https://example.org/down")
    assert budget.stats()["requests"] == 2


@pytest.mark.asyncio
async def test_cancelled_attempt_is_counted():
    async def slow(request):
        await asyncio.sleep(30)
        return ok(request)

    transport = ScriptedTransport([slow])
    budget = HttpBudget(max_requests=10, per_host_max=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            task = asyncio.create_task(client.get("https://example.org/slow"))
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert budget.stats()["requests"] == 1


@pytest.mark.asyncio
async def test_redirect_hops_are_counted():
    def redirect(request):
        return httpx.Response(302, headers={"location": "https://example.org/final"}, request=request)

    transport = ScriptedTransport([redirect, ok])
    budget = HttpBudget(max_requests=10, per_host_max=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            resp = await client.get("https://example.org/start")
            assert resp.status_code == 200
    assert budget.stats()["requests"] == 2
    assert transport.sent == 2


@pytest.mark.asyncio
async def test_budgets_do_not_mix_between_concurrent_users():
    transport = ScriptedTransport([ok] * 20)

    async def user(budget, n):
        with use_budget(budget):
            async with httpx.AsyncClient(transport=transport) as client:
                for _ in range(n):
                    await client.get("https://example.org/x")
        return budget.stats()["requests"]

    b1, b2 = HttpBudget(10, 10), HttpBudget(10, 10)
    r1, r2 = await asyncio.gather(user(b1, 3), user(b2, 5))
    assert (r1, r2) == (3, 5)


@pytest.mark.asyncio
async def test_streaming_cap_aborts_and_closes():
    stream = ChunkStream([b"x" * 600_000, b"y" * 600_000])
    transport = ScriptedTransport([lambda r: httpx.Response(200, stream=stream, request=r)])
    budget = HttpBudget(max_requests=10, per_host_max=10, max_response_bytes=1_000_000)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/big")
    assert stream.closed is True
    assert budget.stats()["requests"] == 1


@pytest.mark.asyncio
async def test_content_length_precheck_skips_reading():
    stream = ChunkStream([b"z" * 100])
    transport = ScriptedTransport([
        lambda r: httpx.Response(200, headers={"content-length": "30000000"}, stream=stream, request=r)
    ])
    budget = HttpBudget(max_requests=10, per_host_max=10, max_response_bytes=25_000_000)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/huge")
    assert stream.iterated is False
    assert stream.closed is True


@pytest.mark.asyncio
async def test_gzip_bomb_caught_by_decoded_size():
    payload = gzip.compress(b"A" * 2_000_000)
    assert len(payload) < 100_000
    stream = ChunkStream([payload])
    transport = ScriptedTransport([
        lambda r: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=stream, request=r)
    ])
    budget = HttpBudget(max_requests=10, per_host_max=10, max_response_bytes=1_000_000)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/bomb")


@pytest.mark.asyncio
async def test_cumulative_byte_cap():
    small = lambda r: httpx.Response(200, content=b"1234", request=r)
    transport = ScriptedTransport([small, small, small])
    budget = HttpBudget(max_requests=10, per_host_max=10, max_response_bytes=25_000_000, max_total_bytes=10)
    with use_budget(budget):
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://example.org/1")
            await client.get("https://example.org/2")
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/3")
    assert budget.stats()["bytes_received"] == 8


class _StubHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, params=None, headers=None):
        self.calls += 1
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_retry_after_honoured_and_counted():
    req = httpx.Request("GET", "https://example.org/x")
    client = _StubHttpClient([
        httpx.Response(429, headers={"retry-after": "0"}, request=req),
        httpx.Response(200, json={"done": True}, request=req),
    ])
    data = await get_json(client, "https://example.org/x", attempts=2)
    assert data == {"done": True}
    assert client.calls == 2


@pytest.mark.asyncio
async def test_retry_after_beyond_deadline_no_retry():
    req = httpx.Request("GET", "https://example.org/x")
    client = _StubHttpClient([httpx.Response(429, headers={"retry-after": "3600"}, request=req)])
    with pytest.raises(AdapterError):
        await get_json(client, "https://example.org/x", attempts=2, max_retry_wait=10)
    assert client.calls == 1


def test_retry_after_parsing():
    assert _retry_after_seconds("5") == 5.0
    assert _retry_after_seconds("0") == 0.0
    assert _retry_after_seconds("") is None
    assert _retry_after_seconds(None) is None
    from email.utils import formatdate

    future = formatdate(time.time() + 120, usegmt=True)
    parsed = _retry_after_seconds(future)
    assert parsed is not None and 100 < parsed <= 120


# --- MCP tool execution (Section 2) ---

class _StubAdapter(LibraryAdapter):
    def __init__(self):
        pass

    library_id = "stub"
    library_name = "Stub"
    supports_in_document_search = True

    async def search(self, query, limit=10):
        return [SearchResult(library_id="stub", library_name="Stub", record_id="r1", title="Stub Book", landing_url="https://example.org/r1")]

    async def get_document(self, record_id):
        return {"id": record_id, "title": "Stub Book", "published": 1900}

    async def search_in_document(self, record_id, query, limit=20):
        return {"matches": {"list": [{"id": "r1@1"}]}}

    async def get_page_text(self, page_id):
        return {
            "page_id": page_id,
            "contents": "発電は明治時代に始まった重要な技術である。水力発電の開発が進み、送電網が各地へ広がった。",
            "verified_mapping": True,
            "image_url": "https://example.org/img.jpg",
            "source": "stub",
        }


@pytest.mark.asyncio
async def test_mcp_tools_execute_consecutively_with_shared_service():
    """The b3.1 review found research_materials could not execute
    at all (async-with on a non-context-manager). All tools must
    run, consecutively, over one shared service/client."""
    import httpx as _httpx

    from global_library_mcp import mcp_server
    from global_library_mcp.service import LibraryService

    client = _httpx.AsyncClient()
    service = LibraryService(client)
    service.adapters = {"stub": _StubAdapter()}
    service.default_libraries = ["stub"]
    previous = mcp_server._shared
    mcp_server._shared = (client, service)
    try:
        r1 = await mcp_server.research_materials("発電", libraries=["stub"], limit=5, mode="quick")
        assert r1["mode"] == "quick"
        assert len(r1["materials"]) == 1
        r2 = await mcp_server.search_catalog("発電", library_id="stub", limit=5)
        assert r2["results"]
        r3 = await mcp_server.get_page_text("stub", "r1@1")
        assert "発電" in (r3.get("contents") or "")
        r4 = await mcp_server.compare_documents(
            [{"library_id": "stub", "record_id": "r1"}, {"library_id": "stub", "record_id": "r1"}],
            aspects=["発電"],
        )
        assert isinstance(r4, dict)
        # the shared client is still usable after all calls
        r5 = await mcp_server.research_materials("発電", libraries=["stub"], limit=5, mode="standard")
        assert r5["mode"] == "standard"
    finally:
        mcp_server._shared = previous
        await client.aclose()


# --- Server-side cancellation (Section 5) ---

@pytest.mark.asyncio
async def test_service_runtime_cancel_stops_only_that_op():
    from global_library_mcp.web.server import ServiceRuntime

    runtime = ServiceRuntime()
    started = asyncio.Event()

    async def slow():
        started.set()
        await asyncio.sleep(60)
        return "done"

    import threading

    results = {}

    def run_named(name):
        try:
            results[name] = runtime.run_op(name, slow())
        except Exception as exc:  # cancelled surfaces here
            results[name] = type(exc).__name__

    ta = threading.Thread(target=run_named, args=("op-a",))
    tb = threading.Thread(target=run_named, args=("op-b",))
    ta.start()
    tb.start()
    await asyncio.sleep(0.5)
    t0 = time.monotonic()
    state = runtime.cancel_op("op-a", wait_s=10)
    stop_s = time.monotonic() - t0
    assert state == "cancelled"
    assert stop_s < 10
    assert runtime.op_state("op-b") == "running"
    assert runtime.cancel_op("op-unknown") == "unknown"
    runtime.cancel_op("op-b", wait_s=10)
    ta.join(timeout=20)
    tb.join(timeout=20)
    assert runtime.op_state("op-b") == "cancelled"


# --- IA restriction re-check (Section 8) ---

@pytest.mark.asyncio
async def test_ia_restricted_change_stops_cached_pages():
    from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter

    adapter = InternetArchiveAdapter(httpx.AsyncClient())
    adapter._pages_cache["item1"] = (adapter._now(), ["page one text"])
    adapter._metadata_cache["item1"] = (
        adapter._now(),
        {"metadata": {"access-restricted-item": "true"}},
    )
    with pytest.raises(AdapterError):
        await adapter._pages("item1")
    assert "item1" not in adapter._pages_cache
