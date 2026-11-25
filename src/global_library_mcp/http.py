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


class BudgetedTransport(httpx.AsyncHTTPTransport):
    """AsyncHTTPTransport enforcing the context's HttpBudget:
    atomic pre-send reservation, a process-wide (per-loop)
    concurrency cap shared across proxy/direct transports, and
    streaming response-size enforcement. With no budget in context
    it behaves like the plain transport (plus the shared cap)."""

    async def _send(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        budget = current_http_budget.get()
        host = request.url.host

        async def honour_gate() -> None:
            # Honour a Retry-After raised by ANY recent request to
            # this host. Checked before reserving AND again
            # immediately before sending: while this request waited
            # (for the gate or the semaphore), another response may
            # have extended the host's deadline (b4 review, S5).
            wait = _host_retry_wait(host)
            if wait > MAX_GATE_WAIT_S:
                raise AdapterError(
                    "http-budget",
                    f"Retry-After for {host} asks for {wait:.0f}s, beyond the {MAX_GATE_WAIT_S:.0f}s send window; not sent",
                    retryable=False,
                )
            if wait > 0:
                await asyncio.sleep(wait)

        await honour_gate()
        if budget is not None:
            budget.reserve(host)
        async with _shared_semaphore():
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
                                # zlib protocol: input that did not
                                # fit the output bound is handed back
                                # via unconsumed_tail and MUST be fed
                                # in again; an empty piece with an
                                # empty tail means this raw chunk is
                                # fully drained.
                                data = decomp.unconsumed_tail
                                if not piece and not data:
                                    break
                            if decomp.eof and decomp.unused_data:
                                # concatenated gzip member (b5, S12)
                                pending = decomp.unused_data
                                decomp = zlib.decompressobj(wbits)
                                data = pending
                                while data:
                                    piece = decomp.decompress(data, 65536)
                                    if piece:
                                        take(piece)
                                    data = decomp.unconsumed_tail
                                    if not piece and not data:
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

    current = url
    origin_domain = registrable_domain(urlparse(url).hostname or "")
    for _ in range(max_hops + 1):
        response = await client.get(current, follow_redirects=False, **kwargs)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("location")
        await response.aclose()
        if not location:
            return response
        target = urljoin(current, location)
        target_domain = registrable_domain(urlparse(target).hostname or "")
        if target_domain != origin_domain:
            raise AdapterError(
                "http-redirect",
                f"redirect from {origin_domain} to a different domain ({target_domain}) refused",
                retryable=False,
            )
        current = target
    raise AdapterError("http-redirect", f"too many redirects (>{max_hops}) for {url}", retryable=False)
