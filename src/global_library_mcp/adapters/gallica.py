from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import sanitize_error
from global_library_mcp.models import Rights, SearchResult

_ARK_RE = re.compile(r"ark:/12148/([A-Za-z0-9]+)")
_BARE_ARK_RE = re.compile(r"^[A-Za-z0-9]+$")


class GallicaAdapter(LibraryAdapter):
    """Gallica / BnF adapter.

    Search uses the SRU API. Page text uses the official per-page
    "texteBrut" view and original verification uses Gallica's IIIF
    manifest and image service. In-document search is not offered by
    an official Gallica API, so it stays unsupported here.

    Live-verification caveat (2026-11-22): from the development
    network, gallica.bnf.fr answers HTTP 403 (bot/policy protection)
    for search and page routes alike. The page methods are therefore
    implemented and unit-tested but not live-verified; no
    access-limit evasion is attempted.
    """

    library_id = "gallica"
    library_name = "Gallica / Bibliothèque nationale de France"

    def __init__(self, client):
        super().__init__(client)
        self._manifest_cache: dict[str, dict[str, Any]] = {}

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

    # --- page-level access ------------------------------------------------

    @staticmethod
    def _extract_ark(record_id: str) -> str:
        match = _ARK_RE.search(record_id or "")
        if match:
            return match.group(1)
        if _BARE_ARK_RE.match(record_id or ""):
            return record_id
        raise AdapterError("gallica", "Gallica record ID does not contain an ARK identifier")

    @classmethod
    def _parse_page_id(cls, page_id: str) -> tuple[str, int]:
        ark, sep, page = (page_id or "").rpartition("@")
        if not sep or not page.isdigit() or int(page) < 1:
            raise AdapterError("gallica", "Gallica page ID must be ark@page (1-based)")
        return cls._extract_ark(ark), int(page)

    @staticmethod
    def image_url(ark: str, page: int) -> str:
        return f"https://gallica.bnf.fr/iiif/ark:/12148/{ark}/f{page}/full/full/0/native.jpg"

    @staticmethod
    def manifest_url(ark: str) -> str:
        return f"https://gallica.bnf.fr/iiif/ark:/12148/{ark}/manifest.json"

    async def _get(self, url: str):
        response = await self.client.get(url, follow_redirects=True)
        if response.status_code == 403:
            raise AdapterError(self.library_id, "Upstream access denied (403; challenge or policy restriction)")
        response.raise_for_status()
        return response

    async def _manifest(self, ark: str) -> dict[str, Any]:
        if ark not in self._manifest_cache:
            response = await self._get(self.manifest_url(ark))
            self._manifest_cache[ark] = response.json()
        return self._manifest_cache[ark]

    @staticmethod
    def _canvases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
        sequences = manifest.get("sequences") or []
        if sequences and isinstance(sequences[0], dict):
            return sequences[0].get("canvases") or []
        return []

    async def get_document(self, record_id: str) -> dict[str, Any]:
        ark = self._extract_ark(record_id)
        manifest = await self._manifest(ark)
        canvases = self._canvases(manifest)
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "ark": ark,
            "title": manifest.get("label"),
            "landing_url": f"https://gallica.bnf.fr/ark:/12148/{ark}",
            "page_count": len(canvases) or None,
            "page_id_format": "ark@page (1-based, Gallica f-number)",
            "rights": {"statement": "BnF/item-specific; verify Gallica terms", "source": f"https://gallica.bnf.fr/ark:/12148/{ark}"},
            "source": "Gallica IIIF manifest",
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        ark, page = self._parse_page_id(page_id)
        response = await self._get(f"https://gallica.bnf.fr/ark:/12148/{ark}/f{page}.texteBrut")
        contents = response.text
        return {
            "library_id": self.library_id,
            "page_id": f"{ark}@{page}",
            "record_id": f"https://gallica.bnf.fr/ark:/12148/{ark}",
            "book_pid": ark,
            "digital_frame": page,
            "printed_page": "unknown",
            "contents": contents,
            "ocr_source": "texteBrut",
            "image_url": self.image_url(ark, page),
            "source": f"https://gallica.bnf.fr/ark:/12148/{ark}/f{page}.texteBrut",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "rights": {"statement": "BnF/item-specific; verify Gallica terms", "source": f"https://gallica.bnf.fr/ark:/12148/{ark}"},
            "verified_mapping": bool(contents.strip()),
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        ark, page = self._parse_page_id(page_id)
        checks: dict[str, dict[str, Any]] = {}
        canvases: list[dict[str, Any]] = []
        try:
            manifest = await self._manifest(ark)
            canvases = self._canvases(manifest)
            checks["manifest"] = {"ok": bool(canvases), "detail": f"{len(canvases)} canvases"}
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            checks["manifest"] = {"ok": False, "detail": f"{type(exc).__name__}: {sanitize_error(exc)}"}
        canvas_ok = any(
            f"/f{page}/" in str(canvas.get("@id", "")) or str(canvas.get("@id", "")).endswith(f"/f{page}")
            for canvas in canvases if isinstance(canvas, dict))
        checks["canvas"] = {"ok": canvas_ok, "detail": f"canvas f{page} present" if canvas_ok else f"canvas f{page} not found"}
        ocr_excerpt = ""
        try:
            page_data = await self.get_page_text(page_id)
            ocr_ok = bool(page_data["contents"].strip())
            ocr_excerpt = page_data["contents"][:200]
            checks["ocr_present"] = {"ok": ocr_ok, "detail": f"{len(page_data['contents'])} OCR characters (texteBrut)"}
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            checks["ocr_present"] = {"ok": False, "detail": f"{type(exc).__name__}: {sanitize_error(exc)}"}
        image_url = self.image_url(ark, page)
        try:
            response = await self.client.get(image_url, headers={"Range": "bytes=0-1023"}, follow_redirects=True)
            if response.status_code == 403:
                raise AdapterError(self.library_id, "Upstream access denied (403; challenge or policy restriction)")
            content_type = response.headers.get("content-type", "")
            ok = response.status_code in (200, 206) and content_type.startswith("image/")
            checks["image_reachable"] = {"ok": ok, "detail": f"HTTP {response.status_code}, {content_type}, {len(response.content)} bytes (range)"}
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            checks["image_reachable"] = {"ok": False, "detail": f"{type(exc).__name__}: {sanitize_error(exc)}"}
        verified = all(check["ok"] for check in checks.values())
        return {
            "library_id": self.library_id,
            "record_id": f"https://gallica.bnf.fr/ark:/12148/{ark}",
            "page_id": f"{ark}@{page}",
            "digital_frame": page,
            "printed_page": "unknown",
            "status": "verified" if verified else "failed",
            "checks": checks,
            "manifest_url": self.manifest_url(ark),
            "canvas_id": None,
            "image_url": image_url,
            "landing_url": f"https://gallica.bnf.fr/ark:/12148/{ark}",
            "ocr_excerpt": ocr_excerpt,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
