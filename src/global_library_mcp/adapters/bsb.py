"""Bayerische Staatsbibliothek / Munich Digitization Center
(BSB/MDZ) adapter (b5, section 4; strictness fixes from the b5
final review).

Access model, per the official MDZ interfaces documentation
(https://www.digitale-sammlungen.de/en/interfaces, checked
2026-11-25):

- IIIF Presentation API 2 manifests:
  ``https://api.digitale-sammlungen.de/iiif/presentation/v2/{object_id}/manifest``
- IIIF Image API 2 services linked from each canvas.
- Per-page OCR (hOCR):
  ``https://api.digitale-sammlungen.de/ocr/{object_id}/{page_num}``
  where ``page_num`` is the 1-based canvas number; each canvas
  links the same URL under ``seeAlso`` (format
  ``text/vnd.hocr+html``).

The interfaces documentation offers NO keyword search API, so
this adapter is ID-addressed: bibliographic discovery of BSB
holdings runs through the DDB aggregator, and this adapter
resolves a known object id (``bsb...``) to its manifest, page
OCR, original images, citation and rights. Claiming a search
capability that does not officially exist would be fabrication.

Page mapping is proven structurally, never by suffix luck
(final review, sections 2-3). ``verified_mapping`` requires ALL
of:

- the manifest's own @id carries the object id as a path
  segment;
- the canvas @id carries the object id as a path segment and
  ends with the exact segments ``canvas/{page_num}``;
- the image service id's final path segment is exactly
  ``{object_id}_{page_num:05d}``;
- the canvas's manifest OCR link (seeAlso) parses to exactly
  ``/ocr/{object_id}/{page_num}`` on the MDZ API host;
- the hOCR payload's parsed <title> element is exactly
  ``{object_id}_{page_num:05d}``.

Being able to CONSTRUCT the OCR URL is not a verification
signal and is not counted. When any required element is absent
(for example a manifest without an OCR link), the page text is
still returned as research material, but with
``verified_mapping`` false.

``verify_original`` reuses the very same page result, so the
two can never disagree, and additionally fetches a small IIIF
image and checks that the response really is an image (status,
Content-Type and magic bytes) - an HTTP 200 HTML error page is
not an original image.

MDZ rate-limits OCR downloads and Image API requests per 24h
(the numeric cap is not published; the Presentation API is
unlimited), so this adapter caches manifests and page OCR,
spaces OCR/image requests out, stops an in-document search at
the first systemic failure, and reports partial coverage
instead of pretending completeness.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import fetch_validated, get_json, response_looks_like_image, sanitize_error
from global_library_mcp.iiif import hocr_title, hocr_to_text, parse_manifest
from global_library_mcp.models import Rights, SearchResult

API_BASE = "https://api.digitale-sammlungen.de"
API_HOST = "api.digitale-sammlungen.de"
_ALLOWED_HOSTS = {API_HOST}
_OBJECT_ID = re.compile(r"^bsb[0-9a-z_]+$", re.I)
_PAGE_ID = re.compile(r"^(bsb[0-9a-z_]+)@([0-9]+)$", re.I)
_IN_DOC_PAGE_CAP = 20
_MANIFEST_TTL_S = 3600.0
_MANIFEST_CACHE_MAX = 32
_PAGE_TTL_S = 3600.0
_PAGE_CACHE_MAX = 64
_MIN_REQUEST_INTERVAL_S = 0.34  # conservative local pacing for the rate-limited OCR/Image APIs; NOT an official MDZ figure


def _segments(url: str) -> list[str]:
    return [seg for seg in urlparse(url or "").path.split("/") if seg]


def _rights_classification(license_url: str | None) -> str:
    """Classify a rights URI without conflating distinct things:
    a Public Domain Mark is not CC0, and NoC-NC is a contractual
    non-commercial restriction, not a copyright expiry finding."""
    if not license_url:
        return "unknown"
    url = license_url.lower()
    if "publicdomain/zero" in url or "/cc0/" in url or url.rstrip("/").endswith("cc0"):
        return "cc0"
    if "publicdomain/mark" in url:
        return "public-domain-mark"
    if "/vocab/noc-nc/" in url:
        return "rightsstatements-noc-nc-noncommercial"
    if "/vocab/" in url:
        return "rightsstatements-other"
    if "creativecommons.org/licenses/" in url:
        return "creative-commons-licence"
    return "other"


class BsbAdapter(LibraryAdapter):
    library_id = "bsb"
    library_name = "Bayerische Staatsbibliothek (MDZ)"
    supports_in_document_search = True  # bounded; coverage is reported

    def __init__(self, client: httpx.AsyncClient):
        super().__init__(client)
        self._manifests: dict[str, tuple[float, Any]] = {}
        self._pages: dict[str, tuple[float, dict[str, Any]]] = {}
        self._now = time.monotonic
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def _pace(self) -> None:
        """Conservative spacing for the per-24h-limited OCR and
        Image APIs (our own operational choice - MDZ publishes no
        numeric cap, and this value is never presented as one)."""
        async with self._rate_lock:
            delay = self._next_request_at - self._now()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = self._now() + _MIN_REQUEST_INTERVAL_S

    # -- helpers -----------------------------------------------------

    def _manifest_url(self, object_id: str) -> str:
        return f"{API_BASE}/iiif/presentation/v2/{object_id}/manifest"

    def _ocr_url(self, object_id: str, page_num: int) -> str:
        return f"{API_BASE}/ocr/{object_id}/{page_num}"

    def landing_url(self, object_id: str) -> str:
        return f"https://www.digitale-sammlungen.de/en/view/{object_id}"

    async def _manifest(self, object_id: str):
        if not _OBJECT_ID.match(object_id or ""):
            raise AdapterError(self.library_id, f"invalid BSB object id: {object_id!r}", retryable=False)
        cached = self._manifests.get(object_id)
        if cached and self._now() - cached[0] < _MANIFEST_TTL_S:
            return cached[1]
        try:
            payload = await get_json(self.client, self._manifest_url(object_id))
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        manifest = parse_manifest(payload)
        if not manifest.canvases:
            raise AdapterError(self.library_id, f"manifest for {object_id} has no canvases", retryable=False)
        self._manifests[object_id] = (self._now(), manifest)
        while len(self._manifests) > _MANIFEST_CACHE_MAX:
            self._manifests.pop(next(iter(self._manifests)))
        return manifest

    @staticmethod
    def _rights(manifest) -> Rights:
        if manifest.license_url:
            tail = manifest.license_url.rstrip("/").rsplit("/", 2)
            statement = "/".join(tail[-2:]) if len(tail) >= 2 else manifest.license_url
            return Rights(
                statement=statement,
                url=manifest.license_url,
                source="IIIF manifest license (MDZ)",
                classification=_rights_classification(manifest.license_url),
            )
        return Rights(statement="unknown", source="no license in IIIF manifest", classification="unknown")

    def _canvas_for(self, manifest, object_id: str, page_num: int):
        if page_num < 1 or page_num > len(manifest.canvases):
            raise AdapterError(
                self.library_id,
                f"page {page_num} out of range 1..{len(manifest.canvases)} for {object_id}",
                retryable=False,
            )
        return manifest.canvases[page_num - 1]

    def _mapping_checks(self, manifest, object_id: str, page_num: int, canvas) -> dict[str, Any]:
        """Structural identity checks (final review S2). Every
        check parses the URL instead of comparing substrings, and
        every check is about THIS object and THIS page."""
        manifest_segments = _segments(manifest.manifest_id or "")
        canvas_segments = _segments(canvas.canvas_id or "")
        service_segments = _segments(canvas.image_service_id or "")
        ocr_link_ok = False
        for link in canvas.ocr_urls:
            parsed = urlparse(link)
            if (parsed.hostname or "") == API_HOST and parsed.path == f"/ocr/{object_id}/{page_num}":
                ocr_link_ok = True
                break
        return {
            "manifest_object_matches": object_id in manifest_segments,
            "canvas_belongs_to_object": object_id in canvas_segments
            and len(canvas_segments) >= 2
            and canvas_segments[-2:] == ["canvas", str(page_num)],
            "image_service_belongs": bool(service_segments)
            and service_segments[-1] == f"{object_id}_{page_num:05d}",
            "ocr_link_in_manifest_matches": ocr_link_ok,
        }

    def _linked_ocr_url(self, canvas, object_id: str, page_num: int) -> str:
        """Fetch the manifest's own OCR link when it is the
        expected one; otherwise fall back to the documented URL
        (the mapping check will already have failed, so the page
        can only ever be unverified research material)."""
        for link in canvas.ocr_urls:
            parsed = urlparse(link)
            if (parsed.hostname or "") == API_HOST and parsed.path == f"/ocr/{object_id}/{page_num}":
                return link
        return self._ocr_url(object_id, page_num)

    # -- adapter API ---------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise AdapterError(
            self.library_id,
            "MDZ offers no official keyword search API (interfaces page, checked 2026-11-25); "
            "BSB is ID-addressed here - discover BSB holdings via DDB, then use get_document with the bsb object id",
            retryable=False,
        )

    async def get_document(self, record_id: str) -> dict[str, Any]:
        manifest = await self._manifest(record_id)
        meta = manifest.metadata
        pages = [
            {
                "page_id": f"{record_id}@{canvas.index + 1}",
                "digital_frame": canvas.index + 1,
                # The canvas label is preserved verbatim but is NOT
                # asserted to be the printed page number (S14).
                "canvas_label": canvas.label,
                "printed_page": "unknown",
                "printed_page_source": "not confirmed by the provider; canvas label kept separately",
                "canvas_id": canvas.canvas_id,
                "image_url": canvas.image_url,
                "ocr_url": canvas.ocr_urls[0] if canvas.ocr_urls else self._ocr_url(record_id, canvas.index + 1),
            }
            for canvas in manifest.canvases[:50]
        ]
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "holding_institution": meta.get("Holding institution") or "Bayerische Staatsbibliothek",
            "title": manifest.label,
            "author": meta.get("Creator"),
            "date": meta.get("Date"),
            "language": meta.get("Language"),
            "publisher": meta.get("Published"),
            "landing_url": self.landing_url(record_id),
            "iiif_manifest_url": self._manifest_url(record_id),
            "page_count": len(manifest.canvases),
            "pages": pages,
            "pages_listed": len(pages),
            "rights": asdict(self._rights(manifest)),
            "source_protocol": "IIIF Presentation API 2 (MDZ)",
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        match = _PAGE_ID.match(page_id or "")
        if not match:
            raise AdapterError(self.library_id, f"invalid BSB page id: {page_id!r} (expected bsb...@N)", retryable=False)
        object_id, page_num = match.group(1), int(match.group(2))
        cached = self._pages.get(page_id)
        if cached and self._now() - cached[0] < _PAGE_TTL_S:
            return dict(cached[1])
        manifest = await self._manifest(object_id)
        canvas = self._canvas_for(manifest, object_id, page_num)
        checks = self._mapping_checks(manifest, object_id, page_num, canvas)
        ocr_url = self._linked_ocr_url(canvas, object_id, page_num)
        await self._pace()
        ocr_fetched = False
        fetch_error: str | None = None
        text: str | None = None
        title_value: str | None = None
        try:
            response = await fetch_validated(self.client, ocr_url, allowed_hosts=_ALLOWED_HOSTS)
            if response.status_code == 429:
                raise AdapterError(self.library_id, "MDZ rate limit (429) on the OCR API; stopped", retryable=False)
            response.raise_for_status()
            hocr = response.text
            ocr_fetched = True
            title_value = hocr_title(hocr)
            text = hocr_to_text(hocr) or None
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            fetch_error = sanitize_error(exc)
        checks["hocr_title_matches"] = title_value == f"{object_id}_{page_num:05d}"
        checks["ocr_fetched"] = ocr_fetched
        verified = bool(
            checks["manifest_object_matches"]
            and checks["canvas_belongs_to_object"]
            and checks["image_service_belongs"]
            and checks["ocr_link_in_manifest_matches"]
            and checks["hocr_title_matches"]
        )
        result = {
            "library_id": self.library_id,
            "page_id": page_id,
            "record_id": object_id,
            "digital_frame": page_num,
            "canvas_label": canvas.label,
            "printed_page": "unknown",
            "printed_page_source": "not confirmed by the provider; canvas label kept separately",
            "contents": text,
            "ocr_source": ocr_url,
            "ocr_format": "hOCR (MDZ OCR API)",
            "ocr_fetched": ocr_fetched,
            "ocr_nonempty": bool(text and text.strip()),
            "page_identity_verified": verified,
            "ocr_fetch_error": fetch_error,
            "image_url": canvas.image_url,
            "image_service_id": canvas.image_service_id,
            "canvas_id": canvas.canvas_id,
            "verified_mapping": verified,
            "mapping_checks": checks,
            "landing_url": self.landing_url(object_id),
            "rights": asdict(self._rights(manifest)),
        }
        if ocr_fetched:
            self._pages[page_id] = (self._now(), dict(result))
            while len(self._pages) > _PAGE_CACHE_MAX:
                self._pages.pop(next(iter(self._pages)))
        return result

    async def search_in_document(
        self,
        record_id: str,
        query: str,
        limit: int = 20,
        *,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> dict[str, Any]:
        """Bounded in-document search in the common result schema
        (final review S7/S8): MDZ has no full-text search API, so
        pages are fetched sequentially inside an explicit page
        window (default the first 20 pages; callers may pass a
        start/end window, still capped at 20 pages per call).
        Partial results are kept and reported when a fetch fails
        or the HTTP budget runs out mid-window - the search is
        never reported complete for pages it did not read."""
        manifest = await self._manifest(record_id)
        total = len(manifest.canvases)
        first = max(1, int(start_page or 1))
        last = min(total, int(end_page) if end_page else total, first + _IN_DOC_PAGE_CAP - 1)
        needle = (query or "").strip().lower()
        matches: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        searched = 0
        stopped_reason: str | None = None
        for page_num in range(first, last + 1):
            try:
                page = await self.get_page_text(f"{record_id}@{page_num}")
            except AdapterError as exc:
                failures.append({"page": page_num, "error": str(exc)[:200]})
                stopped_reason = "fetch_failed"
                break
            except Exception as exc:  # noqa: BLE001 - budget exhaustion lands here too
                failures.append({"page": page_num, "error": sanitize_error(exc)[:200]})
                stopped_reason = "budget_or_transport"
                break
            searched += 1
            if not page.get("ocr_fetched"):
                failures.append({"page": page_num, "error": page.get("ocr_fetch_error") or "OCR not available for this page"})
                continue
            text = page.get("contents") or ""
            idx = text.lower().find(needle) if needle else -1
            if idx >= 0:
                matches.append(
                    {
                        "id": page["page_id"],
                        "page_id": page["page_id"],
                        "record_id": record_id,
                        "match_id": f"{record_id}@{page_num}#{len(matches) + 1}",
                        "snippet": text[max(0, idx - 60) : idx + len(needle) + 60],
                        "score": None,
                        "digital_frame": page_num,
                        "printed_page": page["printed_page"],
                        "mapping_status": "verified" if page["verified_mapping"] else "unverified",
                        "verified_mapping": page["verified_mapping"],
                    }
                )
                if len(matches) >= limit:
                    stopped_reason = "hit_limit"
                    break
        window_complete = stopped_reason is None and not failures and searched >= (last - first + 1)
        covered_all = first == 1 and last >= total and not failures and stopped_reason is None
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "query": query,
            "matches": {"list": matches},
            "hits": matches,  # b5 name kept for readers of the first candidate
            "pages_searched": searched,
            "total_pages": total,
            "searched_range": [first, last],
            "complete": covered_all,
            "window_complete": window_complete and not failures,
            "partial_failures": failures,
            "stopped_reason": stopped_reason,
            "note": (
                "Bounded sequential OCR search (no MDZ full-text search API); "
                f"coverage pages {first}-{last} of {total}. 'No match' refers to the searched range only."
            ),
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        match = _PAGE_ID.match(page_id or "")
        if not match:
            raise AdapterError(self.library_id, f"invalid BSB page id: {page_id!r}", retryable=False)
        object_id, page_num = match.group(1), int(match.group(2))
        # The SAME page result get_page_text produces - the two
        # entry points can therefore never disagree (S3).
        page = await self.get_page_text(page_id)
        checks_in = page.get("mapping_checks") or {}
        image_ok = False
        image_detail = "no image service on canvas"
        service_id = page.get("image_service_id")
        if service_id:
            # A small IIIF rendition, not the full original: enough
            # to prove the service serves THIS page's image.
            image_url = f"{service_id}/full/!256,256/0/default.jpg"
            await self._pace()
            try:
                from global_library_mcp.http import get_within_domain, validate_fetch_url

                validate_fetch_url(image_url, allowed_hosts=_ALLOWED_HOSTS)
                response = await get_within_domain(self.client, image_url)
                body = response.content or b""
                content_type = (response.headers.get("content-type") or "").lower()
                image_ok = response.status_code in (200, 206) and response_looks_like_image(body, content_type)
                image_detail = (
                    f"IIIF image GET status {response.status_code}, content-type {content_type or 'none'}, "
                    f"{len(body)} bytes, image signature {'ok' if image_ok else 'not an image'}"
                )
            except Exception as exc:  # noqa: BLE001
                image_detail = sanitize_error(exc)
        verified = bool(page.get("verified_mapping") and image_ok)
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "status": "verified" if verified else "unverified",
            "checks": {
                "document_identity": {"ok": bool(checks_in.get("manifest_object_matches")), "detail": object_id},
                "page_identity": {
                    "ok": bool(checks_in.get("canvas_belongs_to_object")),
                    "detail": page.get("canvas_id") or "",
                },
                "ocr_fetched": {"ok": bool(page.get("ocr_fetched")), "detail": page.get("ocr_fetch_error") or "hOCR retrieved"},
                "ocr_mapping_verified": {
                    "ok": bool(page.get("verified_mapping")),
                    "detail": str({k: v for k, v in checks_in.items()}),
                },
                "image_service_identity": {"ok": bool(checks_in.get("image_service_belongs")), "detail": service_id or ""},
                "image_reachable": {"ok": image_ok, "detail": image_detail},
            },
            "image_url": page.get("image_url"),
            "landing_url": self.landing_url(object_id),
        }
