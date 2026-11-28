"""b10 final review section 26: external session middleware -
atomic capacity reservation under concurrent initialization,
per-user pre-enforcement, and last_seen ownership discipline."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import global_library_mcp.service as _LS  # noqa: F401,E402

import asyncio  # noqa: E402

from global_library_mcp.external.server import _SessionBindingMiddleware  # noqa: E402


class _FakeApp:
    """SDK stand-in: every session-less POST 'creates' a session."""

    def __init__(self):
        self.created = 0

    async def __call__(self, scope, receive, send):
        self.created += 1
        sid = f"sess-{self.created}"
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"mcp-session-id", sid.encode())]})
        await send({"type": "http.response.body", "body": b"{}"})


def _scope(auth: str, session: str | None = None, method: str = "POST"):
    headers = [(b"authorization", auth.encode())]
    if session:
        headers.append((b"mcp-session-id", session.encode()))
    return {"type": "http", "method": method, "headers": headers}


async def _call(mw, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"{}"}

    async def send(message):
        sent.append(message)

    await mw(scope, receive, send)
    return sent


def test_concurrent_initialization_never_exceeds_cap():
    async def main():
        app = _FakeApp()
        mw = _SessionBindingMiddleware(app)
        mw.MAX_PER_USER = 3
        mw.MAX_PER_TOKEN = 3
        results = await asyncio.gather(*[
            _call(mw, _scope("Bearer tok-a")) for _ in range(10)])
        statuses = []
        for sent in results:
            start = [m for m in sent if m["type"] == "http.response.start"]
            statuses.append(start[0]["status"] if start else None)
        ok = sum(1 for st in statuses if st == 200)
        refused = sum(1 for st in statuses if st == 429)
        assert ok == 3, statuses
        assert refused == 7, statuses
        assert len(mw._bindings) == 3
        assert mw._reservations == []
    asyncio.run(main())


def test_foreign_principal_cannot_refresh_last_seen():
    async def main():
        app = _FakeApp()
        mw = _SessionBindingMiddleware(app)
        await _call(mw, _scope("Bearer tok-a"))
        sid = next(iter(mw._bindings))
        before = mw._bindings[sid]["last_seen"]
        sent = await _call(mw, _scope("Bearer tok-b", session=sid, method="GET"))
        start = [m for m in sent if m["type"] == "http.response.start"][0]
        assert start["status"] == 403
        assert mw._bindings[sid]["last_seen"] == before
    asyncio.run(main())


def test_failed_initialization_releases_reservation():
    async def main():
        class FailingApp:
            async def __call__(self, scope, receive, send):
                await send({"type": "http.response.start", "status": 500,
                            "headers": []})
                await send({"type": "http.response.body", "body": b"err"})

        mw = _SessionBindingMiddleware(FailingApp())
        await _call(mw, _scope("Bearer tok-a"))
        assert mw._reservations == []
        assert mw._bindings == {}
    asyncio.run(main())
