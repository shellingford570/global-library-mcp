"""b6 Multilingual Research regression tests.

Fixture/unit level: language model, historical scripts, lexicon,
expansion engine, resolution refusals, DDB->BSB handoff
extraction, discovery ranking explanations, multilingual
comparison states, LoC newspaper issue discovery, and the
service-level discovery output of research_materials.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from global_library_mcp.service import LibraryService as _LS  # noqa: F401,E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from global_library_mcp import lexicon as lexicon_mod  # noqa: E402
from global_library_mcp.compare import concept_overlap  # noqa: E402
from global_library_mcp.discovery import analyze_discovery_query, detect_language  # noqa: E402
from global_library_mcp.expansion import QueryExpansionEngine  # noqa: E402
from global_library_mcp.handoff import extract_bsb_candidate, titles_correspond  # noqa: E402
from global_library_mcp.models import SearchResponse, SearchResult  # noqa: E402
from global_library_mcp.ranking import score_item  # noqa: E402
from global_library_mcp.resolution import resolve_author, resolve_work  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402


# -- language model (section 5) --------------------------------

def test_language_detection_four_languages():
    assert detect_language("明治時代の水力発電技術")["language"] == "ja"
    assert detect_language("history of the steam engine in the nineteenth century")["language"] == "en"
    assert detect_language("Die Dampfmaschine und ihre Anwendung in der Industrie")["language"] == "de"
    assert detect_language("La machine à vapeur et la Révolution française")["language"] == "fr"


def test_language_short_proper_noun_is_unknown():
    # A bare name must not be forced into a language.
    assert detect_language("Kant")["unknown"] is True
    assert detect_language("Charles Darwin")["unknown"] is True


def test_language_mixed_query():
    result = detect_language("Kritik der reinen Vernunft について知りたい")
    assert result["language"] == "ja"
    assert result["signals"]["de"] > 0  # the German title is seen, not erased


def test_german_concept_extraction_not_ascii_only():
    analysis = analyze_discovery_query("Erkenntnistheorie und Naturwissenschaft")
    assert analysis.query_language["language"] == "de"
    assert any("Erkenntnistheorie" in t for t in analysis.terms)


# -- lexicon (section 7) ----------------------------------------

def test_lexicon_loads_and_is_sized():
    data = lexicon_mod.load_lexicon()
    total = len(data["concepts"]) + len(data["authors"]) + len(data["works"])
    assert total >= 90
    for concept in data["concepts"]:
        assert concept["source"] and concept["verification_status"]


def test_lexicon_near_synonyms_stay_distinct():
    data = lexicon_mod.load_lexicon()
    hydro = next(c for c in data["concepts"] if c["concept_id"] == "concept:hydroelectric-power")
    # water power is a related concept AND an excluded confusion:
    # related enough to suggest, never identical.
    assert "concept:water-power" in hydro["related"]
    assert "concept:water-power" in hydro["excluded_confusions"]


# -- expansion engine (sections 8-11, 15) ------------------------

def test_expansion_steam_engine_matches_brief_example():
    plan = QueryExpansionEngine().expand(analyze_discovery_query("蒸気機関"), mode="deep")
    texts = {v["text"] for v in plan["variants"]}
    assert {"蒸氣機關", "steam engine", "steam-engine", "Dampfmaschine", "machine à vapeur"} <= texts


def test_expansion_historical_kana():
    plan = QueryExpansionEngine().expand(analyze_discovery_query("學問のすゝめ"), mode="deep")
    assert any("すすめ" in v["text"] for v in plan["variants"])


def test_expansion_caps_and_dedupes():
    plan = QueryExpansionEngine().expand(analyze_discovery_query("蒸気機関"), mode="quick")
    assert len(plan["variants"]) <= 3
    texts = [v["text"] for v in plan["variants"]]
    assert len(texts) == len(set(texts))
    assert "蒸気機関" not in texts  # the original is not a variant


def test_expansion_can_be_disabled():
    plan = QueryExpansionEngine().expand(
        analyze_discovery_query("蒸気機関"), mode="deep", expand_multilingual=False)
    kinds = {v["kind"] for v in plan["variants"]}
    assert "concept_translation" not in kinds
    assert any(s["reason"] == "multilingual expansion disabled" for s in plan["skipped"])


def test_expansion_ambiguous_author_not_expanded():
    plan = QueryExpansionEngine().expand(analyze_discovery_query("Müller"), mode="deep")
    assert not any(v["kind"] == "original_title" for v in plan["variants"])
    assert any("ambiguous author" in s["reason"] for s in plan["skipped"])


def test_expansion_german_compound_split_is_conservative():
    plan = QueryExpansionEngine().expand(analyze_discovery_query("Eisenbahngeschichte"), mode="deep")
    assert any(v["kind"] == "compound_split" for v in plan["variants"])
    plan2 = QueryExpansionEngine().expand(analyze_discovery_query("Kant"), mode="deep")
    assert not any(v["kind"] == "compound_split" for v in plan2["variants"])


# -- resolution refusals (sections 12-13) -------------------------

def test_resolve_work_refuses_author_mismatch():
    result = resolve_work("Critique of Pure Reason", "Georg Wilhelm Friedrich Hegel")
    assert result["work_id"] is None and result["status"] == "refused_author_mismatch"


def test_resolve_work_links_translated_title():
    result = resolve_work("資本論", "マルクス")
    assert result["work_id"] == "work:das-kapital" and result["status"] == "candidate_exact_title_and_author"


def test_resolve_author_refuses_shared_surname():
    assert resolve_author("Müller")["status"] == "refused_ambiguous_surname"
    assert resolve_author("Darwin")["status"] == "refused_ambiguous_surname"
    assert resolve_author("Charles Darwin")["author_id"] == "author:darwin"
    assert resolve_author("Alfred Weber")["author_id"] == "author:weber-alfred"


def test_same_name_authors_stay_distinct():
    # Max Weber and Alfred Weber share a surname, never an identity.
    assert resolve_author("Max Weber")["author_id"] != resolve_author("Alfred Weber")["author_id"]


# -- DDB -> BSB handoff (section 17) ------------------------------

_BSB_RAW = {"provider_id": ["PE423JPDSCU6C72BAC2PUBOHAINDRGFO", "00005860"],
            "dataset_label": "Hauptportal: 1689t - BSB München (00005860) - MARC",
            "view": ["Reuleaux, Franz (Verfasser)", "urn:nbn:de:bvb:12-bsb11650472-5"]}


def test_handoff_extracts_from_official_urn():
    result = extract_bsb_candidate(_BSB_RAW)
    assert result["status"] == "candidate" and result["bsb_object_id"] == "bsb11650472"


def test_handoff_refuses_provider_mismatch():
    raw = {"provider_id": ["SOMEONEELSE"], "dataset_label": "A dataset about BSB holdings",
           "view": ["urn:nbn:de:bvb:12-bsb11650472-5"]}
    assert extract_bsb_candidate(raw)["status"] == "refused_provider_mismatch"


def test_handoff_no_identifier_no_candidate():
    raw = {"provider_id": ["00005860"], "dataset_label": "BSB (00005860)", "view": ["no identifiers here"]}
    assert extract_bsb_candidate(raw)["status"] == "no_candidate"


def test_handoff_titles_correspond():
    assert titles_correspond("Kurzgefaßte Geschichte der Dampfmaschine",
                             "Kurzgefasste Geschichte der Dampfmaschine")
    assert not titles_correspond("Die Dampfmaschine", "A Complete History of English Gardening")


# -- discovery ranking explanations (section 19) -------------------

def test_ranking_reasons_and_ocr_is_auxiliary():
    analysis = analyze_discovery_query("カントの認識論")
    with_ocr = SimpleNamespace(title="純粋理性批判", author="カント", subjects=[], year=1914,
                               language="ja", ocr=True, material_type="book",
                               library_id="ndl", record_id="x")
    without_ocr = SimpleNamespace(title="純粋理性批判", author="カント", subjects=[], year=1914,
                                  language="ja", ocr=False, material_type="book",
                                  library_id="ndl", record_id="y")
    s1, r1 = score_item(analysis, with_ocr, {})
    s2, _ = score_item(analysis, without_ocr, {})
    assert r1 and 0 < s1 - s2 <= 0.5  # OCR is a small bonus, never a gate


def test_ranking_era_outside_is_penalised_not_hidden():
    analysis = analyze_discovery_query("19世紀の天文学")
    item = SimpleNamespace(title="現代天文学入門", author="", subjects=[], year=2020,
                           language="ja", ocr=False, material_type="book",
                           library_id="ndl", record_id="z")
    _score, reasons = score_item(analysis, item, {})
    assert any("outside the requested era" in r for r in reasons)


# -- multilingual comparison (section 25) --------------------------

def test_concept_overlap_is_dictionary_only():
    result = concept_overlap({
        "en-doc": "The steam engine changed industry and the railway.",
        "de-doc": "Die Dampfmaschine veränderte die Industrie und die Eisenbahn.",
    })
    assert "concept:steam-engine" in result["dictionary_concept_overlap"]
    assert result["semantic_comparison"] == "not_checked"


# -- LoC newspaper issues (section 18) ------------------------------

@pytest.mark.asyncio
async def test_find_ca_issues_builds_issue_ids(monkeypatch):
    import global_library_mcp.adapters.loc as loc_mod

    async def fake_get_json(client, url, **kwargs):
        assert url == "https://www.loc.gov/search/"
        return {"results": [
            {"id": "http://www.loc.gov/item/sn83030214/", "title": "New-York Tribune (New York [N.Y.]) 1866-1924"},
            {"id": "http://www.loc.gov/item/sn83030214/1907-01-01/ed-1/", "title": "New-York tribune, January 1, 1907"},
            {"id": "http://www.loc.gov/item/sn99999999/1907-01-01/ed-1/", "title": "A different paper entirely"},
        ]}

    monkeypatch.setattr(loc_mod, "get_json", fake_get_json)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        service = LibraryService(client)
        result = await service.newspaper_issues("sn83030214")
    assert result["issue_count"] == 1
    assert result["issues"][0]["issue_id"] == "sn83030214/1907-01-01/ed-1"


@pytest.mark.asyncio
async def test_find_ca_issues_rejects_bad_lccn():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        service = LibraryService(client)
        with pytest.raises(Exception):
            await service.newspaper_issues("not-an-lccn!!")


# -- service-level discovery output (sections 15/16/20/21) ---------

def _ddb_result() -> SearchResult:
    return SearchResult(library_id="ddb", library_name="DDB", record_id="DDB1",
                        title="Kurzgefaßte Geschichte der Dampfmaschine",
                        author="Reuleaux, Franz", date="1891", language="de",
                        raw=_BSB_RAW)


def _ia_result() -> SearchResult:
    return SearchResult(library_id="internet-archive", library_name="IA", record_id="IA1",
                        title="The Steam Engine and Its Inventors",
                        author="Robert L. Galloway", date="1881", language="en", raw={})


@pytest.mark.asyncio
async def test_research_materials_discovery_block(monkeypatch):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        service = LibraryService(client)

        async def fake_search(query, libraries=None, limit=10):
            return SearchResponse(query=query, results=[_ddb_result(), _ia_result()], errors=[])

        monkeypatch.setattr(service, "search", fake_search)
        result = await service.research_materials("蒸気機関の歴史", libraries=["ddb", "internet-archive"])
    assert result["discovery"] is not None
    variants = {v["text"] for v in result["discovery"]["planned_variants"]}
    assert "Dampfmaschine" in variants
    ddb_material = next(m for m in result["materials"] if m["library_id"] == "ddb")
    assert ddb_material["bsb_handoff"]["bsb_object_id"] == "bsb11650472"
    assert ddb_material["bsb_handoff"]["verified"] is False
    assert any(m.get("matched_variant") for m in result["materials"])


@pytest.mark.asyncio
async def test_research_materials_year_filter_reports_metadata_missing(monkeypatch):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        service = LibraryService(client)

        async def fake_search(query, libraries=None, limit=10):
            return SearchResponse(query=query, results=[_ddb_result(), _ia_result()], errors=[])

        monkeypatch.setattr(service, "search", fake_search)
        result = await service.research_materials(
            "steam engine", libraries=["ddb", "internet-archive"], year_from=1890, year_to=1900)
    assert result["filters"]["applied_local"] == ["publication_year_range"]
    titles = [m["title"] for m in result["materials"]]
    assert any("Dampfmaschine" in t for t in titles)       # 1891 kept
    assert not any("Steam Engine and Its Inventors" in t for t in titles)  # 1881 filtered out
