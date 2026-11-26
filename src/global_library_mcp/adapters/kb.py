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

Identity (brief section 10; b8 final review section 5):
the resolver OCR payload carries NO article identifier - only
a <title>. A title correspondence with the SRU record is
reported as ``article_title_matches`` and nothing more: the
same title can head different articles in different papers,
issues and pages, so a title match alone NEVER makes
``verified_mapping`` true and never admits the OCR as
verified evidence. Article URN, issue URN, physical page and
digital page are kept as separate fields; the article is the
OCR unit, and article OCR is not page-full OCR. Constructing
the resolver URL proves nothing on its own.

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
from urllib.parse import parse_qsl, urlparse

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
_URN_RE = re.compile(r"[A-Za-z0-9]+:[0-9A-Za-z]+:mpeg21:[ap]\d+")


def _is_urn(value: Any) -> bool:
    """Full-string URN match: a trailing newline or any extra
    character fails (re.fullmatch, never a $-anchored search,
    so no line-terminator smuggling)."""
    return isinstance(value, str) and _URN_RE.fullmatch(value) is not None


def _cql_literal(text: str) -> str:
    """A CQL string literal for the given plain text (b8 final
    review section 16): backslash and double-quote are escaped
    per the CQL grammar and control characters are refused, so
    caller text can never become CQL syntax (operators, index
    specifications or parentheses stay literal characters
    inside the quoted string)."""
    if any(ord(ch) < 0x20 for ch in text):
        raise ValueError("control characters are not allowed in a KB query")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cql_keyword_query(query: str) -> str:
    """Plain keyword search expressed as ONE quoted literal on
    the default index - never as caller-supplied CQL."""
    terms = " ".join((query or "").split())
    if not terms:
        raise ValueError("empty search query")
    return _cql_literal(terms)


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
    """Article URN out of a resolver identifier URL, parsed
    structurally (b8 final review section 16): exact resolver
    host, /resolve path, no userinfo, no abnormal port, no
    fragment, and EXACTLY ONE urn query parameter whose value
    carries the :ocr suffix and full-matches the URN grammar.
    Duplicated urn parameters or several different article
    identifiers in one URL are refused, never first-wins."""
    if not isinstance(identifier, str) or any(
            ord(ch) < 0x20 for ch in identifier):
        return None
    try:
        parsed = urlparse(identifier)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in _RESOLVER_HOSTS:
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    try:
        if parsed.port not in (None, 80, 443):
            return None
    except ValueError:
        return None
    if parsed.path != "/resolve":
        return None
    urns = [value for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key == "urn"]
    if len(urns) != 1:
        return None
    urn = urns[0]
    if not urn.endswith(":ocr"):
        return None
    urn = urn[: -len(":ocr")]
    return urn if _is_urn(urn) else None


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
    # Bounded by construction: the article is a single
    # page-level unit, so in-document search examines exactly
    # that one text and reports coverage of 1/1.
    supports_in_document_search = True

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
        # Plain keyword search only: the caller's text becomes
        # ONE quoted CQL literal (section 16), so embedded
        # quotes, operators, index names and parentheses are
        # literal characters, never CQL syntax. There is no
        # advanced-CQL mode in this adapter.
        try:
            cql = cql_keyword_query(query or "")
        except ValueError as exc:
            raise AdapterError(self.library_id, str(exc), retryable=False) from exc
        root = await self._sru(cql, min(max(limit, 1), 100))
        return [self._result(record) for record in self._records(root)[:limit]]

    async def _record_by_urn(self, urn: str) -> dict[str, Any]:
        resolver_url = f"http://resolver.kb.nl/resolve?urn={urn}:ocr"
        root = await self._sru(f"dc.identifier all {_cql_literal(resolver_url)}", 5)
        for record in self._records(root):
            if record["urn"] == urn:
                return record
        raise AdapterError(self.library_id, f"KB record not found for URN {urn}", retryable=False)

    async def get_document(self, record_id: str) -> dict[str, Any]:
        urn = (record_id or "").strip()
        if not _is_urn(urn):
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
        if not _is_urn(urn):
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
        # Identity separation (b8 final review section 5): the
        # OCR payload carries no article identifier, so strict
        # article identity CANNOT be confirmed from it; the
        # physical page is a different unit again and is not
        # identified at all. verified_mapping therefore stays
        # False: a title match is a correspondence signal, not
        # proof, and this OCR is never admitted as verified
        # evidence on its basis.
        verified = False
        return {
            "library_id": self.library_id,
            "page_id": urn,
            "record_id": urn,
            "urn": urn,
            "article_urn": urn,
            "issue_urn": urn.rsplit(":", 1)[0],
            "page_urn": None,
            "page_urn_status": "not established: the resolver OCR payload identifies no physical page",
            "digital_page_id": urn,
            "printed_page": "unknown",
            "printed_page_source": "the article URN is the page-level unit in Delpher; a printed page number is not asserted",
            "contents": text,
            "ocr_source": ocr_url,
            "ocr_format": "KB resolver OCR XML (Delpher article unit - not a full page OCR)",
            "ocr_unit": "article",
            "article_ocr_fetched": ocr_fetched,
            "article_title_matches": title_matches,
            "article_identity_confirmed": False,
            "page_identity_confirmed": False,
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
                "article_title_matches": title_matches,
                "ocr_payload_carries_article_identifier": False,
                "article_identity_confirmed": False,
                "page_identity_confirmed": False,
                "identity_note": ("the resolver OCR payload contains no article "
                                  "identifier - only a title - so strict article "
                                  "identity cannot be confirmed; title correspondence "
                                  "alone never verifies the mapping"),
            },
            "image_url": f"{RESOLVER_BASE}?urn={urn}:image",
            "landing_url": f"{RESOLVER_BASE}?urn={urn}",
            "rights": asdict(self._result(record).rights),
        }

    async def search_in_document(self, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        """In-document search over the article's own OCR text
        (the article is the single page-level unit in Delpher),
        in the common result schema."""
        urn = (record_id or "").strip()
        if not _is_urn(urn):
            raise AdapterError(self.library_id, f"invalid KB article URN: {record_id!r}", retryable=False)
        needle = (query or "").strip().lower()
        if not needle:
            raise AdapterError(self.library_id, "empty in-document query", retryable=False)
        page = await self.get_page_text(urn)
        contents = page.get("contents") or ""
        matches: list[dict[str, Any]] = []
        idx = contents.lower().find(needle)
        if idx >= 0:
            matches.append(
                {
                    "id": urn,
                    "page_id": urn,
                    "record_id": urn,
                    "snippet": contents[max(0, idx - 60): idx + len(needle) + 60],
                    "printed_page": page.get("printed_page"),
                    "mapping_status": "verified" if page.get("verified_mapping") else "unverified",
                    "verified_mapping": page.get("verified_mapping"),
                }
            )
        return {
            "library_id": self.library_id,
            "record_id": urn,
            "query": query,
            "matches": {"list": matches},
            "hits": matches,
            "pages_searched": 1,
            "total_pages": 1,
            "complete": True,
            "partial_failures": [],
            "note": "the Delpher article is a single page-level unit; its full OCR text was searched",
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
        # Reachability, format and identity are separate
        # checks (b8 final review section 6): a reachable,
        # well-formed image is not thereby THIS article's page
        # image. The :image URL is constructed from the article
        # URN, the payload carries no image identifier, and
        # article identity itself is unconfirmed - so the
        # status stays unverified. (Live, on 2026-11-26, the
        # :image suffix answered 404 for the tested article.)
        checks = page.get("mapping_checks") or {}
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "status": "unverified",
            "checks": {
                "document_identity": {"ok": bool(checks.get("sru_record_selected_by_exact_identifier")), "detail": page.get("urn") or ""},
                "article_identity": {"ok": False, "detail": "title correspondence only; the OCR payload carries no article identifier"},
                "page_identity": {"ok": False, "detail": "physical page not identified by the article OCR payload"},
                "ocr_fetched": {"ok": bool(page.get("ocr_fetched")), "detail": page.get("ocr_fetch_error") or "article OCR retrieved"},
                "ocr_mapping_verified": {"ok": bool(page.get("verified_mapping")), "detail": str(checks)},
                "image_url_structure": {"ok": bool(image_url and image_url.endswith(":image")), "detail": image_url or ""},
                "image_reachable": {"ok": image_ok, "detail": image_detail},
                "image_identity_confirmed": {"ok": False, "detail": "image bytes carry no identifier; correspondence is not confirmed"},
                "human_visual_check": {"ok": False, "detail": "not performed"},
            },
            "image_url": image_url,
            "image_identity_status": "unconfirmed",
            "landing_url": page.get("landing_url"),
        }
