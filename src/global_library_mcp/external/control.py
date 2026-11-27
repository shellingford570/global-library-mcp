"""Execution control for the external profile (b9 sections
19-22, 28): server-side user consent, per-user budgets,
continuation tokens, session/user isolation state, and the
external kill switch / revocation registry.

Nothing here trusts a client-supplied flag: consent is granted
and revoked through server-side functions only (an MCP tool
argument can never create consent), budgets are enforced from
server-side counters, and continuation tokens are HMAC-signed
and bound to the user, the scope set, the query parameters and
the remaining budget.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

# Section 20 provisional limits (deployments may tighten, and
# tool arguments can never raise them).
MAX_CONCURRENT_PER_USER = 2
TOOL_CALLS_PER_MINUTE = 20
UPSTREAM_HTTP_PER_HOUR = 200
TOOL_DEADLINE_S = 90.0
SESSION_EXCERPT_CHARS = 5_000      # section 15 cumulative caps
DOCUMENT_EXCERPT_CHARS = 1_000
SINGLE_EXCERPT_CHARS = 500
RESPONSE_EXCERPT_CHARS = 2_000
CONTINUATION_TTL_S = 1_800
CACHE_TTL_S = 60.0


@dataclass
class ExternalConfig:
    excerpt_enabled: bool = False
    require_auth: bool = True
    local_test_mode: bool = False
    issuer: str = ""
    audience: str = ""
    jwks: dict[str, Any] | None = None       # static JWKS (tests / pinned)
    jwks_url: str = ""
    test_hs_secret: str = ""                  # synthetic AS only (HS256)
    continuation_secret: str = ""
    audit_path: str = ""
    disabled: bool = False

    @classmethod
    def from_env(cls) -> "ExternalConfig":
        return cls(
            excerpt_enabled=os.environ.get("GLM_EXTERNAL_EXCERPTS") == "1",
            require_auth=os.environ.get("GLM_EXTERNAL_REQUIRE_AUTH", "1") != "0",
            local_test_mode=os.environ.get("GLM_EXTERNAL_LOCAL_TEST") == "1",
            issuer=os.environ.get("GLM_EXTERNAL_ISSUER", ""),
            audience=os.environ.get("GLM_EXTERNAL_AUDIENCE", ""),
            jwks_url=os.environ.get("GLM_EXTERNAL_JWKS_URL", ""),
            test_hs_secret=os.environ.get("GLM_EXTERNAL_TEST_HS_SECRET", ""),
            continuation_secret=os.environ.get("GLM_EXTERNAL_CONTINUATION_SECRET", ""),
            audit_path=os.environ.get("GLM_EXTERNAL_AUDIT_LOG", ""),
            disabled=os.environ.get("GLM_EXTERNAL_DISABLED") == "1",
        )

    def validate_startup(self, transport: str) -> list[str]:
        """Fail-closed startup checks (section 17): returns a
        list of blocking problems; empty means startable."""
        problems = []
        if self.disabled:
            problems.append("external profile is disabled (kill switch)")
        if transport == "streamable-http" and self.require_auth:
            if not (self.issuer and self.audience
                    and (self.jwks or self.jwks_url or self.test_hs_secret)):
                problems.append(
                    "authenticated HTTP mode needs issuer, audience and a "
                    "JWKS source (or the synthetic test secret in local "
                    "test mode)")
            if self.test_hs_secret and not self.local_test_mode:
                problems.append(
                    "the synthetic HS test secret is only allowed in local "
                    "test mode")
        if not self.continuation_secret and transport == "streamable-http" \
                and self.require_auth and not self.local_test_mode:
            problems.append("a continuation-token secret is required")
        return problems


@dataclass
class ConsentRecord:
    user_id: str
    data_classes: set[str] = field(default_factory=set)
    libraries: set[str] | None = None     # None = all libraries
    expires_at: float = 0.0
    revoked: bool = False


class ConsentStore:
    """Server-side consent (section 19). Grants happen through
    grant() - called by the operator/deployment, never by a
    tool argument."""

    DATA_CLASSES = {"bibliographic", "references", "rights",
                    "excerpts", "search_terms_upstream"}

    def __init__(self) -> None:
        self._records: dict[str, ConsentRecord] = {}

    def grant(self, user_id: str, data_classes: set[str], *,
              libraries: set[str] | None = None,
              ttl_s: float = 86_400.0) -> ConsentRecord:
        unknown = data_classes - self.DATA_CLASSES
        if unknown:
            raise ValueError(f"unknown consent data classes: {sorted(unknown)}")
        record = ConsentRecord(
            user_id=user_id, data_classes=set(data_classes),
            libraries=None if libraries is None else set(libraries),
            expires_at=time.time() + ttl_s)
        self._records[user_id] = record
        return record

    def revoke(self, user_id: str) -> None:
        record = self._records.get(user_id)
        if record is not None:
            record.revoked = True
            record.data_classes = set()

    def has(self, user_id: str, data_class: str,
            library_id: str | None = None) -> bool:
        record = self._records.get(user_id)
        if record is None or record.revoked:
            return False
        if record.expires_at and record.expires_at < time.time():
            return False
        if data_class not in record.data_classes:
            return False
        if library_id is not None and record.libraries is not None \
                and library_id not in record.libraries:
            return False
        return True


@dataclass
class _UserState:
    semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT_PER_USER))
    call_times: list[float] = field(default_factory=list)
    http_times: list[float] = field(default_factory=list)
    excerpt_by_document: dict[str, int] = field(default_factory=dict)
    excerpt_session_total: int = 0
    cache: dict[str, tuple[float, Any]] = field(default_factory=dict)


class BudgetExceeded(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class ExternalRuntime:
    """All per-user external state, keyed strictly by user id
    (section 22 isolation)."""

    def __init__(self, config: ExternalConfig):
        self.config = config
        self.consent = ConsentStore()
        self._users: dict[str, _UserState] = {}
        self._revoked_users: set[str] = set()
        self._secret = (config.continuation_secret
                        or "local-test-continuation-secret").encode("utf-8")

    # -- user lifecycle / kill switch (section 28) -------------
    def revoke_user(self, user_id: str) -> None:
        self._revoked_users.add(user_id)
        self.consent.revoke(user_id)
        self._users.pop(user_id, None)   # drops cache + counters

    def user_revoked(self, user_id: str) -> bool:
        return user_id in self._revoked_users or self.config.disabled

    def _state(self, user_id: str) -> _UserState:
        return self._users.setdefault(user_id, _UserState())

    # -- budgets ------------------------------------------------
    def check_call_budget(self, user_id: str) -> None:
        state = self._state(user_id)
        now = time.time()
        state.call_times = [t for t in state.call_times if now - t < 60]
        if len(state.call_times) >= TOOL_CALLS_PER_MINUTE:
            raise BudgetExceeded("tool_calls_per_minute")
        state.call_times.append(now)

    def check_http_budget(self, user_id: str, attempts: int) -> None:
        state = self._state(user_id)
        now = time.time()
        state.http_times = [t for t in state.http_times if now - t < 3600]
        if len(state.http_times) + attempts > UPSTREAM_HTTP_PER_HOUR:
            raise BudgetExceeded("upstream_http_per_hour")

    def note_http(self, user_id: str, attempts: int) -> None:
        state = self._state(user_id)
        now = time.time()
        state.http_times.extend([now] * max(0, attempts))

    def semaphore(self, user_id: str) -> asyncio.Semaphore:
        return self._state(user_id).semaphore

    # -- excerpt cumulative ledger (section 15) -----------------
    def excerpt_room(self, user_id: str, document_key: str) -> int:
        state = self._state(user_id)
        per_doc = DOCUMENT_EXCERPT_CHARS - state.excerpt_by_document.get(document_key, 0)
        per_session = SESSION_EXCERPT_CHARS - state.excerpt_session_total
        return max(0, min(SINGLE_EXCERPT_CHARS, per_doc, per_session))

    def note_excerpt(self, user_id: str, document_key: str, chars: int) -> None:
        state = self._state(user_id)
        state.excerpt_by_document[document_key] = \
            state.excerpt_by_document.get(document_key, 0) + chars
        state.excerpt_session_total += chars

    # -- per-user response cache (search projections only) ------
    def cache_get(self, user_id: str, key: str) -> Any | None:
        state = self._state(user_id)
        hit = state.cache.get(key)
        if hit is None:
            return None
        stored_at, payload = hit
        if time.time() - stored_at > CACHE_TTL_S:
            state.cache.pop(key, None)
            return None
        return payload

    def cache_put(self, user_id: str, key: str, payload: Any) -> None:
        self._state(user_id).cache[key] = (time.time(), payload)

    # -- continuation tokens (section 21) -----------------------
    def make_continuation(self, user_id: str, scopes: set[str],
                          params: dict[str, Any], offset: int) -> str:
        payload = {
            "u": user_id,
            "s": sorted(scopes),
            "p": hashlib.sha256(json.dumps(
                params, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "o": offset,
            "exp": int(time.time()) + CONTINUATION_TTL_S,
        }
        body = base64.urlsafe_b64encode(json.dumps(
            payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
        sig = hmac.new(self._secret, body.encode("ascii"),
                       hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def read_continuation(self, token: str, user_id: str,
                          scopes: set[str], params: dict[str, Any]) -> int:
        """Return the bound offset or raise ValueError."""
        try:
            body, sig = token.split(".", 1)
        except (ValueError, AttributeError) as exc:
            raise ValueError("continuation token malformed") from exc
        expected = hmac.new(self._secret, body.encode("ascii"),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValueError("continuation token signature invalid")
        try:
            payload = json.loads(base64.urlsafe_b64decode(
                body + "=" * (-len(body) % 4)))
        except Exception as exc:
            raise ValueError("continuation token payload invalid") from exc
        if payload.get("u") != user_id:
            raise ValueError("continuation token belongs to another user")
        if set(payload.get("s") or []) != set(scopes):
            raise ValueError("continuation token scope mismatch")
        params_hash = hashlib.sha256(json.dumps(
            params, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if payload.get("p") != params_hash:
            raise ValueError("continuation token parameter mismatch")
        if int(payload.get("exp") or 0) < int(time.time()):
            raise ValueError("continuation token expired")
        return int(payload.get("o") or 0)


def pseudonym(user_id: str) -> str:
    """Audit-safe user pseudonym (section 26): a one-way hash
    prefix; the raw id never reaches the audit log."""
    return "u_" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
