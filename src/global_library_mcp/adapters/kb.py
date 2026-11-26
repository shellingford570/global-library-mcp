"""KB / Delpher adapter (b8, section 9) - historical Dutch
newspapers via the KB's SRU service and resolver.

Access model (official KB interfaces, checked 2026-11-26 and
verified live from this network):

- Search: SRU 1.2 at ``https://jsru.kb.nl/sru/sru``
  (operation=searchRetrieve, collection ``DDD_artikel`` =
  newspaper articles). No registration or API key is required
  for the public collections.
- A record's identifier is a KB resolver URL carrying the
  article URN with an ``:ocr`` suffix
  (``ddd:010286065:mpeg21:a0141``). The URN without the suffix
  is this adapter's record_id; stripping the parent segment
  (``:a0141``) gives the issue URN.
- Page OCR: ``https://resolver.kb.nl/resolve?urn=<URN>:ocr``
  returns an XML document (<text><title/><p/>...) holding the
  article text. The article is the page-level unit here: a
  Delpher article sits on exactly one newspaper page.
- Page image: the same resolver with ``:image``. NOTE: in
  the live run on 2026-11-26 the ``:image`` suffix answered
  404 for the tested article URN, so image verification is
  fixture-verified only and ``verify_original`` honestly
  reports unverified there; no alternative image route was
  guessed.

The Delpher website itself is closed to crawlers and is NOT
scraped; only the SRU API and the resolver are used.

Identity (brief section 10): ``verified_mapping`` for a page
requires the resolver OCR payload's own <title> to correspond
exactly (after normalisation) to the SRU record title for the
SAME URN, where the SRU record was itself selected by an exact
identifier match on the resolver URL. Constructing the
resolver URL proves nothing on its own.

Rights: KB metadata is CC0; the item rights are per-record -
``dc:rights`` when the SRU record carries it (often a holder
statement, not a licence) and ``unknown`` otherwise. Images /
full text frequently carry CC BY-NC-ND at the source; nothing
here upgrades a holder statement into a licence.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import fetch_validated, response_looks_like_image, sanitize_error
from global_library_mcp.models import Rights, SearchResult

SRU_URL = "https://jsru.kb.nl/sru/sru"
RESOLVER_BASE = "https://resolver.kb.nl/resolve"
_RESOLVER_HOSTS = {"resolver.kb.nl"}
COLLECTION = "DDD_artikel"
_MAX_XML = 10_000_000
# Article/page URNs: <prefix>:<digits>:mpeg21:<a|p><digits>
_URN_RE = re.compile(r"^[A-Za-z0-9]+:[0-9A-Za-z]+:mpeg21:[ap]\d+$")
_RESOLVER_URN_RE = re.compile(r"[?&]urn=([^&]+)$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element: ET.Element, name: str) -> list[str]:
    return [
        (child.text or "").strip()
        for child in element
        if _local(child.tag) == name and (child.text or "").strip()
    ]


def _norm_title(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "").lower()).strip()


def _urn_from_identifier(identifier: str) -> str | None:
    """Article URN out of a resolver identifier URL: the URL
    must be on the exact resolver host with a single urn query
    parameter whose value carries the :ocr suffix."""
    try:
        parsed = urlparse(identifier or "")
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in _RESOLVER_HOSTS:
        return None
    if parsed.path != "/resolve":
        return None
    match = _RESOLVER_URN_RE.search("?" + (parsed.query or ""))
    if not match:
        return None
    urn = match.group(1)
    if not urn.endswith(":ocr"):
        return None
    urn = urn[: -len(":ocr")]
    return urn if _URN_RE.match(urn) else None


def _date_from_dc(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.match(r"^(\d{4})/(\d{2})/(\d{2})", raw)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return raw


class KbDelpherAdapter(LibraryAdapter):
    library_id = "kb-delpher"
    library_name = "KB / Delpher (National Library of the Netherlands)"
    supports_in_document_search = False

    async def _sru(self, query: str, maximum: int, start: int = 1) -> ET.Element:
        params = {
            "operation": "searchRetrieve",
            "version": "1.2",
            "query": query,
            "x-collection": COLLECTION,
            "maximumRecords": maximum,
            "startRecord": start,
        }
        body: str | None = None
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.get(SRU_URL, params=params)
                response.raise_for_status()
                body = response.text
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # One bounded retry for transient transport
                # failures (a dropped connection through a proxy
                # was observed live on 2026-11-26); HTTP status
                # errors are not retried here.
                if attempt == 0 and isinstance(exc, httpx.HTTPError) and not isinstance(
                    exc, httpx.HTTPStatusError
                ):
                    continue
                raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if body is None:
            raise AdapterError(self.library_id, sanitize_error(last_exc), retryable=True)
        if len(body) > _MAX_XML:
            raise AdapterError(self.library_id, "SRU response exceeds the size bound", retryable=False)
        if "<!ENTITY" in body:
            raise AdapterError(self.library_id, "SRU response declares XML entities; refused", retryable=False)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError(self.library_id, f"malformed SRU XML: {exc}", retryable=False) from exc
        for diag in root.iter():
            if _local(diag.tag) == "diagnostic":
                message = "; ".join(_children(diag, "message") or _children(diag, "details"))
                raise AdapterError(self.library_id, f"SRU diagnostic: {message or 'unknown'}", retryable=False)
        return root

    def _records(self, root: ET.Element) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record in root.iter():
            if _local(record.tag) != "record":
                continue
            data = None
            for child in record:
                if _local(child.tag) == "recordData":
                    data = child
                    break
            if data is None:
                continue
            fields: dict[str, list[str]] = {}
            for element in data.iter():
                name = _local(element.tag)
                if name in ("recordData",):
                    continue
                text = (element.text or "").strip()
                if text:
                    fields.setdefault(name, []).append(text)
            urn = None
            for identifier in fields.get("identifier", []):
                urn = _urn_from_identifier(identifier)
                if urn:
                    break
            if not urn:
                continue
            records.append({"urn": urn, "fields": fields})
        return records

    def _result(self, record: dict[str, Any]) -> SearchResult:
        fields = record["fields"]
        urn = record["urn"]
        rights_values = fields.get("rights", [])
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=urn,
            title=(fields.get("title") or ["Untitled"])[0],
            author=None,
            date=_date_from_dc((fields.get("date") or [None])[0]),
            language=None,
            description=(fields.get("source") or [None])[0],
            landing_url=f"{RESOLVER_BASE}?urn={urn}",
            fulltext_status="available",
            rights=Rights(
                statement="; ".join(rights_values) if rights_values else "unknown",
                source="KB SRU dc:rights" if rights_values else "no dc:rights in the SRU record; KB metadata is CC0 but item rights are per-record",
            ),
            source_protocol="KB SRU 1.2 (Delpher newspapers)",
            raw={"urn": urn, "fields": fields},
        )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        # Plain keyword CQL: the query is passed as search terms;
        # embedded double quotes are removed so the caller's text
        # cannot silently become a different CQL expression.
        terms = (query or "").replace('"', " ").strip()
        if not terms:
            raise AdapterError(self.library_id, "empty search query", retryable=False)
        root = await self._sru(terms, min(max(limit, 1), 100))
        return [self._result(record) for record in self._records(root)[:limit]]

    async def _record_by_urn(self, urn: str) -> dict[str, Any]:
        resolver_url = f"http://resolver.kb.nl/resolve?urn={urn}:ocr"
        root = await self._sru(f'dc.identifier all "{resolver_url}"', 5)
        for record in self._records(root):
            if record["urn"] == urn:
                return record
        raise AdapterError(self.library_id, f"KB record not found for URN {urn}", retryable=False)

    async def get_document(self, record_id: str) -> dict[str, Any]:
        urn = (record_id or "").strip()
        if not _URN_RE.match(urn):
            raise AdapterError(self.library_id, f"invalid KB article URN: {record_id!r}", retryable=False)
        record = await self._record_by_urn(urn)
        result = self._result(record)
        fields = record["fields"]
        issue_urn = urn.rsplit(":", 1)[0]
        return {
            "library_id": self.library_id,
            "record_id": urn,
            "urn": urn,
            "issue_urn": issue_urn,
            "title": result.title,
            "date": result.date,
            "issued": (fields.get("issued") or [None])[0],
            "publisher": (fields.get("publisher") or [None])[0],
            "source": (fields.get("source") or [None])[0],
            "type": (fields.get("type") or [None])[0],
            "language": None,
            "landing_url": result.landing_url,
            "ocr_url": f"{RESOLVER_BASE}?urn={urn}:ocr",
            "image_url": f"{RESOLVER_BASE}?urn={urn}:image",
            "rights": asdict(result.rights) | {"metadata_licence": "CC0 (KB metadata only; item rights are per-record)"},
            "source_protocol": "KB SRU 1.2 (Delpher newspapers)",
            "note": (
                "Newspaper article record from Delpher via the KB SRU service. The article is "
                "the page-level unit. Metadata is CC0; the article text and page image rights "
                "are per-record (dc:rights kept verbatim when present)."
            ),
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        urn = (page_id or "").strip()
        if not _URN_RE.match(urn):
            raise AdapterError(self.library_id, f"invalid KB page id (article URN expected): {page_id!r}", retryable=False)
        record = await self._record_by_urn(urn)
        expected_title = (record["fields"].get("title") or [""])[0]
        ocr_url = f"{RESOLVER_BASE}?urn={urn}:ocr"
        ocr_fetched = False
        fetch_error: str | None = None
        text: str | None = None
        payload_title: str | None = None
        try:
            response = await fetch_validated(self.client, ocr_url, allowed_hosts=_RESOLVER_HOSTS)
            if response.status_code == 429:
                raise AdapterError(self.library_id, "KB resolver rate limit (429); stopped", retryable=False)
            response.raise_for_status()
            body = response.text
            if len(body) > _MAX_XML:
                raise AdapterError(self.library_id, "OCR response exceeds the size bound", retryable=False)
            if "<!ENTITY" in body:
                raise AdapterError(self.library_id, "OCR response declares XML entities; refused", retryable=False)
            root = ET.fromstring(body)
            paragraphs: list[str] = []
            for element in root.iter():
                name = _local(element.tag)
                if name == "title" and payload_title is None:
                    payload_title = (element.text or "").strip() or None
                elif name == "p":
                    chunk = (element.text or "").strip()
                    if chunk:
                        paragraphs.append(chunk)
            text = "\n\n".join(paragraphs) or None
            ocr_fetched = True
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            fetch_error = sanitize_error(exc)
        title_matches = bool(
            payload_title and expected_title and _norm_title(payload_title) == _norm_title(expected_title)
        )
        verified = bool(ocr_fetched and title_matches)
        return {
            "library_id": self.library_id,
            "page_id": urn,
            "record_id": urn,
            "urn": urn,
            "issue_urn": urn.rsplit(":", 1)[0],
            "printed_page": "unknown",
            "printed_page_source": "the article URN is the page-level unit in Delpher; a printed page number is not asserted",
            "contents": text,
            "ocr_source": ocr_url,
            "ocr_format": "KB resolver OCR XML (Delpher)",
            "ocr_fetched": ocr_fetched,
            "ocr_nonempty": bool(text and text.strip()),
            "ocr_fetch_error": fetch_error,
            "page_identity_verified": verified,
            "verified_mapping": verified,
            "mapping_checks": {
                "sru_record_selected_by_exact_identifier": True,
                "ocr_payload_title": payload_title,
                "sru_record_title": expected_title or None,
                "title_matches": title_matches,
            },
            "image_url": f"{RESOLVER_BASE}?urn={urn}:image",
            "landing_url": f"{RESOLVER_BASE}?urn={urn}",
            "rights": asdict(self._result(record).rights),
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        page = await self.get_page_text(page_id)
        image_url = page.get("image_url")
        image_ok = False
        image_detail = "no image URL"
        if image_url:
            try:
                response = await fetch_validated(self.client, image_url, allowed_hosts=_RESOLVER_HOSTS)
                body = response.content or b""
                content_type = (response.headers.get("content-type") or "").lower()
                image_ok = response.status_code in (200, 206) and response_looks_like_image(body, content_type)
                image_detail = (
                    f"image GET status {response.status_code}, content-type {content_type or 'none'}, "
                    f"{len(body)} bytes, image signature {'ok' if image_ok else 'not an image'}"
                )
            except Exception as exc:  # noqa: BLE001
                image_detail = sanitize_error(exc)
        verified = bool(page.get("verified_mapping") and image_ok)
        checks = page.get("mapping_checks") or {}
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "status": "verified" if verified else "unverified",
            "checks": {
                "document_identity": {"ok": True, "detail": page.get("urn") or ""},
                "page_identity": {"ok": bool(page.get("page_identity_verified")), "detail": str(checks)},
                "ocr_fetched": {"ok": bool(page.get("ocr_fetched")), "detail": page.get("ocr_fetch_error") or "OCR retrieved"},
                "ocr_mapping_verified": {"ok": bool(page.get("verified_mapping")), "detail": str(checks)},
                "image_reachable": {"ok": image_ok, "detail": image_detail},
            },
            "image_url": image_url,
            "landing_url": page.get("landing_url"),
        }
