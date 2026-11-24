from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.adapters.base import AdapterError
from global_library_mcp.models import Rights, SearchResult


class GallicaAdapter(LibraryAdapter):
    library_id = "gallica"
    library_name = "Gallica / Bibliothèque nationale de France"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        response = await self.client.get(
            "https://gallica.bnf.fr/SRU",
            params={
                "version": "1.2",
                "operation": "searchRetrieve",
                "query": f'dc.anywhere all "{query.replace(chr(34), "")}"',
                "maximumRecords": min(max(limit, 1), 50),
            },
        )
        if response.status_code == 403:
            raise AdapterError(self.library_id, "Upstream access denied (403; challenge or policy restriction)")
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {"srw": "http://www.loc.gov/zing/srw/", "dc": "http://purl.org/dc/elements/1.1/"}
        results: list[SearchResult] = []
        for record in root.findall(".//srw:recordData", ns):
            title = record.findtext(".//dc:title", default="Untitled", namespaces=ns)
            identifier = record.findtext(".//dc:identifier", default=title, namespaces=ns)
            creator = record.findtext(".//dc:creator", default=None, namespaces=ns)
            date = record.findtext(".//dc:date", default=None, namespaces=ns)
            results.append(SearchResult(
                library_id=self.library_id,
                library_name=self.library_name,
                record_id=identifier,
                title=title,
                author=creator,
                date=date,
                landing_url=identifier if identifier.startswith("http") else "https://gallica.bnf.fr/",
                rights=Rights(statement="BnF/item-specific; verify Gallica terms", source=identifier),
                source_protocol="Gallica SRU",
                raw={"identifier": identifier},
            ))
        return results
