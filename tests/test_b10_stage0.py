"""b10 Stage 0 regression tests: the b9 residual risks from
brief section 4, each reproduced against the b9 code first
(see ~/workspace/glm-scratch/b10-stage0-repro.py and
docs/b10-b9-regression-hardening.md) and fixed here:

- 4.1 consent/token expiry is part of authorisation currency
  (post-queue, pre-send and pre-return checkpoints);
- 4.2 consent is applied per DATA CLASS at projection time;
- 4.3 sends are bound to their library's consent, not a host;
- 4.4 strict user capacity and an eviction-proof budget ledger;
- 4.5 session bindings: idle TTL, per-user caps, creation
  refused at capacity;
- 4.6 typed projections (no str() of containers, typed
  capabilities);
- 4.7 reference URLs: per-library hosts, no credential-shaped
  query parameters, no disguised numeric IPs;
- 4.8 identity states (upstream_confirmed / request_echo /
  missing) and no rights certification for missing identity;
- 4.9 consent file validation and permissions;
- 4.10 startup validation on direct construction;
- 4.11 audit basis for response size; session-layer audit.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_library_mcp.service import LibraryService as _LS  # noqa: F401,E402
from global_library_mcp.external import models as ext_models  # noqa: E402
from global_library_mcp.external.control import (  # noqa: E402
    BudgetExceeded,
    ConsentStore,
    ExternalConfig,
    ExternalRuntime,
)
from global_library_mcp.external.server import (  # noqa: E402
    _SessionBindingMiddleware,
    build_external_server,
)
from global_library_mcp.http import BudgetExceeded as HttpBudgetExceeded  # noqa: E402
from tests.test_b9_external import (  # noqa: E402
    _FakeService,
    _call,
    _config,
    _grant,
    _server,
)


def _runtime() -> ExternalRuntime:
    return ExternalRuntime(ExternalConfig())


# ---------------------------------------------------------------- 4.1

def test_consent_expiry_refuses_sends_and_marks_guard_stale():
    rt = _runtime()
    rt.consent.grant("u1", {"bibliographic", "search_terms_upstream"},
                     libraries={"ndl"}, ttl_s=0.2)
    guard = rt.http_guard("u1")
    guard.reserve("dl.ndl.go.jp", library_id="ndl")
    assert guard.attempts == 1
    time.sleep(0.3)   # natural expiry; no grant/revoke happens
    assert rt.consent.has("u1", "bibliographic", "ndl") is False
    assert guard.stale() is True
    with pytest.raises(HttpBudgetExceeded):
        guard.reserve("dl.ndl.go.jp", library_id="ndl")
    assert guard.attempts == 1   # the refused send was not counted


def test_token_expiry_marks_guard_stale_and_refuses_sends():
    rt = _runtime()
    rt.consent.grant("u1", {"bibliographic"}, ttl_s=3600)
    guard = rt.http_guard("u1", token_expires_at=time.time() - 1)
    assert guard.stale() is True
    with pytest.raises(HttpBudgetExceeded):
        guard.reserve("dl.ndl.go.jp")
    live = rt.http_guard("u1", token_expires_at=time.time() + 600)
    assert live.stale() is False
    live.reserve("dl.ndl.go.jp")
    assert live.attempts == 1


# ---------------------------------------------------------------- 4.2

def test_search_projection_gates_rights_and_url_on_their_own_classes():
    server, ctx = _server()
    _grant(ctx, classes=("bibliographic", "search_terms_upstream"))
    out = _call(server, "search", {"query": "darwin"})
    payload = json.loads(out)
    item = payload["results"][0]
    assert item["title"]            # bibliographic consent works
    assert item["rights"] is None   # rights class NOT granted
    assert "url" not in item        # references class NOT granted


def test_search_projection_includes_rights_and_url_when_granted():
    server, ctx = _server()
    _grant(ctx)   # bibliographic + references + rights + search terms
    out = _call(server, "search", {"query": "darwin"})
    item = json.loads(out)["results"][0]
    assert item["rights"]["statement"] == "Public Domain"
    assert item["url"] == "https://dl.ndl.go.jp/item/1000"


def test_fetch_projection_gates_image_url_on_images_class():
    # The shipped transfer matrix restricts image URLs for every
    # real library, so the consent gate is exercised at the
    # projection level with the policy decision stubbed open:
    # the b10 gate must withhold the URL unless the "images"
    # class was granted, even when policy allows it.
    from unittest.mock import patch

    decision = {
        "item_rights_category": "public_domain",
        "categories": ["metadata_allowed"],
        "attribution": "",
        "metadata_allowed": True,
        "excerpt_allowed": False,
        "excerpt_denial_reasons": [],
        "reference_allowed": True,
        "image_url_allowed": True,
    }
    doc = {"library_id": "ndl", "record_id": "12345",
           "title": "T", "rights": {"statement": "Public Domain"},
           "image_url": "https://dl.ndl.go.jp/img/1.jpg",
           "landing_url": "https://dl.ndl.go.jp/item/12345"}
    with patch.object(ext_models, "decide_transfer",
                      return_value=decision):
        without = ext_models.project_document(
            doc, granted=frozenset({"bibliographic", "rights",
                                    "references"}))
        assert "image_url" not in without
        assert without["url"] == "https://dl.ndl.go.jp/item/12345"
        with_images = ext_models.project_document(
            doc, granted=frozenset({"bibliographic", "rights",
                                    "references", "images"}))
        assert with_images["image_url"] == \
            "https://dl.ndl.go.jp/img/1.jpg"
        no_refs = ext_models.project_document(
            doc, granted=frozenset({"bibliographic", "rights",
                                    "images"}))
        assert "url" not in no_refs
        assert no_refs["rights"] is not None
        no_rights = ext_models.project_document(
            doc, granted=frozenset({"bibliographic", "references",
                                    "images"}))
        assert no_rights["rights"] is None


# ---------------------------------------------------------------- 4.3

def test_send_refused_for_library_outside_consented_set():
    rt = _runtime()
    rt.consent.grant("u1", {"bibliographic", "search_terms_upstream"},
                     libraries={"ndl"}, ttl_s=3600)
    guard = rt.http_guard("u1")
    guard.reserve("dl.ndl.go.jp", library_id="ndl")
    with pytest.raises(HttpBudgetExceeded):
        guard.reserve("www.loc.gov", library_id="loc")
    # Even on a SHARED host, the library binding decides.
    with pytest.raises(HttpBudgetExceeded):
        guard.reserve("dl.ndl.go.jp", library_id="loc")


# ---------------------------------------------------------------- 4.4

def test_user_capacity_is_strict_when_everyone_is_busy():
    from global_library_mcp.external.control import MAX_TRACKED_USERS

    rt = _runtime()
    for i in range(MAX_TRACKED_USERS):
        uid = f"cap-{i}"
        rt._state(uid)
        rt._inflight[uid] = {object()}   # in-flight, not evictable
    with pytest.raises(BudgetExceeded) as excinfo:
        rt._state("one-too-many")
    assert excinfo.value.kind == "user_capacity"
    assert len(rt._users) == MAX_TRACKED_USERS


def test_budget_history_survives_state_eviction():
    from global_library_mcp.external.control import MAX_TRACKED_USERS

    rt = _runtime()
    rt.consent.grant("victim", {"bibliographic"}, ttl_s=3600)
    guard = rt.http_guard("victim")
    for _ in range(5):
        guard.reserve("example.org")
    for i in range(MAX_TRACKED_USERS + 10):
        rt._state(f"filler-{i}")   # evicts the victim's runtime state
    assert "victim" not in rt._users
    ledger = rt._ledger_for("victim")
    assert len(ledger.http_times) == 5   # budget history intact
    guard2 = rt.http_guard("victim")
    guard2.reserve("example.org")
    assert len(rt._ledger_for("victim").http_times) == 6


def test_revocation_keeps_budget_ledger():
    rt = _runtime()
    rt.consent.grant("u1", {"bibliographic"}, ttl_s=3600)
    guard = rt.http_guard("u1")
    guard.reserve("example.org")
    rt.revoke_user("u1")
    assert len(rt._ledger_for("u1").http_times) == 1


# ---------------------------------------------------------------- 4.5

class _StubApp:
    def __init__(self, session_id="sess-1"):
        self.calls = 0
        self.session_id = session_id

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"mcp-session-id",
                                 self.session_id.encode())]})
        await send({"type": "http.response.body", "body": b"{}"})


def _scope(method="POST", session=None, auth="Bearer tok-a"):
    headers = []
    if auth:
        headers.append((b"authorization", auth.encode()))
    if session:
        headers.append((b"mcp-session-id", session.encode()))
    return {"type": "http", "method": method, "headers": headers}


async def _receive():
    return {"type": "http.request", "body": b""}


class _Send:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return m["status"]
        return None


def _run(coro):
    return asyncio.run(coro)


def test_session_creation_refused_at_capacity():
    app = _StubApp()
    mw = _SessionBindingMiddleware(app)
    mw.MAX_SESSIONS = 2

    async def go():
        await mw(_scope(), _receive, _Send())          # binds sess-1
        app.session_id = "sess-2"
        await mw(_scope(), _receive, _Send())          # binds sess-2
        app.session_id = "sess-3"
        send = _Send()
        await mw(_scope(), _receive, send)             # at capacity
        return send

    send = _run(go())
    assert app.calls == 2          # third request never reached the app
    assert send.status == 429


def test_session_binding_expires_when_idle():
    app = _StubApp()
    mw = _SessionBindingMiddleware(app)
    mw.IDLE_TTL_S = 0.2

    async def go():
        await mw(_scope(), _receive, _Send())          # bind sess-1
        ok = _Send()
        await mw(_scope(session="sess-1"), _receive, ok)
        time.sleep(0.3)
        late = _Send()
        await mw(_scope(session="sess-1"), _receive, late)
        return ok, late

    ok, late = _run(go())
    assert ok.status == 200
    assert late.status == 403      # binding expired; session refused


def test_session_cap_is_per_user_across_tokens():
    app = _StubApp()
    mw = _SessionBindingMiddleware(
        app, user_resolver=lambda auth: "user-a")
    mw.MAX_PER_USER = 1

    async def go():
        await mw(_scope(auth="Bearer tok-1"), _receive, _Send())
        app.session_id = "sess-2"
        send = _Send()
        # A second session for the same user under another
        # token: the response carries a new session id, but the
        # per-user cap means it is never bound, so using it is
        # refused as a mismatch.
        await mw(_scope(auth="Bearer tok-2"), _receive, send)
        use = _Send()
        await mw(_scope(session="sess-2", auth="Bearer tok-2"),
                 _receive, use)
        return use

    use = _run(go())
    assert use.status == 403


def test_session_rejections_are_audited():
    seen = []
    app = _StubApp()
    mw = _SessionBindingMiddleware(app, audit=seen.append)

    async def go():
        await mw(_scope(), _receive, _Send())
        send = _Send()
        await mw(_scope(session="sess-1", auth="Bearer other"),
                 _receive, send)
        return send

    send = _run(go())
    assert send.status == 403
    assert seen == ["session_binding_mismatch"]


# ---------------------------------------------------------------- 4.6

def test_clean_text_drops_containers_and_booleans():
    assert ext_models.clean_text({"note": "CANARY"}, 300) == ""
    assert ext_models.clean_text(["CANARY"], 300) == ""
    assert ext_models.clean_text(True, 300) == ""
    assert ext_models.clean_text(None, 300) == ""
    assert ext_models.clean_text(1859, 300) == "1859"
    assert ext_models.clean_text("  A <b>title</b> ", 300) == "A title"


def test_capabilities_projection_is_typed_and_drops_nested_canaries():
    caps = {
        "id": "ndl", "name": "National Diet Library",
        "country": "Japan", "official_site": "https://www.ndl.go.jp/",
        "languages": ["ja", {"x": "CANARY"}],
        "capabilities": {"catalog_search": True,
                         "page_ocr": "not-a-bool",
                         "evil": {"nested": "CANARY"}},
        "capability_status": {"catalog_search": "verified",
                              "page_ocr": {"nested": "CANARY"}},
        "internal_note": "CANARY",
        "standards": {"nested": "CANARY"},
    }
    out = ext_models.project_capabilities(caps)
    blob = json.dumps(out)
    assert "CANARY" not in blob
    assert out["library_id"] == "ndl"
    assert out["languages"] == ["ja"]
    assert out["capabilities"] == {"catalog_search": True}
    assert out["capability_status"] == {"catalog_search": "verified"}
    assert out["standards"] is None


# ---------------------------------------------------------------- 4.7

def test_clean_url_requires_known_library_host():
    assert ext_models.clean_url(
        "https://dl.ndl.go.jp/item/1", "ndl") is not None
    assert ext_models.clean_url(
        "https://evil.example.com/item/1", "ndl") is None
    assert ext_models.clean_url(
        "https://dl.ndl.go.jp/item/1", "unknown-lib") is None


def test_clean_url_rejects_credential_shaped_query():
    assert ext_models.clean_url(
        "https://dl.ndl.go.jp/item/1?api_key=xyz", "ndl") is None
    assert ext_models.clean_url(
        "https://dl.ndl.go.jp/item/1?token=abc", "ndl") is None
    jwt_like = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" \
               ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" \
               ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
    assert ext_models.clean_url(
        f"https://dl.ndl.go.jp/item/1?ref={jwt_like}", "ndl") is None
    assert ext_models.clean_url(
        "https://dl.ndl.go.jp/item/1?page=3", "ndl") is not None


def test_clean_url_rejects_disguised_numeric_hosts():
    assert ext_models.clean_url("https://2130706433/x", "ndl") is None
    assert ext_models.clean_url("https://0x7f000001/x", "ndl") is None
    assert ext_models.clean_url("https://127.0.0.1/x", "ndl") is None


# ---------------------------------------------------------------- 4.8

class _EchoService(_FakeService):
    """Payload asserts the requested ids but marks nothing as
    upstream-carried: the identifiers are a request echo."""

    async def get_document(self, library_id, record_id):
        doc = dict(self.doc, library_id=library_id,
                   record_id=record_id)
        return doc


class _MissingIdService(_FakeService):
    async def get_document(self, library_id, record_id):
        return {"rights": {"statement": "Public Domain"},
                "title": "No identifiers at all"}


def _doc_id(library="ndl", record="12345"):
    from global_library_mcp.external.ids import make_document_id
    return make_document_id(library, record)


def test_fetch_distinguishes_echo_from_upstream_confirmation():
    server, ctx = _server(service=_EchoService())
    _grant(ctx)
    out = _call(server, "fetch", {"id": _doc_id()})
    doc = json.loads(out)["document"]
    assert doc["verification"]["identity_state"] == "request_echo"
    assert doc["verification"]["document_identity_verified"] is False


def test_fetch_reports_missing_identity():
    server, ctx = _server(service=_MissingIdService())
    _grant(ctx)
    out = _call(server, "fetch", {"id": _doc_id()})
    doc = json.loads(out)["document"]
    assert doc["verification"]["identity_state"] == "missing"
    assert doc["verification"]["document_identity_verified"] is False


def test_rights_are_not_certified_for_missing_identity():
    server, ctx = _server(service=_MissingIdService())
    _grant(ctx)
    out = _call(server, "get_document_rights", {"id": _doc_id()})
    assert "document_identity_unverified" in out


def test_rights_report_identity_state_for_echo():
    server, ctx = _server(service=_EchoService())
    _grant(ctx)
    out = _call(server, "get_document_rights", {"id": _doc_id()})
    rights = json.loads(out)["rights"]
    assert rights["identity_state"] == "request_echo"
    assert rights["identity_verified"] is False


# ---------------------------------------------------------------- 4.9

def test_consent_file_rejects_nan_and_unknown_classes(tmp_path):
    path = tmp_path / "consent.json"
    path.write_text(json.dumps({"users": {
        "nan-user": {"data_classes": ["bibliographic"],
                     "libraries": None, "expires_at": float("nan"),
                     "revoked": False, "generation": 1},
        "unknown-class": {"data_classes": ["bibliographic", "telepathy"],
                          "libraries": None, "expires_at": 9999999999,
                          "revoked": False, "generation": 1},
        "bad-libs": {"data_classes": ["bibliographic"],
                     "libraries": ["NDL!!"], "expires_at": 9999999999,
                     "revoked": False, "generation": 1},
        "good": {"data_classes": ["bibliographic"],
                 "libraries": ["ndl"], "expires_at": 9999999999,
                 "revoked": False, "generation": 3},
    }}), encoding="utf-8")
    store = ConsentStore(str(path))
    assert store.has("nan-user", "bibliographic") is False
    assert store.has("unknown-class", "bibliographic") is False
    assert store.has("bad-libs", "bibliographic", "ndl") is False
    assert store.has("good", "bibliographic", "ndl") is True
    assert store.generation("good") == 3


def test_consent_file_written_owner_only_with_version(tmp_path):
    path = tmp_path / "consent.json"
    store = ConsentStore(str(path))
    store.grant("u1", {"bibliographic"}, ttl_s=3600)
    mode = os.stat(path).st_mode & 0o777
    assert mode == 0o600, oct(mode)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    # And it round-trips.
    store2 = ConsentStore(str(path))
    assert store2.has("u1", "bibliographic") is True


def test_consent_file_symlink_is_refused(tmp_path):
    target = tmp_path / "real.json"
    target.write_text(json.dumps({"users": {
        "u1": {"data_classes": ["bibliographic"], "libraries": None,
               "expires_at": 9999999999, "revoked": False,
               "generation": 1}}}), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    store = ConsentStore(str(link))
    assert store.has("u1", "bibliographic") is False


def test_consent_file_future_version_fails_closed(tmp_path):
    path = tmp_path / "consent.json"
    path.write_text(json.dumps({"version": 99, "users": {
        "u1": {"data_classes": ["bibliographic"], "libraries": None,
               "expires_at": 9999999999, "revoked": False,
               "generation": 1}}}), encoding="utf-8")
    store = ConsentStore(str(path))
    assert store.has("u1", "bibliographic") is False


# ---------------------------------------------------------------- 4.10

def test_direct_construction_refuses_disabled_profile():
    with pytest.raises(RuntimeError):
        build_external_server(_config(disabled=True))


def test_direct_construction_refuses_dns_check_disabled():
    with pytest.raises(RuntimeError):
        build_external_server(_config(dns_check_explicitly_disabled=True))


# ---------------------------------------------------------------- 4.11

def test_audit_records_response_size_basis():
    server, ctx = _server()
    _grant(ctx)
    _call(server, "list_libraries", {})
    events = [e for e in ctx.audit.events if e["tool"] == "list_libraries"]
    assert events and events[0]["response_bytes_basis"] == "projected_json"
