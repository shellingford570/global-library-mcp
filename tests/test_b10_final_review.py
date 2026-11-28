"""b10 final-review regression tests (brief sections 3-29).

Each test pins a defect reproduced BEFORE the fix on HEAD
dc8d794 (see docs/b10-final-review.md and the reproduction
record). Synthetic semantic backends are used for the service
path; the real MiniLM model is exercised only by
eval/b10_final_eval.py, never by mandatory CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import global_library_mcp.service as _LS  # noqa: F401,E402  (import order)

import httpx  # noqa: E402
import pytest  # noqa: E402

from global_library_mcp import authority, research  # noqa: E402
from global_library_mcp.adapters.base import LibraryAdapter  # noqa: E402
from global_library_mcp.models import SearchResult  # noqa: E402
from global_library_mcp.research import build_trusted_candidate  # noqa: E402
from global_library_mcp.semantic_local import (  # noqa: E402
    SemanticBackendUnavailable, verify_model_dir)
from global_library_mcp.service import LibraryService, adaptive_stop_allowed  # noqa: E402
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    import_artefact, list_artefacts, project_relationship_graph,
    project_research_progress, save_artefact)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


# ------------------------------------------------------------------ fixtures

def _result(record_id, title, author=None, date=None, language=None):
    return SearchResult(library_id="stub", library_name="Stub",
                        record_id=record_id, title=title, author=author,
                        date=date, language=language,
                        landing_url=f"https://example.org/{record_id}", raw={})


class _Adapter(LibraryAdapter):
    library_id = "stub"
    library_name = "Stub"
    supports_in_document_search = False

    def __init__(self, records):
        self.records = records

    async def search(self, query, limit=10):
        return list(self.records)


def _service(records, backend=None):
    svc = LibraryService(httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    svc.adapters = {"stub": _Adapter(records)}
    svc.default_libraries = ["stub"]
    if backend is not None:
        svc._semantic_backend = backend
    return svc


class _SyntheticBackend:
    """Deterministic stand-in: NOT the real model."""
    model_id = "synthetic-test-backend"
    model_revision = "test-1"
    dimension = 2

    def encode(self, texts):
        return [[1.0, 0.0] if "蒸気" in t else [0.0, 1.0] for t in texts]


# ------------------------------------------------------- semantic (sec. 4-6)

@pytest.mark.asyncio
async def test_semantic_mode_actually_applies_scores():
    svc = _service([_result("a", "鉄道の歴史", "著者甲", "1900", "ja"),
                    _result("b", "蒸気機関の発達", "著者乙", "1900", "ja")],
                   backend=_SyntheticBackend())
    out = await svc.collect_evidence("蒸気機関", libraries=["stub"],
                                     ranking_mode="semantic")
    ranking = out["search"]["ranking"]
    assert ranking["requested_ranking_mode"] == "semantic"
    assert ranking["effective_ranking_mode"] == "semantic"
    assert ranking["semantic_applied"] is True
    assert ranking["model_id"] == "synthetic-test-backend"
    assert out["search"]["results"][0]["record_id"] == "b"
    assert any("semantic relevance" in r
               for r in out["search"]["results"][0].get("ranking_reasons", []))


@pytest.mark.asyncio
async def test_semantic_mode_without_model_falls_back_with_reason():
    svc = _service([_result("a", "鉄道の歴史", "著者甲", "1900", "ja")])
    out = await svc.collect_evidence("蒸気機関", libraries=["stub"],
                                     ranking_mode="semantic")
    ranking = out["search"]["ranking"]
    assert ranking["semantic_applied"] is False
    assert ranking["effective_ranking_mode"] == "lexical"
    assert ranking["fallback_reason"]


@pytest.mark.asyncio
async def test_legacy_mode_never_claims_semantic():
    svc = _service([_result("a", "鉄道の歴史", "著者甲", "1900", "ja")],
                   backend=_SyntheticBackend())
    out = await svc.collect_evidence("蒸気機関", libraries=["stub"])
    ranking = out["search"]["ranking"]
    assert ranking["effective_ranking_mode"] == "legacy"
    assert ranking["semantic_applied"] is False


def test_model_dir_hash_verification(tmp_path):
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "model_quint8_avx2.onnx").write_bytes(b"corrupt")
    (tmp_path / "tokenizer.json").write_bytes(b"{}")
    with pytest.raises(SemanticBackendUnavailable):
        verify_model_dir(tmp_path)


def test_backend_singleton(monkeypatch, tmp_path):
    import global_library_mcp.semantic_local as sl
    sl.reset_backend_cache()
    monkeypatch.setenv("GLM_SEMANTIC_MODEL_DIR", str(tmp_path))
    assert sl.get_local_backend() is None  # missing files
    assert sl.backend_unavailable_reason()
    sl.reset_backend_cache()


# ------------------------------------------------------- authority (sec. 7-10)

def test_local_lexicon_never_verifies():
    res = authority.AuthorityResolver().resolve_person(
        "Immanuel Kant", birth_year=1724, death_year=1804)
    assert res.status == "authority_candidate"


def test_fetched_official_record_can_verify():
    from global_library_mcp.authority import AuthorityRecord

    class FakeGND:
        name = "gnd"

        def search_person(self, name, birth_year=None):
            return [AuthorityRecord(
                authority_id="gnd:118559796", authority_source="gnd",
                entity_type="person", canonical_name="Immanuel Kant",
                birth_year=1724, death_year=1804, fetched=True,
                external_identifiers={"gnd": "118559796"})]

    res = authority.AuthorityResolver(live_sources=[FakeGND()]).resolve_person(
        "Immanuel Kant", birth_year=1724, death_year=1804)
    assert res.status == "authority_verified"


def test_same_gnd_id_conflicting_years_detected():
    from global_library_mcp.authority import AuthorityRecord

    class FakeGND:
        name = "gnd"

        def search_person(self, name, birth_year=None):
            return [
                AuthorityRecord(authority_id="gnd:118559796", authority_source="gnd",
                                entity_type="person", canonical_name="Immanuel Kant",
                                birth_year=1724, fetched=True,
                                external_identifiers={"gnd": "118559796"}),
                AuthorityRecord(authority_id="gnd:118559796", authority_source="gnd",
                                entity_type="person", canonical_name="Immanuel Kant",
                                birth_year=1700, fetched=True,
                                external_identifiers={"gnd": "118559796"})]

    res = authority.AuthorityResolver(live_sources=[FakeGND()]).resolve_person(
        "Immanuel Kant", birth_year=1724)
    assert res.status == "conflicting_authorities"


def test_forged_external_id_in_lexicon_does_not_verify():
    # A lexicon entry carrying a GND number is unverified data.
    res = authority.AuthorityResolver().resolve_person(
        "夏目漱石", birth_year=1867, death_year=1916)
    assert res.status != "authority_verified"
    assert res.candidates[0].record.external_identifiers.get("gnd") == "118785737"


def test_gnd_query_injection_is_neutralised():
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return {"member": []}

    src = authority.GndSource(fetch=fake_fetch)
    src.search_person('Kant" OR dateOfBirth:1900* AND preferredName:(*')
    url = captured["url"]
    assert "dateOfBirth:1900*" not in url.split("q=")[1].split("&")[0].replace(
        "%3A", ":").replace("%22", '"') or True  # raw check below
    from urllib.parse import unquote
    q = unquote(url.split("q=")[1].split("&")[0])
    assert q.count("preferredName:") == 1
    # the user input is a single quoted phrase value: operators
    # inside it are literal text, not query syntax
    assert q.startswith('preferredName:"') and q.endswith('"')


def test_identify_edition_is_candidate_only():
    ed = authority.identify_edition("work:kritik-reinen-vernunft", 1781)
    assert ed["status"] == "edition_candidate"
    assert ed["basis"] == "publication_year_only"


# ------------------------------------------------- editions/dedupe/stop (11-12)

@pytest.mark.asyncio
async def test_different_editions_both_kept():
    svc = _service([
        _result("k1781", "Kritik der reinen Vernunft", "Kant, Immanuel", "1781", "de"),
        _result("k1787", "Kritik der reinen Vernunft", "Kant, Immanuel", "1787", "de")])
    out = await svc.research_materials("純粋理性批判", libraries=["stub"],
                                       mode="quick")
    assert {m["record_id"] for m in out["materials"]} == {"k1781", "k1787"}


def test_adaptive_stop_blocked_by_intent_and_filters():
    assert adaptive_stop_allowed("蒸気機関の歴史", None, None)[0] is True
    assert adaptive_stop_allowed("純粋理性批判の版を比較", None, None)[0] is False
    assert adaptive_stop_allowed("蒸気機関", {"author": "x"}, None)[0] is False
    assert adaptive_stop_allowed("蒸気機関", None, ["ndl"])[0] is False


# ------------------------------------------------------- claims (sec. 13-16)

def test_forged_admitted_flag_refused():
    claim = research.structure_claim("明治25年に横浜で発電所が完成した")
    rows = research.assess_claim_evidence(claim, [{
        "admitted": True, "document_id": "fake", "page_id": "1",
        "text": "明治25年 横浜 発電所 完成"}])
    assert rows[0]["status"] == "not_checked"
    assert "caller-asserted" in rows[0]["reason"]


def test_trusted_candidate_requires_complete_ref():
    claim = research.structure_claim("明治25年に横浜で発電所が完成した")
    # b11 Stage 0: candidates are built from registry-issued
    # tokens only; tampering with the reference breaks the match.
    from global_library_mcp.research import register_admitted_evidence
    _tok = register_admitted_evidence(
        library_id="ndl", record_id="1", page_id="1",
        text="明治25年 横浜 発電所",
        document_identity_state="upstream_confirmed",
        page_identity_state="verified_mapping", admission_state="admitted")
    cand = build_trusted_candidate(evidence_ref_token=_tok,
                                   text="明治25年 横浜 発電所")
    cand["evidence_ref"].pop("page_id")
    rows = research.assess_claim_evidence(claim, [cand])
    assert rows[0]["status"] == "not_checked"


def test_compare_kw_vs_mw_not_consistent():
    out = research.compare_facts([
        {"value": 100, "unit": "kW", "document_id": "a",
         "subject": "発電所", "predicate": "出力", "object": "発電設備", "place": "横浜"},
        {"value": 100, "unit": "MW", "document_id": "b",
         "subject": "発電所", "predicate": "出力", "object": "発電設備", "place": "横浜"}])
    # 100 kW != 100 MW after normalisation - a contradiction
    # CANDIDATE (never consistent, never confirmed).
    assert out["pairs"][0]["status"] == "contradiction_candidate"
    assert out["pairs"][0]["converted"]["a_base"] == 100_000.0
    assert out["pairs"][0]["converted"]["b_base"] == 100_000_000.0


def test_compare_unit_conversion_can_reconcile():
    out = research.compare_facts([
        {"value": 1, "unit": "MW", "document_id": "a",
         "subject": "発電所", "predicate": "出力", "object": "発電設備", "place": "横浜"},
        {"value": 1000, "unit": "kW", "document_id": "b",
         "subject": "発電所", "predicate": "出力", "object": "発電設備", "place": "横浜"}])
    assert out["pairs"][0]["status"] == "consistent_candidate"


def test_compare_different_place_not_contradiction():
    out = research.compare_facts([
        {"value": 10, "unit": "hp", "document_id": "a", "place": "東京",
         "subject": "発電所", "predicate": "出力", "object": "発電設備"},
        {"value": 20, "unit": "hp", "document_id": "b", "place": "大阪",
         "subject": "発電所", "predicate": "出力", "object": "発電設備"}])
    assert out["pairs"][0]["status"] == "differing_scope"


def test_independence_never_overcounted():
    out = research.compare_facts([
        {"value": 1, "unit": "kw", "document_id": "a", "library_id": "ndl",
         "record_id": "1"},
        {"value": 1, "unit": "kw", "document_id": "b", "library_id": "ia",
         "record_id": "2"}])
    assert out["distinct_document_count"] == 2
    assert out["independently_confirmed_source_count"] == 0
    assert out["independence_unknown_count"] == 2
    assert out["independent_source_count"] is None


# ------------------------------------------------------- artefacts (sec. 17-19)

def _store(tmp_path):
    store = WorkspaceStore(tmp_path / "ws.db")
    project = store.create_project("p")
    return store, project["project_id"]


def test_artefact_schema_rejects_unknown_fields_and_text(tmp_path):
    store, pid = _store(tmp_path)
    with pytest.raises(ValueError):
        save_artefact(store, pid, "contradiction", "x", {"bogus": 1})
    with pytest.raises(ValueError):
        save_artefact(store, pid, "contradiction", "x",
                      {"pairs": [], "note": "n", "ocr_text": "full text"})
    with pytest.raises(ValueError):
        save_artefact(store, pid, "contradiction", "x", ["not-a-dict"])


def test_manual_note_cannot_forge_verified_progress(tmp_path):
    store, pid = _store(tmp_path)
    import json as _json
    forged = {"kind": "b10_authority_resolution", "version": 1,
              "payload": {"status": "authority_verified"}}
    store.save_note(pid, _json.dumps(forged), title="forged")
    progress = project_research_progress(store, pid)
    # The forged note is user-asserted: it must NOT reduce the
    # unverified tally or count as a server artefact.
    assert progress["unverified_authority_candidates"] == 0
    assert progress["untrusted_artefacts"] == 1
    arts = list_artefacts(store, pid)
    assert arts[0]["trust"] == "user_asserted"


def test_imported_artefact_downgraded(tmp_path):
    store, pid = _store(tmp_path)
    import_artefact(store, pid, "authority_resolution", "imp",
                    {"query": "Kant", "status": "authority_verified"})
    arts = list_artefacts(store, pid)
    assert arts[0]["trust"] == "imported_unverified"
    progress = project_research_progress(store, pid)
    assert progress["unverified_authority_candidates"] == 0
    assert progress["untrusted_artefacts"] == 1


def test_artefact_cross_project_reference_refused(tmp_path):
    store, pid = _store(tmp_path)
    other = store.create_project("other")
    store.save_document(other["project_id"], "ndl", "999", {"title": "X"})
    with pytest.raises(ValueError):
        save_artefact(store, pid, "ranking_explanation", "x", {
            "query": "q", "ranking": {},
            "record_refs": [{"library_id": "ndl", "record_id": "999"}]})


def test_graph_caps_and_aggregation(tmp_path):
    store, pid = _store(tmp_path)
    for i in range(12):
        store.save_document(pid, "ndl", str(i), {
            "title": f"doc{i}", "work_id_candidate": "work:x"})
    graph = project_relationship_graph(store, pid)
    assert any(n["type"] == "group" for n in graph["nodes"])
    assert len(graph["edges"]) <= 500
    assert "omitted_edges" in graph


@pytest.mark.asyncio
async def test_standard_mode_adaptive_stop_path_does_not_crash():
    # Regression: the final-review stop guard referenced an
    # unbound variable when no bibliographic filter was present
    # (found by the stop A/B probe, 2026-11-28).
    svc = _service([
        _result("k1", "Kritik der reinen Vernunft", "Kant, Immanuel", "1781", "de"),
        _result("k2", "Kritik der reinen Vernunft", "Kant, Immanuel", "1787", "de"),
        _result("k3", "Kritik der reinen Vernunft", "Kant, Immanuel", "1781", "de"),
        _result("k4", "Kritik der reinen Vernunft", "Kant, Immanuel", "1787", "de")])
    out = await svc.research_materials("純粋理性批判の版を比較したい",
                                       libraries=["stub"], mode="standard")
    assert out["materials"]  # comparison intent: full sweep, no crash
    assert not any(e.get("status") == "adaptive_stop"
                   for e in out.get("stage_log", []))
