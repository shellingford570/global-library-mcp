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

    async def answer(self, query: str, libraries: Iterable[str] | None = None, limit: int = 10, provider: Any = None) -> dict[str, Any]:
        """Answer a question from verified OCR evidence only.

        Flow: collect page-level evidence, hand only the verified pages
        to the provider, then re-validate every returned citation key
        against the evidence whitelist in this layer as well, so a
        misbehaving provider cannot smuggle in a citation. When no
        verified evidence exists the answer is withheld and the status
        is ``insufficient_evidence``; bibliographic records alone never
        ground an answer.
        """
        import os

        from global_library_mcp.answer import MockProvider, compact_evidence, validate_citation_keys

        collected = await self.collect_evidence(query, libraries, limit)
        evidence = collected["evidence"]
        base: dict[str, Any] = {
            "query": query,
            "terms": collected["terms"],
            "evidence": evidence,
            "unverified": collected["unverified"],
            "search": collected["search"],
        }
        if not evidence:
            return {
                **base,
                "status": "insufficient_evidence",
                "available": False,
                "answer": None,
                "citations": [],
                "message": "確認できる根拠（検証済みのOCRページ）が見つかりませんでした。",
                "limitations": ["No verified OCR page evidence was collected for this question"],
            }
        if provider is None:
            if os.getenv("LLM_PROVIDER", "").lower() == "mock":
                provider = MockProvider()
            else:
                provider = OpenAICompatibleProvider(self.client)
        payload = compact_evidence(evidence)
        result = await provider.answer(query, payload)
        if not result.get("available"):
            return {
                **base,
                "status": "llm_unavailable",
                "available": False,
                "answer": None,
                "citations": [],
                "reason": result.get("reason"),
                "limitations": ["The answer provider did not produce an answer; the verified evidence above can be read directly"],
            }
        keys = validate_citation_keys(result.get("citations", []), payload)
        if keys is None:
            return {
                **base,
                "status": "citation_validation_failed",
                "available": False,
                "answer": None,
                "citations": [],
                "reason": "Provider returned citations outside the supplied evidence; answer withheld",
                "limitations": ["Citation whitelist validation failed at the service layer"],
            }
        by_key = {item["citation_key"]: item for item in evidence}
        citations = []
        for key in keys:
            item = by_key[key]
            citations.append({
                "citation_key": key,
                "library_id": item["library_id"],
                "library_name": item["library_name"],
                "record_id": item["record_id"],
                "page_id": item["page_id"],
                "digital_frame": item["digital_frame"],
                "title": item["title"],
                "image_url": item["image_url"],
                "landing_url": item["landing_url"],
            })
        from global_library_mcp.claims import verify_claims

        raw_claims = result.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raw_claims = [{"text": result.get("answer") or "", "citations": keys}]
        clean_claims = []
        for claim in raw_claims:
            if isinstance(claim, dict) and isinstance(claim.get("text"), str):
                clean_claims.append({
                    "text": claim["text"],
                    "citations": [c for c in claim.get("citations", []) if isinstance(c, str)],
                    **({"conflict": True} if claim.get("conflict") else {}),
                })
        claims = verify_claims(clean_claims, evidence)
        return {
            **base,
            "status": "answered",
            "available": True,
            "answer": result.get("answer"),
            "citations": citations,
            "claims": claims,
            "limitations": result.get("limitations", []),
        }

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

    async def compare_documents(
        self,
        documents: list[dict[str, str]],
        aspects: list[str] | None = None,
        question: str | None = None,
        pages_per_aspect: int = 2,
    ) -> dict[str, Any]:
        """Compare 2-4 documents aspect by aspect on verified OCR pages.

        Only pages passing the same identity + quality gates as the
        evidence pipeline are used. The comparison is textual: excerpts
        per aspect with citations, shared/unique content tokens, and
        explicit gaps where a document has no verified page for an
        aspect. Nothing is inferred beyond what the pages contain.
        """
        import re

        from global_library_mcp.adapters.base import AdapterError
        from global_library_mcp.compare import compare_aspect
        from global_library_mcp.evidence import assess_ocr_quality, extract_terms

        refs = [doc for doc in documents if doc.get("library_id") and doc.get("record_id")][:4]
        if len(refs) < 2:
            return {"status": "invalid_request", "reason": "compare_documents needs at least two documents", "documents": []}
        aspect_list = [a.strip() for a in (aspects or []) if a and a.strip()]
        if not aspect_list and question:
            aspect_list = extract_terms(question)
        if not aspect_list:
            aspect_list = ["概要"]

        doc_results: list[dict[str, Any]] = []
        per_aspect_texts: dict[str, dict[str, str]] = {aspect: {} for aspect in aspect_list}
        for ref in refs:
            library_id, record_id = ref["library_id"], ref["record_id"]
            entry: dict[str, Any] = {"library_id": library_id, "record_id": record_id, "title": record_id,
                                     "date": None, "landing_url": None, "pages": [], "error": None}
            try:
                adapter = self.adapters.get(library_id)
                if adapter is None:
                    raise AdapterError(library_id, f"Unknown library: {library_id}")
                if not adapter.supports_in_document_search:
                    raise AdapterError(library_id, "adapter does not support in-document search")
                try:
                    doc = await adapter.get_document(record_id)
                    book = doc.get("book") if isinstance(doc.get("book"), dict) else {}
                    entry["title"] = doc.get("title") or book.get("title") or record_id
                    entry["date"] = doc.get("date") or book.get("published") or book.get("date") or book.get("issued")
                    entry["landing_url"] = doc.get("landing_url")
                except Exception:  # noqa: BLE001 - metadata is best-effort; pages are the evidence
                    pass
                seen_pages: set[str] = set()
                for aspect in aspect_list:
                    found = await adapter.search_in_document(record_id, aspect)
                    matches = (found.get("matches") or {}).get("list", []) if isinstance(found, dict) else []
                    for match in matches[:pages_per_aspect]:
                        page_id = match.get("id") if isinstance(match, dict) else None
                        if not page_id or page_id in seen_pages:
                            continue
                        seen_pages.add(page_id)
                        page = await adapter.get_page_text(page_id)
                        text = page.get("contents") or ""
                        quality = assess_ocr_quality(text)
                        if not page.get("verified_mapping") or not quality["usable"]:
                            continue
                        position = text.find(aspect)
                        excerpt = text[max(0, position - 60):position + 220] if position >= 0 else text[:280]
                        entry["pages"].append({
                            "aspect": aspect,
                            "page_id": page.get("page_id"),
                            "digital_frame": page.get("digital_frame"),
                            "citation_key": f"{library_id}:{record_id}:{page.get('page_id')}",
                            "image_url": page.get("image_url"),
                            "excerpt": excerpt.strip(),
                        })
                        per_aspect_texts[aspect][record_id] = per_aspect_texts[aspect].get(record_id, "") + "\n" + text
            except Exception as exc:  # noqa: BLE001 - per-document failure is reported, not raised
                entry["error"] = str(exc) if isinstance(exc, AdapterError) else sanitize_error(exc)
            doc_results.append(entry)

        rows = []
        for aspect in aspect_list:
            texts = per_aspect_texts[aspect]
            comparison = compare_aspect(aspect, texts) if len(texts) == 2 else {"aspect": aspect, "shared_terms": [], "unique_terms": {}}
            rows.append({
                "aspect": aspect,
                "documents": {
                    entry["record_id"]: {
                        "found": any(p["aspect"] == aspect for p in entry["pages"]),
                        "excerpts": [p for p in entry["pages"] if p["aspect"] == aspect],
                    } for entry in doc_results
                },
                "shared_terms": comparison["shared_terms"],
                "unique_terms": comparison["unique_terms"],
            })

        notes = ["比較は検証済みOCRページのテキストに基づく機械的な対照です。語の有無は意味の同一・相違を証明しません。",
                 "翻訳は行っていません。抜粋は原文のままです。"]
        years = []
        for entry in doc_results:
            match = re.search(r"(1[5-9]\d{2}|20\d{2})", str(entry.get("date") or ""))
            if match:
                years.append((entry["record_id"], int(match.group(1))))
        if len(years) == 2 and abs(years[0][1] - years[1][1]) >= 10:
            notes.append(f"刊行年に差があります（{years[0][0]}: {years[0][1]}年 / {years[1][0]}: {years[1][1]}年）。資料が扱う内容の年代と刊行年は同一とは限りません。")
        with_pages = [entry for entry in doc_results if entry["pages"]]
        return {
            "status": "compared" if len(with_pages) >= 2 else "insufficient_evidence",
            "question": question,
            "aspects": aspect_list,
            "documents": [{key: entry[key] for key in ("library_id", "record_id", "title", "date", "landing_url", "error")} | {"verified_pages": len(entry["pages"])} for entry in doc_results],
            "rows": rows,
            "notes": notes,
        }
