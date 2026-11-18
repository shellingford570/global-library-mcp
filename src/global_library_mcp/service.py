from __future__ import annotations

import asyncio
from collections.abc import Iterable

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.adapters.gallica import GallicaAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.adapters.ndl import NdlAdapter
from global_library_mcp.http import ResponseCache
from global_library_mcp.models import SearchResponse


class LibraryService:
    def __init__(self, client: httpx.AsyncClient):
        cache = ResponseCache()
        self.adapters: dict[str, LibraryAdapter] = {
            "loc": LocAdapter(client, cache),
            "ndl": NdlAdapter(client),
            "gallica": GallicaAdapter(client),
        }

    async def search(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10) -> SearchResponse:
        selected = list(libraries or self.adapters)
        selected = [library_id for library_id in selected if library_id in self.adapters]
        async def one(library_id: str):
            try:
                return library_id, await self.adapters[library_id].search(query, limit)
            except Exception as exc:
                return library_id, exc
        pairs = await asyncio.gather(*(one(library_id) for library_id in selected))
        results = []
        errors = []
        seen: set[tuple[str, str]] = set()
        for library_id, value in pairs:
            if isinstance(value, Exception):
                errors.append({"library_id": library_id, "error": str(value)})
                continue
            for result in value:
                key = (result.title.casefold(), (result.author or "").casefold())
                if key not in seen:
                    seen.add(key)
                    results.append(result)
        return SearchResponse(query=query, results=results, errors=errors)
