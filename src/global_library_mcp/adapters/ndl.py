from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.models import Rights, SearchResult


class NdlAdapter(LibraryAdapter):
    library_id = "ndl"
    library_name = "National Diet Library / 次世代デジタルライブラリー"
    base_url = "https://lab.ndl.go.jp/dl"
    image_base = "https://dl.ndl.go.jp/api/iiif"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        # The Next Digital Library Book API searches bibliographic fields and OCR text.
        response = await self.client.get(
            f"{self.base_url}/api/book/search",
            params={"keyword": query, "size": min(max(limit, 1), 20)},
        )
        response.raise_for_status()
        payload = response.json()
        return [self._book_result(item, query) for item in payload.get("list", [])]

    def _book_result(self, item: dict[str, Any], query: str = "") -> SearchResult:
        pid = str(item.get("id") or "unknown")
        landing = f"https://dl.ndl.go.jp/pid/{pid}"
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=pid,
            title=item.get("title") or "Untitled",
            author=item.get("responsibility"),
            date=str(item.get("published")) if item.get("published") else None,
            description="; ".join(str(value) for value in item.get("highlights", [])[:3]) or None,
            landing_url=landing,
            fulltext_status="available" if item.get("highlights") else "unknown",
            rights=Rights(statement="著作権保護期間満了資料を中心とする。資料単位で確認", url="https://lab.ndl.go.jp/service/tsugidigi/apiinfo/", source=landing),
            source_protocol="NDL Next Digital Library Book API",
            raw={"pid": pid, "query": query, "book": item},
        )

    async def get_document(self, record_id: str) -> dict[str, Any]:
        pid = self._safe_pid(record_id)
        response = await self.client.get(f"{self.base_url}/api/book/{pid}")
        response.raise_for_status()
        book = response.json()
        return {
            "library_id": self.library_id,
            "record_id": pid,
            "book": book,
            "landing_url": f"https://dl.ndl.go.jp/pid/{pid}",
            "fulltext_json_url": f"{self.base_url}/api/book/fulltext-json/{pid}",
            "rights": {"statement": "資料単位で確認; NDL APIの対象は公開可能資料", "source": "https://lab.ndl.go.jp/service/tsugidigi/apiinfo/"},
            "iiif_image_template": f"{self.image_base}/{pid}/R{{page:07d}}/full/full/0/default.jpg",
        }

    async def search_in_document(self, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        pid = self._safe_pid(record_id)
        response = await self.client.get(
            f"{self.base_url}/api/page/search",
            params={"f-book": pid, "q-contents": query, "size": min(max(limit, 1), 100), "searchfield": "contentonly"},
        )
        response.raise_for_status()
        return {"library_id": self.library_id, "record_id": pid, "query": query, "matches": response.json(), "source": "NDL Page API"}

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        safe_page_id = self._safe_page_id(page_id)
        response = await self.client.get(f"{self.base_url}/api/page/{safe_page_id}")
        response.raise_for_status()
        page = response.json()
        book = str(page.get("book") or safe_page_id.rsplit("_", 1)[0])
        page_number = int(page.get("page") or safe_page_id.rsplit("_", 1)[-1])
        coordjson = page.get("coordjson")
        ocr_text = page.get("contents")
        if not ocr_text and coordjson:
            try:
                import json
                tokens = json.loads(coordjson)
                ocr_text = " ".join(str(token.get("contenttext", "")) for token in tokens if token.get("contenttext"))
            except (TypeError, ValueError):
                ocr_text = None
        return {
            "library_id": self.library_id,
            "page_id": safe_page_id,
            "book_pid": book,
            "digital_frame": page_number,
            "printed_page": "unknown",
            "contents": ocr_text,
            "coordjson": coordjson,
            "highlights": page.get("highlights", []),
            "image_url": self.image_url(book, page_number),
            "source": "NDL Page API",
            "verified_mapping": bool(page.get("id") and (ocr_text is not None or coordjson is not None)),
        }

    @staticmethod
    def image_url(book_pid: str, page: int) -> str:
        if not book_pid.isdigit():
            raise AdapterError("ndl", "NDL PID must contain digits only")
        return f"https://dl.ndl.go.jp/api/iiif/{book_pid}/R{int(page):07d}/full/full/0/default.jpg"

    @staticmethod
    def _safe_pid(value: str) -> str:
        if not value.isdigit():
            raise AdapterError("ndl", "NDL PID must contain digits only")
        return value

    @classmethod
    def _safe_page_id(cls, value: str) -> str:
        parts = value.split("_", 1)
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise AdapterError("ndl", "NDL page ID must be PID_page")
        return f"{parts[0]}_{int(parts[1])}"
