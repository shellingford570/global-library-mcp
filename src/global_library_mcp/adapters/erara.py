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
platform viewer; a usable officially documented per-page OCR or
IIIF endpoint could not be confirmed in this phase (the API
information page was reviewed; that a capability is mentioned
somewhere on the site does not by itself make it a usable
per-page API), so page text is reported as unsupported rather
than scraped. This does not assert that no such interface
exists anywhere. The holding institution
comes from the record's OAI set membership / publisher fields
where present; e-rara itself is the delivery platform, not the
holding library.
"""

from __future__ import annotations

import re
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
_DOI = re.compile(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.I)


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
        body = None
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.get(OAI_BASE, params=params)
                response.raise_for_status()
                body = response.text
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # The OAI endpoint intermittently answers 503
                # (observed twice on 2026-11-25, then recovered);
                # one bounded retry is appropriate for a GET, and
                # it honours the server's Retry-After when given
                # (final review S13).
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt == 0 and status in (502, 503):
                    import asyncio

                    from global_library_mcp.http import _retry_after_seconds

                    retry_after = None
                    resp = getattr(exc, "response", None)
                    if resp is not None:
                        retry_after = _retry_after_seconds(resp.headers.get("retry-after"))
                    await asyncio.sleep(min(retry_after, 10.0) if retry_after is not None else 2.0)
                    continue
                raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if body is None:
            raise AdapterError(self.library_id, sanitize_error(last_exc), retryable=True)
        if len(body) > _MAX_XML:
            raise AdapterError(self.library_id, "OAI response exceeds the size bound", retryable=False)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError(self.library_id, f"malformed OAI XML: {exc}", retryable=False) from exc
        error = root.find(f".//{_OAI}error")
        if error is not None:
            raise AdapterError(self.library_id, f"OAI error: {error.get('code')} {error.text or ''}".strip(), retryable=False)
        header = root.find(f".//{_OAI}header")
        header_identifier = (header.findtext(f"{_OAI}identifier") or "").strip() if header is not None else ""
        if header_identifier != f"oai:www.e-rara.ch:{numeric}":
            raise AdapterError(
                self.library_id,
                f"OAI header identifier {header_identifier!r} does not match the requested id {numeric}; record identity not established",
                retryable=False,
            )
        if header is not None and header.get("status") == "deleted":
            raise AdapterError(self.library_id, f"OAI record {numeric} is marked deleted", retryable=False)
        record = root.find(f".//{_OAI}metadata")
        if record is None:
            raise AdapterError(self.library_id, f"no metadata in OAI record for {numeric}", retryable=False)

        def values(tag: str) -> list[str]:
            return [el.text.strip() for el in record.iter(f"{_DC}{tag}") if el.text and el.text.strip()]

        identifiers = values("identifier")
        landing = next((i for i in identifiers if i.startswith("http")), None)
        doi = None
        for identifier in identifiers:
            doi_match = _DOI.match(identifier.strip())
            if doi_match:
                doi = doi_match.group(1)
                break
        rights = values("rights")
        sets = [el.text for el in root.iter(f"{_OAI}setSpec") if el.text]
        return {
            "library_id": self.library_id,
            "record_id": numeric,
            "oai_identifier": header_identifier,
            # The OAI setSpec is a collection code, not an
            # institution name, and dc:publisher is the publisher -
            # neither is asserted to be the holding institution
            # (final review S13).
            "holding_institution": "unknown",
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
                "values": rights,
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
