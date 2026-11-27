"""b9 external profile tests (final-review rework): the
five-tool allowlist, per-library id grammars, projections,
auth, per-library consent (incl. persistence), the send-path
HTTP guard, revocation semantics, rights negation handling,
and the audit log.

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
from global_library_mcp.external.control import (
    ConsentStore,
    ExternalConfig,
    ExternalRuntime,
)
from global_library_mcp.external.grammars import validate_record_id
from global_library_mcp.external.models import envelope
from global_library_mcp.external.rights_policy import (
    classify_item_rights,
    decide_transfer,
)
from global_library_mcp.external.server import (
    EXTERNAL_TOOLS,
    build_external_server,
)
from global_library_mcp.models import Rights, SearchResponse, SearchResult

HS_SECRET = "synthetic-test-secret"
ISSUER = "https://as.example.test"
AUDIENCE = "https://localhost/external-mcp"
ALL_TEST_SCOPES = ("catalog:search", "metadata:read",
                   "libraries:read", "references:read")


def _config(**overrides) -> ExternalConfig:
    base = dict(
        excerpt_enabled=False,
        require_auth=True,
        local_test_mode=True,
        issuer=ISSUER,
        audience=AUDIENCE,
        test_hs_secret=HS_SECRET,
    )
    base.update(overrides)
    return ExternalConfig(**base)


def _token(sub="user-a", scopes=ALL_TEST_SCOPES,
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
    default_libraries = ("ndl",)

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
        self.queried: list[str] = []

    async def search(self, query, libraries, limit):
        self.queried = list(libraries or [])
        results = [
            SearchResult(
                library_id="ndl", library_name="National Diet Library",
                record_id=f"100{i}", title=f"Title {i}", author="A U Thor",
                date="1900", language="en",
                landing_url=f"https://dl.ndl.go.jp/item/100{i}",
                rights=Rights(statement="Public Domain"))
            for i in range(8)
        ]
        return SearchResponse(query=query, results=results[:limit],
                              queried_libraries=list(libraries or []),
                              http_stats={"attempts": 2})

    def _filter_spec(self, author, title, year_from, year_to, languages,
                     include_unknown_year):
        return {}

    async def get_document(self, library_id, record_id):
        return dict(self.doc, library_id=library_id, record_id=record_id)


class _MismatchService(_FakeService):
    """Returns a payload naming a DIFFERENT record than asked."""

    async def get_document(self, library_id, record_id):
        return dict(self.doc, library_id=library_id, record_id="99999")


def _server(service=None, **cfg_overrides):
    server, ctx = build_external_server(
        _config(**cfg_overrides), service=service or _FakeService(),
        registry=_FakeRegistry())
    ctx.local_principal = Principal(
        user_id="user-a", scopes=set(ALL_TEST_SCOPES))
    return server, ctx


def _grant(ctx, user="user-a", classes=("bibliographic", "references",
                                        "rights", "search_terms_upstream"),
           libraries=None):
    ctx.runtime.consent.grant(user, set(classes), libraries=libraries)


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
    doc = ext_ids.make_document_id("ndl", "12345")
    assert ext_ids.parse_document_id(doc) == ("ndl", "12345")
    page = ext_ids.make_page_id("internet-archive", "item@leaf-3")
    assert ext_ids.parse_page_id(page) == ("internet-archive", "item@leaf-3")
    for bad in ("https://evil.example/x", "../etc/passwd", "glm1.ndl.",
                "glm2.ndl.QUJD", "glm1.NDL.QUJD", "glm1.ndl.QUJD.extra",
                "glm1.ndl.QUJD=", "glm1.ndl.!!!", "", "glm1..QUJD"):
        with pytest.raises(ext_ids.ExternalIdError):
            ext_ids.parse_document_id(bad)
    with pytest.raises(ext_ids.ExternalIdError):
        ext_ids.parse_page_id(doc)   # document id is not a page id


def test_record_id_grammars_per_library():
    valid = {
        "ndl": "992954",
        "internet-archive": "onoriginofspecie1859darw",
        "loc": "sn83030214/1900-01-05/ed-1",
        "gallica": "https://gallica.bnf.fr/ark:/12148/bpt6k1234567",
        "bsb": "bsb10000001",
        "e-rara": "12345678",
        "europeana": "/9200332/BibliographicResource_123",
        "ddb": "ABC123def456",
        "finna": "finna.12345678",
        "finland-nl-digi": "987654",
        "kb-delpher": "ddd:010567890:mpeg21:a0001",
        "japan-search": "ndl-1234567",
        "dpla": "abc123def456",
    }
    for library_id, record_id in valid.items():
        validate_record_id(library_id, record_id)
    invalid = [
        ("ndl", "abc123"),                       # NDL pids are numeric
        ("ndl", "123/456"),                      # no path fragments
        ("internet-archive", "../secret"),       # traversal
        ("internet-archive", "https://evil.example/x"),
        ("loc", "sn83030214/1900-13-45"),        # not the issue grammar
        ("gallica", "https://evil.example/ark:/12148/bpt6k1"),
        ("bsb", "xyz10000001"),
        ("kb-delpher", "ddd:010567890"),         # truncated URN
        ("japan-search", "NDL-123"),             # source prefix is lowercase
        ("finland-nl-digi", "binding-12"),
        ("unknown-library", "12345"),
    ]
    for library_id, record_id in invalid:
        with pytest.raises(ext_ids.ExternalIdError):
            validate_record_id(library_id, record_id)


def test_fetch_rejects_grammar_invalid_id():
    server, ctx = _server()
    _grant(ctx)
    bad = ext_ids.make_document_id("ndl", "not-a-pid")
    out = _call(server, "fetch", {"id": bad})
    assert "invalid_document_id" in out


def test_fetch_identity_mismatch_is_refused():
    server, ctx = _server(service=_MismatchService())
    _grant(ctx)
    doc_id = ext_ids.make_document_id("ndl", "12345")
    out = _call(server, "fetch", {"id": doc_id})
    assert "document_identity_mismatch" in out


def test_fetch_identity_verified_when_payload_matches():
    server, ctx = _server()
    _grant(ctx)
    doc_id = ext_ids.make_document_id("ndl", "12345")
    payload = json.loads(_call(server, "fetch", {"id": doc_id}))
    assert payload["document"]["verification"]["document_identity_verified"] is True


# ---------------------------------------------------------------- allowlist

def test_allowlist_is_exactly_five_and_workspace_free():
    server, _ctx = _server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == set(EXTERNAL_TOOLS)
    assert len(names) == 5
    for gone in ("research_question", "get_page_text",
                 "verify_original_reference", "get_allowed_excerpt",
                 "research_materials_external", "compare_documents_external"):
        assert gone not in names
    pkg = Path(__file__).resolve().parents[1] / "src" / "global_library_mcp" / "external"
    import ast

    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = ",".join(a.name for a in node.names)
            assert not ("workspace" in module and "global_library_mcp" in module), \
                f"{path.name} imports the workspace package"


def test_removed_tools_refuse_direct_calls():
    server, ctx = _server()
    _grant(ctx)
    for name in ("get_allowed_excerpt", "verify_original_reference",
                 "compare_documents_external", "research_materials_external"):
        out = _call(server, name, {})
        assert "ERROR" in out  # unknown tool, refused by the server


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
    with pytest.raises(AuthError):
        validator.validate(_token(sub="   "))


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


def test_search_excludes_libraries_without_consent():
    service = _FakeService()
    server, ctx = _server(service=service)
    _grant(ctx, libraries={"e-rara"})
    out = _call(server, "search",
                {"query": "darwin", "libraries": ["ndl", "e-rara"]})
    payload = json.loads(out)
    assert payload["search_scope"]["excluded_no_consent"] == ["ndl"]
    assert service.queried == ["e-rara"]   # NDL was never queried
    out = _call(server, "search", {"query": "darwin", "libraries": ["ndl"]})
    assert "consent_required:libraries" in out
    assert service.queried == ["e-rara"]   # still never queried


def test_consent_persistence_round_trip(tmp_path):
    path = str(tmp_path / "consent.json")
    store = ConsentStore(path)
    store.grant("user-a", {"bibliographic"}, libraries={"ndl"},
                ttl_s=3600)
    reloaded = ConsentStore(path)
    assert reloaded.has("user-a", "bibliographic", "ndl")
    assert not reloaded.has("user-a", "bibliographic", "loc")
    reloaded.revoke("user-a")
    assert not ConsentStore(path).has("user-a", "bibliographic", "ndl")


def test_user_revocation_blocks_everything():
    server, ctx = _server()
    _grant(ctx)
    ctx.runtime.revoke_user("user-a")
    out = _call(server, "list_libraries", {})
    assert "access_revoked" in out


# ---------------------------------------------------------------- send-path guard

def test_http_guard_counts_and_caps_on_the_send_path():
    import global_library_mcp.external.control as control
    from global_library_mcp.http import BudgetExceeded as HttpBudgetExceeded

    runtime = ExternalRuntime(_config())
    runtime.consent.grant("user-a", {"bibliographic"})
    guard = runtime.http_guard("user-a")
    original = control.UPSTREAM_HTTP_PER_HOUR
    control.UPSTREAM_HTTP_PER_HOUR = 3
    try:
        for _ in range(3):
            guard.reserve("example.org")
        assert guard.attempts == 3
        with pytest.raises(HttpBudgetExceeded):
            guard.reserve("example.org")
        assert guard.attempts == 3   # refused sends are not double-counted
    finally:
        control.UPSTREAM_HTTP_PER_HOUR = original


def test_http_guard_stops_when_consent_changes_or_user_revoked():
    from global_library_mcp.http import BudgetExceeded as HttpBudgetExceeded

    runtime = ExternalRuntime(_config())
    runtime.consent.grant("user-a", {"bibliographic"})
    guard = runtime.http_guard("user-a")
    guard.reserve("example.org")
    runtime.consent.revoke("user-a")          # generation changes
    assert guard.stale()
    with pytest.raises(HttpBudgetExceeded):
        guard.reserve("example.org")
    runtime2 = ExternalRuntime(_config())
    runtime2.consent.grant("user-b", {"bibliographic"})
    guard2 = runtime2.http_guard("user-b")
    runtime2.revoke_user("user-b")
    with pytest.raises(HttpBudgetExceeded):
        guard2.reserve("example.org")


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


def test_search_results_carry_no_raw_and_paginate_by_offset():
    server, ctx = _server()
    _grant(ctx)
    out = _call(server, "search", {"query": "species", "limit": 3})
    payload = json.loads(out)
    first = payload["results"][0]
    assert first["id"].startswith("glm1.ndl.")
    assert "raw" not in first
    assert payload["data_notice"]
    out2 = _call(server, "search",
                 {"query": "species", "limit": 3, "offset": 3})
    payload2 = json.loads(out2)
    assert payload2["results"][0]["title"] != payload["results"][0]["title"]


def test_envelope_size_cap_counts_the_final_mcp_response():
    big = envelope({"blob": "x" * (200 * 1024)}, returned=1)
    assert big["error"] == "response_too_large"
    assert big["truncated"] is True


# ---------------------------------------------------------------- rights policy

def test_rights_negation_is_never_an_allowance():
    assert classify_item_rights(
        "This work is not in the public domain") != "public_domain"
    assert classify_item_rights(
        "Not public domain; all rights reserved") == "copyrighted"
    assert classify_item_rights("Public Domain") == "public_domain"
    assert classify_item_rights(
        "https://creativecommons.org/publicdomain/mark/1.0/") == "public_domain"


def test_real_libraries_never_allow_excerpts_even_with_switch():
    for library_id in ("ndl", "internet-archive", "loc", "bsb", "gallica",
                       "europeana", "finna", "japan-search"):
        decision = decide_transfer(
            library_id, "https://creativecommons.org/publicdomain/mark/1.0/",
            excerpt_enabled=True)
        assert decision["excerpt_allowed"] is False, library_id
        assert decision["full_text_allowed"] is False
        assert decision["image_binary_allowed"] is False


def test_excerpt_allow_path_needs_ocr_rights_confirmation():
    row = {"metadata": "allowed", "reference_url": "allowed",
           "ocr_excerpt": "allowed", "image_url": "restricted",
           "third_party_ai": "allowed", "attribution": "Test Library",
           "source": "synthetic fixture"}
    decision = decide_transfer(
        "ndl", "https://creativecommons.org/publicdomain/mark/1.0/",
        excerpt_enabled=True, matrix=row)
    assert decision["excerpt_allowed"] is False   # ocr_rights unconfirmed
    row["ocr_rights"] = "allowed"
    decision = decide_transfer(
        "ndl", "https://creativecommons.org/publicdomain/mark/1.0/",
        excerpt_enabled=True, matrix=row)
    assert decision["excerpt_allowed"] is True


def test_rights_decision_separates_metadata_and_ocr():
    decision = decide_transfer(
        "ndl", {"statement": "Public Domain",
                "ocr_statement": "In Copyright"})
    assert decision["metadata_rights_category"] == "public_domain"
    assert decision["ocr_rights_category"] == "copyrighted"
    assert decision["ocr_rights_basis"] == "separate_ocr_statement"


# ---------------------------------------------------------------- budgets

def test_call_budget_denies_21st_call():
    server, ctx = _server()
    _grant(ctx)
    for _ in range(20):
        out = _call(server, "list_libraries", {})
        assert "budget_exceeded" not in out
    out = _call(server, "list_libraries", {})
    assert "budget_exceeded" in out


# ---------------------------------------------------------------- audit

def test_audit_records_denials_and_has_no_research_content():
    server, ctx = _server()
    out = _call(server, "search", {"query": "secret research topic darwin"})
    assert "consent_required" in out
    _grant(ctx)
    _call(server, "search", {"query": "secret research topic darwin"})
    blob = json.dumps(ctx.audit.events)
    assert "secret research topic" not in blob
    assert "user-a" not in blob          # HMAC-pseudonymised
    denied = [e for e in ctx.audit.events if e["status"] == "denied"]
    assert denied and denied[0]["error_class"].startswith("consent_required")
    ok = [e for e in ctx.audit.events
          if e["tool"] == "search" and e["status"] == "ok"]
    assert ok and "bytes_received" in ok[0] and "response_bytes" in ok[0]


def test_doctor_runs_without_network():
    from global_library_mcp.external.doctor import run_doctor

    report = run_doctor()
    assert report["network_used"] is False
    names = {c["check"] for c in report["checks"]}
    assert {"external_allowlist", "transfer_matrix",
            "workspace_separation", "local_profiles"} <= names
    by_name = {c["check"]: c for c in report["checks"]}
    assert by_name["external_allowlist"]["ok"] is True
    assert by_name["workspace_separation"]["ok"] is True
    blob = json.dumps(report)
    assert HS_SECRET not in blob


# ---------------------------------------------------------------- startup

def test_startup_fail_closed_without_auth_config():
    cfg = ExternalConfig(require_auth=True, local_test_mode=False)
    problems = cfg.validate_startup("streamable-http")
    assert problems


def test_startup_refuses_disabled_auth_and_dns_off():
    cfg = _config(require_auth=False)
    assert any("authentication cannot be disabled" in p
               for p in cfg.validate_startup("streamable-http"))
    cfg = _config(dns_check_explicitly_disabled=True)
    assert any("DNS" in p for p in cfg.validate_startup("stdio"))
    cfg = _config(jwks_url="https://as.example.test/jwks.json")
    assert any("ambiguous" in p for p in cfg.validate_startup("streamable-http"))
    cfg = _config(disabled=True)
    assert cfg.validate_startup("stdio")
