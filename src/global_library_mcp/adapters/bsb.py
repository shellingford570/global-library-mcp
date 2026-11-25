"""Bayerische Staatsbibliothek / Munich Digitization Center
(BSB/MDZ) adapter (b5, section 4).

Access model, per the official MDZ interfaces documentation
(https://www.digitale-sammlungen.de/en/interfaces, checked
2026-11-25):

- IIIF Presentation API 2 manifests:
  ``https://api.digitale-sammlungen.de/iiif/presentation/v2/{object_id}/manifest``
- IIIF Image API 2 services linked from each canvas.
- Per-page OCR (hOCR):
  ``https://api.digitale-sammlungen.de/ocr/{object_id}/{page_num}``
  where ``page_num`` is the 1-based canvas number; each canvas
  also links its OCR under ``seeAlso`` when present.

The interfaces documentation offers NO keyword search API, so
this adapter is ID-addressed: bibliographic discovery of BSB
holdings runs through the DDB aggregator, and this adapter
resolves a known object id (``bsb...``) to its manifest, page
OCR, original images, citation and rights. Claiming a search
capability that does not officially exist would be fabrication.

Page mapping is proven, never guessed: for page ``n`` the
manifest canvas ``.../canvas/{n}``, its image service id
suffix ``_{n:05d}``, the documented OCR URL ``/ocr/{id}/{n}``
and the hOCR payload's own title (``{id}_{n:05d}``) must all
agree before ``verified_mapping`` is true.

MDZ rate-limits OCR downloads and Image API requests per 24h
(Presentation API is unlimited), so manifests are cached and
in-document search is hard-bounded with explicit coverage.
"""

from __future__ import annotations

import re
from dataclasses import asdict
import time
from typing import Any

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json, sanitize_error
from global_library_mcp.iiif import hocr_to_text, parse_manifest
from global_library_mcp.models import Rights, SearchResult

API_BASE = "https://api.digitale-sammlungen.de"
_OBJECT_ID = re.compile(r"^bsb[0-9a-z_]+$", re.I)
_PAGE_ID = re.compile(r"^(bsb[0-9a-z_]+)@([0-9]+)$", re.I)
_IN_DOC_PAGE_CAP = 20
_MANIFEST_TTL_S = 3600.0
_MANIFEST_CACHE_MAX = 32


