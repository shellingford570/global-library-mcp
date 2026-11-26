from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from global_library_mcp.adapters.base import AdapterError


class ResponseCache:
    def __init__(self, ttl_seconds: int = 60, max_size: int = 256):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._values.get(key)
        if not item or time.monotonic() - item[0] > self.ttl_seconds:
            return None
        return item[1]

    def put(self, key: str, value: Any) -> None:
        self._values[key] = (time.monotonic(), value)
        while len(self._values) > self.max_size:
            self._values.pop(next(iter(self._values)))


def sanitize_error(value: object) -> str:
    """Return an upstream error safe to expose without query credentials."""
    text = str(value)
    secret_names = {"api_key", "apikey", "key", "token", "wskey", "access_token"}
    url_pattern = re.compile(r"https?://[^\s'\"]+")
    def redact(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            parts = urlsplit(raw)
            query = urlencode([(key, "[redacted]" if key.lower() in secret_names else val) for key, val in parse_qsl(parts.query, keep_blank_values=True)])
            return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        except ValueError:
            return raw
    return url_pattern.sub(redact, text)


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        moment = parsedate_to_datetime(value)
        if moment is None:
            return None
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.timezone.utc)
        return max((moment - now).total_seconds(), 0.0)
    except Exception:
        return None


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    cache: ResponseCache | None = None,
    attempts: int = 2,
    max_retry_wait: float = 10.0,
) -> Any:
    key = str(httpx.URL(url, params=params))
    if cache:
        cached = cache.get(key)
        if cached is not None:
            return cached
    last_error: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(attempts):
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "")
                # b3.1 (review fix): honour the library's Retry-After
                # in full - never retry earlier than specified. Both
                # delta-seconds and HTTP-date forms are parsed. If the
                # required wait exceeds max_retry_wait (the caller's
                # deadline budget), do not retry at all: surface a
                # partial failure instead. 403 is never retried.
                wait = _retry_after_seconds(retry_after)
                if attempt + 1 < attempts and wait is not None and wait <= max_retry_wait:
                    await asyncio.sleep(max(wait, 0.0))
                    continue
                if wait is not None and wait > max_retry_wait:
                    # Retrying would mean returning earlier than the
                    # library allowed OR waiting past the caller's
                    # deadline; neither is acceptable, and the outer
                    # handler must not retry either (retryable=False).
                    raise AdapterError("http", f"Upstream rate limit (429); Retry-After={retry_after} exceeds the {max_retry_wait:.0f}s retry deadline; not retried", retryable=False)
                raise AdapterError("http", f"Upstream rate limit (429); Retry-After={retry_after or 'unknown'}", retryable=True)
            if response.status_code == 403:
                raise AdapterError("http", "Upstream access denied (403; challenge or policy restriction)", retryable=False)
            response.raise_for_status()
            value = response.json()
            if cache:
                cache.put(key, value)
            return value
        except (httpx.HTTPError, AdapterError) as exc:
            last_error = exc
            if isinstance(exc, AdapterError) and not exc.retryable:
                raise
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (attempt + 1))
    raise AdapterError("http", f"Upstream request failed: {sanitize_error(last_error)}", retryable=True)


# --- Real HTTP request budget (b3, Section 9; hardened in b3.1) -------------
# The service-layer budget counts processing units, not wire requests.
# HttpBudget counts every actual HTTP request attempt that leaves the
# process. Reservation is ATOMIC (b3.1 review fix): the attempt is
# counted under a lock BEFORE anything is sent, checking the total
# and per-host caps together, so concurrent requests cannot race
# past the limit. Attempts that time out, fail to connect or are
# cancelled stay counted - they did consume upstream attention.
# Received bytes are recorded separately from the request count.
# Response size is enforced WHILE STREAMING: a response is aborted
# and closed as soon as it exceeds the per-response cap or the
# operation's cumulative byte cap; Content-Length is checked before
# reading when present. Byte counts are of the DECODED body, so a
# small compressed response that expands hugely is still caught.

import contextlib
import contextvars
import threading


class BudgetExceeded(AdapterError):
    """Raised before a request is sent (or while streaming an
    oversized response) when the HTTP budget is spent."""

    def __init__(self, detail: str):
        super().__init__("http-budget", f"HTTP request budget exceeded: {detail}", retryable=False)
        self.detail = detail


