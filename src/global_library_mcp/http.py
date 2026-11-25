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
    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._values.get(key)
        if not item or time.monotonic() - item[0] > self.ttl_seconds:
            return None
        return item[1]

    def put(self, key: str, value: Any) -> None:
        self._values[key] = (time.monotonic(), value)


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


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    cache: ResponseCache | None = None,
    attempts: int = 2,
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
                # b3: honour Retry-After before retrying (capped at
                # 5s so interactive use stays responsive); a second
                # 429 surfaces as an error. Never bypass rate limits.
                if attempt + 1 < attempts:
                    try:
                        wait = min(float(retry_after), 5.0)
                    except (TypeError, ValueError):
                        wait = 1.0
                    await asyncio.sleep(max(wait, 0.2))
                    continue
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


# --- Real HTTP request budget (b3, Section 9) -------------------------------
# The service-layer budget counts processing units, not wire requests.
# HttpBudget counts every actual HTTP request that leaves the process
# (each retry and each redirect hop is a separate transport request),
# per operation and per host, with a response-size cap. It is carried
# in a context variable so one operation (one question) gets one
# budget no matter how many adapters share the client.

import contextvars
import threading


class BudgetExceeded(AdapterError):
    """Raised before a request is sent when the HTTP budget is spent."""

    def __init__(self, detail: str):
        super().__init__("http-budget", f"HTTP request budget exceeded: {detail}", retryable=False)
        self.detail = detail


class HttpBudget:
    def __init__(self, max_requests: int = 80, per_host_max: int = 40, max_response_bytes: int = 25_000_000):
        self.max_requests = max_requests
        self.per_host_max = per_host_max
        self.max_response_bytes = max_response_bytes
        self.requests = 0
        self.bytes_received = 0
        self.per_host: dict[str, int] = {}
        self.exceeded = False
        self._lock = threading.Lock()

    def check(self, host: str) -> None:
        with self._lock:
            if self.requests >= self.max_requests:
                self.exceeded = True
                raise BudgetExceeded(f"operation limit {self.max_requests} requests reached")
            if self.per_host.get(host, 0) >= self.per_host_max:
                self.exceeded = True
                raise BudgetExceeded(f"per-host limit {self.per_host_max} requests for {host} reached")

    def record(self, host: str, nbytes: int) -> None:
        with self._lock:
            self.requests += 1
            self.per_host[host] = self.per_host.get(host, 0) + 1
            self.bytes_received += nbytes

    def stats(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "bytes_received": self.bytes_received,
            "per_host": dict(self.per_host),
            "max_requests": self.max_requests,
            "per_host_max": self.per_host_max,
            "exceeded": self.exceeded,
        }


current_http_budget: contextvars.ContextVar[HttpBudget | None] = contextvars.ContextVar(
    "current_http_budget", default=None
)


class BudgetedTransport(httpx.AsyncHTTPTransport):
    """AsyncHTTPTransport that enforces the context's HttpBudget and
    a process-wide concurrency cap. With no budget in context it
    behaves like the plain transport (plus the concurrency cap)."""

    def __init__(self, *args: Any, max_concurrency: int = 8, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _send(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        budget = current_http_budget.get()
        host = request.url.host
        if budget is not None:
            budget.check(host)
        async with self._semaphore:
            response = await self._send(request)
            if budget is not None:
                body = await response.aread()
                if len(body) > budget.max_response_bytes:
                    budget.record(host, len(body))
                    raise BudgetExceeded(
                        f"response from {host} exceeded {budget.max_response_bytes} bytes"
                    )
                budget.record(host, len(body))
            return response


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
        headers={"User-Agent": "global-library-mcp/1.0 (+https://github.com/shellingford570/global-library-mcp)"},
        transport=BudgetedTransport(),
        mounts=mounts or None,
        **kwargs,
    )
