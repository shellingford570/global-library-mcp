from __future__ import annotations

import os
from typing import Any

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.models import Rights, SearchResult


class EuropeanaAdapter(LibraryAdapter):
    library_id = "europeana"
    library_name = "Europeana"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        api_key = os.getenv("EUROPEANA_API_KEY")
        if not api_key:
            raise AdapterError(self.library_id, "EUROPEANA_API_KEY is required; live search not attempted")
        response = await self.client.get("https://api.europeana.eu/record/v2/search.json", params={"wskey": api_key, "query": query, "rows": min(max(limit, 1), 100)})
        response.raise_for_status()
        return [self._result(item) for item in response.json().get("items", [])]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        record_id = str(item.get("id") or "unknown")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=record_id,
            title=(item.get("title") or ["Untitled"])[0] if isinstance(item.get("title"), list) else item.get("title") or "Untitled",
            description=(item.get("dcDescription") or [None])[0] if isinstance(item.get("dcDescription"), list) else item.get("dcDescription"),
            landing_url=item.get("guid") or f"https://www.europeana.eu/item{record_id}",
            rights=Rights(statement=(item.get("rights") or ["unknown"])[0] if isinstance(item.get("rights"), list) else item.get("rights") or "unknown", source=item.get("guid")),
            source_protocol="Europeana Record API",
            raw=item,
        )


class DdbAdapter(LibraryAdapter):
    library_id = "ddb"
    library_name = "Deutsche Digitale Bibliothek"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        response = await self.client.get("https://api.deutsche-digitale-bibliothek.de/2/search", params={"query": query, "limit": min(max(limit, 1), 50)})
        if response.status_code in (401, 403):
            raise AdapterError(self.library_id, "DDB API requires access credentials or has denied this request")
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") or payload.get("results") or []
        return [self._result(item) for item in items]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        record_id = str(item.get("id") or item.get("itemId") or "unknown")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=record_id,
            title=item.get("title") or "Untitled",
            author=item.get("creator"),
            date=str(item.get("date")) if item.get("date") else None,
            landing_url=item.get("url") or item.get("itemUrl"),
            rights=Rights(statement=item.get("rights") or "institution-specific; verify", source=item.get("url")),
            source_protocol="DDB API v2",
            raw=item,
        )
