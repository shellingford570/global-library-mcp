from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from global_library_mcp.adapters.aggregators import DdbAdapter, EuropeanaAdapter
from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.adapters.gallica import GallicaAdapter
from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.adapters.ndl import NdlAdapter
from global_library_mcp.answer import OpenAICompatibleProvider
from global_library_mcp.http import ResponseCache
from global_library_mcp.models import SearchResponse


class LibraryService:
    default_libraries = ("loc", "ndl", "gallica", "internet-archive")

    def __init__(self, client: httpx.AsyncClient):
        cache = ResponseCache()
        self.adapters: dict[str, LibraryAdapter] = {
            "loc": LocAdapter(client, cache),
            "ndl": NdlAdapter(client),
            "gallica": GallicaAdapter(client),
            "internet-archive": InternetArchiveAdapter(client),
            "ddb": DdbAdapter(client),
            "europeana": EuropeanaAdapter(client),
        }
        self.client = client

    async def search(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10) -> SearchResponse:
        selected = list(libraries or self.default_libraries)
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

    async def get_document(self, library_id: str, record_id: str) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.get_document(record_id)

    async def search_in_document(self, library_id: str, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.search_in_document(record_id, query, limit)

    async def get_page_text(self, library_id: str, page_id: str) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.get_page_text(page_id)

    async def answer(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10) -> dict[str, Any]:
        search = await self.search(query, libraries, limit)
        provider = OpenAICompatibleProvider(self.client)
        answer = await provider.answer(query, [item.to_dict() for item in search.results])
        answer["search"] = search.to_dict()
        return answer
