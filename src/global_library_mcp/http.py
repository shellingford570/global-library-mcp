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
