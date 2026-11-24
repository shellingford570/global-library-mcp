from __future__ import annotations

import os
from typing import Any

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json
from global_library_mcp.models import Rights, SearchResult


class EuropeanaAdapter(LibraryAdapter):
    library_id = "europeana"
    library_name = "Europeana"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        api_key = os.getenv("EUROPEANA_API_KEY")
        if not api_key:
            raise AdapterError(self.library_id, "EUROPEANA_API_KEY is required; live search not attempted")
        payload = await get_json(self.client, "https://api.europeana.eu/record/v2/search.json", params={"wskey": api_key, "query": query, "rows": min(max(limit, 1), 100)}, attempts=1)
        return [self._result(item) for item in payload.get("items", []) if isinstance(item, dict)]

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
        headers: dict[str, str] = {}
        api_key = os.getenv("DDB_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = await get_json(self.client, "https://api.deutsche-digitale-bibliothek.de/2/search/index/search/select", params={"q": query, "rows": min(max(limit, 1), 50)}, headers=headers, attempts=1)
        response = payload.get("response") if isinstance(payload, dict) else None
        items = response.get("docs", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise AdapterError(self.library_id, "DDB response schema changed", retryable=False)
        return [self._result(item) for item in items if isinstance(item, dict)]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        record_id = str(item.get("id") or item.get("itemId") or "unknown")
        title = item.get("title") or item.get("label") or ["Untitled"]
        author = item.get("creator") or item.get("affiliate")
        rights = item.get("license") or item.get("metadata_rights") or item.get("rights") or ["verify item-level rights"]
        title = title[0] if isinstance(title, list) and title else title
        author = author[0] if isinstance(author, list) and author else author
        rights = rights[0] if isinstance(rights, list) and rights else rights
        if not isinstance(title, str):
            title = "Untitled"
        if not isinstance(author, str):
            author = None
        if not isinstance(rights, str):
            rights = "verify item-level rights"
        landing_url = item.get("url") or item.get("itemUrl")
        if not landing_url and record_id != "unknown":
            landing_url = f"https://www.deutsche-digitale-bibliothek.de/item/{record_id}"
        rights_url = item.get("license") if isinstance(item.get("license"), str) else item.get("metadata_rights")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=record_id,
            title=title,
            author=author,
            date=str(item.get("date")) if item.get("date") else None,
            landing_url=landing_url,
            rights=Rights(statement=rights, url=rights_url, source=landing_url),
            source_protocol="DDB API v2",
            raw=item,
        )
