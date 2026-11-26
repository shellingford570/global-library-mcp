"""b6 final-review regression tests.

Each test pins one external-review finding: Quick ignoring the
structured options, author/title filters that were only hints,
filters applied after OCR fetching, expansion toggles leaking
through some generation paths, permissive work/author linking,
string-pattern handoff identifiers, edition over-classification,
unnormalised language filters, OCR-requirement semantics,
routing to an authentication-pending library, and
planned-vs-executed variant reporting.
"""
from __future__ import annotations

import httpx
import pytest

from global_library_mcp.adapters.base import LibraryAdapter
from global_library_mcp.models import SearchResult
from global_library_mcp.service import LibraryService


def _result(record_id, title, author=None, date=None, language=None, library_id="stub", raw=None):
    return SearchResult(library_id=library_id, library_name="Stub", record_id=record_id,
                        title=title, author=author, date=date, language=language,
                        landing_url=f"https://example.org/{record_id}", raw=raw or {})


class _RecAdapter(LibraryAdapter):
    """Records every call; returns a fixed record set for any
    query and fixed in-document hits per record."""

    library_id = "stub"
    library_name = "Stub"
    supports_in_document_search = True

    def __init__(self, records, hits=None):
        self.records = records
        self.hits = hits or {}
        self.search_queries: list[str] = []
        self.in_doc_calls: list[str] = []
        self.page_calls: list[str] = []

    async def search(self, query, limit=10):
        self.search_queries.append(query)
        return list(self.records)

    async def search_in_document(self, record_id, query, limit=20):
        self.in_doc_calls.append(record_id)
        return {"matches": {"list": [{"id": pid} for pid in self.hits.get(record_id, [])]}}

    async def get_page_text(self, page_id):
        self.page_calls.append(page_id)
        return {"page_id": page_id, "contents": "stub page text about the topic",
                "verified_mapping": True, "image_url": "https://example.org/img.jpg",
                "source": "stub"}