class HttpBudget:
    def __init__(
        self,
        max_requests: int = 80,
        per_host_max: int = 40,
        max_response_bytes: int = 25_000_000,
        max_total_bytes: int = 120_000_000,
    ):
        self.max_requests = max_requests
        self.per_host_max = per_host_max
        self.max_response_bytes = max_response_bytes
        self.max_total_bytes = max_total_bytes
        self.requests = 0
        self.bytes_received = 0
        self.wire_bytes = 0
        self.per_host: dict[str, int] = {}
        self.exceeded = False
        self._lock = threading.Lock()

    def reserve(self, host: str) -> None:
        """Atomically claim one request attempt for `host`.

        Raises BudgetExceeded before any network activity when the
        total or per-host cap is already reached."""
        with self._lock:
            if self.requests >= self.max_requests:
                self.exceeded = True
                raise BudgetExceeded(f"operation limit {self.max_requests} requests reached")
            if self.per_host.get(host, 0) >= self.per_host_max:
                self.exceeded = True
                raise BudgetExceeded(f"per-host limit {self.per_host_max} requests for {host} reached")
            self.requests += 1
            self.per_host[host] = self.per_host.get(host, 0) + 1

    def record_bytes(self, nbytes: int) -> None:
        with self._lock:
            self.bytes_received += nbytes

    def record_wire_bytes(self, nbytes: int) -> None:
        """Bytes as they arrived on the network (still compressed).
        Tracked separately from the decoded byte count that the
        cumulative cap applies to (b4 review, Section 5)."""
        with self._lock:
            self.wire_bytes += nbytes

    def add_streamed_bytes(self, nbytes: int) -> None:
        """Account for response bytes AS THEY ARRIVE (b4, Section 2).

        Bytes are added atomically during streaming, so (a) several
        responses streaming concurrently share one running total and
        cannot jointly slip past the cumulative cap, and (b) bytes
        from responses that are later aborted, time out or are
        cancelled stay counted - they were received. Raises
        BudgetExceeded the moment the cumulative cap is crossed."""
        with self._lock:
            self.bytes_received += nbytes
            if self.bytes_received > self.max_total_bytes:
                self.exceeded = True
                raise BudgetExceeded(
                    f"cumulative response bytes exceeded the {self.max_total_bytes}-byte operation cap"
                )

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests": self.requests,
                "bytes_received": self.bytes_received,
            "bytes_on_wire": self.wire_bytes,
                "per_host": dict(self.per_host),
                "max_requests": self.max_requests,
                "per_host_max": self.per_host_max,
                "max_total_bytes": self.max_total_bytes,
                "exceeded": self.exceeded,
            }


# Per-host Retry-After gate (b4, Section 2): a 429 from a host
# raises a process-wide "not before" timestamp for that host, so a
# later request - from another operation or another user of this
# process - does not ignore the library's instruction either.
_host_gates: dict[str, float] = {}
_host_gates_lock = threading.Lock()


def _note_retry_after(host: str, seconds: float) -> None:
    import time as _time

    with _host_gates_lock:
        until = _time.monotonic() + max(seconds, 0.0)
        if until > _host_gates.get(host, 0.0):
            _host_gates[host] = until


# A Retry-After longer than this is not waited out inside a
# request; the send is refused and the caller reports a partial
# failure instead (b4 review, Section 5).
MAX_GATE_WAIT_S = 30.0


def _host_retry_wait(host: str) -> float:
    import time as _time

    with _host_gates_lock:
        return max(_host_gates.get(host, 0.0) - _time.monotonic(), 0.0)


current_http_budget: contextvars.ContextVar[HttpBudget | None] = contextvars.ContextVar(
    "current_http_budget", default=None
)


@contextlib.contextmanager
def use_budget(budget: HttpBudget):
    """Set the active HTTP budget, restoring the previous one on
    exit no matter how the block ends (b3.1: try/finally)."""
    token = current_http_budget.set(budget)
    try:
        yield budget
    finally:
        current_http_budget.reset(token)


# One concurrency cap shared by every BudgetedTransport on the same
# event loop (b3.1: proxy and direct transports previously had
# separate caps, doubling the effective limit).
_loop_semaphores: dict[int, asyncio.Semaphore] = {}


def _shared_semaphore(limit: int = 8) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = id(loop)
    semaphore = _loop_semaphores.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(limit)
        _loop_semaphores[key] = semaphore
    return semaphore


