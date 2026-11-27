"""b9 external profile tests: allowlist, ids, projections,
auth, consent, budgets, continuation, excerpt gating, audit.

All upstream data is synthetic; the service is a fake with
canned payloads, the authorization server is a local HS256
test signer (PyJWT), and no network is touched.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import jwt as pyjwt
import pytest

from global_library_mcp.external import ids as ext_ids
from global_library_mcp.external.auth import (
    AuthError,
    Principal,
    TokenValidator,
)
from global_library_mcp.external.control import ExternalConfig
from global_library_mcp.external.models import envelope
from global_library_mcp.external.server import (
    EXTERNAL_TOOLS,
    build_external_server,
)
from global_library_mcp.models import Rights, SearchResponse, SearchResult

HS_SECRET = "synthetic-test-secret"
ISSUER = "https://as.example.test"
AUDIENCE = "https://localhost/external-mcp"


def _config(**overrides) -> ExternalConfig:
    base = dict(
        excerpt_enabled=False,
        require_auth=True,
        local_test_mode=True,
        issuer=ISSUER,
        audience=AUDIENCE,
        test_hs_secret=HS_SECRET,
        continuation_secret="test-continuation-secret",
    )
    base.update(overrides)
    return ExternalConfig(**base)


def _token(sub="user-a", scopes=("catalog:search", "metadata:read",
                                 "libraries:read", "references:read",
                                 "originals:verify", "excerpts:read",
                                 "comparisons:read"),
           exp_offset=600, **claims) -> str:
    payload = {
        "sub": sub, "iss": ISSUER, "aud": AUDIENCE,
        "exp": int(time.time()) + exp_offset,
        "scope": " ".join(scopes),
    }
    payload.update(claims)
    return pyjwt.encode(payload, HS_SECRET, algorithm="HS256")


class _FakeRegistry:
    def list(self):
        return [{"id": "ndl", "name": "National Diet Library",
                 "country": "Japan"},
                {"id": "e-rara", "name": "e-rara", "country": "Switzerland"}]

    def capabilities(self, library_id):
        return {"library_id": library_id, "catalog_search": "verified",
                "page_ocr": "verified", "internal_note": "must not cross"}


class _FakeService:
    def __init__(self):
        self.doc = {
            "library_id": "ndl", "record_id": "12345",
            "title": "On the Origin of Species",
            "author": "Charles Darwin", "date": "1859",
            "language": "en", "landing_url": "https://dl.ndl.go.jp/item/12345",
            "rights": {"statement": "Public Domain"},
            "raw": {"secret_internal": "RAW-MUST-NOT-CROSS"},
            "description": "<p>long</p>" * 100,
        }
        self.page = {
            "library_id": "ndl", "record_id": "12345",
            "page_id": "12345_0007", "contents": "verbatim page text " * 40,
            "verified_mapping": True,
            "ocr_state": {"page_identity_verified": True},
            "rights": {"statement": "Public Domain"},
        }

    async def search(self, query, libraries, limit):
        results = [
            SearchResult(
                library_id="ndl", library_name="National Diet Library",
                record_id=f"r{i}", title=f"Title {i}", author="A U Thor",
                date="1900", language="en",
                landing_url=f"https://dl.ndl.go.jp/item/r{i}",
                rights=Rights(statement="Public Domain"))
            for i in range(8)
        ]
        return SearchResponse(query=query, results=results[:limit],
                              queried_libraries=["ndl"],
                              http_stats={"attempts": 2})

    def _filter_spec(self, author, title, year_from, year_to, languages,
                     include_unknown_year):
        return {}

    async def get_document(self, library_id, record_id):
        return dict(self.doc, library_id=library_id, record_id=record_id)

    async def get_page_text(self, library_id, page_id):
        return dict(self.page, library_id=library_id, page_id=page_id)

    async def verify_page(self, library_id, page_id):
        return {"checks": {"page_identity": {"ok": True},
                           "image_reachable": {"ok": True},
                           "image_identity": {"ok": False},
                           "ocr": {"ok": True}},
                "admitted": False}

    async def research_materials(self, query, libraries, limit, **kw):
        return {"materials": [{
            "document": dict(self.doc), "admitted": True,
            "verification": {"page_identity_verified": True}}],
            "search_scope": {"libraries": ["ndl"]}, "http_stats": {}}

    async def compare_documents(self, documents, aspects=None, question=None):
        return {"documents": [
            {"library_id": d["library_id"], "title": "T",
             "rights": {"statement": "Public Domain"}} for d in documents],
            "aspects": aspects or [], "gaps": [], "semantic_status": "not_checked"}


def _server(**cfg_overrides):
    server, ctx = build_external_server(
        _config(**cfg_overrides), service=_FakeService(),
        registry=_FakeRegistry())
    ctx.local_principal = Principal(
        user_id="user-a",
        scopes={"catalog:search", "metadata:read", "libraries:read",
                "references:read", "originals:verify", "excerpts:read",
                "comparisons:read"})
    return server, ctx


def _grant(ctx, user="user-a", classes=("bibliographic", "references",
                                        "rights", "search_terms_upstream",
                                        "excerpts")):
    ctx.runtime.consent.grant(user, set(classes))


def _call(server, name, args):
    async def go():
        try:
            result = await server.call_tool(name, args)
        except Exception as exc:  # FastMCP ToolError carries the code
            return f"ERROR: {exc}"
        content = result[0] if isinstance(result, tuple) else result
        texts = [getattr(c, "text", "") for c in content]
        return "\n".join(texts)
    return asyncio.run(go())


# ---------------------------------------------------------------- ids

def test_ids_round_trip_and_rejections():
    doc = ext_ids.make_document_id("ndl", "info:ndljp/pid/12345")
    assert ext_ids.parse_document_id(doc) == ("ndl", "info:ndljp/pid/12345")
    page = ext_ids.make_page_id("internet-archive", "item@leaf-3")
    assert ext_ids.parse_page_id(page) == ("internet-archive", "item@leaf-3")
    for bad in ("https://evil.example/x", "../etc/passwd", "glm1.ndl.",
                "glm2.ndl.QUJD", "glm1.NDL.QUJD", "glm1.ndl.QUJD.extra",
                "glm1.ndl.QUJD=", "glm1.ndl.!!!", "", "glm1..QUJD"):
        with pytest.raises(ext_ids.ExternalIdError):
            ext_ids.parse_document_id(bad)
    with pytest.raises(ext_ids.ExternalIdError):
        ext_ids.parse_page_id(doc)   # document id is not a page id


# ---------------------------------------------------------------- allowlist

def test_allowlist_is_exact_and_workspace_free():
    server, _ctx = _server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == set(EXTERNAL_TOOLS)
    assert "research_question" not in names
    assert "get_page_text" not in names
    pkg = Path(__file__).resolve().parents[1] / "src" / "global_library_mcp" / "external"
    for path in pkg.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "global_library_mcp.workspace" not in text, path.name
        assert "GLM_WORKSPACE" not in text, path.name


def test_resources_and_prompts_are_empty():
    server, _ctx = _server()

    async def go():
        resources = await server.list_resources()
        prompts = await server.list_prompts()
        templates = await server.list_resource_templates()
        return resources, prompts, templates
    resources, prompts, templates = asyncio.run(go())
    assert resources == [] and prompts == [] and templates == []


# ---------------------------------------------------------------- auth

def test_token_validation_matrix():
    validator = TokenValidator(_config())
    principal = validator.validate(_token())
    assert principal.user_id == "user-a"
    assert "catalog:search" in principal.scopes
    with pytest.raises(AuthError) as e1:
        validator.validate(_token(exp_offset=-10))
    assert e1.value.kind == "token_expired"
    with pytest.raises(AuthError) as e2:
        validator.validate(_token(aud="https://other.example"))
    assert e2.value.kind == "wrong_audience"
    with pytest.raises(AuthError) as e3:
        validator.validate(_token(iss="https://evil.example"))
    assert e3.value.kind == "wrong_issuer"
    forged = pyjwt.encode(
        {"sub": "user-a", "iss": ISSUER, "aud": AUDIENCE,
         "exp": int(time.time()) + 600, "scope": "catalog:search"},
        "attacker-secret", algorithm="HS256")
    with pytest.raises(AuthError) as e4:
        validator.validate(forged)
    assert e4.value.kind == "bad_signature"
    with pytest.raises(AuthError):
        validator.validate("")


def test_scope_denied_on_direct_call():
    server, ctx = _server()
    ctx.local_principal = Principal(user_id="user-a",
                                    scopes={"libraries:read"})
    _grant(ctx)
    out = _call(server, "search", {"query": "darwin"})
    assert "insufficient_scope" in out


# ---------------------------------------------------------------- consent

def test_consent_required_then_granted_then_revoked():
    server, ctx = _server()
    out = _call(server, "search", {"query": "darwin"})
    assert "consent_required" in out
    _grant(ctx)
    out = _call(server, "search", {"query": "darwin"})
    payload = json.loads(out)
    assert payload["returned_count"] >= 1
    assert payload["results"][0]["title"] == "Title 0"
    ctx.runtime.consent.revoke("user-a")
    out = _call(server, "search", {"query": "darwin"})
    assert "consent_required" in out


def test_user_revocation_blocks_everything():
    server, ctx = _server()
    _grant(ctx)
    ctx.runtime.revoke_user("user-a")
    out = _call(server, "list_libraries", {})
    assert "access_revoked" in out or "consent_required" in out


# ---------------------------------------------------------------- projections

def test_fetch_projection_drops_raw_and_markup():
    server, ctx = _server()
    _grant(ctx)
    doc_id = ext_ids.make_document_id("ndl", "12345")
    out = _call(server, "fetch", {"id": doc_id})
    assert "RAW-MUST-NOT-CROSS" not in out
    assert "<p>" not in out
    payload = json.loads(out)
    document = payload["document"]
    assert document["title"] == "On the Origin of Species"
    assert document["transfer"]["full_text_allowed"] is False
    assert "raw" not in document and "description" not in document


def test_search_results_carry_no_raw():
    server, ctx = _server()
    _grant(ctx)
    out = _call(server, "search", {"query": "species"})
    payload = json.loads(out)
    first = payload["results"][0]
    assert first["id"].startswith("glm1.ndl.")
    assert "raw" not in first
    assert payload["data_notice"]


def test_envelope_size_cap():
    big = envelope({"blob": "x" * (300 * 1024)}, returned=1)
    assert big["error"] == "response_too_large"
    assert big["truncated"] is True


# ---------------------------------------------------------------- budgets

def test_call_budget_denies_21st_call():
    server, ctx = _server()
    _grant(ctx)
    for _ in range(20):
        out = _call(server, "list_libraries", {})
        assert "budget_exceeded" not in out
    out = _call(server, "list_libraries", {})
    assert "budget_exceeded" in out


def test_continuation_binds_user_params_and_expiry():
    server, ctx = _server()
    _grant(ctx)
    out = _call(server, "search", {"query": "darwin", "limit": 3})
    payload = json.loads(out)
    token = payload.get("continuation")
    assert token
    out2 = _call(server, "search",
                 {"query": "darwin", "limit": 3, "continuation": token})
    payload2 = json.loads(out2)
    assert payload2["results"][0]["title"] != payload["results"][0]["title"]
    tampered = token[:-2] + "xx"
    out3 = _call(server, "search",
                 {"query": "darwin", "limit": 3, "continuation": tampered})
    assert "continuation_invalid" in out3
    out4 = _call(server, "search",
                 {"query": "other", "limit": 3, "continuation": token})
    assert "continuation_invalid" in out4


# ---------------------------------------------------------------- excerpts

def test_excerpt_denied_by_default_policy():
    server, ctx = _server()
    _grant(ctx)
    doc_id = ext_ids.make_document_id("ndl", "12345")
    page_id = ext_ids.make_page_id("ndl", "12345_0007")
    out = _call(server, "get_allowed_excerpt",
                {"id": doc_id, "page_id": page_id})
    assert "excerpt_not_permitted" in out
    assert "verbatim page text" not in out


def test_excerpt_allowed_only_with_matrix_and_switch(tmp_path=None):
    import global_library_mcp.external.server as server_mod
    from global_library_mcp.external import rights_policy

    server, ctx = _server(excerpt_enabled=True)
    _grant(ctx)
    original = rights_policy.decide_transfer

    def patched(library_id, statement, *, excerpt_enabled=False, matrix=None):
        row = {"metadata": "allowed", "reference_url": "allowed",
               "ocr_excerpt": "allowed", "image_url": "restricted",
               "third_party_ai": "allowed", "attribution": "Test Library",
               "source": "synthetic fixture"}
        return original(library_id, statement,
                        excerpt_enabled=excerpt_enabled, matrix=row)

    server_mod.decide_transfer = patched
    try:
        doc_id = ext_ids.make_document_id("ndl", "12345")
        page_id = ext_ids.make_page_id("ndl", "12345_0007")
        out = _call(server, "get_allowed_excerpt",
                    {"id": doc_id, "page_id": page_id})
        payload = json.loads(out)
        excerpt = payload["excerpt"]
        assert excerpt["chars"] <= 500
        assert excerpt["text"].startswith("verbatim page text")
        # Cumulative per-document cap: 1,000 chars total.
        _call(server, "get_allowed_excerpt",
              {"id": doc_id, "page_id": page_id})
        out3 = _call(server, "get_allowed_excerpt",
                     {"id": doc_id, "page_id": page_id})
        assert "excerpt_budget_exhausted" in out3 or "excerpt" in out3
    finally:
        server_mod.decide_transfer = original


def test_verify_original_reference_states():
    server, ctx = _server()
    _grant(ctx)
    doc_id = ext_ids.make_document_id("ndl", "12345")
    page_id = ext_ids.make_page_id("ndl", "12345_0007")
    out = _call(server, "verify_original_reference",
                {"id": doc_id, "page_id": page_id})
    payload = json.loads(out)
    verification = payload["verification"]
    assert verification["page_identity_verified"] is True
    assert verification["image_identity_verified"] is False
    assert verification["human_visual_verified"] is False


# ---------------------------------------------------------------- audit

def test_audit_log_has_no_research_content():
    server, ctx = _server()
    _grant(ctx)
    _call(server, "search", {"query": "secret research topic darwin"})
    blob = json.dumps(ctx.audit.events)
    assert "secret research topic" not in blob
    assert "user-a" not in blob          # pseudonymised
    assert any(e["tool"] == "search" for e in ctx.audit.events)


# ---------------------------------------------------------------- startup

def test_startup_fail_closed_without_auth_config():
    cfg = ExternalConfig(require_auth=True, local_test_mode=False)
    problems = cfg.validate_startup("streamable-http")
    assert problems
    cfg2 = _config(disabled=True)
    assert cfg2.validate_startup("stdio")
