"""Execution control for the external profile (b9 sections
19-22, 28; final-review P0 rework).

Server-side user consent (per data class AND per library,
optionally persisted by the operator), per-user budgets
enforced ON THE SEND PATH through a guard object the budgeted
transport consults immediately before every wire send,
bounded-queue execution slots under one absolute deadline,
in-flight task tracking so revocation cancels running work,
and strict per-user state isolation with capacity caps.

Nothing here trusts a client-supplied flag: consent is granted
and revoked through server-side functions only (an MCP tool
argument can never create consent), and budgets are enforced
from server-side counters at the moment of sending.

Final-review changes: the earlier post-hoc check_http_budget /
note_http pair (which never blocked a send) is gone - the
UserHttpGuard IS the enforcement. Continuation tokens were
removed from the external profile entirely: pagination is a
plain offset, and every call is independently authorised,
consented and budgeted, so there is no bearer artefact whose
binding could go stale.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Section 20 provisional limits (deployments may tighten, and
# tool arguments can never raise them).
MAX_CONCURRENT_PER_USER = 2
MAX_WAITING_PER_USER = 4
TOOL_CALLS_PER_MINUTE = 20
UPSTREAM_HTTP_PER_HOUR = 200
UPSTREAM_HTTP_PER_HOST_HOUR = 100
TOOL_DEADLINE_S = 90.0
CACHE_TTL_S = 60.0
CACHE_MAX_ENTRIES = 64
MAX_TRACKED_USERS = 1_000


@dataclass
class ExternalConfig:
    excerpt_enabled: bool = False
    require_auth: bool = True
    local_test_mode: bool = False
    issuer: str = ""
    audience: str = ""
    resource_url: str = ""
    jwks: dict[str, Any] | None = None       # static JWKS (tests / pinned)
    jwks_url: str = ""
    test_hs_secret: str = ""                  # synthetic AS only (HS256)
    audit_path: str = ""
    audit_hmac_key: str = ""
    consent_path: str = ""
    dns_check_explicitly_disabled: bool = False
    disabled: bool = False

    @classmethod
    def from_env(cls) -> "ExternalConfig":
        dns_raw = os.environ.get("GLM_DNS_CHECK", "").strip().lower()
        return cls(
            excerpt_enabled=os.environ.get("GLM_EXTERNAL_EXCERPTS") == "1",
            require_auth=os.environ.get("GLM_EXTERNAL_REQUIRE_AUTH", "1") != "0",
            local_test_mode=os.environ.get("GLM_EXTERNAL_LOCAL_TEST") == "1",
            issuer=os.environ.get("GLM_EXTERNAL_ISSUER", ""),
            audience=os.environ.get("GLM_EXTERNAL_AUDIENCE", ""),
            resource_url=os.environ.get("GLM_EXTERNAL_RESOURCE_URL", ""),
            jwks_url=os.environ.get("GLM_EXTERNAL_JWKS_URL", ""),
            test_hs_secret=os.environ.get("GLM_EXTERNAL_TEST_HS_SECRET", ""),
            audit_path=os.environ.get("GLM_EXTERNAL_AUDIT_LOG", ""),
            audit_hmac_key=os.environ.get("GLM_EXTERNAL_AUDIT_HMAC_KEY", ""),
            consent_path=os.environ.get("GLM_EXTERNAL_CONSENT_FILE", ""),
            dns_check_explicitly_disabled=dns_raw in ("0", "false", "no"),
            disabled=os.environ.get("GLM_EXTERNAL_DISABLED") == "1",
        )

    def validate_startup(self, transport: str) -> list[str]:
        """Fail-closed startup checks (section 17; final review:
        direct server construction and the CLI share these).
        Returns a list of blocking problems; empty = startable."""
        problems = []
        if self.disabled:
            problems.append("external profile is disabled (kill switch)")
        if self.dns_check_explicitly_disabled:
            problems.append(
                "the DNS pre-check cannot be disabled in the external "
                "profile (GLM_DNS_CHECK=0 is refused)")
        if transport == "streamable-http" and not self.require_auth:
            problems.append(
                "authentication cannot be disabled in external HTTP mode")
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
            if self.test_hs_secret and (self.jwks or self.jwks_url):
                problems.append(
                    "ambiguous key source: configure either the synthetic "
                    "test secret or a JWKS source, not both")
            if self.resource_url and self.audience \
                    and self.resource_url != self.audience \
                    and not self.local_test_mode:
                problems.append(
                    "the OAuth resource URL and the token audience differ; "
                    "they must identify the same resource")
        return problems


@dataclass
class ConsentRecord:
    user_id: str
    data_classes: set[str] = field(default_factory=set)
    libraries: set[str] | None = None     # None = all libraries
    expires_at: float = 0.0
    revoked: bool = False
    generation: int = 0


class ConsentStore:
    """Server-side consent (section 19). Grants happen through
    grant() - called by the operator/deployment, never by a
    tool argument. Records carry a per-user generation counter
    that increments on every grant/revoke, so in-flight work
    holding an older generation is refused at the next send.

    When ``path`` is configured the store is persisted as JSON
    (atomic replace) so consent, its expiry and revocations
    survive restarts; the file is operator-managed state and is
    never written by tool calls."""

    DATA_CLASSES = {"bibliographic", "references", "rights",
                    "excerpts", "search_terms_upstream"}

    def __init__(self, path: str = "") -> None:
        self._records: dict[str, ConsentRecord] = {}
        self._path = path
        if path:
            self._load()

    # -- persistence -------------------------------------------
    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return  # unreadable consent state = no consent (fail-closed)
        for user_id, row in (raw.get("users") or {}).items():
            if not isinstance(row, dict):
                continue
            libraries = row.get("libraries")
            self._records[user_id] = ConsentRecord(
                user_id=user_id,
                data_classes=set(row.get("data_classes") or []),
                libraries=None if libraries is None else set(libraries),
                expires_at=float(row.get("expires_at") or 0.0),
                revoked=bool(row.get("revoked")),
                generation=int(row.get("generation") or 0))

    def _save(self) -> None:
        if not self._path:
            return
        payload = {"users": {
            uid: {
                "data_classes": sorted(r.data_classes),
                "libraries": None if r.libraries is None else sorted(r.libraries),
                "expires_at": r.expires_at,
                "revoked": r.revoked,
                "generation": r.generation,
            } for uid, r in self._records.items()}}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, self._path)

    # -- operations ---------------------------------------------
    def grant(self, user_id: str, data_classes: set[str], *,
              libraries: set[str] | None = None,
              ttl_s: float = 86_400.0) -> ConsentRecord:
        unknown = data_classes - self.DATA_CLASSES
        if unknown:
            raise ValueError(f"unknown consent data classes: {sorted(unknown)}")
        previous = self._records.get(user_id)
        record = ConsentRecord(
            user_id=user_id, data_classes=set(data_classes),
            libraries=None if libraries is None else set(libraries),
            expires_at=time.time() + ttl_s,
            generation=(previous.generation + 1) if previous else 1)
        self._records[user_id] = record
        self._save()
        return record

    def revoke(self, user_id: str) -> None:
        record = self._records.get(user_id)
        if record is not None:
            record.revoked = True
            record.data_classes = set()
            record.generation += 1
            self._save()

    def generation(self, user_id: str) -> int:
        record = self._records.get(user_id)
        return record.generation if record is not None else 0

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
    waiting: int = 0
    call_times: list[float] = field(default_factory=list)
    http_times: list[float] = field(default_factory=list)
    http_host_times: dict[str, list[float]] = field(default_factory=dict)
    cache: dict[str, tuple[float, int, Any]] = field(default_factory=dict)
    last_used: float = 0.0


class BudgetExceeded(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class QueueFull(Exception):
    """The per-user wait queue is at capacity (final review:
    waiting work is bounded, never unbounded)."""


class UserHttpGuard:
    """Per-tool-call send guard (final review P0). Installed
    into BudgetedTransport through the current_send_guard
    contextvar; the transport calls reserve() immediately
    before every wire send and note_bytes() with the decoded
    body size. Counters on this object are the call's REAL
    upstream attempt/byte counts for the audit log."""

    def __init__(self, runtime: "ExternalRuntime", user_id: str,
                 consent_generation: int):
        self._runtime = runtime
        self.user_id = user_id
        self._consent_generation = consent_generation
        self.attempts = 0
        self.bytes_received = 0

    def reserve(self, host: str) -> None:
        self._runtime._guard_reserve(self, host)

    def note_bytes(self, nbytes: int) -> None:
        self.bytes_received += int(nbytes)

    def stale(self) -> bool:
        """True when the authorisation snapshot this guard was
        created under no longer holds (user revoked, or consent
        granted/revoked since) - checked after queueing and
        before returning a response."""
        return self._runtime.user_revoked(self.user_id) \
            or self._runtime.consent.generation(self.user_id) \
            != self._consent_generation


class ExternalRuntime:
    """All per-user external state, keyed strictly by user id
    (section 22 isolation), with capacity caps."""

    def __init__(self, config: ExternalConfig):
        self.config = config
        self.consent = ConsentStore(config.consent_path)
        self._users: dict[str, _UserState] = {}
        self._revoked_users: set[str] = set()
        self._inflight: dict[str, set[asyncio.Task]] = {}
        self._lock = threading.Lock()
        # Set by the server context: called with the user id on
        # revocation so the event reaches the audit log.
        self.on_revoke: Callable[[str], None] | None = None

    # -- user lifecycle / kill switch (section 28) -------------
    def revoke_user(self, user_id: str) -> None:
        self._revoked_users.add(user_id)
        self.consent.revoke(user_id)
        self._users.pop(user_id, None)   # drops cache + counters
        for task in list(self._inflight.get(user_id, ())):
            task.cancel()                # in-flight work stops now
        if self.on_revoke is not None:
            self.on_revoke(user_id)

    def user_revoked(self, user_id: str) -> bool:
        return user_id in self._revoked_users or self.config.disabled

    def _state(self, user_id: str) -> _UserState:
        state = self._users.get(user_id)
        if state is None:
            if len(self._users) >= MAX_TRACKED_USERS:
                idle = [uid for uid, s in self._users.items()
                        if not self._inflight.get(uid)]
                if idle:
                    oldest = min(idle, key=lambda u: self._users[u].last_used)
                    self._users.pop(oldest, None)
            state = _UserState()
            self._users[user_id] = state
        state.last_used = time.monotonic()
        return state

    # -- in-flight tracking (final review: revocation cancels) --
    def track(self, user_id: str, task: asyncio.Task) -> None:
        self._inflight.setdefault(user_id, set()).add(task)
        task.add_done_callback(
            lambda _t: self._inflight.get(user_id, set()).discard(task))

    # -- tool-call rate budget ----------------------------------
    def check_call_budget(self, user_id: str) -> None:
        state = self._state(user_id)
        now = time.time()
        state.call_times = [t for t in state.call_times if now - t < 60]
        if len(state.call_times) >= TOOL_CALLS_PER_MINUTE:
            raise BudgetExceeded("tool_calls_per_minute")
        state.call_times.append(now)

    # -- the send-path guard (final review P0) -------------------
    def http_guard(self, user_id: str) -> UserHttpGuard:
        return UserHttpGuard(self, user_id, self.consent.generation(user_id))

    def _guard_reserve(self, guard: UserHttpGuard, host: str) -> None:
        """Atomic check-and-count, called by BudgetedTransport
        immediately before a send. Any refusal raises the http
        layer's BudgetExceeded, so nothing is sent. Counts are
        taken pre-send and never refunded: retries, redirects,
        failures and cancellations all consumed upstream
        attention. Cache hits never reach this point."""
        from global_library_mcp.http import BudgetExceeded as HttpBudgetExceeded

        user_id = guard.user_id
        with self._lock:
            if self.user_revoked(user_id):
                raise HttpBudgetExceeded(
                    "external access for this user was revoked")
            if self.consent.generation(user_id) != guard._consent_generation:
                raise HttpBudgetExceeded(
                    "consent changed during the operation; sends stopped")
            state = self._state(user_id)
            now = time.time()
            state.http_times = [t for t in state.http_times if now - t < 3600]
            if len(state.http_times) >= UPSTREAM_HTTP_PER_HOUR:
                raise HttpBudgetExceeded(
                    f"per-user upstream HTTP budget exhausted "
                    f"({UPSTREAM_HTTP_PER_HOUR}/hour)")
            host_times = state.http_host_times.setdefault(host, [])
            host_times[:] = [t for t in host_times if now - t < 3600]
            if len(host_times) >= UPSTREAM_HTTP_PER_HOST_HOUR:
                raise HttpBudgetExceeded(
                    f"per-user per-host HTTP budget exhausted for {host} "
                    f"({UPSTREAM_HTTP_PER_HOST_HOUR}/hour)")
            state.http_times.append(now)
            host_times.append(now)
            guard.attempts += 1

    # -- execution slot: bounded queue + absolute deadline -------
    @contextlib.asynccontextmanager
    async def slot(self, user_id: str, deadline_monotonic: float):
        """At most MAX_CONCURRENT_PER_USER running and
        MAX_WAITING_PER_USER waiting per user; the wait counts
        against the caller's absolute deadline."""
        state = self._state(user_id)
        if state.waiting >= MAX_WAITING_PER_USER and state.semaphore.locked():
            raise QueueFull(user_id)
        state.waiting += 1
        try:
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("deadline exceeded while queued")
            await asyncio.wait_for(state.semaphore.acquire(),
                                   timeout=remaining)
        finally:
            state.waiting -= 1
        try:
            yield
        finally:
            state.semaphore.release()

    # -- per-user response cache (search projections only) ------
    # Entries are bound to the consent generation they were
    # produced under: any grant/revoke makes them unreadable,
    # so a cached permission-era response can never be served
    # after consent changes (section 22).
    def cache_get(self, user_id: str, key: str) -> Any | None:
        state = self._state(user_id)
        hit = state.cache.get(key)
        if hit is None:
            return None
        stored_at, generation, payload = hit
        if generation != self.consent.generation(user_id):
            state.cache.pop(key, None)
            return None
        if time.time() - stored_at > CACHE_TTL_S:
            state.cache.pop(key, None)
            return None
        return payload

    def cache_put(self, user_id: str, key: str, payload: Any) -> None:
        state = self._state(user_id)
        state.cache[key] = (time.time(), self.consent.generation(user_id),
                            payload)
        while len(state.cache) > CACHE_MAX_ENTRIES:
            state.cache.pop(next(iter(state.cache)))


def pseudonym(user_id: str) -> str:
    """Audit-safe user pseudonym (section 26): a one-way hash
    prefix; the raw id never reaches the audit log. The audit
    log itself uses an HMAC form when a key is configured."""
    return "u_" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
