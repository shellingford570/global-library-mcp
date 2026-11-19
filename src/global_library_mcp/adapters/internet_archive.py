from __future__ import annotations

from typing import Any

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.http import get_json
from global_library_mcp.models import Rights, SearchResult


class InternetArchiveAdapter(LibraryAdapter):
    library_id = "internet-archive"
    library_name = "Internet Archive"
    base_url = "https://archive.org"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = await get_json(self.client, f"{self.base_url}/advancedsearch.php", params={
                "q": query,
                "fl[]": ["identifier", "title", "creator", "date", "description", "rights", "licenseurl"],
                "rows": min(max(limit, 1), 50),
                "page": 1,
                "output": "json",
            }, attempts=1)
        response = payload.get("response") if isinstance(payload, dict) else None
        docs = response.get("docs", []) if isinstance(response, dict) else None
        if not isinstance(docs, list):
            raise ValueError("Internet Archive response schema changed")
        return [self._result(item) for item in docs if isinstance(item, dict)]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        identifier = str(item.get("identifier") or "unknown")
        title = item.get("title") or identifier
        creator = item.get("creator")
        rights = item.get("rights") or item.get("licenseurl") or "item-specific; verify the item rights and file metadata"
        if isinstance(title, list):
            title = title[0] if title else identifier
        if isinstance(creator, list):
            creator = ", ".join(str(value) for value in creator)
        elif not isinstance(creator, str):
            creator = None
        if isinstance(rights, list):
            rights = "; ".join(str(value) for value in rights)
        if not isinstance(rights, str):
            rights = "item-specific; verify the item rights and file metadata"
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=identifier,
            title=str(title),
            author=creator,
            date=str(item.get("date")) if item.get("date") else None,
            description=item.get("description") if isinstance(item.get("description"), str) else None,
            landing_url=f"{self.base_url}/details/{identifier}",
            rights=Rights(statement=rights, url=item.get("licenseurl") if isinstance(item.get("licenseurl"), str) else None, source=f"{self.base_url}/details/{identifier}"),
            source_protocol="Internet Archive Advanced Search API",
            raw=item,
        )
