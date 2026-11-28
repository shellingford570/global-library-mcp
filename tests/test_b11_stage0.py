"""b11 Stage 0: b10 residual trust-boundary fixes (brief 5-14).

Every mandatory negative from the brief: forged v2 artefacts
(correct self-computed hash included), forged evidence
references, rights smuggling through nested fields, import /
restore trust forgery, independence over-counting, incomplete
comparison conditions, semantic fallback mismatch, model
resource limits, schema migration from v4.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, build_trusted_candidate, compare_facts,
    register_admitted_evidence, revoke_evidence_ref, structure_claim)
from global_library_mcp.workspace.research_artefacts import (  # noqa: E402
    import_artefact, list_artefacts, project_research_progress,
    save_artefact, validate_payload)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402
from global_library_mcp.workspace.transfer import (  # noqa: E402
    export_project, import_project)


def _store(tmp_path):
    store = WorkspaceStore(tmp_path / "ws.db")
    pid = store.create_project("p")["project_id"]
    return store, pid


# ---------------------------------------------------------- artefacts

def test_forged_v2_envelope_with_correct_hash_not_trusted(tmp_path):
    store, pid = _store(tmp_path)
    from global_library_mcp.workspace.research_artefacts import _integrity
    payload = {"claim_id": "c1",
               "assessments": [{"status": "insufficient_evidence"}]}
    env = {"kind": "b10_claim_assessment", "version": 2,
           "provenance": "server", "trust": "server_generated",
           "integrity": _integrity(payload), "payload": payload}
    store.save_note(pid, json.dumps(env), title="forged")
    arts = list_artefacts(store, pid)
    assert arts and all(a["trust"] == "user_asserted" for a in arts)
    prog = project_research_progress(store, pid)
    assert prog["claims_with_insufficient_evidence"] == 0
    assert prog["b10_artefacts"] == {}
    assert prog["untrusted_artefacts"] == 1


def test_server_artefact_still_counts(tmp_path):
    store, pid = _store(tmp_path)
    save_artefact(store, pid, "claim_assessment", "t",
                  {"claim_id": "c1",
                   "assessments": [{"status": "insufficient_evidence"}]})
    prog = project_research_progress(store, pid)
    assert prog["claims_with_insufficient_evidence"] == 1


def test_artefact_copied_to_other_project_note_not_trusted(tmp_path):
    store, pid = _store(tmp_path)
    pid2 = store.create_project("q")["project_id"]
    saved = save_artefact(store, pid, "contradiction", "t",
                          {"pairs": [{"a": "x", "b": "y",
                                      "status": "contradiction_candidate"}]})
    row = store.list_artefact_rows(pid)[0]
    payload = row["payload"]
    if not isinstance(payload, dict):
        payload = json.loads(payload)
    env = {"kind": row["kind"], "version": 2, "trust": "server_generated",
           "integrity": hashlib.sha256(
               json.dumps(payload, sort_keys=True).encode()).hexdigest(),
           "payload": payload}
    store.save_note(pid2, json.dumps(env), title="copy")
    assert project_research_progress(store, pid2)["contradiction_candidates"] == 0
    assert saved["trust"] == "server_generated"


def test_imported_artefact_downgraded(tmp_path):
    store, pid = _store(tmp_path)
    out = import_artefact(store, pid, "authority_resolution", "t",
                          {"query": "Kant", "status": "authority_verified",
                           "candidates": []})
    assert out["trust"] == "imported_unverified"
    prog = project_research_progress(store, pid)
    assert prog["b10_artefacts"] == {}


def test_nested_schema_rejects_unknown_and_status_and_text_smuggling():
    with pytest.raises(ValueError):
        validate_payload("claim_assessment",
                         {"assessments": [{"status": "supported_candidate",
                                           "surprise_field": 1}]})
    with pytest.raises(ValueError):
        validate_payload("claim_assessment",
                         {"assessments": [{"status": "totally_verified"}]})
    with pytest.raises(ValueError):
        validate_payload("contradiction",
                         {"pairs": [], "note": "x" * 500})
    with pytest.raises(ValueError):
        validate_payload("claim_assessment",
                         {"assessments": [{"status": "not_checked",
                                           "reason": "y" * 500}]})
    with pytest.raises(ValueError):
        validate_payload("claim_assessment",
                         {"config": {"mode": float("nan")}})
    with pytest.raises(ValueError):
        validate_payload("claim_assessment",
                         {"claim": {"text": "ok", "ocr_text": "smuggled"}})


def test_project_json_import_downgrades_artefacts(tmp_path):
    store, pid = _store(tmp_path)
    save_artefact(store, pid, "claim_assessment", "t",
                  {"claim_id": "c1",
                   "assessments": [{"status": "insufficient_evidence"}]})
    payload = export_project(store, pid)
    assert payload["research_artefacts"]
    store2 = WorkspaceStore(tmp_path / "ws2.db")
    result = import_project(store2, payload)
    new_pid = result["project"]["project_id"]
    assert result["imported_artefacts"] == 1
    arts = list_artefacts(store2, new_pid)
    assert arts[0]["trust"] == "imported_unverified"
    assert project_research_progress(store2, new_pid)["claims_with_insufficient_evidence"] == 0


def test_restore_downgrades_server_artefacts(tmp_path):
    store, pid = _store(tmp_path)
    save_artefact(store, pid, "claim_assessment", "t",
                  {"claim_id": "c1",
                   "assessments": [{"status": "insufficient_evidence"}]})
    store.apply_restore_trust_downgrade()
    arts = list_artefacts(store, pid)
    assert arts[0]["trust"] == "restored_unverified"
    assert project_research_progress(store, pid)["claims_with_insufficient_evidence"] == 0


def test_schema_v5_migration_from_v4(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    store = WorkspaceStore(path)
    pid = store.create_project("legacy")["project_id"]
    store.save_note(pid, "keep me", title="n")
    store.close()
    conn = sqlite3.connect(str(path))
    conn.execute("DROP TABLE research_artefacts")
    conn.execute("DELETE FROM schema_migrations WHERE version = 5")
    conn.commit(); conn.close()
    store2 = WorkspaceStore(path)
    assert store2.schema_version == 5
    assert store2.list_notes(pid)[0]["content"] == "keep me"
    assert (tmp_path / "old.db.pre-migration-v4.bak").exists()
    store2.close()


# ---------------------------------------------------------- evidence refs

def test_forged_complete_evidence_ref_refused():
    claim = structure_claim("明治25年に横浜で発電所が完成した")
    forged = {"admitted": True, "admission_source": "glm_evidence_pipeline",
              "evidence_ref": {
                  "library_id": "ndl", "record_id": "X", "page_id": "1",
                  "excerpt_hash": hashlib.sha256(b"never admitted").hexdigest(),
                  "admission_state": "admitted",
                  "document_identity_state": "upstream_confirmed",
                  "page_identity_state": "verified_mapping"},
              "document_id": "ndl:X", "library_id": "ndl",
              "record_id": "X", "page_id": "1", "text": "never admitted"}
    rows = assess_claim_evidence(claim, [forged])
    assert rows[0]["status"] == "not_checked"


def test_registry_token_roundtrip_and_tampering():
    claim = structure_claim("明治25年に横浜で発電所が完成した")
    text = "明治25年、横浜で発電所が完成した。"
    tok = register_admitted_evidence(library_id="ndl", record_id="1",
                                     page_id="1", text=text)
    cand = build_trusted_candidate(evidence_ref_token=tok, text=text)
    rows = assess_claim_evidence(claim, [cand])
    assert rows[0]["status"] != "not_checked"
    # text substitution after issuance
    bad = dict(cand); bad["text"] = "明治25年、横浜で発電所が完成した。改竄"
    rows = assess_claim_evidence(claim, [bad])
    assert rows[0]["status"] == "not_checked"
    # other record's page: ref mismatch
    bad2 = json.loads(json.dumps(cand))
    bad2["evidence_ref"]["record_id"] = "999"
    rows = assess_claim_evidence(claim, [bad2])
    assert rows[0]["status"] == "not_checked"
    # revoked token
    revoke_evidence_ref(tok)
    rows = assess_claim_evidence(claim, [cand])
    assert rows[0]["status"] == "not_checked"
    with pytest.raises(ValueError):
        build_trusted_candidate(evidence_ref_token="evr_forged", text=text)


def test_expired_token_refused():
    text = "明治25年、横浜で発電所が完成した。"
    tok = register_admitted_evidence(library_id="ndl", record_id="1",
                                     page_id="1", text=text, ttl_seconds=-1)
    with pytest.raises(ValueError):
        build_trusted_candidate(evidence_ref_token=tok, text=text)


# ---------------------------------------------------------- compare/independence

_ID = {"subject": "発電所", "predicate": "出力", "object": "発電設備",
       "place": "横浜"}


def test_independence_requires_basis():
    out = compare_facts([
        {**_ID, "value": 100, "unit": "kW", "document_id": "a:1",
         "independence_confirmed": True},
        {**_ID, "value": 100, "unit": "kW", "document_id": "b:2",
         "independence_confirmed": True,
         "independence_basis": "distinct primary sources verified"}])
    assert out["independently_confirmed_source_count"] == 1
    assert out["independence_unknown_count"] == 1


def test_independence_flag_conflict_falls_back_unknown():
    out = compare_facts([
        {**_ID, "value": 100, "unit": "kW", "document_id": "a:1",
         "independence_confirmed": True,
         "independence_basis": "x", "dependent_on": "b:2"},
        {**_ID, "value": 100, "unit": "kW", "document_id": "b:2"}])
    assert out["independently_confirmed_source_count"] == 0
    assert out["independence_flag_conflicts"] == 1
    assert out["independence_unknown_count"] == 2


def test_compare_missing_conditions_insufficient():
    out = compare_facts([
        {"value": 100, "unit": "kW", "document_id": "a:1"},
        {"value": 200, "unit": "kW", "document_id": "b:2"}])
    assert out["pairs"][0]["status"] == "insufficient_context"


def test_compare_nonfinite_and_negation():
    out = compare_facts([
        {**_ID, "value": float("inf"), "unit": "kW", "document_id": "a:1"},
        {**_ID, "value": 100, "unit": "kW", "document_id": "b:2"}])
    assert out["pairs"][0]["status"] == "insufficient_context"
    out = compare_facts([
        {**_ID, "value": 100, "unit": "kW", "document_id": "a:1"},
        {**_ID, "value": 100, "unit": "kW", "document_id": "b:2",
         "negated": True}])
    assert out["pairs"][0]["status"] == "contradiction_candidate"
    out = compare_facts([
        {**_ID, "value": 100, "unit": "kW", "document_id": "a:1",
         "approximate": True},
        {**_ID, "value": 105, "unit": "kW", "document_id": "b:2",
         "approximate": True}])
    assert out["pairs"][0]["status"] == "insufficient_context"


# ---------------------------------------------------------- semantic fallback

@pytest.mark.asyncio
async def test_quick_semantic_fallback_actually_ranks_lexically():
    import httpx
    from global_library_mcp.adapters.base import LibraryAdapter
    from global_library_mcp.models import SearchResult
    from global_library_mcp.service import LibraryService

    class Adapter(LibraryAdapter):
        library_id = "stub"; library_name = "Stub"
        supports_in_document_search = False
        def __init__(self):
            pass
        async def search(self, query, limit=10):
            return [SearchResult(library_id="stub", library_name="Stub",
                                 record_id="irr", title="鉄道の歴史",
                                 author="著者", date="1900", language="ja",
                                 landing_url="https://example.org/irr", raw={}),
                    SearchResult(library_id="stub", library_name="Stub",
                                 record_id="rel", title="蒸気機関の発達",
                                 author="著者", date="1900", language="ja",
                                 landing_url="https://example.org/rel", raw={})]

    svc = LibraryService(httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    svc.adapters = {"stub": Adapter()}
    svc.default_libraries = ["stub"]
    out = await svc.research_materials("蒸気機関", libraries=["stub"],
                                       mode="quick", ranking_mode="semantic",
                                       expand_multilingual=False,
                                       expand_historical=False)
    ranking = out["ranking"]
    assert ranking["effective_ranking_mode"] == "lexical"
    assert ranking["semantic_applied"] is False
    assert ranking["fallback_reason"]
    ids = [m["record_id"] for m in out["materials"]]
    assert ids[0] == "rel", ids


# ---------------------------------------------------------- model resources

@pytest.mark.asyncio
async def test_encode_async_concurrency_cap_and_queue():
    from global_library_mcp.semantic_local import (
        LocalSemanticBackend, MAX_CONCURRENT_INFERENCE)
    backend = object.__new__(LocalSemanticBackend)
    state = {"cur": 0, "peak": 0}
    lock = threading.Lock()

    def slow_encode(texts):
        with lock:
            state["cur"] += 1
            state["peak"] = max(state["peak"], state["cur"])
        time.sleep(0.15)
        with lock:
            state["cur"] -= 1
        return [[1.0] + [0.0] * 383 for _ in texts]
    backend.encode = slow_encode
    await asyncio.gather(*[backend.encode_async(["x"]) for _ in range(6)])
    assert state["peak"] <= MAX_CONCURRENT_INFERENCE


def test_cosine_rejects_invalid_vectors():
    from global_library_mcp.semantic_local import cosine_scores
    with pytest.raises(ValueError):
        cosine_scores([1.0, float("nan")], [[1.0, 0.0]])
    with pytest.raises(ValueError):
        cosine_scores([1.0, 0.0], [[1.0, 0.0, 0.0]])