class FixtureTransport(httpx.AsyncBaseTransport):
    """Fixed upstream HTTP fixtures (b8 final review section
    18): serves recorded responses from a directory holding a
    manifest.json of routes {host, path, query_contains?,
    file, content_type?, status?}. Every other request is a
    404 - fixture mode NEVER falls through to the live
    network. Used by the mandatory CI configuration: real web
    server, real WorkspaceApi, real LibraryService, real
    adapters, real BudgetedTransport (this transport sits
    under it), real SQLite - only the upstream HTTP is fixed.
    """

    def __init__(self, fixture_dir: str):
        import json as _json
        from pathlib import Path as _Path
        self._dir = _Path(fixture_dir)
        manifest = _json.loads((self._dir / "manifest.json").read_text(encoding="utf-8"))
        self._routes = manifest.get("routes") or []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        query = str(request.url.query or "")
        for route in self._routes:
            if route.get("host") != host or route.get("path") != path:
                continue
            needle = route.get("query_contains")
            if needle and needle not in query:
                continue
            body = (self._dir / route["file"]).read_bytes()
            return httpx.Response(
                int(route.get("status", 200)), content=body,
                headers={"content-type": route.get("content_type", "application/octet-stream")},
                request=request)
        return httpx.Response(404, content=b"no upstream fixture for this request",
                              headers={"content-type": "text/plain"}, request=request)


