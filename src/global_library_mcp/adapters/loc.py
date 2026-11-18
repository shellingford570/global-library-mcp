from __future__ import annotations

from typing import Any

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import ResponseCache, get_json
from global_library_mcp.models import Rights, SearchResult


class LocAdapter(LibraryAdapter):
    library_id = "loc"
    library_name = "Library of Congress"

    def __init__(self, client: httpx.AsyncClient, cache: ResponseCache | None = None):
        super().__init__(client)
        self.cache = cache

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = await get_json(
            self.client,
            "https://www.loc.gov/search/",
            params={"q": query, "fo": "json", "c": min(max(limit, 1), 100)},
            cache=self.cache,
        )
        return [self._result(item) for item in payload.get("results", [])]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        resource = item.get("resources") or []
        image_url = None
        if resource and isinstance(resource[0], dict):
            image_url = resource[0].get("thumbnail_url") or resource[0].get("url")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=str(item.get("id") or item.get("title") or "unknown"),
            title=item.get("title") or item.get("description") or "Untitled",
            author=(item.get("contributor") or [None])[0] if isinstance(item.get("contributor"), list) else item.get("contributor"),
            date=item.get("date") or item.get("date_of_publication"),
            language=",".join(item.get("language", [])) if isinstance(item.get("language"), list) else item.get("language"),
            description=item.get("description") if isinstance(item.get("description"), str) else None,
            landing_url=item.get("id"),
            image_url=image_url,
            fulltext_status="available" if item.get("item", {}).get("fulltext_service") else "unknown",
            rights=Rights(statement=item.get("rights") or "unknown", source=item.get("id")),
            source_protocol="LoC JSON API",
            raw=item,
        )
