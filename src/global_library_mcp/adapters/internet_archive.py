from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import get_json, sanitize_error
from global_library_mcp.models import Rights, SearchResult

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InternetArchiveAdapter(LibraryAdapter):
    library_id = "internet-archive"
    library_name = "Internet Archive"
    base_url = "https://archive.org"
    supports_in_document_search = True

    def __init__(self, client):
        super().__init__(client)
        self._metadata_cache: dict[str, dict[str, Any]] = {}
        self._pages_cache: dict[str, list[str]] = {}

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = await get_json(self.client, f"{self.base_url}/advancedsearch.php", params={
                "q": query,
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
        if identifier not in self._metadata_cache:
            payload = await get_json(self.client, f"{self.base_url}/metadata/{identifier}", attempts=1)
            if not isinstance(payload, dict) or not payload.get("metadata"):
                raise AdapterError(self.library_id, f"Internet Archive item not found: {identifier}")
            self._metadata_cache[identifier] = payload
        return self._metadata_cache[identifier]

    @staticmethod
    def _is_restricted(metadata_payload: dict[str, Any]) -> bool:
        return bool((metadata_payload.get("metadata") or {}).get("access-restricted-item"))

    @staticmethod
    def _has_file(metadata_payload: dict[str, Any], suffix: str) -> bool:
        return any(str(f.get("name", "")).endswith(suffix) for f in metadata_payload.get("files", []) if isinstance(f, dict))

    async def _pages(self, identifier: str) -> list[str]:
        """Fetch the item's djvu.txt OCR and split it into leaf pages.

        The djvu text file separates scanned leaves with form feeds, so
        page index == leaf number, the same index the BookReader page
        images use. Restricted items are refused here, per item-level
        access conditions.
        """
        identifier = self._safe_id(identifier)
        if identifier in self._pages_cache:
            return self._pages_cache[identifier]
        payload = await self._metadata(identifier)
        if self._is_restricted(payload):
            raise AdapterError(self.library_id, f"Item {identifier} is access-restricted; full text is not public")
        if not self._has_file(payload, "_djvu.txt"):
            raise AdapterError(self.library_id, f"Item {identifier} has no public djvu.txt OCR file")
        response = await self.client.get(f"{self.base_url}/download/{identifier}/{identifier}_djvu.txt", follow_redirects=True)
        response.raise_for_status()
        pages = response.text.split("\f")
        self._pages_cache[identifier] = pages
        return pages

    async def get_document(self, record_id: str) -> dict[str, Any]:
        identifier = self._safe_id(record_id)
        payload = await self._metadata(identifier)
        md = payload.get("metadata") or {}
        pages = None
        if not self._is_restricted(payload) and self._has_file(payload, "_djvu.txt"):
            try:
                pages = len(await self._pages(identifier))
            except Exception:  # noqa: BLE001 - page count is informational here
                pages = None
        return {
            "library_id": self.library_id,
            "record_id": identifier,
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
        return {
            "library_id": self.library_id,
            "record_id": identifier,
            "query": query,
            "matches": {"list": matches, "hit": len(matches)},
            "source": "local search over the item's public djvu.txt OCR (Internet Archive)",
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        identifier, leaf = self._parse_page_id(page_id)
        pages = await self._pages(identifier)
        in_range = 0 <= leaf < len(pages)
        contents = pages[leaf] if in_range else ""
        verified = in_range and bool(contents.strip())
        return {
            "library_id": self.library_id,
            "page_id": self.page_id_for(identifier, leaf),
            "record_id": identifier,
            "book_pid": identifier,
            "digital_frame": leaf,
            "printed_page": "unknown",
            "contents": contents,
            "ocr_source": "djvu.txt",
            "image_url": self.image_url(identifier, leaf),
            "page_count": len(pages),
            "source": f"{self.base_url}/download/{identifier}/{identifier}_djvu.txt",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "rights": {"statement": "item-specific; verify at the item page", "source": f"{self.base_url}/details/{identifier}"},
            "verified_mapping": verified,
        }

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        identifier, leaf = self._parse_page_id(page_id)
        checks: dict[str, dict[str, Any]] = {}
        pages: list[str] = []
        try:
            payload = await self._metadata(identifier)
            checks["metadata"] = {"ok": True, "detail": f"item {identifier} found"}
            restricted = self._is_restricted(payload)
            checks["access"] = {"ok": not restricted, "detail": "access-restricted item" if restricted else "public item"}
            has_djvu = self._has_file(payload, "_djvu.txt")
            checks["djvu_present"] = {"ok": has_djvu, "detail": "djvu.txt present" if has_djvu else "no djvu.txt file"}
            if has_djvu and not restricted:
                pages = await self._pages(identifier)
        except Exception as exc:  # noqa: BLE001 - recorded as failed checks
            checks["metadata"] = {"ok": False, "detail": sanitize_error(exc)}
            checks["access"] = {"ok": False, "detail": "metadata unavailable"}
            checks["djvu_present"] = {"ok": False, "detail": "metadata unavailable"}
        in_range = bool(pages) and 0 <= leaf < len(pages)
        checks["page_in_range"] = {"ok": in_range, "detail": f"leaf {leaf} of {len(pages)} pages" if pages else "page list unavailable"}
        ocr_ok = in_range and bool(pages[leaf].strip())
        checks["ocr_present"] = {"ok": ocr_ok, "detail": f"{len(pages[leaf]) if in_range else 0} OCR characters on this leaf"}
        image_url = self.image_url(identifier, leaf)
        try:
            response = await self.client.get(image_url, headers={"Range": "bytes=0-1023"}, follow_redirects=True)
            content_type = response.headers.get("content-type", "")
            ok = response.status_code in (200, 206) and content_type.startswith("image/")
            checks["image_reachable"] = {"ok": ok, "detail": f"HTTP {response.status_code}, {content_type}, {len(response.content)} bytes (range)"}
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            checks["image_reachable"] = {"ok": False, "detail": sanitize_error(exc)}
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
            "ocr_excerpt": (pages[leaf][:200] if in_range else ""),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