class BudgetedTransport(httpx.AsyncHTTPTransport):
    """AsyncHTTPTransport enforcing the context's HttpBudget:
    atomic pre-send reservation, a process-wide (per-loop)
    concurrency cap shared across proxy/direct transports, and
    streaming response-size enforcement. With no budget in context
    it behaves like the plain transport (plus the shared cap).

    ``inner`` optionally replaces the wire transport (the
    fixed-fixture configuration): budget accounting, gates and
    size enforcement above it are unchanged."""

    def __init__(self, *args: Any, inner: Any = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._inner = inner

    async def _send(self, request: httpx.Request) -> httpx.Response:
        if self._inner is not None:
            return await self._inner.handle_async_request(request)
        return await super().handle_async_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        budget = current_http_budget.get()
        host = request.url.host
        # ONE absolute send deadline for the whole attempt (b5
        # final review, S10): gate waits and semaphore waits all
        # count against the same MAX_GATE_WAIT_S window, so a
        # Retry-After that keeps being extended by other requests
        # cannot stretch this send indefinitely.
        send_deadline = time.monotonic() + MAX_GATE_WAIT_S

        async def honour_gate() -> None:
            # Honour a Retry-After raised by ANY recent request to
            # this host, re-checking the LATEST deadline after
            # every sleep: while this request waited, another
            # response may have extended the host's deadline, and
            # this request must not be sent before the new one.
            while True:
                wait = _host_retry_wait(host)
                if wait <= 0:
                    return
                remaining = send_deadline - time.monotonic()
                if remaining <= 0 or wait > remaining:
                    raise AdapterError(
                        "http-budget",
                        f"Retry-After for {host} asks for {wait:.0f}s, beyond the {MAX_GATE_WAIT_S:.0f}s send window; not sent",
                        retryable=False,
                    )
                await asyncio.sleep(min(wait, remaining))

        await honour_gate()
        if budget is not None:
            budget.reserve(host)
        semaphore = _shared_semaphore()
        remaining = send_deadline - time.monotonic()
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=max(remaining, 0.0))
        except (asyncio.TimeoutError, TimeoutError):
            raise AdapterError(
                "http-budget",
                f"send window ({MAX_GATE_WAIT_S:.0f}s) expired while waiting for a connection slot for {host}; not sent",
                retryable=False,
            )
        try:
            await honour_gate()
            response = await self._send(request)
            if response.status_code == 429:
                wait = _retry_after_seconds(response.headers.get("retry-after"))
                if wait is not None:
                    _note_retry_after(host, wait)
            encoding = (response.headers.get("content-encoding") or "").strip().lower()
            if encoding not in ("", "identity", "gzip", "deflate"):
                await response.aclose()
                raise AdapterError(
                    "http-budget",
                    f"unsupported content-encoding {encoding!r} from {host}; refused",
                    retryable=False,
                )
            if budget is None:
                return response
            try:
                if encoding not in ("gzip", "deflate"):
                    # Content-Length pre-check (identity only: with
                    # compression the header counts wire bytes, not
                    # the decoded size the cap applies to).
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            declared = int(content_length)
                        except ValueError:
                            declared = -1
                        if declared > budget.max_response_bytes:
                            raise BudgetExceeded(
                                f"response from {host} declares {declared} bytes, over the {budget.max_response_bytes}-byte cap"
                            )
                body = bytearray()

                def take(piece: bytes) -> None:
                    budget.add_streamed_bytes(len(piece))
                    body.extend(piece)
                    if len(body) > budget.max_response_bytes:
                        raise BudgetExceeded(
                            f"response from {host} exceeded the {budget.max_response_bytes}-byte cap while streaming"
                        )

                if encoding in ("gzip", "deflate"):
                    # Incremental decompression (b4 review, S5): the
                    # decompressor is fed raw chunks and drained in
                    # <=64KB pieces, so no large intermediate decode
                    # buffer is ever built; decoded bytes are charged
                    # piece by piece and wire bytes counted apart.
                    import zlib

                    wbits = 16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
                    decomp = zlib.decompressobj(wbits)
                    raw_fallback_tried = False
                    try:
                        async for raw in response.aiter_raw():
                            budget.record_wire_bytes(len(raw))
                            data = raw
                            # One raw chunk can contain the end of
                            # one gzip member, several whole members
                            # and the start of the next, in any
                            # alignment (final review S11): keep
                            # swapping in a fresh decompressor for
                            # as long as the current one reports
                            # end-of-stream with bytes left over.
                            while True:
                                while True:
                                    try:
                                        piece = decomp.decompress(data, 65536)
                                    except zlib.error:
                                        if encoding == "deflate" and not raw_fallback_tried and not body:
                                            raw_fallback_tried = True
                                            decomp = zlib.decompressobj(-zlib.MAX_WBITS)
                                            piece = decomp.decompress(data, 65536)
                                        else:
                                            raise
                                    if piece:
                                        take(piece)
                                    data = decomp.unconsumed_tail
                                    if not piece and not data:
                                        break
                                if decomp.eof and decomp.unused_data:
                                    data = decomp.unused_data
                                    decomp = zlib.decompressobj(wbits)
                                    continue
                                break
                        if not decomp.eof:
                            raise httpx.DecodingError(
                                f"truncated {encoding} response from {host}: stream ended before the end-of-stream marker"
                            )
                        tail = decomp.flush()
                        if tail:
                            take(tail)
                    except zlib.error as exc:
                        raise httpx.DecodingError(f"error decoding response from {host}: {exc}") from exc
                else:
                    async for chunk in response.aiter_bytes(65536):
                        budget.record_wire_bytes(len(chunk))
                        take(chunk)
            except BaseException:
                await response.aclose()
                raise
            await response.aclose()
            # The buffered body is already DECODED, so the
            # reconstructed response must not keep the original
            # content-encoding or content-length headers - otherwise
            # callers would try to decode plain bytes a second time
            # (zlib "incorrect header check") and read a wrong length.
            clean_headers = httpx.Headers(
                {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                }
            )
            clean_headers["content-length"] = str(len(body))
            return httpx.Response(
                status_code=response.status_code,
                headers=clean_headers,
                content=bytes(body),
                request=request,
                extensions=response.extensions,
            )
        finally:
            semaphore.release()


def make_client(timeout: float = 30, **kwargs: Any) -> httpx.AsyncClient:
    """The standard client for the web and MCP entry points: budgeted
    transport, library-friendly user agent, no implicit redirects
    (each redirect hop stays visible to the budget).

    Proxy note: when a custom transport is supplied, httpx does NOT
    apply environment proxies automatically, so the standard
    HTTP(S)_PROXY variables are wired in explicitly as budgeted
    proxy mounts (an earlier build without this failed every live
    call in proxied environments with SSL errors)."""
    import os

    fixture_dir = os.getenv("GLM_UPSTREAM_FIXTURE_DIR")
    if fixture_dir:
        # Fixed-fixture mode (CI, b8 final review section 18):
        # no proxy mounts, no live network - the budgeted
        # transport serves recorded upstream responses only.
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": "global-library-mcp/1.0 (+https://github.com/shellingford570/global-library-mcp)",
                "Accept-Encoding": "gzip, deflate",
            },
            transport=BudgetedTransport(inner=FixtureTransport(fixture_dir)),
            **kwargs,
        )

    mounts: dict[str, httpx.AsyncHTTPTransport] = {}
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if https_proxy:
        mounts["https://"] = BudgetedTransport(proxy=https_proxy)
    if http_proxy:
        mounts["http://"] = BudgetedTransport(proxy=http_proxy)
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={
            "User-Agent": "global-library-mcp/1.0 (+https://github.com/shellingford570/global-library-mcp)",
            # Only encodings the budgeted transport decodes
            # incrementally; anything else is refused (b5, S12).
            "Accept-Encoding": "gzip, deflate",
        },
        transport=BudgetedTransport(),
        mounts=mounts or None,
        **kwargs,
    )


