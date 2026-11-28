"""Execution control for the external profile (b9 sections
19-22, 28; final-review P0 rework; b10 Stage 0 hardening).

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

b10 Stage 0 changes (docs/b10-b9-regression-hardening.md):
authorisation currency now includes EXPIRY - natural consent
expiry and access-token expiry make a guard stale and refuse
sends, not only grant/revoke generation changes; the send-path
guard also receives the library each send belongs to and
refuses sends to libraries outside the consent record's
library set; per-user budget history lives in a ledger that
state eviction and revocation can never erase inside its
measurement window, and the tracked-user cap is strict (new
users are refused at capacity instead of silently exceeding
it); the persisted consent file is strictly validated
(unknown data classes, non-finite expiries and malformed rows
are refused fail-closed), carries a policy version, and is
written with owner-only permissions.

Deployment limit, stated plainly: all counters, ledgers and
revocation sets here are PER-PROCESS. A multi-process or
restarted deployment does not share them; only the persisted
consent file (grants, expiries, revocations) survives a
restart. Operators needing cross-process budget enforcement
must front the profile with a single process or an external
coordinator - that is a production blocker, not a detail.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
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


CONSENT_FILE_VERSION = 1
_LIBRARY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ConsentStore:
    """Server-side consent (section 19). Grants happen through
    grant() - called by the operator/deployment, never by a
    tool argument. Records carry a per-user generation counter
    that increments on every grant/revoke, so in-flight work
    holding an older generation is refused at the next send.

    When ``path`` is configured the store is persisted as JSON
    (atomic replace) so consent, its expiry and revocations
    survive restarts; the file is operator-managed state and is
    never written by tool calls.

    b10 Stage 0 (brief 4.9): the persisted file is validated
    strictly on load - a symlinked path is refused, unknown
    policy versions fail closed, and any row with wrong types,
    unknown data classes, malformed library ids or a
    non-finite expiry (NaN/Infinity would otherwise make
    consent permanent) is dropped, so a corrupt or hostile
    file can only ever REMOVE consent, never create it. The
    file is written owner-only (0600). A policy ``version``
    distinguishes the operator's consent format; administrator
    revocation and the data subject's own grant are the same
    record here - the store records WHAT is consented, and the
    operator channel that calls grant()/revoke() is the trust
    boundary (there is no tool path to either)."""

    DATA_CLASSES = {"bibliographic", "references", "rights",
                    "images", "excerpts", "search_terms_upstream"}

    def __init__(self, path: str = "") -> None:
        self._records: dict[str, ConsentRecord] = {}
        self._path = path
        self._lock = threading.Lock()
        if path:
            self._load()

    # -- persistence -------------------------------------------
    def _load(self) -> None:
        if os.path.islink(self._path):
            return  # symlinked consent state is refused (fail-closed)
        try:
            with open(self._path, encoding="utf-8") as fh:
                # NaN/Infinity parse to non-finite floats and
                # are rejected per-row by the finite checks in
                # _parse_consent_row (one corrupt row must not
                # erase every other user's consent).
                raw = json.load(fh)
        except (OSError, ValueError):
            return  # unreadable consent state = no consent (fail-closed)
        if not isinstance(raw, dict):
            return
        version = raw.get("version", CONSENT_FILE_VERSION)
        if not isinstance(version, int) or isinstance(version, bool) \
                or version > CONSENT_FILE_VERSION:
            return  # unknown future format: fail closed
        users = raw.get("users")
        if not isinstance(users, dict):
            return
        for user_id, row in users.items():
            record = _parse_consent_row(user_id, row)
            if record is not None:
                self._records[user_id] = record

    def _save(self) -> None:
        if not self._path or os.path.islink(self._path):
            return
        payload = {"version": CONSENT_FILE_VERSION, "users": {
            uid: {
                "data_classes": sorted(r.data_classes),
                "libraries": None if r.libraries is None else sorted(r.libraries),
                "expires_at": r.expires_at,
                "revoked": r.revoked,
                "generation": r.generation,
            } for uid, r in self._records.items()}}
        tmp = self._path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, self._path)

    # -- operations ---------------------------------------------
    def grant(self, user_id: str, data_classes: set[str], *,
              libraries: set[str] | None = None,
              ttl_s: float = 86_400.0) -> ConsentRecord:
        unknown = data_classes - self.DATA_CLASSES
        if unknown:
            raise ValueError(f"unknown consent data classes: {sorted(unknown)}")
        with self._lock:
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
        with self._lock:
            record = self._records.get(user_id)
            if record is not None:
                record.revoked = True
                record.data_classes = set()
                record.generation += 1
                self._save()

    def generation(self, user_id: str) -> int:
        record = self._records.get(user_id)
        return record.generation if record is not None else 0

    def _expired(self, record: ConsentRecord) -> bool:
        return bool(record.expires_at) and record.expires_at < time.time()

    def current(self, user_id: str, generation: int) -> bool:
        """The full authorisation-currency check (b10 4.1): the
        snapshot still matches reality - no record appeared, the
        record is not revoked, still carries the generation the
        caller snapshotted, and has NOT reached its natural
        expiry. Generation alone was insufficient - expiry does
        not change the generation."""
        record = self._records.get(user_id)
        if record is None:
            return generation == 0
        if record.revoked or record.generation != generation:
            return False
        return not self._expired(record)

    def granted_classes(self, user_id: str,
                        library_id: str | None = None) -> frozenset[str]:
        """The data classes currently in force for a user (and
        library, when given) - the projection layer gates each
        field on its own class (b10 4.2), so this is the single
        source the projections consult."""
        record = self._records.get(user_id)
        if record is None or record.revoked or self._expired(record):
            return frozenset()
        if library_id is not None and record.libraries is not None \
                and library_id not in record.libraries:
            return frozenset()
        return frozenset(record.data_classes)

    def has(self, user_id: str, data_class: str,
            library_id: str | None = None) -> bool:
        record = self._records.get(user_id)
        if record is None or record.revoked:
            return False
        if self._expired(record):
            return False
        if data_class not in record.data_classes:
            return False
        if library_id is not None and record.libraries is not None \
                and library_id not in record.libraries:
            return False
        return True


def _parse_consent_row(user_id: Any, row: Any) -> ConsentRecord | None:
    """One persisted consent row -> record, or None when the
    row is malformed in ANY way (fail-closed per user)."""
    if not isinstance(user_id, str) or not user_id \
            or not isinstance(row, dict):
        return None
    classes = row.get("data_classes")
    if not isinstance(classes, list) \
            or not all(isinstance(c, str) for c in classes) \
            or not set(classes) <= ConsentStore.DATA_CLASSES:
        return None
    libraries = row.get("libraries")
    if libraries is not None:
        if not isinstance(libraries, list) \
                or not all(isinstance(lib, str)
                           and _LIBRARY_ID_RE.match(lib)
                           for lib in libraries):
            return None
        libraries = set(libraries)
    expires_at = row.get("expires_at")
    if isinstance(expires_at, bool) \
            or not isinstance(expires_at, (int, float)) \
            or not math.isfinite(expires_at):
        return None
    revoked = row.get("revoked")
    if not isinstance(revoked, bool):
        return None
    generation = row.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) \
            or generation < 0:
        return None
    return ConsentRecord(
        user_id=user_id, data_classes=set(classes),
        libraries=libraries, expires_at=float(expires_at),
        revoked=revoked, generation=generation)


@dataclass
class _UserState:
    """Ephemeral per-user execution state (semaphore, response
    cache). Safe to evict: nothing security-relevant lives here
    any more (b10 4.4) - budgets moved to the ledger below."""
    semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT_PER_USER))
    waiting: int = 0
    cache: dict[str, tuple[float, int, Any]] = field(default_factory=dict)
    last_used: float = 0.0


@dataclass
class _BudgetLedger:
    """Per-user budget history (b10 4.4). Kept APART from the
    evictable execution state: evicting or revoking a user's
    runtime state must never hand them a fresh HTTP budget
    inside the measurement window. Entries are dropped only
    once every timestamp has aged out of its window."""
    call_times: list[float] = field(default_factory=list)
    http_times: list[float] = field(default_factory=list)
    http_host_times: dict[str, list[float]] = field(default_factory=dict)

    def idle(self, now: float) -> bool:
        if any(now - t < 60 for t in self.call_times):
            return False
        if any(now - t < 3600 for t in self.http_times):
            return False
        return all(now - t >= 3600
                   for times in self.http_host_times.values()
                   for t in times)


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
    upstream attempt/byte counts for the audit log.

    b10 4.1/4.3: the guard snapshots the consent generation AND
    the access token's expiry, and reserve() receives the
    library the send belongs to (when the service layer knows
    it), so expiry and per-library consent are re-evaluated at
    the last moment before the wire, not only at call start."""

    def __init__(self, runtime: "ExternalRuntime", user_id: str,
                 consent_generation: int, token_expires_at: float = 0.0):
        self._runtime = runtime
        self.user_id = user_id
        self._consent_generation = consent_generation
        self._token_expires_at = float(token_expires_at or 0.0)
        self.attempts = 0
        self.bytes_received = 0

    def reserve(self, host: str, library_id: str | None = None) -> None:
        self._runtime._guard_reserve(self, host, library_id)

    def note_bytes(self, nbytes: int) -> None:
        self.bytes_received += int(nbytes)

    def token_expired(self) -> bool:
        return bool(self._token_expires_at) \
            and time.time() >= self._token_expires_at

    def stale(self) -> bool:
        """True when the authorisation snapshot this guard was
        created under no longer holds: user revoked, consent
        granted/revoked since, consent EXPIRED naturally, or
        the access token has reached its expiry (b10 4.1) -
        checked after queueing and before returning a
        response."""
        return self._runtime.user_revoked(self.user_id) \
            or not self._runtime.consent.current(
                self.user_id, self._consent_generation) \
            or self.token_expired()


