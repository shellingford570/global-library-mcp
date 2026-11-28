from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json, sanitize_error, get_within_domain
from global_library_mcp.models import Rights, SearchResult

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InternetArchiveAdapter(LibraryAdapter):
    library_id = "internet-archive"
    library_name = "Internet Archive"
    base_url = "https://archive.org"
    supports_in_document_search = True

    def __init__(self, client):
        super().__init__(client)
        # b3.1 (Section 8): with a shared long-lived service these
        # caches persist, so they are bounded and TTL'd. Metadata
        # (which carries the access-restriction flag) is re-fetched
        # after 300s, and the restriction check runs against that
        # metadata BEFORE cached pages are served, so an item that
        # becomes lending-restricted stops being served from cache.
        import time as _time

        self._now = _time.monotonic
        self._metadata_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._metadata_locks: dict[str, Any] = {}
        self._pages_cache: dict[str, tuple[float, list[str]]] = {}
        self._ocr_sources: dict[str, str] = {}
        # Provenance of the OCR file actually fetched per item:
        # {"name", "format", "url", "file_count", "mapping_confirmed"}.
        self._ocr_files: dict[str, dict[str, Any]] = {}

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        scoped = query if "mediatype:" in query else f"({query}) AND mediatype:texts AND NOT collection:inlibrary"
        payload = await get_json(self.client, f"{self.base_url}/advancedsearch.php", params={
                "q": scoped,
                "fl[]": ["identifier", "title", "creator", "date", "description", "rights", "licenseurl"],
                "rows": min(max(limit, 1), 50),
                "page": 1,
                "output": "json",
            }, attempts=1)
        response = payload.get("response") if isinstance(payload, dict) else None
        docs = response.get("docs", []) if isinstance(response, dict) else None
        if not isinstance(docs, list):
            raise ValueError("Internet Archive response schema changed")
        return [self._result(item) for item in docs if isinstance(item, dict)]

    def _result(self, item: dict[str, Any]) -> SearchResult:
        identifier = str(item.get("identifier") or "unknown")
        title = item.get("title") or identifier
        creator = item.get("creator")
        rights = item.get("rights") or item.get("licenseurl") or "item-specific; verify the item rights and file metadata"
        if isinstance(title, list):
            title = title[0] if title else identifier
        if isinstance(creator, list):
            creator = ", ".join(str(value) for value in creator)
        elif not isinstance(creator, str):
            creator = None
        if isinstance(rights, list):
            rights = "; ".join(str(value) for value in rights)
        if not isinstance(rights, str):
            rights = "item-specific; verify the item rights and file metadata"
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=identifier,
            title=str(title),
            author=creator,
            date=str(item.get("date")) if item.get("date") else None,
            description=item.get("description") if isinstance(item.get("description"), str) else None,
            landing_url=f"{self.base_url}/details/{identifier}",
            rights=Rights(statement=rights, url=item.get("licenseurl") if isinstance(item.get("licenseurl"), str) else None, source=f"{self.base_url}/details/{identifier}"),
            source_protocol="Internet Archive Advanced Search API",
            raw=item,
        )

    # --- page-level OCR (djvu.txt) -------------------------------------

    @staticmethod
    def _safe_id(value: str) -> str:
        if not _ID_RE.match(value or "") or ".." in value:
            raise AdapterError("internet-archive", "Invalid Internet Archive identifier")
        return value

    @classmethod
    def _parse_page_id(cls, page_id: str) -> tuple[str, int]:
        identifier, sep, leaf = (page_id or "").rpartition("@")
        if not sep or not leaf.isdigit():
            raise AdapterError("internet-archive", "IA page ID must be identifier@leaf")
        return cls._safe_id(identifier), int(leaf)

    @staticmethod
    def page_id_for(identifier: str, leaf: int) -> str:
        return f"{identifier}@{leaf}"

    @staticmethod
    def image_url(identifier: str, leaf: int) -> str:
        return f"https://archive.org/download/{identifier}/page/n{int(leaf)}.jpg"

    async def _metadata(self, identifier: str) -> dict[str, Any]:
        identifier = self._safe_id(identifier)
        cached = self._metadata_cache.get(identifier)
        if cached is not None and self._now() - cached[0] < 300:
            return cached[1]
        # Dedupe concurrent fetches of the same item's metadata.
        import asyncio as _asyncio

        lock = self._metadata_locks.setdefault(identifier, _asyncio.Lock())
        async with lock:
            cached = self._metadata_cache.get(identifier)
            if cached is not None and self._now() - cached[0] < 300:
                return cached[1]
            payload = await get_json(self.client, f"{self.base_url}/metadata/{identifier}", attempts=1)
            if not isinstance(payload, dict) or not payload.get("metadata"):
                raise AdapterError(self.library_id, f"Internet Archive item not found: {identifier}")
            self._metadata_cache[identifier] = (self._now(), payload)
            while len(self._metadata_cache) > 128:
                self._metadata_cache.pop(next(iter(self._metadata_cache)))
            while len(self._metadata_locks) > 256:
                self._metadata_locks.pop(next(iter(self._metadata_locks)))
            return payload

    @staticmethod
    def _is_restricted(metadata_payload: dict[str, Any]) -> bool:
        value = (metadata_payload.get("metadata") or {}).get("access-restricted-item")
        return value is True or (isinstance(value, str) and value.lower() == "true")

    @staticmethod
    def _has_file(metadata_payload: dict[str, Any], suffix: str) -> bool:
        return any(str(f.get("name", "")).endswith(suffix) for f in metadata_payload.get("files", []) if isinstance(f, dict))


    @staticmethod
    def _file_name(metadata_payload: dict[str, Any], suffix: str, identifier: str) -> str | None:
        """Resolve the real file name for ``suffix`` from the metadata
        file list. IA items do not always name files
        ``{identifier}_djvu.xml``: multi-volume items carry volume
        suffixes (e.g. ``UBM_1932_01_02_djvu.xml``) and some items' file
        stems differ from the identifier entirely (e.g.
        ``1872_Origin_F391_djvu.xml``). Guessing the name returns 404
        for those items (found live during the Research Beta
        integration checks, 2026-11-24). Prefers the exact
        ``{identifier}{suffix}`` name when present."""
        names = sorted(
            str(f.get("name", ""))
            for f in metadata_payload.get("files", [])
            if isinstance(f, dict)
            and str(f.get("name", "")).endswith(suffix)
            and "/" not in str(f.get("name", ""))
            and "\\" not in str(f.get("name", ""))
            and ".." not in str(f.get("name", ""))
        )
        if not names:
            return None
        exact = f"{identifier}{suffix}"
        return exact if exact in names else names[0]

    @staticmethod
    def _file_count(metadata_payload: dict[str, Any], suffix: str) -> int:
        return sum(
            1
            for f in metadata_payload.get("files", [])
            if isinstance(f, dict) and str(f.get("name", "")).endswith(suffix)
        )

    def _download_url(self, identifier: str, file_name: str) -> str:
        """Build the download URL for a metadata-supplied file name.
        File names are external data: percent-encode everything
        outside the unreserved set so a crafted name cannot inject
        path segments, a query string or a fragment."""
        return f"{self.base_url}/download/{identifier}/{quote(file_name, safe='')}"

    def _record_ocr_file(self, identifier: str, payload: dict[str, Any], name: str, fmt: str) -> None:
        count = self._file_count(payload, "_djvu.xml" if fmt == "djvu.xml" else "_djvu.txt")
        self._ocr_files[identifier] = {
            "name": name,
            "format": fmt,
            "url": self._download_url(identifier, name),
            "file_count": count,
            # The page<->image correspondence is only confirmable when
            # a single OCR file covers the whole item. With several
            # volume files, the first file's leaves cannot be matched
            # to the item-wide BookReader numbering from metadata
            # alone, so the mapping must stay unverified.
            "mapping_confirmed": count == 1,
        }

    async def _pages(self, identifier: str) -> list[str]:
        """Fetch the item's page-level OCR, split by scanned leaf.

        Primary source is djvu.xml: each OBJECT element is one leaf, in
        order, so page index == leaf number == the BookReader page
        image index. djvu.txt is only a fallback, because some items'
        text files contain no form-feed page separators at all (found
        live on hydroelectricdev00koesrich, 2026-11-22). Restricted
        items are refused here, per item-level access conditions.
        """
        identifier = self._safe_id(identifier)
        # Restriction is checked against current (TTL'd) metadata
        # BEFORE any cached pages are served.
        payload = await self._metadata(identifier)
        if self._is_restricted(payload):
            self._pages_cache.pop(identifier, None)
            raise AdapterError(self.library_id, f"Item {identifier} is access-restricted; full text is not public")
        cached_pages = self._pages_cache.get(identifier)
        if cached_pages is not None and self._now() - cached_pages[0] < 3600:
            return cached_pages[1]
        pages: list[str] | None = None
        xml_name = self._file_name(payload, "_djvu.xml", identifier)
        if xml_name:
            response = await get_within_domain(self.client, self._download_url(identifier, xml_name))
            response.raise_for_status()
            pages = self._parse_djvu_xml(response.text)
            self._ocr_sources[identifier] = "djvu.xml"
            self._record_ocr_file(identifier, payload, xml_name, "djvu.xml")
        txt_name = self._file_name(payload, "_djvu.txt", identifier)
        if not pages and txt_name:
            response = await get_within_domain(self.client, self._download_url(identifier, txt_name))
            response.raise_for_status()
            split = response.text.split("\f")
            if len(split) > 1:
                pages = split
                self._ocr_sources[identifier] = "djvu.txt"
                self._record_ocr_file(identifier, payload, txt_name, "djvu.txt")
        if not pages:
            raise AdapterError(self.library_id, f"Item {identifier} has no usable page-level OCR (djvu.xml/djvu.txt)")
        self._pages_cache[identifier] = (self._now(), pages)
        # Bounds: at most 16 items and ~32M characters of OCR.
        while len(self._pages_cache) > 16 or sum(len(pg) for _ts, pgs in self._pages_cache.values() for pg in pgs) > 32_000_000:
            self._pages_cache.pop(next(iter(self._pages_cache)))
        while len(self._ocr_sources) > 128:
            self._ocr_sources.pop(next(iter(self._ocr_sources)))
        while len(self._ocr_files) > 128:
            self._ocr_files.pop(next(iter(self._ocr_files)))
        return pages

    @staticmethod
    def _parse_djvu_xml(xml_text: str) -> list[str]:
        import xml.etree.ElementTree as ET

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        root = ET.fromstring(xml_text)
        pages: list[str] = []
        for obj in root.iter():
            if local(obj.tag) != "OBJECT":
                continue
            lines: list[str] = []
            for line in obj.iter():
                if local(line.tag) != "LINE":
                    continue
                words = [word.text or "" for word in line.iter() if local(word.tag) == "WORD"]
                if words:
                    lines.append(" ".join(words))
            pages.append("\n".join(lines))
        return pages

    async def get_document(self, record_id: str) -> dict[str, Any]:
        identifier = self._safe_id(record_id)
        payload = await self._metadata(identifier)
        md = payload.get("metadata") or {}
        pages = None
        if not self._is_restricted(payload) and (self._has_file(payload, "_djvu.xml") or self._has_file(payload, "_djvu.txt")):
            try:
                pages = len(await self._pages(identifier))
            except Exception:  # noqa: BLE001 - page count is informational here
                pages = None
        return {
            "library_id": self.library_id,
            "record_id": identifier,
            # b10 4.8: identity provenance. The metadata payload
            # is the upstream's own response and carries its own
            # identifier field; only when THAT field equals the
            # requested identifier is the identity confirmed by
            # the upstream rather than echoed from the request.
            "identity_source": "upstream"
            if str(md.get("identifier") or "") == identifier
            else "request_echo",
            "title": md.get("title"),
            "creator": md.get("creator"),
            "date": md.get("date"),
            "landing_url": f"{self.base_url}/details/{identifier}",
            "access_restricted": self._is_restricted(payload),
            "has_djvu_txt": self._has_file(payload, "_djvu.txt"),
            "has_djvu_xml": self._has_file(payload, "_djvu.xml"),
            "page_count": pages,
            "page_id_format": "identifier@leaf (leaf = scanned page index, 0-based)",
            "rights": {"statement": md.get("rights") or md.get("licenseurl") or "item-specific; verify at the item page", "source": f"{self.base_url}/details/{identifier}"},
            "source": "Internet Archive Metadata API",
        }

    async def search_in_document(self, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        identifier = self._safe_id(record_id)
        pages = await self._pages(identifier)
        needle = (query or "").strip().lower()
        matches = []
        if needle:
            for leaf, text in enumerate(pages):
                if needle in text.lower():
                    snippet = text.strip().replace("\n", " ")[:200]
                    matches.append({"id": self.page_id_for(identifier, leaf), "leaf": leaf, "snippet": snippet})
                if len(matches) >= min(max(limit, 1), 100):
                    break
        provenance = self._ocr_files.get(identifier, {})
        fmt = provenance.get("format", self._ocr_sources.get(identifier, "djvu.txt"))
        result: dict[str, Any] = {
            "library_id": self.library_id,
            "record_id": identifier,
            "query": query,
            "matches": {"list": matches, "hit": len(matches)},
            "source": f"local search over the item's public {fmt} OCR (file: {provenance.get('name', 'unknown')}) (Internet Archive)",
            "ocr_file": provenance.get("name"),
            "ocr_format": fmt,
            "mapping_status": "verified" if provenance.get("mapping_confirmed") else "unverified",
        }
        if not provenance.get("mapping_confirmed"):
            result["mapping_note"] = (
                "multi-file item: OCR pages come from the first OCR file and their "
                "correspondence to the item's page images is unverified; see the "
                f"original at {self.base_url}/details/{identifier}"
            )
        return result

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        identifier, leaf = self._parse_page_id(page_id)
        pages = await self._pages(identifier)
        in_range = 0 <= leaf < len(pages)
        contents = pages[leaf] if in_range else ""
        provenance = self._ocr_files.get(identifier, {})
        mapping_confirmed = bool(provenance.get("mapping_confirmed"))
        verified = in_range and bool(contents.strip()) and mapping_confirmed
        result: dict[str, Any] = {
            "library_id": self.library_id,
            "page_id": self.page_id_for(identifier, leaf),
            "record_id": identifier,
            "book_pid": identifier,
            "digital_frame": leaf,
            "printed_page": "unknown",
            "contents": contents,
            "ocr_source": provenance.get("format", self._ocr_sources.get(identifier, "djvu.xml")),
            "ocr_file": provenance.get("name"),
            "image_url": self.image_url(identifier, leaf),
            "page_count": len(pages),
            "source": provenance.get("url", f"{self.base_url}/details/{identifier}"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "rights": {"statement": "item-specific; verify at the item page", "source": f"{self.base_url}/details/{identifier}"},
            "verified_mapping": verified,
            "mapping_status": "verified" if verified else "unverified",
        }
        if not mapping_confirmed:
            result["mapping_note"] = (
                f"multi-file item ({provenance.get('file_count', 0)} OCR files): OCR pages come from "
                f"{provenance.get('name', 'the first OCR file')} and their correspondence to the item's "
                f"page images is unverified; see the original at {self.base_url}/details/{identifier}"
            )
        return result

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        identifier, leaf = self._parse_page_id(page_id)
        checks: dict[str, dict[str, Any]] = {}
        pages: list[str] = []
        try:
            payload = await self._metadata(identifier)
            checks["metadata"] = {"ok": True, "detail": f"item {identifier} found"}
            restricted = self._is_restricted(payload)
            checks["access"] = {"ok": not restricted, "detail": "access-restricted item" if restricted else "public item"}
            has_djvu = self._has_file(payload, "_djvu.xml") or self._has_file(payload, "_djvu.txt")
            checks["djvu_present"] = {"ok": has_djvu, "detail": "djvu OCR files present" if has_djvu else "no djvu OCR files"}
            if has_djvu and not restricted:
                pages = await self._pages(identifier)
        except Exception as exc:  # noqa: BLE001 - recorded as failed checks
            checks["metadata"] = {"ok": False, "detail": f"{type(exc).__name__}: {sanitize_error(exc)}"}
            checks["access"] = {"ok": False, "detail": "metadata unavailable"}
            checks["djvu_present"] = {"ok": False, "detail": "metadata unavailable"}
        in_range = bool(pages) and 0 <= leaf < len(pages)
        checks["page_in_range"] = {"ok": in_range, "detail": f"leaf {leaf} of {len(pages)} pages" if pages else "page list unavailable"}
        provenance = self._ocr_files.get(identifier, {})
        mapping_confirmed = bool(pages) and bool(provenance.get("mapping_confirmed"))
        checks["page_mapping"] = {
            "ok": mapping_confirmed,
            "detail": (
                f"single OCR file ({provenance.get('name')}); leaf order matches the item's page images"
                if mapping_confirmed
                else f"multi-file item ({provenance.get('file_count', 0)} OCR files) or pages unavailable; page-to-image correspondence unverified"
            ),
        }
        ocr_ok = in_range and bool(pages[leaf].strip())
        checks["ocr_present"] = {"ok": ocr_ok, "detail": f"{len(pages[leaf]) if in_range else 0} OCR characters on this leaf"}
        image_url = self.image_url(identifier, leaf)
        try:
            response = await get_within_domain(self.client, image_url, headers={"Range": "bytes=0-1023"})
            content_type = response.headers.get("content-type", "")
            ok = response.status_code in (200, 206) and content_type.startswith("image/")
            checks["image_reachable"] = {"ok": ok, "detail": f"HTTP {response.status_code}, {content_type}, {len(response.content)} bytes (range)"}
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            checks["image_reachable"] = {"ok": False, "detail": f"{type(exc).__name__}: {sanitize_error(exc)}"}
        verified = all(check["ok"] for check in checks.values())
        return {
            "library_id": self.library_id,
            "record_id": identifier,
            "page_id": self.page_id_for(identifier, leaf),
            "digital_frame": leaf,
            "printed_page": "unknown",
            "status": "verified" if verified else "failed",
            "checks": checks,
            "manifest_url": None,
            "canvas_id": None,
            "image_url": image_url,
            "landing_url": f"{self.base_url}/details/{identifier}",
            "ocr_file": provenance.get("name"),
            "mapping_status": "verified" if verified else "unverified",
            "ocr_excerpt": (pages[leaf][:200] if in_range else ""),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
