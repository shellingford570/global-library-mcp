from __future__ import annotations

import asyncio
import re
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


def rank_candidates(analysis: Any, items: list[Any], query_hits: dict[tuple[str, str], int]) -> list[Any]:
    """Stage-1 (bibliographic) ranking of the merged candidate pool.

    Signals: core-concept families in the title (anchor family
    weighted double), a family match in author/description, and
    query multiplicity - a record surfaced by several independent
    query variants is likelier to be the specialist monograph than
    one surfaced once by a broad query.
    """
    from global_library_mcp.question import concept_variants, normalize_text
    from global_library_mcp.relevance import concept_families

    families = concept_families(analysis.core_concepts)

    def score(item: Any) -> int:
        title_n = normalize_text(item.title or "")
        total = 0
        for idx, family in enumerate(families):
            if any(variant in title_n for variant in concept_variants(family)):
                total += 2 if idx == 0 else 1
        meta_n = normalize_text(f"{item.author or ''} {item.description or ''}")
        if families and any(any(variant in meta_n for variant in concept_variants(family)) for family in families):
            total += 1
        total += min(query_hits.get((item.library_id, item.record_id), 1) - 1, 2)
        return total

    return sorted(items, key=lambda item: -score(item))


# Page kinds that can carry an assertion (as opposed to naming,
# listing or picturing the topic). Promotion paths and era-bound
# admissions are restricted to these (Phase 7-B/7-D policy).
NARRATIVE_KINDS = ("body", "table")


def rejection_reasons(
    status: str,
    semantics: dict[str, Any] | None,
    record: dict[str, Any] | None,
    page_kind: str | None,
) -> list[str]:
    """Why a page may not ground an answer, in plain terms.

    Shared by the evidence states (8-B) and the research
    materials mode (8-D), so a candidate always explains itself
    the same way.
    """
    semantics = semantics or {}
    relation = semantics.get("relation")
    reasons: list[str] = []
    if status not in ("relevant", "partially_relevant"):
        reasons.append("質問の中心概念との語彙的一致が不足している")
    if relation == "mentions_only":
        reasons.append("資料は話題に言及しているが、質問が求める出来事・普及を主張していない")
    elif relation == "insufficient":
        reasons.append("中心概念に言及する文が本文にない")
    elif relation == "contradicts":
        reasons.append("資料は質問の前提と矛盾する記述を含む")
    checks = (record or {}).get("checks", {})
    if checks.get("era_anchor") is False:
        reasons.append("出来事と時代を直接結び付ける記述（時代アンカー）が確認できない")
    if checks.get("page_kind_ok") is False or (
        relation in ("uncertain", "not_checked") and page_kind not in NARRATIVE_KINDS
    ):
        reasons.append(f"ページ種別（{page_kind}）は列挙的であり、事実認定の根拠には使えない")
    if not reasons:
        reasons.append("根拠評価の条件を満たさなかった")
    return reasons


