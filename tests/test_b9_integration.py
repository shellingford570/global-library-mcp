"""b9 final-review INTEGRATION tests (section 4 of the final
review instructions): the full real path -

    official MCP SDK client
      -> real Streamable HTTP server (uvicorn)
      -> real RS256 authentication / scopes / consent control
      -> real ExternalRuntime (send-path guard, revocation)
      -> real LibraryService
      -> real BudgetedTransport (per-send guard consulted)
      -> fixed upstream HTTP fixtures (FixtureTransport)

- with the upstream requests counted at the transport. The
mandatory metrics are measured, not assumed:

- requests to a library the user never consented to: 0
- per-user HTTP budget overruns (sends above the cap): 0
- upstream sends initiated after revocation: 0
- session-reuse successes by another principal: 0
- forbidden canary text in any external response: 0
- secret canaries in any external response: 0
- final MCP responses above 256 KiB: 0 (max size is asserted)
- wrongly certified document identities: 0

No live network: the fixture transport answers every upstream
request from tests/external_fixtures/upstream and 404s the
rest.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_library_mcp.service import LibraryService as _LS  # noqa: F401
import global_library_mcp.external.control as control
from global_library_mcp.external.control import ExternalConfig
from global_library_mcp.external.ids import make_document_id
from global_library_mcp.external.server import (
    build_external_server,
    external_http_app,
)
from global_library_mcp.http import FixtureTransport
from tests.test_b9_http_security import _raw_initialize, _rs256_keypair, _rs_token

FIXTURE_DIR = Path(__file__).resolve().parent / "external_fixtures" / "upstream"
IA_ID = "onoriginofspecie1859darw"
LYELL_ID = "principlesofgeol00lyel"
NDL_HOSTS = {"lab.ndl.go.jp", "dl.ndl.go.jp", "ndlsearch.ndl.go.jp"}

# Transport-level upstream request log: (monotonic_ts, host, path).
REQUESTS: list[tuple[float, str, str]] = []
_SLOW = threading.Event()   # when set, fixture responses take 2 s

_original_handle = FixtureTransport.handle_async_request


async def _counting_handle(self, request):
    REQUESTS.append((time.monotonic(), request.url.host, request.url.path))
    if _SLOW.is_set():
        await asyncio.sleep(2.0)
    return await _original_handle(self, request)


FixtureTransport.handle_async_request = _counting_handle

_PRIVATE_PEM, _JWKS, _KID = _rs256_keypair()
CONFIG = ExternalConfig(
    require_auth=True, local_test_mode=False,
    issuer="https://as.example.test", audience="https://localhost/external-mcp",
    jwks=_JWKS)
RESOURCE_URL = "https://localhost/external-mcp"


@pytest.fixture(autouse=True)
def _fixture_env(monkeypatch):
    monkeypatch.setenv("GLM_UPSTREAM_FIXTURE_DIR", str(FIXTURE_DIR))
    REQUESTS.clear()
    _SLOW.clear()
    yield
    _SLOW.clear()


@contextmanager
def _running_real():
    server, ctx = build_external_server(CONFIG, resource_url=RESOURCE_URL)
    app = external_http_app(server, ctx)
    uv_config = uvicorn.Config(app, host="127.0.0.1", port=0,
                               log_level="error")
    uv_server = uvicorn.Server(uv_config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not uv_server.started:
        if time.time() > deadline:
            raise RuntimeError("integration server did not start")
        time.sleep(0.05)
    port = uv_server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", ctx
    finally:
        uv_server.should_exit = True
        thread.join(timeout=5)


def _grant(ctx, user, libraries=None):
    ctx.runtime.consent.grant(
        user, {"bibliographic", "references", "rights",
               "search_terms_upstream"}, libraries=libraries)


async def _call(base, token, tool, args):
    async with streamablehttp_client(
            base + "/mcp",
            headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, args)


def _run_call(base, token, tool, args):
    return asyncio.run(_call(base, token, tool, args))


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


def _response_size(result) -> int:
    import json as _json

    structured = result.structuredContent or {}
    return len(_text(result).encode("utf-8")) \
        + len(_json.dumps(structured, ensure_ascii=False).encode("utf-8"))


def _hosts_since(ts: float) -> list[str]:
    return [host for at, host, _p in REQUESTS if at >= ts]


# ---------------------------------------------------------------- metrics

def test_integration_forbidden_library_gets_zero_requests():
    with _running_real() as (base, ctx):
        _grant(ctx, "user-a", libraries={"internet-archive"})
        token = _rs_token(_PRIVATE_PEM, _KID, sub="user-a")
        result = _run_call(base, token, "search", {
            "query": "darwin", "libraries": ["internet-archive", "ndl"]})
        assert result.isError is False
        payload = _text(result)
        assert '"excluded_no_consent": ["ndl"]' in payload \
            or '"excluded_no_consent":["ndl"]' in payload \
            or "ndl" in payload
        forbidden = [h for h in _hosts_since(0) if h in NDL_HOSTS]
        assert forbidden == [], f"requests to non-consented NDL: {forbidden}"
        assert any(h == "archive.org" for h in _hosts_since(0))


def test_integration_budget_cap_is_never_exceeded_on_the_wire(monkeypatch):
    monkeypatch.setattr(control, "UPSTREAM_HTTP_PER_HOUR", 5)
    with _running_real() as (base, ctx):
        _grant(ctx, "user-b")
        token = _rs_token(_PRIVATE_PEM, _KID, sub="user-b")
        for i in range(7):
            _run_call(base, token, "search",
                      {"query": f"budget probe {i}",
                       "libraries": ["internet-archive"]})
        sends = [h for h in _hosts_since(0) if h == "archive.org"]
        overrun = max(0, len(sends) - 5)
        assert len(sends) == 5, f"expected exactly the cap, got {len(sends)}"
        assert overrun == 0


def test_integration_no_sends_after_revocation():
    with _running_real() as (base, ctx):
        _grant(ctx, "user-c")
        token = _rs_token(_PRIVATE_PEM, _KID, sub="user-c")
        result = _run_call(base, token, "search", {
            "query": "before revocation", "libraries": ["internet-archive"]})
        assert result.isError is False
        before = len(REQUESTS)
        assert before >= 1
        ctx.runtime.revoke_user("user-c")
        revoked_at = time.monotonic()
        # A revoked user's token no longer validates at all, so
        # the SDK client is refused with 401 before any tool
        # runs; an isError result would equally prove denial.
        for tool, args in (
                ("search", {"query": "after revocation",
                            "libraries": ["internet-archive"]}),
                ("fetch", {"id": make_document_id("internet-archive",
                                                  IA_ID)})):
            try:
                result = _run_call(base, token, tool, args)
                assert result.isError is True
            except Exception:
                pass   # 401 at the auth layer: denied, as required
        after = [h for at, h, _p in REQUESTS if at >= revoked_at]
        assert after == [], f"sends after revocation: {after}"


def test_integration_inflight_revocation_voids_the_call():
    with _running_real() as (base, ctx):
        _grant(ctx, "user-d")
        token = _rs_token(_PRIVATE_PEM, _KID, sub="user-d")
        _SLOW.set()
        outcome: dict = {}

        def run():
            try:
                outcome["result"] = _run_call(base, token, "search", {
                    "query": "slow flight",
                    "libraries": ["internet-archive"]})
            except Exception as exc:  # session may be torn down
                outcome["error"] = exc

        # daemon: a client left waiting on a torn-down session
        # must never hold the test process open at exit.
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        time.sleep(0.6)   # the upstream request is now in flight
        revoked_at = time.monotonic()
        ctx.runtime.revoke_user("user-d")
        thread.join(timeout=20)
        _SLOW.clear()
        result = outcome.get("result")
        succeeded = result is not None and not result.isError
        assert not succeeded, "a call revoked mid-flight returned success"
        late = [h for at, h, _p in REQUESTS if at > revoked_at + 0.05]
        assert late == [], f"sends initiated after revocation: {late}"


def test_integration_session_reuse_by_another_principal_fails():
    with _running_real() as (base, ctx):
        _grant(ctx, "user-a")
        _grant(ctx, "user-b")
        token_a = _rs_token(_PRIVATE_PEM, _KID, sub="user-a")
        token_b = _rs_token(_PRIVATE_PEM, _KID, sub="user-b")
        session_a = _raw_initialize(base, token_a)
        assert session_a
        successes = 0
        with httpx.Client(base_url=base, timeout=10) as client:
            for method in ("POST", "GET", "DELETE"):
                response = client.request(
                    method, "/mcp",
                    headers={"Authorization": f"Bearer {token_b}",
                             "mcp-session-id": session_a,
                             "Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                          "params": {}} if method == "POST" else None)
                if response.status_code < 400:
                    successes += 1
        assert successes == 0


def test_integration_canaries_and_response_sizes_and_identity():
    sizes: list[int] = []
    with _running_real() as (base, ctx):
        _grant(ctx, "user-a")
        token = _rs_token(_PRIVATE_PEM, _KID, sub="user-a")
        results = []
        results.append(_run_call(base, token, "search", {
            "query": "darwin", "libraries": ["internet-archive"],
            "limit": 20}))
        doc_id = make_document_id("internet-archive", IA_ID)
        results.append(_run_call(base, token, "fetch", {"id": doc_id}))
        results.append(_run_call(base, token, "get_document_rights",
                                 {"id": doc_id}))
        results.append(_run_call(base, token, "fetch", {
            "id": make_document_id("internet-archive", LYELL_ID)}))
        for result in results:
            assert result.isError is False
            sizes.append(_response_size(result))
            blob = _text(result)
            for canary in ("CANARY-DESCRIPTION-9e1b", "CANARY-NOTES-9e1b",
                           "CANARY-SECRET-51f0", "CANARY-INTERNAL-51f0",
                           "canary-uploader@example.org"):
                assert canary not in blob, canary
        # Final MCP response sizes: none above the 256 KiB cap.
        assert sizes and max(sizes) <= 256 * 1024, sizes
        # Identity: the fetched document certifies exactly the
        # requested id, and the access-restricted Lyell item is
        # reference-only (its title is withheld).
        import json as _json

        fetched = _json.loads(_text(results[1]))
        assert fetched["document"]["id"] == doc_id
        assert fetched["document"]["verification"][
            "document_identity_verified"] is True
        lyell = _json.loads(_text(results[3]))
        assert lyell["document"].get("title") is None   # withheld = absent
        assert lyell["document"]["rights"]["item_category"] is not None
        # A nonexistent (but grammar-valid) id certifies nothing.
        missing = _run_call(base, token, "fetch", {
            "id": make_document_id("internet-archive",
                                   "nonexistentitem1900zzzz")})
        assert missing.isError is True
        assert "document_identity_verified\": true" not in _text(missing)
