"""Finna adapter (b8, sections 4-6) - Finland's national
discovery service, operated by the National Library of Finland.

Finna is a CROSS-SEARCH PLATFORM, not a single holding library.
This adapter keeps four things strictly separate, as the b8 brief
requires:

- the Finna record id (``<source>.<local id>``, e.g.
  ``helle.687105``; the prefix is the contributing data source);
- the provider / data source that contributed the record;
- the holding institution(s) from the record's ``buildings``
  hierarchy (consortium -> library -> branch);
- the original item at the provider, reached only through the
  structural handoff rules in ``handoff.py`` / the provider
  adapters - never by fetching an arbitrary URL from the record.

Rights are likewise separated (brief section 13): Finna METADATA
is CC0 1.0, but that says nothing about the item itself. The
per-record ``usageRights`` labels are the item-level statement;
an empty list means NO statement was made, which is recorded as
``unknown`` - never as permission. Finna usage-rights labels are
institutional collection labels (e.g. ``Paikalliskokoelma`` =
local collection), not licences, so no CC classification is
invented for them.

Access: the official REST API v1
(https://api.finna.fi/api/v1/search and /record) needs no API
key. The published rate limit could not be confirmed (recorded
as unconfirmed in docs/b8-api-research.md). From this
development network api.finna.fi answers with a Cloudflare bot
challenge (HTTP 403, observed 2026-11-26 via curl, the project
HTTP client and a text fetch); the same URL returned raw JSON
in the user's ordinary browser after the browser's own
challenge flow. NO evasion is attempted: the 403 surfaces as a
normal non-retryable adapter error, and live verification
through LibraryService is reported as NOT achieved from this
network. The response shape below was confirmed against a real
response observed in that browser (2026-11-26): two
observations of the same query disagreed on whether ``formats``
/ ``buildings`` entries are plain strings or {value, translated}
objects, so both shapes are parsed defensively.

Finna itself provides no page OCR. Digitised items live at the
providers (notably the National Library of Finland's Digi
service); page-level access is the provider adapters' job
(Stage 3), reached through the validated handoff.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json, sanitize_error
from global_library_mcp.languages import normalize_language
from global_library_mcp.models import Rights, SearchResult

API_BASE = "https://api.finna.fi/api/v1"
API_HOST = "api.finna.fi"
LANDING_BASE = "https://www.finna.fi/Record/"

_FIELDS = [
    "id",
    "title",
    "authors",
    "year",
    "languages",
    "formats",
    "buildings",
    "institutions",
    "usageRights",
    "onlineUrls",
    "urls",
    "publishers",
    "subjects",
    "series",
]

_SEARCH_TYPES = {"AllFields", "Title", "Author", "Subject"}

# Hosts of providers this project can hand off to structurally
# (brief section 6). A URL in a Finna record is a CANDIDATE only;
# it is never fetched by this adapter.
_KNOWN_PROVIDER_HOSTS = {
    "digi.kansalliskirjasto.fi": "finland-nl-digi",
    "digi.nationallibrary.fi": "finland-nl-digi",
}


def _facet_entries(value: Any) -> list[dict[str, str]]:
    """Normalise a Finna facet field to {value, translated} dicts.

    Both observed shapes are accepted: plain strings
    (``"0/Book/"``) and objects (``{"value": "0/Book/",
    "translated": "Kirja"}``). Anything else is dropped, never
    guessed at.
    """
    out: list[dict[str, str]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, str):
            out.append({"value": item, "translated": item})
        elif isinstance(item, dict):
            raw_value = str(item.get("value") or "")
            translated = str(item.get("translated") or raw_value)
            if raw_value or translated:
                out.append({"value": raw_value, "translated": translated})
    return out


def _facet_leaf(value: str) -> str:
    """Leaf label of a Finna facet path like ``1/Book/Book/``."""
    parts = [p for p in (value or "").split("/") if p and not p.isdigit()]
    return parts[-1] if parts else ""


def _facet_depth(value: str) -> int:
    parts = [p for p in (value or "").split("/") if p]
    if parts and parts[0].isdigit():
        return int(parts[0])
    return 0


def _authors(record: dict[str, Any]) -> str | None:
    authors = record.get("authors")
    if not isinstance(authors, dict):
        return None
    names: list[str] = []
    for group in ("primary", "secondary", "corporate"):
        entries = authors.get(group)
        if isinstance(entries, dict):
            for name in entries.keys():
                name = str(name).strip()
                if name and name not in names:
                    names.append(name)
        elif isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    name = str(entry.get("name") or "").strip()
                else:
                    name = str(entry or "").strip()
                if name and name not in names:
                    names.append(name)
    return "; ".join(names) or None


def _usage_rights(record: dict[str, Any]) -> Rights:
    raw = record.get("usageRights")
    labels: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = str(item or "").strip()
            # Facet-style values carry a depth prefix ("0/...").
            if "/" in text:
                head, _, rest = text.partition("/")
                if head.isdigit():
                    text = rest.strip()
            if text and text not in labels:
                labels.append(text)
    if not labels:
        return Rights(
            statement="unknown",
            source="Finna record carries no usageRights statement; the Finna metadata licence (CC0) does not extend to the item",
        )
    return Rights(
        statement="; ".join(labels),
        source="Finna record usageRights (institutional label, not a licence grant)",
    )


def _provider_links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """External links from the record, kept as DATA.

    These URLs come from upstream metadata; they are reported to
    the caller (and used as handoff candidates after structural
    validation elsewhere) but are NEVER fetched by this adapter.
    """
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field_name in ("onlineUrls", "urls"):
        entries = record.get(field_name)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                url = str(entry.get("url") or "").strip()
                text = str(entry.get("text") or "").strip() or None
                source = str(entry.get("source") or "").strip() or None
            elif isinstance(entry, str):
                url, text, source = entry.strip(), None, None
            else:
                continue
            if not url or url in seen:
                continue
            seen.add(url)
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            links.append(
                {
                    "url": url,
                    "text": text,
                    "source": source,
                    "host": host,
                    "field": field_name,
                    "handoff_library_id": _KNOWN_PROVIDER_HOSTS.get(host),
                }
            )
    return links


class FinnaAdapter(LibraryAdapter):
    library_id = "finna"
    library_name = "Finna (Finnish discovery service, National Library of Finland)"
    supports_in_document_search = False

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = await get_json(self.client, f"{API_BASE}{path}", params=params)
        except AdapterError as exc:
            raise AdapterError(self.library_id, str(exc), retryable=exc.retryable) from exc
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if not isinstance(payload, dict) or payload.get("status") not in (None, "OK"):
            raise AdapterError(
                self.library_id,
                f"Finna API returned an unexpected payload (status={payload.get('status') if isinstance(payload, dict) else type(payload).__name__})",
                retryable=False,
            )
        return payload

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return await self.search_typed(query, limit=limit)

    async def search_typed(
        self,
        query: str,
        *,
        limit: int = 10,
        search_type: str = "AllFields",
        page: int = 1,
        year: str | None = None,
        language: str | None = None,
        format_value: str | None = None,
    ) -> list[SearchResult]:
        """Keyword / title / author / subject search with the
        brief section 4 filters (year, language, format) applied
        as Finna API filters, and pagination via limit/page."""
        if search_type not in _SEARCH_TYPES:
            raise AdapterError(self.library_id, f"unsupported Finna search type: {search_type!r}", retryable=False)
        limit = min(max(limit, 1), 100)
        filters: list[str] = []
        if year:
            filters.append(f"search_daterange_mv:{year}")
        if language:
            codes = normalize_language(language)
            filters.append(f"language:{codes[0] if codes else language}")
        if format_value:
            filters.append(f"format:{format_value}")
        params: dict[str, Any] = {
            "lookfor": query,
            "type": search_type,
            "limit": limit,
            "page": max(page, 1),
            "field[]": _FIELDS,
            "lng": "en-gb",
        }
        if filters:
            params["filter[]"] = filters
        payload = await self._get("/search", params)
        records = payload.get("records")
        if not isinstance(records, list):
            return []
        return [self._result(record) for record in records if isinstance(record, dict)]

    async def search_page(
        self, query: str, *, limit: int = 10, page: int = 1, search_type: str = "AllFields"
    ) -> dict[str, Any]:
        """Search with the total count, for pagination-aware
        callers. Returns {result_count, results}."""
        payload = await self._get(
            "/search",
            {
                "lookfor": query,
                "type": search_type,
                "limit": min(max(limit, 1), 100),
                "page": max(page, 1),
                "field[]": _FIELDS,
                "lng": "en-gb",
            },
        )
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        return {
            "result_count": payload.get("resultCount"),
            "results": [self._result(r) for r in records if isinstance(r, dict)],
        }

    def _result(self, record: dict[str, Any]) -> SearchResult:
        record_id = str(record.get("id") or "").strip()
        formats = _facet_entries(record.get("formats"))
        format_labels = [
            entry["translated"] if entry["translated"] != entry["value"] else _facet_leaf(entry["value"])
            for entry in formats
        ]
        languages_raw = record.get("languages") if isinstance(record.get("languages"), list) else []
        codes: list[str] = []
        for raw_lang in languages_raw:
            for code in normalize_language(raw_lang):
                if code not in codes:
                    codes.append(code)
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=record_id,
            title=str(record.get("title") or "Untitled"),
            author=_authors(record),
            date=str(record["year"]) if record.get("year") not in (None, "") else None,
            language=codes[0] if codes else None,
            description=None,
            landing_url=f"{LANDING_BASE}{record_id}" if record_id else None,
            fulltext_status="unknown",
            rights=_usage_rights(record),
            source_protocol="Finna API v1",
            raw=record,
        )

    def _document(self, record: dict[str, Any]) -> dict[str, Any]:
        result = self._result(record)
        buildings = _facet_entries(record.get("buildings"))
        holding = None
        consortium = None
        if buildings:
            deepest = max(buildings, key=lambda e: _facet_depth(e["value"]))
            holding = deepest["translated"]
            shallowest = min(buildings, key=lambda e: _facet_depth(e["value"]))
            consortium = shallowest["translated"]
        institutions = _facet_entries(record.get("institutions"))
        provider_links = _provider_links(record)
        record_id = result.record_id
        source_prefix = record_id.split(".", 1)[0] if "." in record_id else None
        formats = _facet_entries(record.get("formats"))
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "platform": "finna",
            "platform_record_id": record_id,
            "data_source": source_prefix,
            "title": result.title,
            "author": result.author,
            "date": result.date,
            "language": result.language,
            "languages_raw": record.get("languages"),
            "formats": [
                {"value": e["value"], "label": e["translated"]} for e in formats
            ],
            "format_labels": [e["translated"] for e in formats],
            "holding_institution": holding,
            "holding_consortium": consortium,
            "buildings": [
                {"value": e["value"], "label": e["translated"]} for e in buildings
            ],
            "provider_institutions": [e["translated"] for e in institutions],
            "publishers": record.get("publishers"),
            "subjects": record.get("subjects"),
            "series": record.get("series"),
            "landing_url": result.landing_url,
            "provider_links": provider_links,
            "handoff_candidates": [
                link for link in provider_links if link.get("handoff_library_id")
            ],
            "rights": {
                "statement": result.rights.statement,
                "url": result.rights.url,
                "source": result.rights.source,
                "classification": result.rights.classification,
                "metadata_licence": "CC0 1.0 (Finna metadata only; does not extend to the item, its OCR or its images)",
            },
            "source_protocol": "Finna API v1",
            "note": (
                "Bibliographic record from the Finna cross-search platform. Finna is not the "
                "holding library: holding_institution / buildings name the holders, "
                "provider_links point at the provider's own service and are not fetched by "
                "this adapter. Page OCR is not a Finna capability; digitised items are read "
                "through the provider (Stage 3 handoff)."
            ),
        }

    async def get_document(self, record_id: str) -> dict[str, Any]:
        record_id = (record_id or "").strip()
        if not record_id:
            raise AdapterError(self.library_id, "empty Finna record id", retryable=False)
        payload = await self._get(
            "/record",
            {"id": record_id, "field[]": _FIELDS, "lng": "en-gb"},
        )
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise AdapterError(self.library_id, f"Finna record not found: {record_id}", retryable=False)
        record = records[0]
        if not isinstance(record, dict) or str(record.get("id") or "") != record_id:
            raise AdapterError(
                self.library_id,
                f"Finna record identity mismatch: requested {record_id!r}, got {record.get('id') if isinstance(record, dict) else None!r}",
                retryable=False,
            )
        return self._document(record)
