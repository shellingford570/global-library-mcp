"""b3 (Sections 6/7/9/10): real HTTP budget, search deadline and
circuit breaker, quick mode. All fixture-based; no live network."""
import asyncio
import time

import httpx
import pytest

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.http import (
    BudgetedTransport,
    BudgetExceeded,
    HttpBudget,
    current_http_budget,
)
from global_library_mcp.models import SearchResult
from global_library_mcp.service import LibraryService


class _CannedTransport(BudgetedTransport):
    def __init__(self):
        super().__init__()
        self.sent = 0

    async def _send(self, request):
        self.sent += 1
        return httpx.Response(200, json={"ok": True}, request=request)


@pytest.mark.asyncio
async def test_http_budget_caps_actual_requests():
    """Fixed fixture: with a budget of 3, the 4th wire request is
    refused BEFORE it is sent — retries/redirects included, since
    every attempt passes through the transport."""
    transport = _CannedTransport()
    budget = HttpBudget(max_requests=3, per_host_max=10)
    token = current_http_budget.set(budget)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            for _ in range(3):
                resp = await client.get("https://example.org/x")
                assert resp.status_code == 200
            with pytest.raises(BudgetExceeded):
                await client.get("https://example.org/x")
    finally:
        current_http_budget.reset(token)
    assert transport.sent == 3
    assert budget.stats()["requests"] == 3
    assert budget.stats()["exceeded"] is True


@pytest.mark.asyncio
async def test_http_budget_per_host_cap():
    transport = _CannedTransport()
    budget = HttpBudget(max_requests=100, per_host_max=2)
    token = current_http_budget.set(budget)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://a.example/1")
            await client.get("https://a.example/2")
            with pytest.raises(BudgetExceeded):
                await client.get("https://a.example/3")
            resp = await client.get("https://b.example/1")
            assert resp.status_code == 200
    finally:
        current_http_budget.reset(token)


class _SlowAdapter(LibraryAdapter):
    def __init__(self):
        pass

    library_id = "slow"
    library_name = "Slow"
    supports_in_document_search = False

    async def search(self, query, limit=10):
        await asyncio.sleep(30)
        return []


class _FailingAdapter(LibraryAdapter):
    library_id = "bad"
    library_name = "Bad"
    supports_in_document_search = False

    def __init__(self):
        self.calls = 0

    async def search(self, query, limit=10):
        self.calls += 1
        raise RuntimeError("boom")


def _service_with(adapter):
    svc = LibraryService.__new__(LibraryService)
    svc.adapters = {adapter.library_id: adapter}
    svc.default_libraries = [adapter.library_id]
    svc._breaker = {}
    svc.last_search_timings = {}
    svc.client = None
    return svc


@pytest.mark.asyncio
async def test_search_deadline_cuts_slow_library(monkeypatch):
    monkeypatch.setenv("GLM_SEARCH_DEADLINE_S", "0.2")
    svc = _service_with(_SlowAdapter())
    started = time.monotonic()
    resp = await svc.search("anything")
    elapsed = time.monotonic() - started
    assert elapsed < 5
    assert resp.results == []
    assert any("deadline" in e["error"] for e in resp.errors)


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures():
    adapter = _FailingAdapter()
    svc = _service_with(adapter)
    for _ in range(3):
        await svc.search("q")
    assert adapter.calls == 3
    resp = await svc.search("q")
    assert adapter.calls == 3  # breaker open: not called again
    assert any("circuit open" in e["error"] for e in resp.errors)


@pytest.mark.asyncio
async def test_quick_mode_never_fetches_pages():
    """Quick Search is bibliographic only: no in-document search,
    no page fetch, whatever the adapters support."""
    calls = {"in_doc": 0}

    class Stubborn(LibraryAdapter):
        def __init__(self):
            pass

        library_id = "stub"
        library_name = "Stub"
        supports_in_document_search = True

        async def search(self, query, limit=10):
            return [SearchResult(library_id="stub", library_name="Stub", record_id="r1", title="T", landing_url="https://example.org/r1")]

        async def search_in_document(self, record_id, query, limit=20):
            calls["in_doc"] += 1
            raise AssertionError("quick mode must not fetch")

    svc = _service_with(Stubborn())
    svc._search_cache = {}
    svc.cache_stats = {"search_hits": 0, "search_misses": 0}
    result = await svc.research_materials("q", libraries=["stub"], mode="quick")
    assert result["mode"] == "quick"
    assert len(result["materials"]) == 1
    assert result["materials"][0]["access_state"]["ocr_fetched"] is False
    assert calls["in_doc"] == 0
