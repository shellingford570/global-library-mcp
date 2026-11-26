"""National Library of Finland Digi adapter (b8, sections
5, 6 and 10) - digitised newspapers, journals and books at
digi.kansalliskirjasto.fi.

Access model, per the documented Digi interfaces (University
of Helsinki research wiki "Interfaces of
digi.kansalliskirjasto.fi", checked 2026-11-26, and the Digi
terms of use it links):

- Bibliographic identity by binding id via OAI-PMH:
  ``GET /interfaces/OAI-PMH?verb=GetRecord&
  metadataPrefix=qdc_finna&
  identifier=oai:digi.kansalliskirjasto.fi:<binding_id>``
  The qdc_finna record carries dc fields plus the binding's own
  file links (kk:file) and per-page checksums (kk:checksum).
- Page OCR (ALTO XML):
  ``/<genre>/binding/<binding_id>/page-<n>.xml``
  (plain text twin: ``page-<n>.txt``)
- Page image: ``/<genre>/binding/<binding_id>/image/<n>``
  (JPEG); thumbnail at ``/thumbnail/<n>``.
- <genre> is sanomalehti (newspaper), aikakauslehti (journal)
  or teos (book). The genre is NEVER guessed: it is recovered
  from the binding's own OAI file links, which carry the genre
  path on the official host.

Digi offers no keyword search over bindings (OAI-PMH is a
harvesting protocol and the JSON endpoints list titles only),
so ``search`` is unsupported with that reason stated:
discovery runs through Finna, and the Finna -> Digi handoff
(``handoff.extract_digi_candidate``) resolves a Finna record
to a binding id. Claiming a search capability that does not
officially exist would be fabrication.

Page identity is proven structurally, never by URL
constructibility (brief section 10): ``verified_mapping``
requires the fetched ALTO to carry at least one internal
identity signal for THIS binding and page - the ALTO Page
element's PHYSICAL_IMG_NR equals the requested page, or the
ALTO source-image fileName mentions the binding id and the
page as delimited tokens. Digi answers out-of-range page
requests with an error page rather than an error status, so
HTTP 200 alone certifies nothing.

Rights: the OAI record's dc:rights is kept verbatim (Finnish
statements such as "Tekijänoikeuden alainen" = in copyright).
No licence classification is invented. Per the Digi access
notes, interface access covers material available online
(newspapers/journals to 1949 as digitisation progresses);
in-copyright material restricted at the source (e.g. Haka
login) is never fetched - an access page is not content, and
the image/OCR checks below reject non-content responses.

Live status (2026-11-26): digi.kansalliskirjasto.fi could not
be reached from this development network at all (the proxied
connection returned an empty reply), so this adapter is
fixture-verified only; live verification is reported as NOT
achieved in docs/b8-live-verification.md. No evasion was
attempted.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import fetch_validated, response_looks_like_image, sanitize_error
from global_library_mcp.iiif import alto_to_text
from global_library_mcp.models import Rights, SearchResult

HOST = "digi.kansalliskirjasto.fi"
ALIAS_HOST = "digi.nationallibrary.fi"
_ALLOWED_HOSTS = {HOST, ALIAS_HOST}
BASE = f"https://{HOST}"
OAI_URL = f"{BASE}/interfaces/OAI-PMH"
GENRES = ("sanomalehti", "aikakauslehti", "teos")
_BINDING_ID = re.compile(r"^\d+$")
_PAGE_ID = re.compile(r"^(\d+)@(\d+)$")
_MAX_XML = 20_000_000
_IN_DOC_PAGE_CAP = 20


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _iter_local(root: ET.Element, name: str):
    for element in root.iter():
        if _local(element.tag) == name:
            yield element


def _texts(root: ET.Element, name: str) -> list[str]:
    return [
        (element.text or "").strip()
        for element in _iter_local(root, name)
        if (element.text or "").strip()
    ]


def _genre_from_href(href: str, binding_id: str) -> str | None:
    """Genre segment of a binding file link from the record
    itself: exact host, path /<genre>/binding/<binding_id>/..."""
    try:
        parsed = urlparse(href or "")
    except ValueError:
        return None
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        return None
    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if len(segments) >= 3 and segments[0] in GENRES and segments[1] == "binding" and segments[2] == binding_id:
        return segments[0]
    return None


def _alto_identity(xml_text: str, binding_id: str, page_num: int) -> dict[str, Any]:
    """Internal identity signals inside an ALTO document."""
    signals: dict[str, Any] = {
        "alto_parsed": False,
        "physical_img_nr": None,
        "source_filename": None,
        "page_nr_matches": False,
        "filename_mentions_binding": False,
        "filename_mentions_page": False,
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return signals
    signals["alto_parsed"] = True
    for page in _iter_local(root, "Page"):
        nr = page.get("PHYSICAL_IMG_NR")
        if nr is not None:
            signals["physical_img_nr"] = nr
            try:
                signals["page_nr_matches"] = int(nr) == page_num
            except ValueError:
                signals["page_nr_matches"] = False
        break
    filename = None
    for element in _iter_local(root, "fileName"):
        filename = (element.text or "").strip() or None
        if filename:
            break
    signals["source_filename"] = filename
    if filename:
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", filename) if t]
        signals["filename_mentions_binding"] = binding_id in tokens
        signals["filename_mentions_page"] = str(page_num) in tokens or f"{page_num:04d}" in tokens
    return signals


class DigiAdapter(LibraryAdapter):
    library_id = "finland-nl-digi"
    library_name = "National Library of Finland (Digi)"
    supports_in_document_search = True  # bounded; coverage is reported

    def __init__(self, client: httpx.AsyncClient):
        super().__init__(client)
        self._documents: dict[str, dict[str, Any]] = {}

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise AdapterError(
            self.library_id,
            "Digi offers no keyword search over bindings (OAI-PMH is a harvesting protocol; "
            "the JSON endpoints list titles only); discovery runs through Finna and the "
            "Finna -> Digi handoff resolves a record to a binding id",
            retryable=False,
        )

    # -- document -------------------------------------------------

    async def _fetch_oai(self, binding_id: str) -> str:
        params = {
            "verb": "GetRecord",
            "metadataPrefix": "qdc_finna",
            "identifier": f"oai:digi.kansalliskirjasto.fi:{binding_id}",
        }
        try:
            response = await self.client.get(OAI_URL, params=params)
            response.raise_for_status()
            body = response.text
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        if len(body) > _MAX_XML:
            raise AdapterError(self.library_id, "OAI response exceeds the size bound", retryable=False)
        if "<!ENTITY" in body:
            raise AdapterError(self.library_id, "OAI response declares XML entities; refused", retryable=False)
        return body

    async def get_document(self, record_id: str) -> dict[str, Any]:
        binding_id = (record_id or "").strip()
        if not _BINDING_ID.match(binding_id):
            raise AdapterError(
                self.library_id,
                f"invalid Digi binding id: {record_id!r} (numeric binding id expected)",
                retryable=False,
            )
        cached = self._documents.get(binding_id)
        if cached:
            return dict(cached)
        body = await self._fetch_oai(binding_id)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError(self.library_id, f"malformed OAI XML: {exc}", retryable=False) from exc
        for error in _iter_local(root, "error"):
            raise AdapterError(
                self.library_id,
                f"OAI error: {error.get('code')} {(error.text or '').strip()}".strip(),
                retryable=False,
            )
        header = next(_iter_local(root, "header"), None)
        header_identifier = ""
        deleted = False
        if header is not None:
            header_identifier = next(
                ((el.text or "").strip() for el in _iter_local(header, "identifier") if (el.text or "").strip()),
                "",
            )
            deleted = header.get("status") == "deleted"
        if header_identifier != f"oai:digi.kansalliskirjasto.fi:{binding_id}":
            raise AdapterError(
                self.library_id,
                f"OAI header identifier {header_identifier!r} does not match the requested binding {binding_id}; record identity not established",
                retryable=False,
            )
        if deleted:
            raise AdapterError(self.library_id, f"Digi binding {binding_id} is marked deleted", retryable=False)
        metadata = next(_iter_local(root, "metadata"), None)
        if metadata is None:
            raise AdapterError(self.library_id, f"no metadata in OAI record for binding {binding_id}", retryable=False)

        titles = _texts(metadata, "title")
        dates = _texts(metadata, "date")
        rights_values = _texts(metadata, "rights")
        publishers = _texts(metadata, "publisher")
        languages = _texts(metadata, "language")
        identifiers = _texts(metadata, "identifier")

        genre: str | None = None
        file_links: list[dict[str, Any]] = []
        page_numbers: set[int] = set()
        for element in _iter_local(metadata, "file"):
            href = (element.get("href") or "").strip()
            if not href:
                continue
            file_links.append(
                {
                    "href": href,
                    "bundle": element.get("bundle"),
                    "type": element.get("type"),
                }
            )
            found_genre = _genre_from_href(href, binding_id)
            if found_genre and genre is None:
                genre = found_genre
        for element in _iter_local(metadata, "checksum"):
            pagenumber = element.get("pagenumber")
            if pagenumber and pagenumber.isdigit():
                page_numbers.add(int(pagenumber))
        rights = Rights(
            statement="; ".join(rights_values) if rights_values else "unknown",
            source="Digi OAI-PMH dc:rights (qdc_finna)" if rights_values else "no dc:rights in the Digi OAI record",
        )
        document = {
            "library_id": self.library_id,
            "record_id": binding_id,
            "binding_id": binding_id,
            "genre": genre,
            "title": titles[0] if titles else None,
            "date": dates[0] if dates else None,
            "publisher": "; ".join(publishers) or None,
            "language": languages[0] if languages else None,
            "identifiers": identifiers,
            "page_count": max(page_numbers) if page_numbers else None,
            "page_count_source": "OAI kk:checksum page numbers" if page_numbers else None,
            "landing_url": f"{BASE}/{genre}/binding/{binding_id}" if genre else f"{BASE}/sanomalehti/binding/{binding_id}",
            "rights": asdict(rights),
            "source_protocol": "OAI-PMH (qdc_finna)",
            "note": (
                "Binding-level metadata from Digi's OAI-PMH. The genre segment used for page "
                "URLs is recovered from the record's own file links on the official host; "
                "when no such link exists the genre stays unknown and page access is refused "
                "rather than guessed."
            ),
        }
        self._documents[binding_id] = dict(document)
        return document

    async def _genre_for(self, binding_id: str) -> str:
        document = await self.get_document(binding_id)
        genre = document.get("genre")
        if not genre:
            raise AdapterError(
                self.library_id,
                f"Digi binding {binding_id}: genre not established from the OAI record's file links; page access refused rather than guessed",
                retryable=False,
            )
        return str(genre)

    # -- pages ------------------------------------------------------

    def _page_urls(self, genre: str, binding_id: str, page_num: int) -> dict[str, str]:
        root = f"{BASE}/{genre}/binding/{binding_id}"
        return {
            "alto": f"{root}/page-{page_num}.xml",
            "text": f"{root}/page-{page_num}.txt",
            "image": f"{root}/image/{page_num}",
            "landing": f"{root}?page={page_num}",
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        match = _PAGE_ID.match(page_id or "")
        if not match:
            raise AdapterError(
                self.library_id,
                f"invalid Digi page id: {page_id!r} (expected <binding_id>@<page>)",
                retryable=False,
            )
        binding_id, page_num = match.group(1), int(match.group(2))
        if page_num < 1:
            raise AdapterError(self.library_id, f"invalid Digi page number: {page_num}", retryable=False)
        document = await self.get_document(binding_id)
        genre = await self._genre_for(binding_id)
        urls = self._page_urls(genre, binding_id, page_num)
        alto_url = urls["alto"]
        ocr_fetched = False
        fetch_error: str | None = None
        text: str | None = None
        identity: dict[str, Any] = {"alto_parsed": False}
        try:
            response = await fetch_validated(self.client, alto_url, allowed_hosts=_ALLOWED_HOSTS)
            if response.status_code == 429:
                raise AdapterError(self.library_id, "Digi rate limit (429) on the ALTO endpoint; stopped", retryable=False)
            response.raise_for_status()
            body = response.text
            if len(body) > _MAX_XML:
                raise AdapterError(self.library_id, "ALTO response exceeds the size bound", retryable=False)
            identity = _alto_identity(body, binding_id, page_num)
            text = alto_to_text(body) or None
            ocr_fetched = True
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            fetch_error = sanitize_error(exc)
        verified = bool(
            ocr_fetched
            and identity.get("alto_parsed")
            and (identity.get("page_nr_matches") or (identity.get("filename_mentions_binding") and identity.get("filename_mentions_page")))
        )
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "record_id": binding_id,
            "binding_id": binding_id,
            "genre": genre,
            "digital_frame": page_num,
            "printed_page": "unknown",
            "printed_page_source": "not confirmed by the provider; digital page number kept separately",
            "contents": text,
            "ocr_source": alto_url,
            "ocr_format": "ALTO XML (Digi page component)",
            "ocr_fetched": ocr_fetched,
            "ocr_nonempty": bool(text and text.strip()),
            "ocr_fetch_error": fetch_error,
            "page_identity_verified": verified,
            "verified_mapping": verified,
            "mapping_checks": identity,
            "image_url": urls["image"],
            "landing_url": urls["landing"],
            "rights": document.get("rights"),
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        page = await self.get_page_text(page_id)
        image_url = page.get("image_url")
        image_ok = False
        image_detail = "no image URL"
        if image_url:
            try:
                response = await fetch_validated(self.client, image_url, allowed_hosts=_ALLOWED_HOSTS)
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
                "document_identity": {"ok": True, "detail": page.get("binding_id") or ""},
                "page_identity": {
                    "ok": bool(page.get("page_identity_verified")),
                    "detail": str({k: checks.get(k) for k in ("physical_img_nr", "source_filename")}),
                },
                "ocr_fetched": {"ok": bool(page.get("ocr_fetched")), "detail": page.get("ocr_fetch_error") or "ALTO retrieved"},
                "ocr_mapping_verified": {"ok": bool(page.get("verified_mapping")), "detail": str(checks)},
                "image_reachable": {"ok": image_ok, "detail": image_detail},
            },
            "image_url": image_url,
            "landing_url": page.get("landing_url"),
        }

    async def search_in_document(self, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        document = await self.get_document(record_id)
        page_count = document.get("page_count")
        if not page_count:
            raise AdapterError(
                self.library_id,
                "in-document search requires the binding's page count from its OAI record; not established",
                retryable=False,
            )
        needle = (query or "").strip().lower()
        if not needle:
            raise AdapterError(self.library_id, "empty in-document query", retryable=False)
        cap = min(int(page_count), _IN_DOC_PAGE_CAP)
        hits: list[dict[str, Any]] = []
        failures = 0
        for page_num in range(1, cap + 1):
            try:
                page = await self.get_page_text(f"{record_id}@{page_num}")
            except AdapterError:
                failures += 1
                continue
            contents = page.get("contents") or ""
            if needle in contents.lower():
                hits.append(
                    {
                        "page_id": page["page_id"],
                        "page": page_num,
                        "verified_mapping": page.get("verified_mapping"),
                    }
                )
                if len(hits) >= limit:
                    break
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "query": query,
            "hits": hits,
            "pages_examined": cap,
            "page_count": page_count,
            "complete": cap >= int(page_count),
            "partial_failures": failures,
            "note": "bounded in-document search over the binding's ALTO pages; coverage is reported, not implied",
        }