def _service(adapter) -> LibraryService:
    svc = LibraryService(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    svc.adapters = {adapter.library_id: adapter}
    svc.default_libraries = [adapter.library_id]
    return svc


KANT = _result("k1", "Kritik der reinen Vernunft", "Kant, Immanuel", "1781", "de")
HEGEL = _result("h1", "Phänomenologie des Geistes", "Hegel, Georg Wilhelm Friedrich", "1807", "de")


# ---------------------------------------------------------------- Quick (section 2)

@pytest.mark.asyncio
async def test_quick_author_filter_actually_applies():
    svc = _service(_RecAdapter([KANT, HEGEL]))
    out = await svc.research_materials("哲学", libraries=["stub"], mode="quick",
                                       author="Immanuel Kant")
    assert [m["record_id"] for m in out["materials"]] == ["k1"]
    assert out["materials"][0]["filter_match"]["author_match"] == "exact_or_variant"
    assert out["filters"]["candidates_before"] == 2
    assert out["filters"]["candidates_after"] == 1
    assert out["discovery"] is not None


@pytest.mark.asyncio
async def test_quick_title_filter_actually_applies():
    svc = _service(_RecAdapter([KANT, HEGEL]))
    out = await svc.research_materials("哲学", libraries=["stub"], mode="quick",
                                       title="純粋理性批判")
    assert [m["record_id"] for m in out["materials"]] == ["k1"]
    assert out["materials"][0]["filter_match"]["title_match"] in ("exact", "contains")


@pytest.mark.asyncio
async def test_quick_language_filter_normalises_codes():
    records = [_result("a", "A", "X", "1900", "German"),
               _result("b", "B", "Y", "1900", "jpn"),
               _result("c", "C", "Z", "1900", None)]
    svc = _service(_RecAdapter(records))
    out = await svc.research_materials("q", libraries=["stub"], mode="quick", languages=["de"])
    kept = {m["record_id"] for m in out["materials"]}
    assert kept == {"a", "c"}  # German == de; jpn is not de; unknown kept but not a match
    c_entry = next(m for m in out["materials"] if m["record_id"] == "c")
    assert c_entry["filter_match"]["language_match"] is None
    assert out["filters"]["metadata_missing"]["document_language"] == 1


@pytest.mark.asyncio
async def test_quick_year_range_and_unknown_year_handling():
    records = [_result("a", "A", "X", "1850", "en"),
               _result("b", "B", "Y", None, "en")]
    svc = _service(_RecAdapter(records))
    out = await svc.research_materials("q", libraries=["stub"], mode="quick",
                                       year_from=1900, year_to=2000)
    assert [m["record_id"] for m in out["materials"]] == ["b"]  # unknown year kept by default
    out2 = await svc.research_materials("q", libraries=["stub"], mode="quick",
                                        year_from=1900, year_to=2000, include_unknown_year=False)
    assert out2["materials"] == []
    assert out2["filters"]["candidates_after"] == 0


@pytest.mark.asyncio
async def test_quick_multilingual_disabled_sends_no_foreign_queries():
    adapter = _RecAdapter([KANT])
    svc = _service(adapter)
    await svc.research_materials("純粋理性批判", libraries=["stub"], mode="quick",
                                 expand_multilingual=False)
    assert adapter.search_queries[0] == "純粋理性批判"  # original always runs
    assert not any("Kritik" in q or "Critique" in q for q in adapter.search_queries)


@pytest.mark.asyncio
async def test_quick_historical_toggle_controls_sent_queries():
    adapter = _RecAdapter([_result("s1", "蒸気機関", "佐藤", "1900", "ja")])
    svc = _service(adapter)
    await svc.research_materials("蒸気機関", libraries=["stub"], mode="quick",
                                 expand_historical=False)
    assert not any("蒸氣機關" in q for q in adapter.search_queries)
    adapter.search_queries.clear()
    await svc.research_materials("蒸気機関", libraries=["stub"], mode="quick",
                                 expand_historical=True)
    assert any("蒸氣機關" in q for q in adapter.search_queries)


@pytest.mark.asyncio
async def test_quick_never_investigates_pages_and_reports_budget():
    adapter = _RecAdapter([KANT], hits={"k1": ["k1@1"]})
    svc = _service(adapter)
    out = await svc.research_materials("純粋理性批判", libraries=["stub"], mode="quick")
    assert adapter.in_doc_calls == [] and adapter.page_calls == []
    assert out["http_stats"]["max_requests"] == 30
    assert all(m["access_state"]["ocr_fetched"] is False for m in out["materials"])


@pytest.mark.asyncio
async def test_quick_ocr_required_is_bibliographic_only():
    class _PlainAdapter(LibraryAdapter):
        """No page-text implementation at all (base class only)."""

        library_id = "plain"
        library_name = "Plain"
        supports_in_document_search = False

        def __init__(self, records):
            self.records = records

        async def search(self, query, limit=10):
            return list(self.records)

    records = [_result("a", "A", "X", "1900", "en", library_id="stub"),
               _result("b", "B", "Y", "1900", "en", library_id="plain")]
    svc = LibraryService(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    capable = _RecAdapter(records[:1])
    plain = _PlainAdapter(records[1:])
    svc.adapters = {"stub": capable, "plain": plain}
    svc.default_libraries = ["stub", "plain"]
    out = await svc.research_materials("q", libraries=["stub", "plain"], mode="quick",
                                       ocr_required=True)
    assert [m["record_id"] for m in out["materials"]] == ["a"]
    assert out["filters"]["ocr_required_basis"]["confirmed_ocr"] == 0
    assert out["filters"]["ocr_required_basis"]["adapter_capable_unconfirmed"] == 1


# --------------------------------------- Filters before OCR (sections 3/4)

@pytest.mark.asyncio
async def test_author_filter_runs_before_ocr_investigation():
    adapter = _RecAdapter([KANT, HEGEL], hits={"k1": ["k1@1"], "h1": ["h1@1"]})
    svc = _service(adapter)
    out = await svc.research_materials("哲学", libraries=["stub"], mode="standard",
                                       author="Immanuel Kant")
    assert "h1" not in adapter.in_doc_calls  # excluded record never investigated
    assert [m["record_id"] for m in out["materials"]] == ["k1"]
    assert out["filters"]["candidates_before"] == 2
    assert out["filters"]["candidates_after"] == 1
    assert out["filters"]["stage"].startswith("bibliographic")


@pytest.mark.asyncio
async def test_filtered_out_record_cannot_make_answerable():
    adapter = _RecAdapter([HEGEL], hits={"h1": ["h1@1"]})
    svc = _service(adapter)
    out = await svc.research_materials("哲学", libraries=["stub"], mode="standard",
                                       author="Immanuel Kant")
    assert out["materials"] == []
    assert out["answerable"] is False
    assert adapter.in_doc_calls == []


@pytest.mark.asyncio
async def test_without_filter_the_same_record_is_kept():
    adapter = _RecAdapter([HEGEL], hits={"h1": ["h1@1"]})
    svc = _service(adapter)
    out = await svc.research_materials("哲学", libraries=["stub"], mode="standard")
    assert [m["record_id"] for m in out["materials"]] == ["h1"]


@pytest.mark.asyncio
async def test_author_filter_counts_missing_author_metadata():
    adapter = _RecAdapter([_result("n1", "匿名の書", None, "1900", "ja")])
    svc = _service(adapter)
    out = await svc.research_materials("哲学", libraries=["stub"], mode="standard",
                                       author="Immanuel Kant")
    assert out["materials"] == []
    assert out["filters"]["metadata_missing"]["author"] == 1


# --------------------------------------- Expansion toggles (section 5)

def test_expansion_toggle_combinations():
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.expansion import QueryExpansionEngine

    analysis = analyze_discovery_query("蒸気機関")
    engine = QueryExpansionEngine()
    both = engine.expand(analysis, mode="standard", expand_multilingual=True, expand_historical=True)
    assert any(v["text"] == "Dampfmaschine" for v in both["variants"])
    assert any(v["text"] == "蒸氣機關" for v in both["variants"])
    multi_only = engine.expand(analysis, mode="standard", expand_multilingual=True, expand_historical=False)
    assert any(v["text"] == "Dampfmaschine" for v in multi_only["variants"])
    assert not any(v["kind"] == "historical" for v in multi_only["variants"])
    hist_only = engine.expand(analysis, mode="standard", expand_multilingual=False, expand_historical=True)
    assert any(v["text"] == "蒸氣機關" for v in hist_only["variants"])
    assert all(v["language"] in ("ja", "unknown") for v in hist_only["variants"])
    neither = engine.expand(analysis, mode="standard", expand_multilingual=False, expand_historical=False)
    assert all(v["language"] in ("ja", "unknown") for v in neither["variants"])
    assert not any(v["kind"] == "historical" for v in neither["variants"])


def test_expansion_target_languages_restrict_candidates():
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.expansion import QueryExpansionEngine

    analysis = analyze_discovery_query("蒸気機関")
    plan = QueryExpansionEngine().expand(analysis, mode="standard", target_languages=["de"])
    langs = {v["language"] for v in plan["variants"]}
    assert langs <= {"ja", "de"}
    assert any(v["text"] == "Dampfmaschine" for v in plan["variants"])
    assert any(s["candidate"] == "machine à vapeur" for s in plan["skipped"])


@pytest.mark.asyncio
async def test_service_legacy_variants_follow_toggles():
    adapter = _RecAdapter([_result("d1", "発電史", "佐藤", "1900", "ja")])
    svc = _service(adapter)
    await svc.collect_evidence("発電", ["stub"], 5, mode="standard",
                               expand_historical=False)
    assert not any("發電" in q for q in adapter.search_queries)
    adapter.search_queries.clear()
    await svc.collect_evidence("発電", ["stub"], 5, mode="standard",
                               expand_historical=True)
    assert any("發電" in q for q in adapter.search_queries)


# --------------------------------------- Resolution strictness (section 6)

def test_resolution_status_matrix():
    from global_library_mcp import resolution

    r = resolution.resolve_work("Critique of Pure Reason", "")
    assert r["status"] == "candidate_title_only" and r["work_id"] is None
    assert "NOT checked" in r["basis"]
    r = resolution.resolve_work("On the Origin of Species", "Darwin, Erasmus")
    assert r["status"] == "refused_author_mismatch" and r["work_id"] is None
    r = resolution.resolve_work("On the Origin of Species", "Darwin, Charles")
    assert r["status"] == "candidate_exact_title_and_author"
    assert r["work_id"] == "work:origin-of-species"
    assert r["verification_status"] == "lexicon_unverified"
    r = resolution.resolve_work("Kritik der reinen Vernunft: Ein Kommentar", "Kant, Immanuel")
    assert r["status"] == "candidate_title_only" and r["work_id"] is None
    r = resolution.resolve_work("Critique of Pure Reason", "Kant")
    assert r["status"] == "candidate_title_only"  # surname-only agreement
    r = resolution.resolve_author("")
    assert r["status"] == "insufficient_metadata"
    r = resolution.resolve_author("Darwin")
    assert r["status"] == "refused_ambiguous_surname"
    r = resolution.resolve_author("Müller")
    assert r["status"] == "refused_ambiguous_surname"
    r = resolution.resolve_author("Kant, Immanuel")
    assert r["status"] == "candidate_exact"


# --------------------------------------- Edition classification (section 7)

def test_edition_classification_requires_real_agreement():
    svc = _service(_RecAdapter([]))

    def materials(publisher_a, publisher_b, year_a="1808", year_b="1808"):
        mats = [
            {"library_id": "stub", "record_id": "a", "title": "Faust", "author": "Goethe",
             "date": year_a, "work_link": {"work_id": "work:faust"}},
            {"library_id": "stub", "record_id": "b", "title": "Faust", "author": "Goethe",
             "date": year_b, "work_link": {"work_id": "work:faust"}},
        ]
        biblio = {("stub", "a"): {"language": "de", "raw": {"publisher": publisher_a}},
                  ("stub", "b"): {"language": "de", "raw": {"publisher": publisher_b}}}
        svc._attach_grouping(mats, biblio)
        return mats[0]["duplicate_group"]["relation"]

    assert materials("Cotta", "Cotta") == "same_edition_candidate"
    assert materials("Cotta", "Reclam") == "same_work_different_edition_or_translation"
    assert materials(None, None) == "same_work_candidate"
    assert materials("Cotta", "Cotta", year_a=None, year_b=None) == "same_work_candidate"


# --------------------------------------- Handoff structure (section 8)

def test_handoff_structural_verification():
    from global_library_mcp.handoff import extract_bsb_candidate

    base = {"provider_id": ["00005860"]}
    ok = extract_bsb_candidate({**base, "view": ["Digitalisat: urn:nbn:de:bvb:12-bsb11650472-5"]})
    assert ok["status"] == "candidate" and ok["bsb_object_id"] == "bsb11650472"
    ok_url = extract_bsb_candidate({**base, "view": ["https://www.digitale-sammlungen.de/en/view/bsb00050936"]})
    assert ok_url["status"] == "candidate"
    embedded = extract_bsb_candidate({**base, "view": ["https://example.com/redir?u=https://www.digitale-sammlungen.de/view/bsb87654321"]})
    assert embedded["status"] == "no_candidate"
    fake_host = extract_bsb_candidate({**base, "view": ["https://digitale-sammlungen.de.evil.example/view/bsb12345678"]})
    assert fake_host["status"] == "no_candidate"
    malformed = extract_bsb_candidate({**base, "view": ["urn:nbn:de:bvb:12-bsb123-5"]})
    assert malformed["status"] == "no_candidate"
    two = extract_bsb_candidate({**base, "view": ["urn:nbn:de:bvb:12-bsb11650472-5 urn:nbn:de:bvb:12-bsb00050936-1"]})
    assert two["status"] == "refused_ambiguous"
    wrong_provider = extract_bsb_candidate({"provider_id": ["123"], "view": ["urn:nbn:de:bvb:12-bsb11650472-5"]})
    assert wrong_provider["status"] == "refused_provider_mismatch"


# --------------------------------------- Language normalisation (section 11)

def test_language_normalisation():
    from global_library_mcp.languages import language_matches, normalize_language

    assert normalize_language("jpn") == ["ja"]
    assert normalize_language("Japanese") == ["ja"]
    assert normalize_language("日本語") == ["ja"]
    assert normalize_language("ger") == ["de"]
    assert normalize_language("Deutsch") == ["de"]
    assert normalize_language("fre") == ["fr"]
    assert normalize_language("français") == ["fr"]
    assert normalize_language(["eng", "ger"]) == ["en", "de"]
    assert normalize_language("eng; ger") == ["en", "de"]
    assert normalize_language(None) == []
    assert normalize_language("Klingon") == []
    assert language_matches("jpn", ["ja"]) is True
    assert language_matches("jpn", ["de"]) is False
    assert language_matches(None, ["ja"]) is None  # unknown never counts as a match


# --------------------------------------- Empty OCR states (section 10)

@pytest.mark.asyncio
async def test_get_page_text_distinguishes_empty_ocr_from_identity():
    class _EmptyOcr(_RecAdapter):
        async def get_page_text(self, page_id):
            return {"page_id": page_id, "contents": "   ",
                    "verified_mapping": True, "image_url": "https://example.org/i.jpg"}

    svc = _service(_EmptyOcr([]))
    out = await svc.get_page_text("stub", "r1@1")
    assert out["ocr_state"]["page_identity_verified"] is True
    assert out["ocr_state"]["ocr_nonempty"] is False
    assert out["ocr_state"]["ocr_available"] is False

    class _FullOcr(_RecAdapter):
        async def get_page_text(self, page_id):
            return {"page_id": page_id, "contents": "real text",
                    "verified_mapping": True, "image_url": "https://example.org/i.jpg"}

    svc2 = _service(_FullOcr([]))
    out2 = await svc2.get_page_text("stub", "r1@1")
    assert out2["ocr_state"]["ocr_nonempty"] is True


# --------------------------------------- Routing & execution reporting (sections 13/14)

@pytest.mark.asyncio
async def test_routing_never_dispatches_to_keyless_europeana(monkeypatch):
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    adapter = _RecAdapter([KANT])
    svc = _service(adapter)
    out = await svc.research_materials("純粋理性批判", mode="standard")
    assert "europeana" in out["discovery"]["routing_skipped"]
    execution = out["discovery"]["variant_execution"]
    assert execution, "variant execution must be reported"
    assert all(e["status"] in ("executed", "cached", "skipped") for e in execution)
    planned = {v["text"] for v in out["discovery"]["planned_variants"]}
    executed = set(out["discovery"]["executed_variants"])
    assert executed <= planned


# --------------------------------------- Lexicon quality gates (section 23)

def test_lexicon_validation_rejects_bad_entries(tmp_path, monkeypatch):
    import json

    from global_library_mcp import lexicon

    data = json.loads(lexicon._DATA.read_text(encoding="utf-8"))
    data["concepts"][0]["labels"]["ja"] = ["", "x"]  # empty surface
    bad = tmp_path / "lexicon.json"
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(lexicon, "_DATA", bad)
    lexicon.load_lexicon.cache_clear()
    try:
        with pytest.raises(ValueError):
            lexicon.load_lexicon()
    finally:
        lexicon.load_lexicon.cache_clear()


def test_lexicon_candidates_carry_verification_status():
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.expansion import QueryExpansionEngine

    plan = QueryExpansionEngine().expand(analyze_discovery_query("蒸気機関"), mode="standard")
    lexicon_variants = [v for v in plan["variants"] if v["source"].startswith("lexicon:")]
    assert lexicon_variants
    assert all(v.get("lexicon_verification_status") == "unverified" for v in lexicon_variants)


# --------------------------------------- Comparison sharing split (section 24)

def test_concept_overlap_distinguishes_all_vs_some():
    from global_library_mcp.compare import concept_overlap

    docs = {
        "a": "蒸気機関と鉄道の歴史",
        "b": "蒸気機関の仕組み",
        "c": "蒸気機関と産業革命",
    }
    out = concept_overlap(docs)
    assert out["semantic_comparison"] == "not_checked"
    assert set(out["shared_by_all_documents"]) <= set(out["dictionary_concept_overlap"])
    assert set(out["shared_by_some_documents"]) == set(out["dictionary_concept_overlap"]) - set(out["shared_by_all_documents"])


# --------------------------------------- MCP path (section 22/29)

@pytest.mark.asyncio
async def test_mcp_research_materials_quick_honours_filters():
    from global_library_mcp import mcp_server

    adapter = _RecAdapter([KANT, HEGEL])
    svc = _service(adapter)
    client = svc.client
    previous = mcp_server._shared
    mcp_server._shared = (client, svc)
    try:
        out = await mcp_server.research_materials("哲学", libraries=["stub"], mode="quick",
                                                  author="Immanuel Kant")
        assert [m["record_id"] for m in out["materials"]] == ["k1"]
        assert out["discovery"]["planned_variants"]
    finally:
        mcp_server._shared = previous


# ------------------------------------------------- live finding (section 27 case 2)

@pytest.mark.asyncio
async def test_historical_variant_not_starved_by_pool_saturation():
    """Live finding: for 明治時代の水力発電 the historical forms
    (水力發電) duplicate the legacy b4 script variants, kept their
    late legacy position, and were skipped once high-yield concept
    translations saturated the candidate pool. Plan variants must
    execute in plan order (historical before translations) even
    when their text already exists as a legacy variant."""
    records = [_result(f"r{i}", f"水力発電史 第{i}巻", "著者", "1900", "ja") for i in range(10)]
    adapter = _RecAdapter(records)
    svc = _service(adapter)
    out = await svc.research_materials("明治時代の水力発電", libraries=["stub"], mode="standard")
    execution = out["discovery"]["variant_execution"]
    by_text = {e["text"]: e for e in execution}
    assert by_text["水力發電"]["status"] in ("executed", "cached")
    order = [e["text"] for e in execution]
    assert order.index("水力發電") < order.index("hydroelectric power")