# --- Upstream URL safety (b5 final review, S4) ---------------------
# Every URL that arrives inside an upstream payload (a IIIF
# manifest, a loc.gov JSON document, OAI metadata, IA file lists)
# is UNTRUSTED input. Before this process fetches such a URL it
# must pass validate_fetch_url():
#
# - scheme must be https (no http, no javascript:/data:/file:);
# - no embedded username/password;
# - port must be absent or 443;
# - the host must be a normal DNS name or a PUBLIC IP literal -
#   loopback, private, link-local, reserved, multicast and
#   unspecified addresses are refused, as are ambiguous IP forms
#   (bare integers, hex, leading-zero octets) and localhost names;
# - when the caller knows the legitimate hosts (an adapter
#   fetching URLs its provider returned), an exact host allowlist
#   is enforced - suffix matching is NOT used, so a lookalike
#   host such as "evil-loc.gov" or "loc.gov.evil.example" fails.
#
# DNS scope, stated honestly: resolving a name and checking the
# answers cannot fully prevent DNS rebinding (the name can be
# re-resolved between the check and the connection, and httpx
# offers no address pinning). The DNS pre-check therefore runs
# when GLM_DNS_CHECK=1 (intended for direct-connection
# deployments); the always-on controls are the structural checks
# above, exact host allowlists, and redirect confinement. When an
# HTTP(S) proxy is configured, name resolution happens at the
# proxy and local answers do not describe the connection.

import ipaddress
import os as _os
import socket as _socket

_AMBIGUOUS_IP = re.compile(r"^(0x[0-9a-f]+|[0-9]+)$", re.I)


def _ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def validate_fetch_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    """Validate an upstream-supplied URL for fetching. Returns the
    URL unchanged on success; raises AdapterError otherwise."""
    from urllib.parse import urlparse

    def refuse(reason: str) -> AdapterError:
        return AdapterError("http-url", f"refusing to fetch upstream URL ({reason}): {sanitize_error(url)[:160]}", retryable=False)

    if not isinstance(url, str) or not url.strip():
        raise refuse("empty URL")
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in url):
        raise refuse("control or space characters in URL")
    parts = urlparse(url.strip())
    if parts.scheme != "https":
        raise refuse(f"scheme {parts.scheme!r} is not https")
    if parts.username or parts.password:
        raise refuse("embedded credentials in URL")
    host = parts.hostname
    if not host:
        raise refuse("missing host")
    host = host.rstrip(".").lower()
    try:
        port = parts.port
    except ValueError:
        raise refuse("invalid port")
    if port is not None and port != 443:
        raise refuse(f"port {port} is not allowed")
    if "%" in host:
        raise refuse("zone ids / percent-encoded hosts are not allowed")
    ip = _ip_literal(host)
    if ip is not None:
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            raise refuse(f"IP literal {host} is not a public address")
    else:
        if _AMBIGUOUS_IP.match(host) or ("." not in host and ":" not in host and host != "localhost"):
            raise refuse(f"ambiguous host form {host!r}")
        if host == "localhost" or host.endswith(".localhost"):
            raise refuse("localhost is not an upstream host")
        try:
            host.encode("idna")
        except (UnicodeError, ValueError):
            raise refuse("host is not a valid DNS name")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise refuse(f"host {host} is not in this adapter's allowlist")
    return url


def check_dns_public(host: str) -> None:
    """Resolve `host` and refuse when ANY answer is not a public
    address. A pre-check only - see the scope note above."""
    infos = _socket.getaddrinfo(host, 443, proto=_socket.IPPROTO_TCP)
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise AdapterError("http-url", f"DNS returned no addresses for {host}", retryable=False)
    for address in addresses:
        ip = _ip_literal(address)
        if ip is None:
            continue
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            raise AdapterError(
                "http-url",
                f"DNS for {host} returned a non-public address ({address}); refused",
                retryable=False,
            )


