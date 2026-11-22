from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from global_library_mcp.adapters.aggregators import DdbAdapter, EuropeanaAdapter
from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.adapters.gallica import GallicaAdapter
from global_library_mcp.adapters.internet_archive import InternetArchiveAdapter
from global_library_mcp.adapters.loc import LocAdapter
from global_library_mcp.adapters.ndl import NdlAdapter
from global_library_mcp.answer import OpenAICompatibleProvider
from global_library_mcp.http import ResponseCache, sanitize_error
from global_library_mcp.models import SearchResponse


class LibraryService:
    default_libraries = ("loc", "ndl", "gallica", "internet-archive")

    def __init__(self, client: httpx.AsyncClient):
        cache = ResponseCache()
        self.adapters: dict[str, LibraryAdapter] = {
            "loc": LocAdapter(client, cache),
            "ndl": NdlAdapter(client),
            "gallica": GallicaAdapter(client),
            "internet-archive": InternetArchiveAdapter(client),
            "ddb": DdbAdapter(client),
            "europeana": EuropeanaAdapter(client),
        }
        self.client = client

    async def search(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10) -> SearchResponse:
        selected = list(dict.fromkeys(libraries or self.default_libraries))
        unknown = [library_id for library_id in selected if library_id not in self.adapters]
        selected = [library_id for library_id in selected if library_id in self.adapters]
        limit = min(max(limit, 1), 100)
        async def one(library_id: str):
            try:
                return library_id, await self.adapters[library_id].search(query, limit)
            except Exception as exc:
                return library_id, exc
        pairs = await asyncio.gather(*(one(library_id) for library_id in selected))
        grouped_results: list[list[Any]] = []
        errors = []
        seen: set[tuple[str, str]] = set()
        for library_id, value in pairs:
            if isinstance(value, Exception):
                errors.append({"library_id": getattr(value, "library_id", library_id), "error": sanitize_error(value)})
                continue
            grouped_results.append(list(value))
        results = []
        for index in range(max((len(group) for group in grouped_results), default=0)):
            for group in grouped_results:
                if index >= len(group) or len(results) >= limit:
                    continue
                result = group[index]
                key = ("url", result.landing_url) if result.landing_url else ("record", result.library_id, result.record_id)
                if key not in seen:
                    seen.add(key)
                    results.append(result)
            if len(results) >= limit:
                break
        errors = [{"library_id": library_id, "error": "Unknown library"} for library_id in unknown] + errors
        return SearchResponse(query=query, results=results, errors=errors)

    async def get_document(self, library_id: str, record_id: str) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.get_document(record_id)

    async def search_in_document(self, library_id: str, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.search_in_document(record_id, query, limit)

    async def get_page_text(self, library_id: str, page_id: str) -> dict[str, Any]:
        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        return await adapter.get_page_text(page_id)

    async def verify_page(self, library_id: str, page_id: str) -> dict[str, Any]:
        """Verify a page against its original (IIIF) representation.

        Returns the adapter's per-check report. Adapters without an
        implementation yield status ``unsupported`` rather than an
        exception, so callers can show the page as unverifiable instead
        of verified.
        """
        from global_library_mcp.adapters.base import AdapterError

        adapter = self.adapters.get(library_id)
        if not adapter:
            raise ValueError(f"Unknown library: {library_id}")
        try:
            return await adapter.verify_original(page_id)
        except AdapterError as exc:
            return {
                "library_id": library_id,
                "page_id": page_id,
                "status": "unsupported",
                "reason": sanitize_error(exc),
            }

    async def answer(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10) -> dict[str, Any]:
        search = await self.search(query, libraries, limit)
        provider = OpenAICompatibleProvider(self.client)
        answer = await provider.answer(query, [item.to_dict() for item in search.results])
        answer["search"] = search.to_dict()
        return answer

    async def collect_evidence(
        self,
        query: str,
        libraries: Iterable[str] | None = None,
        limit: int = 10,
        max_documents: int = 3,
        pages_per_document: int = 3,
        terms: list[str] | None = None,
    ) -> dict[str, Any]:
        """Collect page-level OCR evidence for a question.

        Bibliographic search alone is never treated as evidence. Only
        pages whose payload identity matches the request (the adapter's
        ``verified_mapping``) and whose OCR passes the quality gate are
        returned as verified evidence; everything else is reported in
        ``unverified`` with the reason, so callers can show it as
        unconfirmed instead of silently dropping or trusting it.
        """
        from global_library_mcp.evidence import assess_ocr_quality, extract_terms
        from global_library_mcp.models import Evidence

        search_terms = terms or extract_terms(query)
        # A natural-language question rarely matches bibliographic fields
        # verbatim, so search with the question first and then with each
        # extracted term, merging unique records until enough
        # in-document-capable candidates are found.
        merged: list[Any] = []
        seen_records: set[tuple[str, str]] = set()
        search_errors: list[dict[str, str]] = []
        capable = 0
        for candidate_query in [query, *search_terms]:
            resp = await self.search(candidate_query, libraries, limit)
            search_errors.extend(resp.errors)
            for item in resp.results:
                key = (item.library_id, item.record_id)
                if key not in seen_records:
                    seen_records.add(key)
                    merged.append(item)
                    adapter = self.adapters.get(item.library_id)
                    if adapter is not None and adapter.supports_in_document_search:
                        capable += 1
            if capable >= max_documents:
                break
        search_view = {"query": query, "results": [item.to_dict() for item in merged], "errors": search_errors}
        verified: list[Evidence] = []
        unverified: list[dict[str, Any]] = []
        documents_tried = 0
        for result in merged:
            if documents_tried >= max_documents:
                break
            adapter = self.adapters.get(result.library_id)
            if adapter is None or not adapter.supports_in_document_search:
                continue
            documents_tried += 1
            page_terms: dict[str, str] = {}
            for term in search_terms:
                try:
                    found = await adapter.search_in_document(result.record_id, term, limit=pages_per_document * 2)
                except Exception as exc:  # noqa: BLE001 - reported, not hidden
                    unverified.append({
                        "library_id": result.library_id, "record_id": result.record_id,
                        "page_id": None, "reason": f"in-document search failed: {sanitize_error(exc)}",
                    })
                    continue
                matches = found.get("matches") if isinstance(found, dict) else None
                entries = matches.get("list") if isinstance(matches, dict) else matches
                for entry in entries or []:
                    page_id = entry.get("id") if isinstance(entry, dict) else None
                    if page_id and page_id not in page_terms:
                        page_terms[page_id] = term
                if len(page_terms) >= pages_per_document:
                    break
            if not page_terms:
                unverified.append({
                    "library_id": result.library_id, "record_id": result.record_id,
                    "page_id": None, "reason": "no in-document page matched the question terms",
                })
                continue
            for page_id, term in list(page_terms.items())[:pages_per_document]:
                try:
                    page = await adapter.get_page_text(page_id)
                except Exception as exc:  # noqa: BLE001 - reported, not hidden
                    unverified.append({
                        "library_id": result.library_id, "record_id": result.record_id,
                        "page_id": page_id, "reason": f"page fetch failed: {sanitize_error(exc)}",
                    })
                    continue
                quality = assess_ocr_quality(page.get("contents"))
                notes: list[str] = list(quality.get("notes", []))
                mapping_ok = bool(page.get("verified_mapping"))
                if not mapping_ok:
                    notes.append("page payload identity did not match the requested page")
                is_verified = mapping_ok and bool(quality.get("usable"))
                evidence = Evidence(
                    library_id=result.library_id,
                    library_name=result.library_name,
                    record_id=result.record_id,
                    title=result.title,
                    page_id=str(page.get("page_id") or page_id),
                    digital_frame=page.get("digital_frame"),
                    printed_page=str(page.get("printed_page") or "unknown"),
                    ocr_text=page.get("contents") or "",
                    ocr_source=str(page.get("ocr_source") or "unknown"),
                    ocr_quality=quality,
                    image_url=page.get("image_url"),
                    landing_url=result.landing_url,
                    matched_term=term,
                    verified=is_verified,
                    verification_notes=notes,
                    rights=result.rights,
                )
                if is_verified:
                    verified.append(evidence)
                else:
                    unverified.append({
                        "library_id": result.library_id, "record_id": result.record_id,
                        "page_id": page_id, "reason": "; ".join(notes) or "unverified",
                        "citation_key": evidence.citation_key,
                    })
        return {
            "query": query,
            "terms": search_terms,
            "evidence": [item.to_dict() for item in verified],
            "unverified": unverified,
            "search": search_view,
        }
