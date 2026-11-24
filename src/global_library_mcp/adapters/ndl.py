from __future__ import annotations

import json
from typing import Any
from datetime import datetime, timezone
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
        expected_book, expected_page = safe_page_id.split("_", 1)
        book = str(page.get("book") or expected_book)
        try:
            page_number = int(page.get("page") or expected_page)
        except (TypeError, ValueError) as exc:
            raise AdapterError(self.library_id, "NDL page response has an invalid page number", retryable=False) from exc
        if not book.isdigit() or page_number < 1:
            raise AdapterError(self.library_id, "NDL page response has an invalid book or page", retryable=False)
        coordjson = page.get("coordjson")
        ocr_text = page.get("contents")
        ocr_source = "contents" if isinstance(ocr_text, str) and ocr_text.strip() else None
        if not ocr_source and coordjson:
            try:
                tokens = json.loads(coordjson) if isinstance(coordjson, str) else coordjson
                if isinstance(tokens, list) and all(isinstance(token, dict) for token in tokens):
                    recovered = " ".join(str(token.get("contenttext", "")).strip() for token in tokens if str(token.get("contenttext", "")).strip())
                    if recovered:
                        ocr_text = recovered
                        ocr_source = "coordjson"
            except (TypeError, ValueError, json.JSONDecodeError):
                ocr_text = None
        response_id = page.get("id")
        verified_mapping = response_id == safe_page_id and book == expected_book and page_number == int(expected_page) and bool(ocr_source)
        return {
            "library_id": self.library_id,
            "page_id": safe_page_id,
            "book_pid": book,
            "digital_frame": page_number,
            "printed_page": "unknown",
            "contents": ocr_text,
            "ocr_source": ocr_source or "unknown",
            "coordjson": coordjson,
            "highlights": page.get("highlights", []),
            "image_url": self.image_url(book, page_number),
            "source": f"{self.base_url}/api/page/{safe_page_id}",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "rights": {"statement": "資料単位で確認; OCR・画像の利用条件を原本で確認", "source": f"{self.base_url}/service/tsugidigi/apiinfo/"},
            "verified_mapping": verified_mapping,
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
