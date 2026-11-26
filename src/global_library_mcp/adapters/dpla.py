"""Digital Public Library of America (DPLA) adapter
(b8, section 7) - authentication-pending implementation.

DPLA's API v2 (https://api.dp.la/v2) requires a 32-character
API key as a query parameter on EVERY request. Keys are free
and self-service, but issuing one was NOT approved for b8, so
no key was requested. Behaviour:

- With no ``DPLA_API_KEY`` in the environment, every operation
  raises an AdapterError whose message states
  ``authentication_required`` (retryable=False). The registry
  capability status says the same. Nothing is silently skipped
  and no anonymous call is attempted.
- With a key configured (by the operator, outside this
  project), search and document retrieval run against the
  official endpoints, fixture-tested here.

DPLA is a metadata aggregator: it provides no full text and
no page OCR, so page methods stay unsupported. Two institution
roles are kept distinct, as the brief requires: ``provider``
is the aggregation hub that contributed the record to DPLA;
``dataProvider`` is the originating institution that holds the
item. ``isShownAt`` / ``object`` are the provider's own URLs -
reported as data / landing link, never fetched by this
adapter. Rights come from ``sourceResource.rights`` (typically
RightsStatements.org URIs) and are classified structurally;
the URI is never paraphrased into a licence grant.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json, sanitize_error
from global_library_mcp.rights_uri import rights_uri_label
from global_library_mcp.models import Rights, SearchResult

API_BASE = "https://api.dp.la/v2"
ENV_KEY = "DPLA_API_KEY"
_RECORD_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _rights_classification(url: str | None) -> str | None:
    """Display-only classification via the shared strict
    rights_uri parser (b8 final review section 15)."""
    return rights_uri_label(url)


def _as_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item or "").strip()]
        return "; ".join(parts) or None
    if isinstance(value, dict):
        return _as_text(value.get("name") or value.get("@value"))
    return None


class DplaAdapter(LibraryAdapter):
    library_id = "dpla"
    library_name = "Digital Public Library of America (DPLA)"
    supports_in_document_search = False

    def _api_key(self) -> str:
        key = (os.getenv(ENV_KEY) or "").strip()
        if not key:
            raise AdapterError(
                self.library_id,
                "authentication_required: the DPLA API requires an API key on every request; "
                f"no key is configured ({ENV_KEY} is unset) and no key was issued for this project",
                retryable=False,
            )
        return key

    def authentication_status(self) -> str:
        return "configured" if (os.getenv(ENV_KEY) or "").strip() else "authentication_required"

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        # Credential hygiene (b8 final review section 17): the
        # key travels ONLY as this request's api_key query
        # parameter. Errors are re-sanitised here as a second
        # line of defence so a URL carrying the key can never
        # surface in an exception, a log line, HTTP statistics
        # (per-host counts only), search history or an MCP
        # response; httpx does not forward query parameters
        # across redirects, so a redirect cannot leak it either.
        key = self._api_key()
        try:
            payload = await get_json(self.client, f"{API_BASE}{path}", params={**params, "api_key": key})
        except AdapterError as exc:
            raise AdapterError(self.library_id, sanitize_error(str(exc)), retryable=exc.retryable) from exc
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if not isinstance(payload, dict):
            raise AdapterError(self.library_id, "DPLA returned an unexpected payload", retryable=False)
        return payload

    def _result(self, doc: dict[str, Any]) -> SearchResult:
        resource = doc.get("sourceResource") or {}
        rights_urls = resource.get("rights") if isinstance(resource.get("rights"), list) else []
        rights_url = str(rights_urls[0]) if rights_urls else None
        date = resource.get("date")
        date_text = None
        if isinstance(date, dict):
            date_text = date.get("displayDate") or date.get("begin") or date.get("end")
        elif isinstance(date, list) and date:
            first = date[0]
            date_text = first.get("displayDate") if isinstance(first, dict) else str(first)
        elif isinstance(date, str):
            date_text = date
        languages = resource.get("language")
        language_name = None
        if isinstance(languages, list) and languages:
            first = languages[0]
            language_name = first.get("name") if isinstance(first, dict) else str(first)
        elif isinstance(languages, dict):
            language_name = languages.get("name")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=str(doc.get("id") or ""),
            title=_as_text(resource.get("title")) or "Untitled",
            author=_as_text(resource.get("creator")),
            date=str(date_text) if date_text else None,
            language=language_name,
            description=_as_text(resource.get("description")),
            landing_url=doc.get("isShownAt") if isinstance(doc.get("isShownAt"), str) else None,
            fulltext_status="unknown",
            rights=Rights(
                statement=rights_url or "unknown",
                url=rights_url,
                source="DPLA sourceResource.rights" if rights_url else "no rights statement in the DPLA record",
                classification=_rights_classification(rights_url),
            ),
            source_protocol="DPLA API v2",
            raw=doc,
        )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = await self._get(
            "/items",
            {"q": query, "page_size": min(max(limit, 1), 100), "page": 1},
        )
        docs = payload.get("docs")
        if not isinstance(docs, list):
            return []
        return [self._result(doc) for doc in docs if isinstance(doc, dict)]

    async def get_document(self, record_id: str) -> dict[str, Any]:
        record_id = (record_id or "").strip()
        if not record_id:
            raise AdapterError(self.library_id, "empty DPLA record id", retryable=False)
        if not _RECORD_ID_RE.fullmatch(record_id):
            # A record id must never change the request's path
            # or query structure (section 17).
            raise AdapterError(self.library_id, f"invalid DPLA record id: {record_id!r}", retryable=False)
        payload = await self._get(f"/items/{quote(record_id, safe='')}", {})
        docs = payload.get("docs")
        if not isinstance(docs, list) or not docs or not isinstance(docs[0], dict):
            raise AdapterError(self.library_id, f"DPLA record not found: {record_id}", retryable=False)
        doc = docs[0]
        if str(doc.get("id") or "") != record_id:
            raise AdapterError(
                self.library_id,
                f"DPLA record identity mismatch: requested {record_id!r}, got {doc.get('id')!r}",
                retryable=False,
            )
        result = self._result(doc)
        resource = doc.get("sourceResource") or {}
        provider = doc.get("provider") if isinstance(doc.get("provider"), dict) else {}
        data_provider = doc.get("dataProvider")
        if isinstance(data_provider, dict):
            data_provider_name = data_provider.get("name")
        else:
            data_provider_name = data_provider if isinstance(data_provider, str) else None
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "platform": "dpla",
            "title": result.title,
            "author": result.author,
            "date": result.date,
            "language": result.language,
            "description": result.description,
            "subjects": resource.get("subject"),
            "types": resource.get("type"),
            "aggregation_provider": provider.get("name"),
            "data_provider": data_provider_name,
            "landing_url": result.landing_url,
            "object_url": doc.get("object") if isinstance(doc.get("object"), str) else None,
            "rights": {
                "statement": result.rights.statement,
                "url": result.rights.url,
                "source": result.rights.source,
                "classification": result.rights.classification,
            },
            "source_protocol": "DPLA API v2",
            "note": (
                "Metadata from the DPLA aggregation platform. aggregation_provider is the hub "
                "that contributed the record; data_provider is the originating institution. "
                "DPLA provides no full text or page OCR; the item itself lives at the "
                "provider (landing_url / object_url are reported, not fetched)."
            ),
        }