def dns_check_enabled() -> bool:
    return _os.getenv("GLM_DNS_CHECK", "").strip().lower() in ("1", "true", "yes")


async def fetch_validated(
    client: httpx.AsyncClient,
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """GET an upstream-supplied URL after validate_fetch_url()
    (plus the DNS pre-check when enabled). Redirects are NOT
    followed here; use get_within_domain for redirecting fetches."""
    validate_fetch_url(url, allowed_hosts=allowed_hosts)
    if dns_check_enabled():
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        if _ip_literal(host) is None:
            await asyncio.to_thread(check_dns_public, host)
    return await client.get(url, follow_redirects=False, **kwargs)


def response_looks_like_image(body: bytes, content_type: str) -> bool:
    """True when a response body is actually an image (magic bytes
    or a non-HTML image Content-Type). An HTTP 200 HTML error or
    access page is NOT an image (b5 final review, S3/S6)."""
    ctype = (content_type or "").lower()
    if "text/html" in ctype or "application/json" in ctype:
        return False
    head = body[:16]
    if head.startswith(b"\xff\xd8\xff"):  # JPEG
        return True
    if head.startswith(b"\x89PNG\r\n\x1a\n"):  # PNG
        return True
    if head.startswith((b"GIF87a", b"GIF89a")):
        return True
    if head.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return True
    if head.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n"):  # JPEG 2000 signature box
        return True
    if ctype.startswith("image/") and not head.lstrip().startswith(b"<"):
        return True
    return False


def is_safe_link_url(url: object) -> bool:
    """True when a URL may be shown as a clickable link (http/https,
    no embedded credentials). Used for upstream-supplied landing /
    licence links so javascript:, data: or file: URLs from a
    payload are never rendered as links."""
    if not isinstance(url, str) or not url:
        return False
    from urllib.parse import urlparse

    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password


_MULTI_LABEL_SUFFIXES = ("ndl.go.jp", "go.jp", "co.uk", "org.uk", "com.au")


def registrable_domain(host: str) -> str:
    """Registrable domain of a host, aware of the multi-label
    public suffixes this project actually talks to."""
    host = host.lower().strip(".")
    for suffix in _MULTI_LABEL_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            head = host[: -len(suffix)].rstrip(".")
            label = head.rsplit(".", 1)[-1] if head else ""
            return f"{label}.{suffix}" if label else suffix
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


async def get_within_domain(
    client: httpx.AsyncClient, url: str, *, max_hops: int = 3, **kwargs: Any
) -> httpx.Response:
    """GET that follows redirects manually (b5, S12): every hop is
    a separate budgeted request, and a redirect to a DIFFERENT
    registrable domain is refused instead of followed. The client
    itself is built with follow_redirects=False."""
    from urllib.parse import urljoin, urlparse

    current = validate_fetch_url(url)
    origin_domain = registrable_domain(urlparse(current).hostname or "")
    origin_host = (urlparse(current).hostname or "").lower()
    hop_headers = dict(kwargs.pop("headers", None) or {})
    for _ in range(max_hops + 1):
        if dns_check_enabled():
            host = urlparse(current).hostname or ""
            if _ip_literal(host) is None:
                await asyncio.to_thread(check_dns_public, host)
        response = await client.get(current, follow_redirects=False, headers=hop_headers or None, **kwargs)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("location")
        await response.aclose()
        if not location:
            return response
        target = urljoin(current, location)
        # Every hop is validated on its own: https only (an
        # https->http downgrade fails the scheme check), no
        # credentials, no private hosts, same registrable domain.
        target = validate_fetch_url(target)
        target_domain = registrable_domain(urlparse(target).hostname or "")
        if target_domain != origin_domain:
            raise AdapterError(
                "http-redirect",
                f"redirect from {origin_domain} to a different domain ({target_domain}) refused",
                retryable=False,
            )
        target_host = (urlparse(target).hostname or "").lower()
        if target_host != origin_host:
            # Never forward credentials to a different host, even
            # inside the same registrable domain.
            hop_headers = {
                key: value
                for key, value in hop_headers.items()
                if key.lower() not in ("authorization", "cookie")
            }
            origin_host = target_host
        current = target
    raise AdapterError("http-redirect", f"too many redirects (>{max_hops}) for {url}", retryable=False)
