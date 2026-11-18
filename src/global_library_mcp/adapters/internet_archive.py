from __future__ import annotations

from typing import Any

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.models import Rights, SearchResult


class InternetArchiveAdapter(LibraryAdapter):
    library_id = "internet-archive"
    library_name = "Internet Archive"
    base_url = "https://archive.org"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        response = await self.client.get(
            f"{self.base_url}/advancedsearch.php",
            params={
                "q": query,
                "fl[]": ["identifier", "title", "creator", "date", "description"],
                "rows": min(max(limit, 1), 50),
                "page": 1,
                "output": "json",
            },
        )
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        return [self._result(item) for item in docs]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        identifier = str(item.get("identifier") or "unknown")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=identifier,
            title=item.get("title") or identifier,
            author=item.get("creator") if isinstance(item.get("creator"), str) else ", ".join(item.get("creator", []) or []),
            date=str(item.get("date")) if item.get("date") else None,
            description=item.get("description") if isinstance(item.get("description"), str) else None,
            landing_url=f"{self.base_url}/details/{identifier}",
            rights=Rights(statement="item-specific; verify the item rights and file metadata", source=f"{self.base_url}/details/{identifier}"),
            source_protocol="Internet Archive Advanced Search API",
            raw=item,
        )
