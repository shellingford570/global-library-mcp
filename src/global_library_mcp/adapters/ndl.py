from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.models import Rights, SearchResult


class NdlAdapter(LibraryAdapter):
    library_id = "ndl"
    library_name = "National Diet Library"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        response = await self.client.get(
            "https://ndlsearch.ndl.go.jp/api/opensearch",
            params={"cnt": min(max(limit, 1), 100), "any": query},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        dc = "http://purl.org/dc/elements/1.1/"
        results: list[SearchResult] = []
        entries = root.findall("./channel/item")
        if not entries:
            atom = "http://www.w3.org/2005/Atom"
            entries = root.findall(f"{{{atom}}}entry")
        for entry in entries:
            def text(name: str) -> str | None:
                node = entry.find(name)
                if node is None:
                    atom = "http://www.w3.org/2005/Atom"
                    node = entry.find(f"{{{atom}}}{name}")
                return node.text.strip() if node is not None and node.text else None
            link = entry.find("link")
            if link is None:
                atom = "http://www.w3.org/2005/Atom"
                link = entry.find(f"{{{atom}}}link")
            href = (link.attrib.get("href") if link is not None else None) or text("link")
            title = text("title") or "Untitled"
            identifier = text("id") or href or title
            creator = entry.find(f"{{{dc}}}creator")
            if creator is None:
                creator = entry.find("creator")
            date = entry.find(f"{{{dc}}}date")
            if date is None:
                date = entry.find("date")
            results.append(SearchResult(
                library_id=self.library_id,
                library_name=self.library_name,
                record_id=identifier,
                title=title,
                author=creator.text.strip() if creator is not None and creator.text else None,
                date=date.text.strip() if date is not None and date.text else None,
                landing_url=href or identifier,
                rights=Rights(statement="provider-specific; verify before reuse", source=href),
                source_protocol="NDL OpenSearch",
                raw={"xml_id": identifier},
            ))
        return results
