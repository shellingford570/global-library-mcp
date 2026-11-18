from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

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
    for attempt in range(attempts):
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 429:
                raise AdapterError("http", "Upstream rate limit (429)", retryable=True)
            if response.status_code == 403:
                raise AdapterError("http", "Upstream access denied (403; challenge or policy restriction)", retryable=False)
            response.raise_for_status()
            value = response.json()
            if cache:
                cache.put(key, value)
            return value
        except (httpx.HTTPError, AdapterError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (attempt + 1))
    raise AdapterError("http", f"Upstream request failed: {last_error}", retryable=True)
