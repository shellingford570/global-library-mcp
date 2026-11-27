"""b9 final-review HTTP tests: real Streamable HTTP with
RS256 and HS256(synthetic) token validation, session-to-token
binding, workspace canary isolation, SSRF validation helpers,
and fail-closed HTTP construction.

Everything is local and synthetic: real uvicorn servers on
loopback, a fake LibraryService, and signing keys generated
in-test. No external network is touched.
"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, so `tests.` imports work under the plain pytest binary too

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order: service first, avoids the http circular import)
from global_library_mcp.external.auth import AuthError, TokenValidator
from global_library_mcp.external.control import ExternalConfig
from global_library_mcp.external.server import (
    build_external_server,
    external_http_app,
)
from global_library_mcp.http import check_dns_public, validate_fetch_url
from tests.test_b9_external import (
    AUDIENCE,
    HS_SECRET,
    ISSUER,
    _FakeRegistry,
    _FakeService,
    _config,
    _token,
)

RESOURCE_URL = AUDIENCE
MCP_URL_PATH = "/mcp"


@contextmanager
def _running(config, service=None, registry=None):
    server, ctx = build_external_server(
        config, service=service or _FakeService(),
        registry=registry or _FakeRegistry(), resource_url=RESOURCE_URL)
    app = external_http_app(server, ctx)
    uv_config = uvicorn.Config(app, host="127.0.0.1", port=0,
                               log_level="error")
    uv_server = uvicorn.Server(uv_config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not uv_server.started:
        if time.time() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    port = uv_server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", ctx
    finally:
        uv_server.should_exit = True
        thread.join(timeout=5)


def _grant_all(ctx, user="user-a"):
    ctx.runtime.consent.grant(
        user, {"bibliographic", "references", "rights",
               "search_terms_upstream"})


async def _sdk_call(base_url, token, tool, args):
    async with streamablehttp_client(
            base_url + MCP_URL_PATH,
            headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(tool, args)
            return tools, result


# ---------------------------------------------------------------- RS256 keys

def _rs256_keypair(kid="test-rs-1"):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    jwk = pyjwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_pem, {"keys": [jwk]}, kid


def _rs_token(private_pem, kid, sub="user-a",
              scopes=("catalog:search", "metadata:read",
                      "libraries:read", "references:read"),
              exp_offset=600, **claims):
    payload = {"sub": sub, "iss": ISSUER, "aud": AUDIENCE,
               "exp": int(time.time()) + exp_offset,
               "scope": " ".join(scopes)}
    payload.update(claims)
    return pyjwt.encode(payload, private_pem, algorithm="RS256",
                        headers={"kid": kid})


# ---------------------------------------------------------------- HTTP auth

def test_http_requires_auth_and_challenges():
    with _running(_config()) as (base, _ctx):
        with httpx.Client(base_url=base, timeout=10) as client:
            response = client.post(MCP_URL_PATH, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/list",
                "params": {}})
            assert response.status_code == 401
            challenge = response.headers.get("www-authenticate", "")
            assert "resource_metadata" in challenge


def test_http_prm_document():
    with _running(_config()) as (base, _ctx):
        with httpx.Client(base_url=base, timeout=10) as client:
            response = client.get(
                "/.well-known/oauth-protected-resource/external-mcp")
            assert response.status_code == 200
            doc = response.json()
            assert doc["resource"] == RESOURCE_URL
            assert doc["authorization_servers"] == [ISSUER]
            assert "catalog:search" in doc["scopes_supported"]
            assert "excerpts:read" not in doc["scopes_supported"]


def test_http_full_flow_hs256_local_test_mode():
    import asyncio

    with _running(_config()) as (base, ctx):
        _grant_all(ctx)
        tools, result = asyncio.run(
            _sdk_call(base, _token(), "list_libraries", {}))
        assert {t.name for t in tools.tools} == {
            "search", "fetch", "list_libraries",
            "get_library_capabilities", "get_document_rights"}
        assert result.isError is False


def test_http_rs256_flow_and_hs256_rejected_in_production_mode():
    import asyncio

    private_pem, jwks, kid = _rs256_keypair()
    config = ExternalConfig(
        require_auth=True, local_test_mode=False,
        issuer=ISSUER, audience=AUDIENCE, jwks=jwks)
    with _running(config) as (base, ctx):
        _grant_all(ctx)
        good = _rs_token(private_pem, kid)
        _tools, result = asyncio.run(
            _sdk_call(base, good, "list_libraries", {}))
        assert result.isError is False
        # An HS256 token (synthetic-secret style) must NOT be
        # accepted by a production JWKS configuration.
        hs = _token()
        with httpx.Client(base_url=base, timeout=10) as client:
            response = client.post(
                MCP_URL_PATH,
                headers={"Authorization": f"Bearer {hs}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                      "params": {}})
            assert response.status_code == 401
        # Expired RS256 likewise.
        expired = _rs_token(private_pem, kid, exp_offset=-30)
        with httpx.Client(base_url=base, timeout=10) as client:
            response = client.post(
                MCP_URL_PATH,
                headers={"Authorization": f"Bearer {expired}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                      "params": {}})
            assert response.status_code == 401


def test_http_scope_enforced_on_call():
    import asyncio

    with _running(_config()) as (base, ctx):
        _grant_all(ctx)
        limited = _token(scopes=("libraries:read",))
        _tools, result = asyncio.run(
            _sdk_call(base, limited, "search", {"query": "darwin"}))
        assert result.isError is True
        blob = " ".join(getattr(c, "text", "") for c in result.content)
        assert "insufficient_scope" in blob


def test_http_construction_refuses_unauthenticated_configs():
    server, ctx = build_external_server(
        _config(require_auth=False), service=_FakeService(),
        registry=_FakeRegistry(), resource_url=RESOURCE_URL)
    with pytest.raises(RuntimeError):
        external_http_app(server, ctx)
    bare = ExternalConfig(require_auth=True, local_test_mode=False,
                          issuer=ISSUER, audience=AUDIENCE)
    server2, ctx2 = build_external_server(
        bare, service=_FakeService(), registry=_FakeRegistry(),
        resource_url=RESOURCE_URL)
    with pytest.raises(RuntimeError):
        external_http_app(server2, ctx2)


# ---------------------------------------------------------------- sessions

def _raw_initialize(base, token):
    with httpx.Client(base_url=base, timeout=10) as client:
        response = client.post(
            MCP_URL_PATH,
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-03-26",
                             "capabilities": {},
                             "clientInfo": {"name": "raw-test",
                                            "version": "0"}}})
        assert response.status_code == 200
        return response.headers.get("mcp-session-id")


def test_session_cannot_be_reused_by_another_principal():
    with _running(_config()) as (base, ctx):
        _grant_all(ctx)
        _grant_all(ctx, user="user-b")
        session_a = _raw_initialize(base, _token(sub="user-a"))
        assert session_a
        with httpx.Client(base_url=base, timeout=10) as client:
            # The owner can use the session.
            own = client.post(
                MCP_URL_PATH,
                headers={"Authorization": f"Bearer {_token(sub='user-a')}",
                         "mcp-session-id": session_a,
                         "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            assert own.status_code in (200, 202)
            # Another principal presenting the same session id
            # is refused at the binding layer - on POST, GET
            # and DELETE alike.
            for method in ("POST", "GET", "DELETE"):
                stolen = client.request(
                    method, MCP_URL_PATH,
                    headers={"Authorization": f"Bearer {_token(sub='user-b')}",
                             "mcp-session-id": session_a,
                             "Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                          "params": {}} if method == "POST" else None)
                assert stolen.status_code == 403, method
                assert "session_binding_mismatch" in stolen.text


# ---------------------------------------------------------------- JWKS URL

def test_jwks_url_loader_limits_and_local_test_loopback():
    private_pem, jwks, kid = _rs256_keypair()
    import json as _json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps(jwks).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/jwks.json"
        config = ExternalConfig(
            require_auth=True, local_test_mode=True,
            issuer=ISSUER, audience=AUDIENCE, jwks_url=url)
        validator = TokenValidator(config)
        principal = validator.validate(_rs_token(private_pem, kid))
        assert principal.user_id == "user-a"
        # The same loopback http URL is refused outside local
        # test mode (production JWKS must be https + public).
        config2 = ExternalConfig(
            require_auth=True, local_test_mode=False,
            issuer=ISSUER, audience=AUDIENCE, jwks_url=url)
        with pytest.raises(AuthError):
            TokenValidator(config2).validate(_rs_token(private_pem, kid))
    finally:
        httpd.shutdown()


# ---------------------------------------------------------------- workspace canary

def test_workspace_canary_never_surfaces(tmp_path, monkeypatch):
    canary = "CANARY-RESEARCH-NOTE-7f3d9a"
    db_dir = tmp_path / "ws"
    db_dir.mkdir()
    (db_dir / "workspace.db").write_text(canary, encoding="utf-8")
    monkeypatch.setenv("GLM_WORKSPACE_PATH", str(db_dir / "workspace.db"))
    import asyncio

    with _running(_config()) as (base, ctx):
        _grant_all(ctx)
        token = _token()
        for tool, args in (("list_libraries", {}),
                           ("search", {"query": "darwin"}),
                           ("get_library_capabilities",
                            {"library_id": "ndl"})):
            _tools, result = asyncio.run(_sdk_call(base, token, tool, args))
            blob = " ".join(getattr(c, "text", "")
                            for c in result.content)
            assert canary not in blob
        blob = " ".join(str(e) for e in ctx.audit.events)
        assert canary not in blob


# ---------------------------------------------------------------- SSRF helpers

def test_validate_fetch_url_refusals():
    for bad in ("http://example.org/x", "https://127.0.0.1/x",
                "https://10.0.0.5/x", "https://[::1]/x",
                "https://user:pass@example.org/x",
                "https://example.org:8443/x",
                "https://localhost/x", "https://169.254.169.254/latest",
                "https://[::ffff:127.0.0.1]/x", "https://2130706433/x"):
        with pytest.raises(Exception):
            validate_fetch_url(bad)
    assert validate_fetch_url("https://www.loc.gov/resource/x/") \
        == "https://www.loc.gov/resource/x/"
    with pytest.raises(Exception):
        validate_fetch_url("https://evil-loc.gov/x",
                           allowed_hosts={"www.loc.gov"})


def test_dns_precheck_refuses_non_public_answers():
    # localhost always resolves to loopback and must be refused.
    with pytest.raises(Exception):
        check_dns_public("localhost")
