"""e-rara adapter (b5, section 6) - metadata by ID via OAI-PMH.

e-rara (ETH Library's platform for digitised rare books from
Swiss libraries) exposes an OAI-PMH endpoint
(https://www.e-rara.ch/oai, Identify verified live 2026-11-25).
OAI-PMH is a harvesting protocol, NOT a keyword search
interface, and this adapter does not pretend otherwise:
``search`` is unsupported with that reason stated. Records are
addressed by their numeric e-rara id (the OAI identifier is
``oai:www.e-rara.ch:<id>``).

Page-level OCR/IIIF: e-rara items are delivered through the
platform viewer; no officially documented per-page OCR or IIIF
endpoint was confirmed in this phase, so page text is reported
as unsupported rather than scraped. The holding institution
comes from the record's OAI set membership / publisher fields
where present; e-rara itself is the delivery platform, not the
holding library.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import sanitize_error
from global_library_mcp.models import SearchResult

OAI_BASE = "https://www.e-rara.ch/oai"
_DC = "{http://purl.org/dc/elements/1.1/}"
_OAI = "{http://www.openarchives.org/OAI/2.0/}"
_MAX_XML = 5_000_000


class EraraAdapter(LibraryAdapter):
    library_id = "e-rara"
    library_name = "e-rara (ETH Library)"
    supports_in_document_search = False

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise AdapterError(
            self.library_id,
            "e-rara offers OAI-PMH harvesting, not an official keyword search interface; "
            "this adapter is ID-addressed (get_document with the numeric e-rara id)",
            retryable=False,
        )

    async def get_document(self, record_id: str) -> dict[str, Any]:
        numeric = (record_id or "").strip().removeprefix("oai:www.e-rara.ch:")
        if not numeric.isdigit():
            raise AdapterError(self.library_id, f"invalid e-rara id: {record_id!r} (numeric id expected)", retryable=False)
        params = {"verb": "GetRecord", "metadataPrefix": "oai_dc", "identifier": f"oai:www.e-rara.ch:{numeric}"}
        try:
            response = await self.client.get(OAI_BASE, params=params)
            response.raise_for_status()
            body = response.text
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if len(body) > _MAX_XML:
            raise AdapterError(self.library_id, "OAI response exceeds the size bound", retryable=False)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError(self.library_id, f"malformed OAI XML: {exc}", retryable=False) from exc
        error = root.find(f".//{_OAI}error")
        if error is not None:
            raise AdapterError(self.library_id, f"OAI error: {error.get('code')} {error.text or ''}".strip(), retryable=False)
        dc = root.find(f".//{_DC}title")
        record = root.find(f".//{_OAI}metadata")
        if record is None:
            raise AdapterError(self.library_id, f"no metadata in OAI record for {numeric}", retryable=False)

        def values(tag: str) -> list[str]:
            return [el.text.strip() for el in record.iter(f"{_DC}{tag}") if el.text and el.text.strip()]

        identifiers = values("identifier")
        landing = next((i for i in identifiers if i.startswith("http")), None)
        doi = next((i for i in identifiers if "10." in i and "/" in i), None)
        rights = values("rights")
        sets = [el.text for el in root.iter(f"{_OAI}setSpec") if el.text]
        return {
            "library_id": self.library_id,
            "record_id": numeric,
            "holding_institution": None,
            "oai_sets": sets,
            "title": (values("title") or [None])[0],
            "author": "; ".join(values("creator")) or None,
            "publisher": "; ".join(values("publisher")) or None,
            "date": (values("date") or [None])[0],
            "language": (values("language") or [None])[0],
            "type": "; ".join(values("type")) or None,
            "landing_url": landing,
            "doi": doi,
            "rights": {
                "statement": "; ".join(rights) if rights else "unknown",
                "url": None,
                "source": "OAI-PMH dc:rights" if rights else "no dc:rights in OAI record",
            },
            "source_protocol": "OAI-PMH (oai_dc)",
            "note": (
                "Metadata only in this phase: no officially documented per-page OCR/IIIF "
                "endpoint was confirmed for e-rara; the digitised item itself is on the "
                "e-rara platform (landing_url)."
            ),
        }