def evidence_states(
    source_verified: bool,
    status: str | None,
    semantics: dict[str, Any] | None,
    admitted: bool,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    """The Phase 8-B state record for one fetched page."""
    semantics = semantics or {}
    return {
        "discovered": True,
        "accessible": True,
        "source_verified": bool(source_verified),
        "relevant_candidate": status in ("relevant", "partially_relevant"),
        "supporting_passage": bool(semantics.get("stance_sentences")),
        "assessed_evidence": bool(admitted),
        "rejected_for_answer": not admitted,
        "rejection_reasons": reasons or [],
    }


def admission_decision(
    analysis: Any,
    status: str,
    semantics: dict[str, Any] | None,
    page_kind: str | None,
    publication_year: int | None,
    anchor_matched: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """May this gated page ground an answer? (Phase 7-B)

    One rule for every path - direct, semantic promotion, union.
    Era-bound questions are the false-answer surface: a page
    grounds an era answer only when the checker *asserts* the
    asked stance and that assertion is anchored (in-era textual
    anchor, or a source contemporary with the era), or when the
    checker is out of scope (dated-event / general demands) and
    the page is narrative prose. A mention is not an assertion:
    mentions_only and insufficient never ground an era answer,
    whatever the page kind - the Phase 6 fixtures q52/h03/h22
    (mentions) and h05 (insufficient) all entered this way.
    Promotion paths additionally require narrative page kinds:
    contents pages, indexes and administrative lists name topics
    and numbers without asserting them (q35/q40).

    Returns (admitted, promotion record) - the record is stored
    on the evidence so every answer can show *why* a page was
    admitted (brief section 4.3 checks).
    """
    semantics = semantics or {}
    relation = semantics.get("relation")
    era = getattr(analysis, "era", None)
    contemporary = bool(semantics.get("contemporary_source"))
    anchored = bool(semantics.get("anchored_support")) or contemporary
    checks: dict[str, Any] = {
        "concepts": status in ("relevant", "partially_relevant"),
        "stance": relation,
        "era_anchor": None,
        "page_kind": page_kind,
        "ocr_quality": True,  # guaranteed by the verified gate upstream
        "citation_exists": True,
    }
    path = "direct" if status == "relevant" else "semantic"
    record: dict[str, Any] = {"path": path, "checks": checks}
    if status not in ("relevant", "partially_relevant") or relation == "contradicts":
        return False, record
    if status == "partially_relevant":
        # Semantic promotion: partial lexical relevance upgraded by
        # a checker assertion. Never from an enumerative page.
        if not anchor_matched:
            return False, record
        if page_kind not in NARRATIVE_KINDS:
            checks["page_kind_ok"] = False
            return False, record
        if era is not None:
            if relation != "supports":
                return False, record
            checks["era_anchor"] = anchored
            return anchored, record
        # No era premise: the checker is a stance instrument for
        # era questions; for general demands its out-of-scope
        # verdicts do not veto a promotion.
        return relation in ("supports", "uncertain", "not_checked"), record
    # Direct path (lexically relevant).
    if era is None:
        return True, record
    if relation == "supports":
        checks["era_anchor"] = anchored
        return anchored, record
    if relation in ("uncertain", "not_checked"):
        # The checker has no stance opinion (dated events, general
        # demands): narrative prose may ground the answer, an
        # enumerative page may not - unless the question asks for
        # exactly what that page kind is authoritative for
        # (Phase 7-D usage policy): a title page or colophon for a
        # bibliographic question, front matter for a structure
        # question. Factual era questions get no such bypass.
        if page_kind in NARRATIVE_KINDS:
            return True, record
        raw = getattr(analysis, "raw", "") or ""
        bibliographic = any(w in raw for w in ("書名", "題名", "タイトル", "著者", "誰が書", "出版社", "いつの本"))
        structure = any(w in raw for w in ("目次", "章構成", "何章", "構成を"))
        if bibliographic and page_kind in ("title_page", "colophon"):
            checks["kind_purpose"] = "bibliographic"
            return True, record
        if structure and page_kind == "front_matter":
            checks["kind_purpose"] = "structure"
            return True, record
        return False, record
    return False, record


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
        self._page_cache: dict[tuple[str, str], dict[str, Any]] = {}
        # Bibliographic search cache (Phase 7-G): identical queries
        # recur across questions in a session; caching them is a
        # pure load reduction with no behavioural change.
        self._search_cache: dict[tuple[str, tuple[str, ...], int], Any] = {}
        self.cache_stats = {"search_hits": 0, "search_misses": 0}

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

    async def _get_page_text_cached(self, adapter: LibraryAdapter, library_id: str, page_id: str) -> dict[str, Any]:
        """Page payloads are immutable; reuse them within this service
        instance (an answer flow plus a comparison in one process
        should not refetch the same page). Failures are not cached."""
        key = (library_id, str(page_id))
        if key not in self._page_cache:
            self._page_cache[key] = await adapter.get_page_text(page_id)
        return self._page_cache[key]

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
        related = collected.get("related", [])
        analysis = collected.get("analysis", {})
        base: dict[str, Any] = {
            "query": query,
            "terms": collected["terms"],
            "analysis": analysis,
            "evidence": evidence,
            "retrieval": collected.get("retrieval", {}),
            "premise_contradictions": collected.get("premise_contradictions", []),
            "related": related,
            "unverified": collected["unverified"],
            "search": collected["search"],
        }
        if not evidence:
            # Corrected premise: no page supports the question, but a
            # gated page *contradicts* its premise with quotable text
            # (negation, or an onset dated after the asked era). That
            # is a grounded correction, not a plain refusal - and it
            # is only offered with the contradicting sentences quoted
            # verbatim from the cited page.
            contradictions = collected.get("premise_contradictions", [])
            if contradictions:
                item = contradictions[0]
                sem = item.get("semantics") or {}
                quotes: list[str] = []
                for sentence in (sem.get("onset_after_era") or []):
                    if sentence not in quotes:
                        quotes.append(sentence)
                for sentence in ((sem.get("stance_sentences") or {}).get("negation") or []):
                    if sentence not in quotes:
                        quotes.append(sentence)
                quotes = quotes[:2]
                if quotes:
                    from global_library_mcp.claims import verify_claims

                    era_info = analysis.get("era") or {}
                    era_label = era_info.get("label") or "その時代"
                    concepts = analysis.get("core_concepts", [])
                    topic = concepts[0] if concepts else "その主題"
                    quoted = "。".join(q.strip().rstrip("。") for q in quotes)
                    answer_text = (
                        f"質問の前提（{topic}が{era_label}に存在・実現していた）は、確認できた資料では支持されません。"
                        f"『{item['title']}』には「{quoted}」とあり、前提とは異なる時期・状況が示されています。"
                    )
                    citation = {
                        "citation_key": item["citation_key"], "library_id": item["library_id"],
                        "library_name": item["library_name"], "record_id": item["record_id"],
                        "page_id": item["page_id"], "digital_frame": item.get("digital_frame"),
                        "title": item["title"], "image_url": item.get("image_url"),
                        "landing_url": item.get("landing_url"),
                    }
                    claims = verify_claims(
                        [{"text": q, "citations": [item["citation_key"]]} for q in quotes], [item]
                    )
                    return {
                        **base,
                        "status": "corrected_premise",
                        "available": True,
                        "answer": answer_text,
                        "citations": [citation],
                        "claims": claims,
                        "correction": {
                            "basis_citation_key": item["citation_key"],
                            "quotes": quotes,
                            "reasons": sem.get("reasons", []),
                        },
                        "limitations": ["前提の訂正は引用した資料の記述に基づきます。その資料自体が誤っている可能性は残るため、原本ページでも確認してください。"],
                    }
            # Name what the *closest* candidate lacked, not the union
            # over every related page (which blamed concepts that the
            # best pages actually contained).
            missing = []
            if related:
                missing = list((related[0].get("relevance") or {}).get("missing_concepts", []))
            if not missing:
                missing = list(analysis.get("core_concepts", []))
            if missing:
                reason = f"質問の中心概念（{'、'.join(missing)}）を裏付けるOCR本文が確認できませんでした。"
            else:
                reason = "質問に答えるための検証済みOCR本文が確認できませんでした。"
            limitations = ["No OCR page passed both the quality gate and the relevance gate for this question"]
            if related:
                reason += "関連する資料は見つかりましたが、質問への関連性が不足するため、回答の根拠には採用していません（参考資料として表示します）。"
                limitations.append("Related documents exist but were not adopted as evidence; see related_documents")
            related_documents = [{
                "citation_key": item["citation_key"], "library_id": item["library_id"],
                "record_id": item["record_id"], "page_id": item["page_id"], "title": item["title"],
                "image_url": item.get("image_url"), "landing_url": item.get("landing_url"),
                "relevance_status": (item.get("relevance") or {}).get("status"),
                "relevance_reasons": (item.get("relevance") or {}).get("reasons", []),
            } for item in related]
            return {
                **base,
                "status": "insufficient_evidence",
                "available": False,
                "answer": None,
                "citations": [],
                "reason": reason,
                "message": reason,
                "related_documents": related_documents,
                "limitations": limitations,
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
        claims = verify_claims(clean_claims, evidence, analysis=analysis)
        blocking = [c for c in claims if c.get("support") in {"unsupported", "conflicting"}]
        if blocking:
            return {
                **base,
                "status": "answer_withheld",
                "available": False,
                "answer": None,
                "citations": citations,
                "claims": claims,
                "reason": "回答に含まれる主張の一部について、引用したOCR本文による裏付けが確認できなかったため、回答を保留しました。",
                "limitations": [
                    f"claim not supported by its cited OCR: {c.get('text', '')[:80]}" for c in blocking
                ] + list(result.get("limitations", [])),
            }
        limitations = list(result.get("limitations", []))
        if any(c.get("support") == "uncertain" for c in claims):
            limitations.append("一部の主張は自動スクリーニングで裏付けが不確実です（uncertain）。原本ページで確認してください。")
        return {
            **base,
            "status": "answered",
            "available": True,
            "answer": result.get("answer"),
            "citations": citations,
            "claims": claims,
            "limitations": limitations,
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
        from global_library_mcp.question import analyze_question
        from global_library_mcp.relevance import assess_relevance, concept_families
        from global_library_mcp.semantics import get_semantic_checker

        semantic_checker = get_semantic_checker()
        analysis = analyze_question(query)
        search_terms = terms or extract_terms(query)
        # A natural-language question rarely matches bibliographic fields
        # verbatim, so search with the question first and then with each
        # extracted term, merging unique records until enough
        # in-document-capable candidates are found.
        merged: list[Any] = []
        seen_records: set[tuple[str, str]] = set()
        query_hits: dict[tuple[str, str], int] = {}
        search_errors: list[dict[str, str]] = []
        # Run every query variant: stopping as soon as a few
        # candidates exist (the old behaviour) let broad survey
        # volumes fill the pool before the specialist query ran.
        # One exception (Phase 7-G): a variant that is a substring
        # of a longer variant adds almost no discovery - its hits
        # are the longer query's neighbourhood - but costs a full
        # search per library. The full question always runs.
        variants = list(dict.fromkeys([query, *search_terms]))
        term_variants = variants[1:]
        variants = variants[:1] + [
            variant for variant in term_variants
            if not any(variant != other and variant in other for other in term_variants)
        ]
        for candidate_query in variants:
            cache_key = (candidate_query, tuple(sorted(libraries)), limit)
            resp = self._search_cache.get(cache_key)
            if resp is not None:
                self.cache_stats["search_hits"] += 1
            else:
                self.cache_stats["search_misses"] += 1
                resp = await self.search(candidate_query, libraries, limit)
                self._search_cache[cache_key] = resp
            search_errors.extend(resp.errors)
            for item in resp.results:
                key = (item.library_id, item.record_id)
                query_hits[key] = query_hits.get(key, 0) + 1
                if key not in seen_records:
                    seen_records.add(key)
                    merged.append(item)
        # Series dedupe: identical normalised title + author is one
        # candidate, however many queries surfaced it.
        from global_library_mcp.question import normalize_text

        deduped: list[Any] = []
        seen_series: set[tuple[str, str, str]] = set()
        for item in merged:
            series_key = (item.library_id, normalize_text(item.title or ""), normalize_text(item.author or ""))
            if series_key in seen_series:
                continue
            seen_series.add(series_key)
            deduped.append(item)
        merged = deduped[:30]
        ranked = rank_candidates(analysis, merged, query_hits)
        search_view = {"query": query, "results": [item.to_dict() for item in ranked], "errors": search_errors}
        verified: list[Evidence] = []
        premise_contradictions: list[dict[str, Any]] = []
        related: list[dict[str, Any]] = []
        unverified: list[dict[str, Any]] = []
        documents_tried = 0
        budget_extended = False
        evidence_document_ranks: list[int] = []
        doc_states: dict[int, dict[str, Any]] = {}

        async def screen(rank: int, result: Any, page_budget: int, include_adjacent: bool = False) -> None:
            nonlocal documents_tried
            adapter = self.adapters.get(result.library_id)
            if adapter is None or not adapter.supports_in_document_search:
                return
            state = doc_states.setdefault(rank, {"seen": set(), "hits": {}, "hit_terms": {}, "related_pages": []})
            if state.get("failed"):
                return
            if not state.get("counted"):
                documents_tried += 1
                state["counted"] = True
            outcome = await self._gate_document_pages(
                adapter, result, analysis, search_terms, page_budget, state, semantic_checker,
                include_adjacent=include_adjacent,
            )
            for ev in outcome["verified"]:
                verified.append(ev)
                if rank not in evidence_document_ranks:
                    evidence_document_ranks.append(rank)
            premise_contradictions.extend(outcome["contradictions"])
            related.extend(outcome["related"])
            unverified.extend(outcome["unverified"])
            if outcome.get("doc_failed"):
                state["failed"] = True

        # Staged fetching (Phase 6-C). Wave 1 screens more
        # documents with few pages each - the right book at rank 7
        # with 2 pages beats the wrong book at rank 1 with 3.
        wave1 = ranked[: max_documents + 6]
        for rank, result in enumerate(wave1, start=1):
            await screen(rank, result, 2)
            if len(verified) >= 3:
                break
        # Wave 2 deepens documents that produced a
        # partially_relevant page: their remaining hit pages.
        if not verified:
            for rank, result in enumerate(wave1, start=1):
                state = doc_states.get(rank)
                if state and any((p.get("relevance") or {}).get("status") == "partially_relevant" for p in state["related_pages"]):
                    await screen(rank, result, 2, include_adjacent=True)
        # Wave 3 extends to deeper candidates.
        if not verified and len(ranked) > len(wave1):
            budget_extended = True
            for rank, result in enumerate(ranked[len(wave1): len(wave1) + 6], start=len(wave1) + 1):
                await screen(rank, result, 2)
                if len(verified) >= 3:
                    break
        if not verified:
            promoted, promoted_keys = self._union_promote(doc_states, analysis)
            for ev in promoted:
                verified.append(ev)
                for rank, state in doc_states.items():
                    if any(obj is ev for obj in state.get("partial_objects", [])) and rank not in evidence_document_ranks:
                        evidence_document_ranks.append(rank)
            if promoted_keys:
                related = [item for item in related if item.get("citation_key") not in promoted_keys]
        related.sort(key=lambda item: (item.get("relevance") or {}).get("score", 0), reverse=True)
        if verified:
            failure_reason = None
        elif not merged:
            failure_reason = "no_candidates"
        elif premise_contradictions:
            failure_reason = "premise_contradicted"
        elif related:
            failure_reason = "no_relevant_pages"
        elif unverified:
            failure_reason = "all_pages_failed_verification"
        else:
            failure_reason = "budget_exhausted"
        retrieval = {
            "candidates": len(merged),
            "documents_tried": documents_tried,
            "budget_extended": budget_extended,
            "first_evidence_rank": evidence_document_ranks[0] if evidence_document_ranks else None,
            "evidence_document_ranks": evidence_document_ranks,
            "failure_reason": failure_reason,
        }
        # Phase 8-B: each pipeline stage reports its own outcome,
        # so a failure is attributable to a stage, not to "search".
        stage_log = [
            {"stage": "query_analysis", "status": "ok",
             "detail": f"core_concepts={len(analysis.core_concepts)}, era={analysis.era['label'] if analysis.era else None}, intent={analysis.intent}"},
            {"stage": "bibliographic_retrieval", "status": "ok" if ranked else "empty",
             "detail": f"{len(ranked)} candidates after ranking"},
            {"stage": "page_retrieval", "status": "ok" if (verified or related) else "empty",
             "detail": f"{len(verified) + len(related)} gated pages"},
            {"stage": "source_identity_verification", "status": "ok",
             "detail": f"{len(unverified)} pages failed identity/quality verification"},
            {"stage": "passage_extraction", "status": "ok",
             "detail": f"{sum(len(item.passages or []) for item in verified)} passages on admitted pages"},
            {"stage": "evidence_assessment", "status": "ok" if verified else "no_admission",
             "detail": f"{len(verified)} assessed evidence, {len(related)} rejected candidates, {len(premise_contradictions)} contradictions"},
        ]
        return {
            "query": query,
            "retrieval": retrieval,
            "terms": search_terms,
            "analysis": analysis.to_dict(),
            "evidence": [item.to_dict() for item in verified],
            "premise_contradictions": premise_contradictions[:4],
            "related": related[:8],
            "unverified": unverified,
            "search": search_view,
            "stage_log": stage_log,
        }

    def _union_promote(self, doc_states: dict[int, dict[str, Any]], analysis: Any) -> tuple[list[Any], set[str]]:
        """Document-level union promotion (Phase 6-D, hardened 7-B).

        Coverage and assertion are different things (brief 4.2):
        that one document's pages jointly *cover* every concept
        family does not assert any fact. A union therefore promotes
        only when at least one member page individually passes the
        admission rule for a checker assertion (anchored, when the
        question is era-bound), every promoted page satisfies the
        era condition *itself* (an era word on another page does
        not date this page's events - brief 4.1), all member pages
        are narrative kinds, the anchor family is present, and no
        page of the document contradicts the premise.
        """
        from global_library_mcp.relevance import concept_families

        families = concept_families(analysis.core_concepts)
        if not families:
            return [], set()
        promoted: list[Any] = []
        keys: set[str] = set()
        for state in doc_states.values():
            objects = [o for o in state.get("partial_objects", []) if o.page_kind in NARRATIVE_KINDS]
            if not objects:
                continue
            covered: set[str] = set()
            for obj in objects:
                covered |= set((obj.relevance or {}).get("matched_concepts", []))
            if not all(family in covered for family in families):
                continue
            if not any(families[0] in (obj.relevance or {}).get("matched_concepts", []) for obj in objects):
                continue
            doc_dicts = state.get("related_pages", [])
            if any((p.get("semantics") or {}).get("relation") == "contradicts" for p in doc_dicts):
                continue
            candidates = []
            for obj in objects:
                # The document-level checks above already verified
                # the anchor family is present in this document, so
                # the per-page admission runs with anchor_matched
                # satisfied; what it must still prove per page is
                # the assertion standard (supports, anchored when
                # era-bound, narrative kind).
                admitted, record = admission_decision(
                    analysis, "partially_relevant", obj.semantics, obj.page_kind,
                    None, True,
                )
                if not admitted:
                    continue
                if analysis.era is not None and "時代条件を満たす" not in " ".join(
                    (obj.relevance or {}).get("reasons", [])
                ):
                    # The era condition must hold on the promoted
                    # page itself, not merely somewhere in the book.
                    continue
                record["path"] = "union"
                candidates.append((obj, record))
            # At least one member must carry the assertion itself;
            # pure coverage never promotes. (Era-bound questions
            # only: for general demands the checker is out of scope
            # and coverage plus non-contradiction is the contract.)
            if analysis.era is not None and not any(
                (obj.semantics or {}).get("relation") == "supports" for obj, _ in candidates
            ):
                continue
            candidates.sort(key=lambda pair: -(pair[0].relevance or {}).get("score", 0))
            for obj, record in candidates[:2]:
                obj.promotion = record
                obj.semantics["union_promoted"] = True
                promoted.append(obj)
                keys.add(obj.citation_key)
        return promoted, keys

    async def _gate_document_pages(
        self, adapter: Any, result: Any, analysis: Any, search_terms: list[str],
        page_budget: int, state: dict[str, Any], semantic_checker: Any,
        include_adjacent: bool = False,
    ) -> dict[str, Any]:
        """Fetch and gate up to ``page_budget`` NEW pages of one document.

        ``state`` persists across waves: ``hits`` (page_id -> first
        hitting term), ``hit_terms`` (page_id -> all hitting terms),
        ``seen`` (page ids already fetched). Gating is exactly the
        Phase 4/5 pipeline: identity + OCR quality, relevance,
        semantics.
        """
        from global_library_mcp.evidence import assess_ocr_quality, classify_page_kind
        from global_library_mcp.models import Evidence
        from global_library_mcp.relevance import assess_relevance, concept_families

        out: dict[str, Any] = {"verified": [], "related": [], "unverified": [], "contradictions": [], "doc_failed": False}
        if not state["hits"] and not state.get("hits_done"):
            state["hits_done"] = True
            for term in search_terms:
                try:
                    found = await adapter.search_in_document(result.record_id, term, limit=8)
                except Exception as exc:  # noqa: BLE001 - reported, not hidden
                    out["unverified"].append({
                        "library_id": result.library_id, "record_id": result.record_id,
                        "page_id": None, "reason": f"in-document search failed: {sanitize_error(exc)}",
                    })
                    out["doc_failed"] = True
                    break
                matches = found.get("matches") if isinstance(found, dict) else None
                entries = matches.get("list") if isinstance(matches, dict) else matches
                for entry in entries or []:
                    page_id = entry.get("id") if isinstance(entry, dict) else None
                    if page_id:
                        state["hit_terms"].setdefault(page_id, set()).add(term)
                        if page_id not in state["hits"]:
                            state["hits"][page_id] = term
                if len(state["hits"]) >= 6:
                    break
            if not state["hits"] and not out["doc_failed"]:
                out["unverified"].append({
                    "library_id": result.library_id, "record_id": result.record_id,
                    "page_id": None, "reason": "no in-document page matched the question terms",
                })
                return out
        def _frame(page_id: str) -> int:
            digits = re.search(r"(\d+)$", str(page_id))
            return int(digits.group(1)) if digits else 0

        core_terms = set(analysis.terms)

        def _selection_key(page_id: str) -> tuple:
            hitting = state["hit_terms"].get(page_id, set())
            return (
                -len(hitting),  # pages hit by several terms first
                0 if hitting & core_terms else 1,  # core-concept hits before generic-term hits
                1 if _frame(page_id) <= 3 else 0,  # title/TOC frames last, never excluded
                _frame(page_id),
            )

        fresh = sorted(
            (pid for pid in state["hits"] if pid not in state["seen"]),
            key=_selection_key,
        )[:page_budget]
        if include_adjacent and len(fresh) < page_budget:
            neighbours: list[str] = []
            for page in state["related_pages"]:
                pid = str(page.get("page_id") or "")
                digits = re.search(r"(\d+)$", pid)
                if not digits:
                    continue
                width = len(digits.group(1))
                base = pid[: -width]
                for delta in (1, -1):
                    nid = f"{base}{int(digits.group(1)) + delta:0{width}d}"
                    if nid not in state["seen"] and nid not in state["hits"] and nid not in neighbours:
                        neighbours.append(nid)
                        state["hits"][nid] = state["hits"].get(pid, "")
            fresh.extend(neighbours[: page_budget - len(fresh)])
        year_match = re.search(r"(1[4-9]\d{2}|20\d{2})", str(result.date or ""))
        pub_year = int(year_match.group(1)) if year_match else None
        families = concept_families(analysis.core_concepts)
        for page_id in fresh:
            state["seen"].add(page_id)
            term = state["hits"][page_id]
            try:
                page = await self._get_page_text_cached(adapter, result.library_id, page_id)
            except Exception as exc:  # noqa: BLE001 - reported, not hidden
                out["unverified"].append({
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
            evidence.page_kind = classify_page_kind(page.get("contents"))
            if not is_verified:
                out["unverified"].append({
                    "library_id": result.library_id, "record_id": result.record_id,
                    "page_id": page_id, "reason": "; ".join(notes) or "unverified",
                    "citation_key": evidence.citation_key,
                })
                continue
            assessment = assess_relevance(analysis, evidence.ocr_text, publication_year=pub_year)
            evidence.relevance = assessment
            evidence.semantics = semantic_checker.assess(analysis, evidence.ocr_text, publication_year=pub_year)
            relation = evidence.semantics.get("relation")
            anchor_matched = bool(families) and families[0] in assessment.get("matched_concepts", [])
            if assessment["status"] == "relevant" and relation == "contradicts" and evidence.page_kind in NARRATIVE_KINDS:
                evidence.states = evidence_states(
                    True, assessment["status"], evidence.semantics, False,
                    rejection_reasons(assessment["status"], evidence.semantics, None, evidence.page_kind),
                )
                # A correction is an assertion too: it may only rest
                # on narrative pages, never on a heading in a
                # contents list or an index entry (Phase 7-E).
                out["contradictions"].append(evidence.to_dict())
                out["related"].append(evidence.to_dict())
                state["related_pages"].append(evidence.to_dict())
            else:
                admitted, record = admission_decision(
                    analysis, assessment["status"], evidence.semantics,
                    evidence.page_kind, pub_year, anchor_matched,
                )
                evidence.promotion = record
                evidence.states = evidence_states(
                    True, assessment["status"], evidence.semantics, admitted,
                    [] if admitted else rejection_reasons(
                        assessment["status"], evidence.semantics, record, evidence.page_kind),
                )
                if record["path"] == "semantic" and admitted:
                    evidence.semantics["promoted"] = True
                if admitted:
                    out["verified"].append(evidence)
                else:
                    out["related"].append(evidence.to_dict())
                    state["related_pages"].append(evidence.to_dict())
                    if assessment["status"] == "partially_relevant":
                        state.setdefault("partial_objects", []).append(evidence)
        return out

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
                        page = await self._get_page_text_cached(adapter, library_id, page_id)
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
