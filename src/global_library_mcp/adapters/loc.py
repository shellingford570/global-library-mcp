from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import ResponseCache, get_json
from global_library_mcp.models import Rights, SearchResult


class LocAdapter(LibraryAdapter):
    library_id = "loc"
    library_name = "Library of Congress"

    def __init__(self, client: httpx.AsyncClient, cache: ResponseCache | None = None):
        super().__init__(client)
        self.cache = cache
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._ca_page_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            delay = self._next_request_at - now
            if delay > 0:
                await asyncio.sleep(delay)
            # LoC JSON/YAML API documents 20 requests/minute; use a conservative 3s interval.
            self._next_request_at = time.monotonic() + 3.0

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        await self._wait_for_rate_limit()
        payload = await get_json(
            self.client,
            "https://www.loc.gov/search/",
            params={"q": query, "fo": "json", "c": min(max(limit, 1), 100)},
            cache=self.cache,
        )
        return [self._result(item) for item in payload.get("results", [])]

    # -- Chronicling America (b5, section 5) --------------------

    async def get_document(self, record_id: str) -> dict[str, Any]:
        issue = _CA_ISSUE_ID.match(record_id or "")
        if not issue:
            raise AdapterError(
                self.library_id,
                "LoC document retrieval here covers Chronicling America issues "
                "(record id: <lccn>/<date>/ed-<n>); general LoC items are search-only in this adapter",
                retryable=False,
            )
        await self._wait_for_rate_limit()
        payload = await get_json(self.client, f"https://www.loc.gov/resource/{record_id}/", params={"fo": "json"}, cache=self.cache)
        item = payload.get("item") or {}
        pagination = payload.get("viewer_pagination") or payload.get("pagination") or {}
        rights_text = _strip_html(" ".join(item.get("rights_advisory") or []))
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "holding_institution": "Library of Congress",
            "title": item.get("title"),
            "date": item.get("date") or issue.group(2),
            "landing_url": f"https://www.loc.gov/resource/{record_id}/",
            "iiif_manifest_url": (payload.get("resource") or {}).get("iiif_manifest_url"),
            "page_count": pagination.get("total"),
            "rights": {
                "statement": rights_text[:400] if rights_text else "unknown",
                "url": "https://www.loc.gov/homepage/legal.html",
                "source": "item rights_advisory (Chronicling America)",
            },
            "source_protocol": "loc.gov JSON API (Chronicling America)",
            "note": "Newspaper issue; page OCR is available per page id <issue>/seq-<n>. Not all LoC materials have OCR.",
        }

    async def get_page_text(self, page_id: str) -> dict[str, Any]:
        match = _CA_PAGE_ID.match(page_id or "")
        if not match:
            raise AdapterError(
                self.library_id,
                f"invalid Chronicling America page id: {page_id!r} (expected <lccn>/<date>/ed-<n>/seq-<k>)",
                retryable=False,
            )
        lccn, date, edition, seq_part = match.groups()
        seq = int(seq_part.split("-")[1])
        cached = self._ca_page_cache.get(page_id)
        if cached and time.monotonic() - cached[0] < 300:
            return dict(cached[1])
        await self._wait_for_rate_limit()
        from global_library_mcp.http import get_within_domain

        response = await get_within_domain(self.client, f"https://www.loc.gov/resource/{page_id}/?fo=json")
        payload = response.json()
        segments = payload.get("segments") or []
        segment_id = payload.get("segment_id") or ""
        resource = payload.get("resource") or {}
        fulltext_url = resource.get("fulltext_file")
        pages = payload.get("page") or []
        image_info = pages[0].get("info") if pages and isinstance(pages[0], dict) else None
        item = payload.get("item") or {}

        # --- strict structural mapping checks (final review S5).
        # Substring matching is not identity: sp is compared as a
        # parsed query value (sp=2 must not match sp=20), the
        # segment count must be exactly one, and every identifier
        # must agree with the requested lccn/date/edition/seq.
        from urllib.parse import parse_qs, urlparse

        issue_path = f"/{lccn}/{date}/{edition}/"
        item_id_path = urlparse(str(item.get("id") or "")).path
        issue_ok = item_id_path.endswith(issue_path)
        segment_url_ok = False
        if len(segments) == 1 and isinstance(segments[0], dict):
            candidates = [segments[0].get("url")] + list(segments[0].get("aka") or [])
            for candidate in candidates:
                if not candidate:
                    continue
                parsed = urlparse(str(candidate))
                if parsed.path.endswith(issue_path.rstrip("/")) or parsed.path == f"/resource{issue_path}":
                    if parse_qs(parsed.query).get("sp") == [str(seq)]:
                        segment_url_ok = True
                        break
        compact_date = date.replace("-", "")
        segment_segments = [seg for seg in segment_id.split("/") if seg]
        segment_id_ok = bool(segment_id) and lccn in segment_segments and any(
            seg.startswith(compact_date) for seg in segment_segments
        )
        fulltext_ok = False
        if fulltext_url:
            parsed_ft = urlparse(str(fulltext_url))
            fulltext_ok = (
                (parsed_ft.hostname or "") in _CA_TEXT_HOSTS
                and parsed_ft.path == "/text-services/word-coordinates-service"
                and parse_qs(parsed_ft.query).get("segment") == [segment_id]
            )
        image_info_ok = False
        if image_info:
            parsed_info = urlparse(str(image_info))
            expected_service = segment_id.strip("/").removesuffix(".xml").replace("/", ":")
            info_id = parsed_info.path.rstrip("/").removesuffix("/info.json").rsplit("/", 1)[-1]
            image_info_ok = (parsed_info.hostname or "") in _CA_TEXT_HOSTS and info_id == expected_service
        text = None
        entry_ok = False
        if fulltext_ok and segment_id:
            await self._wait_for_rate_limit()
            ft = await get_json(self.client, fulltext_url)
            entry = ft.get(segment_id) or {}
            candidate_text = entry.get("full_text")
            if isinstance(candidate_text, str) and candidate_text.strip():
                text = candidate_text
                entry_ok = True
        checks = {
            "single_segment_for_seq": len(segments) == 1,
            "segment_url_matches_seq": segment_url_ok,
            "issue_identity_matches": issue_ok,
            "segment_id_matches_issue": segment_id_ok,
            "fulltext_url_matches_segment": fulltext_ok,
            "text_entry_matches_segment": entry_ok,
            "image_info_belongs_to_segment": image_info_ok,
        }
        verified = all(checks.values())
        rights_text = _strip_html(" ".join(item.get("rights_advisory") or []))
        result = {
            "library_id": self.library_id,
            "page_id": page_id,
            "record_id": "/".join(match.groups()[:3]),
            "digital_frame": seq,
            "printed_page": "unknown",
            "contents": text,
            "ocr_available": text is not None,
            "ocr_source": fulltext_url,
            "ocr_format": "ALTO via loc.gov text-services (word-coordinates-service)",
            "segment_id": segment_id,
            "image_url": (image_info.replace("/info.json", "/full/max/0/default.jpg") if image_info else resource.get("image")),
            "image_info_url": image_info,
            "verified_mapping": verified,
            "mapping_checks": checks,
            "landing_url": f"https://www.loc.gov/resource/{page_id}/",
            "rights": {
                "statement": rights_text[:400] if rights_text else "unknown",
                "url": "https://www.loc.gov/homepage/legal.html",
                "source": "item rights_advisory (Chronicling America)",
            },
        }
        self._ca_page_cache[page_id] = (time.monotonic(), dict(result))
        if len(self._ca_page_cache) > 32:
            self._ca_page_cache.pop(next(iter(self._ca_page_cache)))
        return result

    async def verify_original(self, page_id: str) -> dict[str, Any]:
        """Original verification with the image-service stages
        kept separate (final review S6): a reachable info.json is
        NOT a reachable image. `verified` requires the strict
        page mapping, a service identity match, and a real image
        response (small IIIF rendition, signature-checked)."""
        from global_library_mcp.http import fetch_validated, response_looks_like_image, sanitize_error

        page = await self.get_page_text(page_id)
        info_url = page.get("image_info_url")
        service_base = info_url.removesuffix("/info.json") if info_url else None
        service_reachable = False
        service_identity = False
        image_reachable = False
        detail = "no image info url"
        if service_base:
            await self._wait_for_rate_limit()
            try:
                info_response = await fetch_validated(self.client, info_url, allowed_hosts=_CA_TEXT_HOSTS)
                info = info_response.json() if info_response.status_code == 200 else {}
                service_reachable = info_response.status_code == 200 and isinstance(info, dict)
                declared = str(info.get("@id") or info.get("id") or "").rstrip("/")
                service_identity = bool(declared) and declared == service_base.rstrip("/")
                detail = f"info.json status {info_response.status_code}, @id {'matches' if service_identity else 'mismatch/missing'}"
            except Exception as exc:  # noqa: BLE001
                detail = sanitize_error(exc)
            if service_reachable:
                await self._wait_for_rate_limit()
                image_url = f"{service_base}/full/!128,128/0/default.jpg"
                try:
                    image_response = await fetch_validated(self.client, image_url, allowed_hosts=_CA_TEXT_HOSTS)
                    body = image_response.content or b""
                    image_reachable = image_response.status_code in (200, 206) and response_looks_like_image(
                        body, image_response.headers.get("content-type") or ""
                    )
                    detail += f"; image GET status {image_response.status_code}, signature {'ok' if image_reachable else 'not an image'}"
                except Exception as exc:  # noqa: BLE001
                    detail += f"; image GET failed: {sanitize_error(exc)}"
        verified = bool(page.get("verified_mapping") and service_identity and image_reachable)
        return {
            "library_id": self.library_id,
            "page_id": page_id,
            "status": "verified" if verified else "unverified",
            "checks": {
                "page_mapping_verified": {"ok": bool(page.get("verified_mapping")), "detail": str(page.get("mapping_checks"))},
                "ocr_available": {"ok": bool(page.get("ocr_available")), "detail": "full text present" if page.get("ocr_available") else "no OCR text for this page"},
                "image_service_reachable": {"ok": service_reachable, "detail": detail},
                "image_service_identity_verified": {"ok": service_identity, "detail": service_base or ""},
                "image_reachable": {"ok": image_reachable, "detail": detail},
            },
            "image_url": page.get("image_url"),
            "landing_url": page.get("landing_url"),
        }

    def _result(self, item: dict[str, Any]) -> SearchResult:
        resource = item.get("resources") or []
        image_url = None
        if resource and isinstance(resource[0], dict):
            image_url = resource[0].get("thumbnail_url") or resource[0].get("url")
        return SearchResult(
            library_id=self.library_id,
            library_name=self.library_name,
            record_id=str(item.get("id") or item.get("title") or "unknown"),
            title=item.get("title") or item.get("description") or "Untitled",
            author=(item.get("contributor") or [None])[0] if isinstance(item.get("contributor"), list) else item.get("contributor"),
            date=item.get("date") or item.get("date_of_publication"),
            language=",".join(item.get("language", [])) if isinstance(item.get("language"), list) else item.get("language"),
            description=item.get("description") if isinstance(item.get("description"), str) else None,
            landing_url=item.get("id"),
            image_url=image_url,
            fulltext_status="available" if item.get("item", {}).get("fulltext_service") else "unknown",
            rights=Rights(statement=item.get("rights") or "unknown", source=item.get("id")),
            source_protocol="LoC JSON API",
            raw=item,
        )


# Exact hosts for Chronicling America payload URLs (final review
# S4): suffix matching such as endswith("loc.gov") would also pass
# lookalike hosts, so membership in this set is required.
_CA_TEXT_HOSTS = {"tile.loc.gov", "www.loc.gov"}


# --- Chronicling America newspaper pages (b5, section 5) -----
# The general LoC search above is bibliographic. Newspaper PAGE
# OCR is a separate, narrower capability that applies only to
# Chronicling America issues. The mapping is proven by the
# payload itself: the JSON for .../ed-N/seq-K/ contains exactly
# one segment whose id, IIIF image info and text-services
# full-text file all describe that same page.

import re as _re

_CA_PAGE_ID = _re.compile(r"^([a-z0-9]+)/(\d{4}-\d{2}-\d{2})/(ed-\d+)/(seq-\d+)$")
_CA_ISSUE_ID = _re.compile(r"^([a-z0-9]+)/(\d{4}-\d{2}-\d{2})/(ed-\d+)$")


def _strip_html(text: str) -> str:
    return _re.sub(r"<[^>]+>", "", text or "").strip()