class BsbAdapter(LibraryAdapter):
    library_id = "bsb"
    library_name = "Bayerische Staatsbibliothek (MDZ)"
    supports_in_document_search = True  # bounded; coverage is reported

    def __init__(self, client: httpx.AsyncClient):
        super().__init__(client)
        self._manifests: dict[str, tuple[float, Any]] = {}
        self._now = time.monotonic

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
            return Rights(statement=statement, url=manifest.license_url, source="IIIF manifest license (MDZ)")
        return Rights(statement="unknown", source="no license in IIIF manifest")

    @staticmethod
    def _printed_page(label: str | None) -> str:
        if not label:
            return "unknown"
        head = label.split("(")[0].strip()
        return head or "unknown"

    def _canvas_for(self, manifest, object_id: str, page_num: int):
        if page_num < 1 or page_num > len(manifest.canvases):
            raise AdapterError(
                self.library_id,
                f"page {page_num} out of range 1..{len(manifest.canvases)} for {object_id}",
                retryable=False,
            )
        return manifest.canvases[page_num - 1]

    def _mapping_checks(self, manifest, object_id: str, page_num: int, canvas) -> dict[str, bool]:
        canvas_ok = canvas.canvas_id.rstrip("/").endswith(f"/canvas/{page_num}")
        service_ok = bool(canvas.image_service_id) and canvas.image_service_id.endswith(f"_{page_num:05d}")
        ocr_url = self._ocr_url(object_id, page_num)
        ocr_linked = ocr_url in canvas.ocr_urls if canvas.ocr_urls else None
        return {
            "canvas_id_matches": canvas_ok,
            "image_service_matches": service_ok,
            "ocr_link_in_manifest": bool(ocr_linked) if ocr_linked is not None else False,
            "ocr_url_documented_pattern": True,  # /ocr/{id}/{page} is the documented MDZ pattern
            "_ocr_url": ocr_url,  # type: ignore[dict-item]
        }

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
                "printed_page": self._printed_page(canvas.label),
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
        manifest = await self._manifest(object_id)
        canvas = self._canvas_for(manifest, object_id, page_num)
        checks = self._mapping_checks(manifest, object_id, page_num, canvas)
        ocr_url = checks.pop("_ocr_url")
        try:
            response = await self.client.get(ocr_url)
            response.raise_for_status()
            hocr = response.text
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        title_ok = f"{object_id}_{page_num:05d}" in hocr[:600]
        checks["hocr_title_matches"] = title_ok
        verified = bool(checks["canvas_id_matches"] and checks["image_service_matches"] and title_ok)
        text = hocr_to_text(hocr)
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "record_id": object_id,
            "digital_frame": page_num,
            "printed_page": self._printed_page(canvas.label),
            "contents": text or None,
            "ocr_source": ocr_url,
            "ocr_format": "hOCR (MDZ OCR API)",
            "image_url": canvas.image_url,
            "canvas_id": canvas.canvas_id,
            "verified_mapping": verified,
            "mapping_checks": checks,
            "landing_url": self.landing_url(object_id),
            "rights": asdict(self._rights(manifest)),
        }

    async def search_in_document(self, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        """Bounded in-document search: MDZ has no full-text search
        API, so pages are fetched sequentially up to a hard cap
        and the coverage is reported - never presented as a
        complete search of a longer work."""
        manifest = await self._manifest(record_id)
        total = len(manifest.canvases)
        needle = (query or "").strip().lower()
        hits: list[dict[str, Any]] = []
        searched = 0
        for page_num in range(1, min(total, _IN_DOC_PAGE_CAP) + 1):
            page = await self.get_page_text(f"{record_id}@{page_num}")
            searched += 1
            text = page.get("contents") or ""
            idx = text.lower().find(needle) if needle else -1
            if idx >= 0:
                hits.append(
                    {
                        "page_id": page["page_id"],
                        "digital_frame": page_num,
                        "printed_page": page["printed_page"],
                        "snippet": text[max(0, idx - 60) : idx + len(needle) + 60],
                        "verified_mapping": page["verified_mapping"],
                    }
                )
                if len(hits) >= limit:
                    break
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "query": query,
            "hits": hits,
            "pages_searched": searched,
            "total_pages": total,
            "complete": searched >= total,
            "note": (
                "Bounded sequential OCR search (no MDZ full-text search API); "
                f"coverage {searched}/{total} pages."
            ),
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        match = _PAGE_ID.match(page_id or "")
        if not match:
            raise AdapterError(self.library_id, f"invalid BSB page id: {page_id!r}", retryable=False)
        object_id, page_num = match.group(1), int(match.group(2))
        manifest = await self._manifest(object_id)
        canvas = self._canvas_for(manifest, object_id, page_num)
        checks = self._mapping_checks(manifest, object_id, page_num, canvas)
        checks.pop("_ocr_url", None)
        image_ok = False
        detail = "no image url on canvas"
        if canvas.image_url:
            try:
                response = await self.client.get(canvas.image_url, headers={"Range": "bytes=0-1023"})
                image_ok = response.status_code in (200, 206)
                detail = f"image GET status {response.status_code}"
            except Exception as exc:  # noqa: BLE001
                detail = sanitize_error(exc)
        verified = bool(checks["canvas_id_matches"] and checks["image_service_matches"] and image_ok)
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "status": "verified" if verified else "unverified",
            "checks": {
                "canvas_id_matches": {"ok": checks["canvas_id_matches"], "detail": canvas.canvas_id},
                "image_service_matches": {"ok": checks["image_service_matches"], "detail": canvas.image_service_id or ""},
                "image_reachable": {"ok": image_ok, "detail": detail},
            },
            "image_url": canvas.image_url,
            "landing_url": self.landing_url(object_id),
        }