class ExternalRuntime:
    """All per-user external state, keyed strictly by user id
    (section 22 isolation), with capacity caps."""

    def __init__(self, config: ExternalConfig):
        self.config = config
        self.consent = ConsentStore(config.consent_path)
        self._users: dict[str, _UserState] = {}
        self._ledger: dict[str, _BudgetLedger] = {}
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
        # Ephemeral state (cache, semaphore) is dropped, but the
        # budget LEDGER is deliberately kept (b10 4.4): if the
        # revocation is ever lifted inside the measurement
        # window, the user's earlier sends still count.
        self._users.pop(user_id, None)
        for task in list(self._inflight.get(user_id, ())):
            task.cancel()                # in-flight work stops now
        if self.on_revoke is not None:
            self.on_revoke(user_id)

    def user_revoked(self, user_id: str) -> bool:
        return user_id in self._revoked_users or self.config.disabled

    def _ledger_for(self, user_id: str) -> _BudgetLedger:
        ledger = self._ledger.get(user_id)
        if ledger is None:
            if len(self._ledger) >= MAX_TRACKED_USERS:
                now = time.time()
                stale = [uid for uid, entry in self._ledger.items()
                         if entry.idle(now)]
                for uid in stale:
                    self._ledger.pop(uid, None)
            if len(self._ledger) >= MAX_TRACKED_USERS:
                # Strict cap (b10 4.4): a new user whose budget
                # cannot even be recorded is refused, never
                # silently untracked.
                raise BudgetExceeded("user_capacity")
            ledger = _BudgetLedger()
            self._ledger[user_id] = ledger
        return ledger

    def _state(self, user_id: str) -> _UserState:
        state = self._users.get(user_id)
        if state is None:
            if len(self._users) >= MAX_TRACKED_USERS:
                idle = [uid for uid, s in self._users.items()
                        if not self._inflight.get(uid)]
                if idle:
                    oldest = min(idle, key=lambda u: self._users[u].last_used)
                    self._users.pop(oldest, None)
                else:
                    # Strict cap (b10 4.4): everyone is busy, so
                    # the new user is refused rather than the cap
                    # being exceeded.
                    raise BudgetExceeded("user_capacity")
            state = _UserState()
            self._users[user_id] = state
        state.last_used = time.monotonic()
        return state

    # -- in-flight tracking (final review: revocation cancels) --
    def track(self, user_id: str, task: asyncio.Task) -> None:
        self._inflight.setdefault(user_id, set()).add(task)
        task.add_done_callback(
            lambda _t: self._inflight.get(user_id, set()).discard(task))

    def untrack(self, user_id: str, task: asyncio.Task) -> None:
        """Remove a task when its CALL finishes. Tracking is
        per call, not per task lifetime: a host task that runs
        many calls must not stay registered (and cancellable)
        after the call it was tracked for has ended."""
        self._inflight.get(user_id, set()).discard(task)

    # -- tool-call rate budget ----------------------------------
    def check_call_budget(self, user_id: str) -> None:
        ledger = self._ledger_for(user_id)
        now = time.time()
        ledger.call_times = [t for t in ledger.call_times if now - t < 60]
        if len(ledger.call_times) >= TOOL_CALLS_PER_MINUTE:
            raise BudgetExceeded("tool_calls_per_minute")
        ledger.call_times.append(now)

    # -- the send-path guard (final review P0) -------------------
    def http_guard(self, user_id: str,
                   token_expires_at: float = 0.0) -> UserHttpGuard:
        return UserHttpGuard(self, user_id,
                             self.consent.generation(user_id),
                             token_expires_at=token_expires_at)

    def _guard_reserve(self, guard: UserHttpGuard, host: str,
                       library_id: str | None = None) -> None:
        """Atomic check-and-count, called by BudgetedTransport
        immediately before a send. Any refusal raises the http
        layer's BudgetExceeded, so nothing is sent. Counts are
        taken pre-send and never refunded: retries, redirects,
        failures and cancellations all consumed upstream
        attention. Cache hits never reach this point.

        b10 4.1/4.3: the authorisation re-evaluated here is the
        CURRENT one - revocation, consent generation, consent
        EXPIRY and token expiry all refuse the send - and when
        the send's library is known, the consent record's
        library set binds it: a send for a library outside the
        consented set is refused whatever host it targets, so
        future routing changes cannot silently reach an
        unconsented library through a shared host."""
        from global_library_mcp.http import BudgetExceeded as HttpBudgetExceeded

        user_id = guard.user_id
        with self._lock:
            if self.user_revoked(user_id):
                raise HttpBudgetExceeded(
                    "external access for this user was revoked")
            if guard._consent_generation == 0 \
                    or not self.consent.current(
                        user_id, guard._consent_generation):
                raise HttpBudgetExceeded(
                    "consent expired or changed during the operation; "
                    "sends stopped")
            if guard.token_expired():
                raise HttpBudgetExceeded(
                    "access token expired during the operation; "
                    "sends stopped")
            if library_id is not None:
                record = self.consent._records.get(user_id)
                if record is not None and record.libraries is not None \
                        and library_id not in record.libraries:
                    raise HttpBudgetExceeded(
                        f"library {library_id} is outside the consented "
                        "library set; send refused")
            try:
                ledger = self._ledger_for(user_id)
            except BudgetExceeded as exc:
                raise HttpBudgetExceeded(
                    "per-user budget ledger is at capacity") from exc
            now = time.time()
            ledger.http_times = [t for t in ledger.http_times
                                 if now - t < 3600]
            if len(ledger.http_times) >= UPSTREAM_HTTP_PER_HOUR:
                raise HttpBudgetExceeded(
                    f"per-user upstream HTTP budget exhausted "
                    f"({UPSTREAM_HTTP_PER_HOUR}/hour)")
            host_times = ledger.http_host_times.setdefault(host, [])
            host_times[:] = [t for t in host_times if now - t < 3600]
            if len(host_times) >= UPSTREAM_HTTP_PER_HOST_HOUR:
                raise HttpBudgetExceeded(
                    f"per-user per-host HTTP budget exhausted for {host} "
                    f"({UPSTREAM_HTTP_PER_HOST_HOUR}/hour)")
            ledger.http_times.append(now)
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
