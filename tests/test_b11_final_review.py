"""b11 final-review regression tests.

Each test reproduces one external-review finding (brief section
number in the name/docstring) and pins the fixed behaviour.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

import pytest  # noqa: E402

from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, build_trusted_candidate,
    evidence_ref_status, evidence_registry_stats,
    register_admitted_evidence, revoke_evidence_ref,
    revoke_session_evidence_refs, structure_claim)

_PIPE = dict(document_identity_state="upstream_confirmed",
             page_identity_state="verified_mapping",
             admission_state="admitted")
_TEXT = "明治25年、横浜で発電所が完成した。"
_CLAIM = "明治25年に横浜で発電所が完成した"


def _issue(**kw):
    args = dict(library_id="ndl", record_id="1", page_id="1",
                text=_TEXT, **_PIPE)
    args.update(kw)
    return register_admitted_evidence(**args)


def _assess(cand, store=None):
    return assess_claim_evidence(structure_claim(_CLAIM), [cand],
                                 store=store)[0]


# -- section 3: registration derives state from the actual pipeline ---------

def test_register_without_identity_states_is_reference_only():
    tok = register_admitted_evidence(library_id="ndl", record_id="1",
                                     page_id="1", text=_TEXT)
    cand = build_trusted_candidate(**{"evidence_ref_token": tok}, text=_TEXT)
    row = _assess(cand)
    assert row["status"] == "not_checked"
    assert "reference-only" in row["reason"]


def test_register_from_evidence_object_carries_real_states():
    from global_library_mcp.models import Evidence
    ev = Evidence(library_id="ndl", library_name="NDL", record_id="9",
                  title="t", page_id="3", ocr_text=_TEXT,
                  ocr_source="ndl-djvu", verified=True,
                  states={"source_verified": True,
                          "assessed_evidence": True},
                  passages=[{"passage_id": "ndl:9:3#p1",
                             "char_start": 0, "char_end": 5}])
    tok = register_admitted_evidence(evidence=ev, operation_id="op-x")
    cand = build_trusted_candidate(**{"evidence_ref_token": tok}, text=_TEXT)
    assert cand["evidence_ref"]["passage_id"] == "ndl:9:3#p1"
    assert cand["evidence_ref"]["excerpt_start"] == 0
    assert cand["evidence_ref"]["document_identity_state"] == "upstream_confirmed"
    assert _assess(cand)["status"] != "not_checked"
    # an UNVERIFIED evidence object never yields an assessable ref
    ev2 = Evidence(library_id="ndl", library_name="NDL", record_id="9",
                   title="t", page_id="4", ocr_text=_TEXT, verified=False,
                   states={"source_verified": False,
                           "assessed_evidence": False})
    tok2 = register_admitted_evidence(evidence=ev2)
    cand2 = build_trusted_candidate(**{"evidence_ref_token": tok2}, text=_TEXT)
    assert _assess(cand2)["status"] == "not_checked"


# -- section 4: the ten mandatory tamper negatives ---------------------------

def test_token_plus_other_library_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand["library_id"] = "gallica"
    assert _assess(cand)["status"] == "not_checked"


def test_token_plus_other_record_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand["record_id"] = "999"
    assert _assess(cand)["status"] == "not_checked"


def test_token_plus_other_page_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand["page_id"] = "77"
    assert _assess(cand)["status"] == "not_checked"


def test_token_plus_tampered_years_not_used():
    # caller years are user_asserted only; a year absent from the
    # registered text must not create a time signal either way
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()},
                                   text=_TEXT, years=[2500], place="火星")
    assert cand["user_asserted"] == {"years": [2500], "place": "火星"}
    assert cand["years"] is None and cand["place"] is None
    row = _assess(cand)
    assert row["status"] != "not_checked"  # assessed on the text itself
    assert "time_outside_claim_range" not in row.get("signals", [])


def test_token_plus_tampered_rights_state_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand["evidence_ref"]["rights_state"] = "public_domain"
    assert _assess(cand)["status"] == "not_checked"


def test_token_plus_missing_text_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand.pop("text")
    assert _assess(cand)["status"] == "not_checked"


def test_token_plus_nonstring_text_refused():
    cand = build_trusted_candidate(**{"evidence_ref_token": _issue()}, text=_TEXT)
    cand["text"] = ["明治25年、横浜で発電所が完成した。"]
    assert _assess(cand)["status"] == "not_checked"


# -- section 5: citation binding / current validity ---------------------------

def _store_with_citation(tmp_path):
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / "ws.db"))
    pid = store.create_project("P")["project_id"]
    doc = store.save_document(pid, "ndl", "1", {"title": "資料"})
    cit = store.save_citation(doc["saved_document_id"], {
        "page_id": "1", "citation_key": "k1",
        "original_excerpt": _TEXT, "excerpt_hash": None,
        "quotation_verification_status": "verified",
        "page_mapping_status": "verified"})
    return store, pid, doc, cit


def test_citation_bound_ref_current_then_deleted(tmp_path):
    import hashlib
    store, pid, doc, cit = _store_with_citation(tmp_path)
    # bind the stored excerpt hash so issue/use agree
    h = hashlib.sha256(_TEXT.encode()).hexdigest()
    store._conn.execute(
        "UPDATE saved_citations SET excerpt_hash = ? WHERE citation_id = ?",
        (h, cit["citation_id"]))
    store._conn.commit()
    tok = register_admitted_evidence(
        library_id="ndl", record_id="1", page_id="1", text=_TEXT,
        citation_id=cit["citation_id"], project_id=pid, **_PIPE)
    cand = build_trusted_candidate(**{"evidence_ref_token": tok}, text=_TEXT)
    assert _assess(cand, store=store)["status"] != "not_checked"
    # without the store, current validity cannot be confirmed
    assert _assess(cand)["status"] == "not_checked"
    store.delete_citation(cit["citation_id"])
    assert evidence_ref_status(tok, store)["state"] == "invalidated"
    assert _assess(cand, store=store)["status"] == "not_checked"


def test_citation_bound_ref_other_project_refused(tmp_path):
    store, pid, doc, cit = _store_with_citation(tmp_path)
    tok = register_admitted_evidence(
        library_id="ndl", record_id="1", page_id="1", text=_TEXT,
        citation_id=cit["citation_id"], project_id="another-project",
        **_PIPE)
    cand = build_trusted_candidate(**{"evidence_ref_token": tok}, text=_TEXT)
    assert _assess(cand, store=store)["status"] == "not_checked"


# -- section 6: registry capacity ---------------------------------------------

def test_registry_caps_and_session_revocation():
    stats = evidence_registry_stats()
    assert stats["max_entries"] == 4096
    toks = [register_admitted_evidence(
        library_id="ndl", record_id=str(i), page_id="1", text=_TEXT,
        session_id="sess-cap", **_PIPE) for i in range(3)]
    assert evidence_ref_status(toks[0])["state"] == "current"
    n = revoke_session_evidence_refs("sess-cap")
    assert n == 3
    assert evidence_ref_status(toks[0])["state"] == "unknown_or_revoked"
    # per-operation cap: 256
    with pytest.raises(ValueError):
        for i in range(300):
            register_admitted_evidence(
                library_id="ndl", record_id=f"op{i}", page_id="1",
                text=_TEXT, operation_id="op-cap", session_id="s2",
                **_PIPE)
    revoke_session_evidence_refs("s2")


# -- section 11: rights observation ordering ---------------------------------

def _store_doc(tmp_path, name="ws.db"):
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / name))
    pid = store.create_project("P")["project_id"]
    doc = store.save_document(pid, "ndl", "1", {"title": "資料"})
    return store, doc


def test_rights_seq_same_second_pd_then_copyright(tmp_path):
    store, doc = _store_doc(tmp_path)
    did = doc["saved_document_id"]
    store.add_rights_observation(did, "Public Domain", "public_domain",
                                 "live_fetch", "observed")
    store.add_rights_observation(did, "In Copyright", "in_copyright",
                                 "live_fetch", "observed")
    latest = store.latest_rights_observation(did)
    assert latest["category"] == "in_copyright"
    assert latest["seq"] is not None
    seqs = [r["seq"] for r in store.list_rights_observations(did)]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_rights_seq_reverse_order_server_update_wins(tmp_path):
    store, doc = _store_doc(tmp_path)
    did = doc["saved_document_id"]
    store.add_rights_observation(did, "In Copyright", "in_copyright",
                                 "live_fetch", "observed")
    store.add_rights_observation(did, "Public Domain", "public_domain",
                                 "reverify", "observed")
    # an explicit later SERVER observation is a real update
    assert store.latest_rights_observation(did)["category"] == "public_domain"


def test_rights_same_timestamp_untrusted_conflict_fails_closed(tmp_path):
    import sqlite3
    store, doc = _store_doc(tmp_path)
    did = doc["saved_document_id"]
    conn = sqlite3.connect(str(tmp_path / "ws.db"))
    # imported (non-server) rows, identical timestamps, PD last by
    # insertion: the restriction must win the tie
    conn.execute(
        "INSERT INTO rights_observations (observation_id, saved_document_id,"
        " statement, category, source, observed_at, change_status, trust, seq)"
        " VALUES ('o1', ?, 'IC', 'in_copyright', 'imported:x',"
        " '2026-01-01T00:00:00Z', 'observed', 'imported_claim', 1)", (did,))
    conn.execute(
        "INSERT INTO rights_observations (observation_id, saved_document_id,"
        " statement, category, source, observed_at, change_status, trust, seq)"
        " VALUES ('o2', ?, 'PD', 'public_domain', 'imported:x',"
        " '2026-01-01T00:00:00Z', 'observed', 'imported_claim', 2)", (did,))
    conn.commit(); conn.close()
    assert store.latest_rights_observation(did)["category"] == "in_copyright"


def test_rights_seq_migration_from_v5(tmp_path):
    import sqlite3
    store, doc = _store_doc(tmp_path)
    did = doc["saved_document_id"]
    store.add_rights_observation(did, "Public Domain", "public_domain",
                                 "live_fetch", "observed")
    store.add_rights_observation(did, "In Copyright", "in_copyright",
                                 "live_fetch", "observed")
    path = str(tmp_path / "ws.db")
    store._conn.close()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE rights_observations DROP COLUMN seq")
    conn.execute("DROP TABLE rights_seq_counter")
    conn.execute("DELETE FROM schema_migrations WHERE version = 6")
    conn.commit(); conn.close()
    from global_library_mcp.workspace.store import WorkspaceStore
    store2 = WorkspaceStore(path)
    latest = store2.latest_rights_observation(did)
    assert latest["category"] == "in_copyright"
    assert latest["seq"] == 2


# -- sections 8-10: strict artefact schemas + reference integrity ------------

def test_empty_payload_rejected():
    from global_library_mcp.workspace.research_artefacts import (
        validate_payload)
    with pytest.raises(ValueError):
        validate_payload("claim_assessment", {})


def test_nested_arbitrary_dict_rejected():
    from global_library_mcp.workspace.research_artefacts import (
        validate_payload)
    with pytest.raises(ValueError):
        validate_payload("claim_assessment", {
            "claim": {"time": {"anything": {"deep": 1}}},
            "assessments": []})


def test_nonstring_status_rejected():
    from global_library_mcp.workspace.research_artefacts import (
        validate_payload)
    with pytest.raises(ValueError):
        validate_payload("claim_assessment", {
            "assessments": [{"claim_id": "c", "status": 123}]})


def test_unknown_status_and_deep_text_key_rejected():
    from global_library_mcp.workspace.research_artefacts import (
        validate_payload)
    with pytest.raises(ValueError):
        validate_payload("claim_assessment", {
            "assessments": [{"claim_id": "c", "status": "totally_verified"}]})
    with pytest.raises(ValueError):
        validate_payload("claim_assessment", {
            "assessments": [{"claim_id": "c", "status": "not_checked",
                             "reason": "x", "ocr_text": "smuggled"}]})


def test_cross_document_ref_combination_rejected(tmp_path):
    from global_library_mcp.workspace.research_artefacts import (
        save_artefact)
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / "ws.db"))
    pid = store.create_project("P")["project_id"]
    da = store.save_document(pid, "ndl", "A", {"title": "A"})
    store.save_document(pid, "ndl", "B", {"title": "B"})
    # document A's saved_document_id + document B's record_id,
    # nested inside an assessment
    with pytest.raises(ValueError):
        save_artefact(store, pid, "claim_assessment", "t", {
            "assessments": [{
                "claim_id": "c", "status": "supported_candidate",
                "library_id": "ndl", "record_id": "B",
                "saved_document_id": da["saved_document_id"]}]})


def test_citation_ref_must_match_its_document_and_page(tmp_path):
    from global_library_mcp.workspace.research_artefacts import (
        save_artefact)
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / "ws.db"))
    pid = store.create_project("P")["project_id"]
    doc = store.save_document(pid, "ndl", "A", {"title": "A"})
    cit = store.save_citation(doc["saved_document_id"], {
        "page_id": "p1", "citation_key": "k",
        "quotation_verification_status": "verified",
        "page_mapping_status": "verified"})
    with pytest.raises(ValueError):
        save_artefact(store, pid, "claim_assessment", "t", {
            "assessments": [{
                "claim_id": "c", "status": "supported_candidate",
                "citation_id": cit["citation_id"], "page_id": "OTHER"}]})
    ok = save_artefact(store, pid, "claim_assessment", "t", {
        "assessments": [{
            "claim_id": "c", "status": "supported_candidate",
            "citation_id": cit["citation_id"], "page_id": "p1",
            "library_id": "ndl", "record_id": "A"}]})
    assert ok["trust"] == "server_generated"


# -- sections 12/16/18: graph over real store rows ---------------------------

def test_graph_question_claim_and_citation_nodes(tmp_path):
    from global_library_mcp.evidence_graph import build_project_graph
    from global_library_mcp.workspace.research_artefacts import (
        save_artefact)
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / "ws.db"))
    pid = store.create_project("P")["project_id"]
    doc = store.save_document(pid, "ndl", "R1", {"title": "Doc"})
    cit = store.save_citation(doc["saved_document_id"], {
        "page_id": "p7", "citation_key": "ndl:R1:p7",
        "quotation_verification_status": "verified",
        "page_mapping_status": "verified"})
    q = save_artefact(store, pid, "research_question", "q",
                      {"question": {"text": "Q?", "claim_id": "c1"}})
    save_artefact(store, pid, "claim_assessment", "c", {
        "claim": {"claim_id": "c1", "original_statement": "S.",
                  "question_id": q["artefact_id"]},
        "assessments": []})
    g = build_project_graph(store, pid)
    types = {n["type"] for n in g["nodes"]}
    assert {"question", "claim", "page", "citation"} <= types
    claim = [n for n in g["nodes"] if n["type"] == "claim"][0]
    assert claim["evidence_state"] == "no_evidence_registered"
    assert claim["assessment_count"] == 0
    cit_node = [n for n in g["nodes"] if n["type"] == "citation"][0]
    assert cit_node["reference_available"] is True
    assert cit_node["revalidation_required"] is False
    edges = {(e["source"].split(":")[0], e["type"]) for e in g["edges"]}
    assert ("document", "has_page") in edges
    assert ("page", "has_citation") in edges
    assert ("question", "asks_about") in edges
    # rights change: reference stays, excerpt display forbidden
    store.add_rights_observation(doc["saved_document_id"], "x",
                                  "in_copyright", "test", "changed")
    g2 = build_project_graph(store, pid)
    cn2 = [n for n in g2["nodes"] if n["type"] == "citation"][0]
    assert cn2["reference_available"] is True
    assert cn2["excerpt_display"] == "forbidden"


def test_graph_unknown_status_never_support_edge(tmp_path):
    from global_library_mcp.evidence_graph import STATUS_EDGE_MAP
    assert STATUS_EDGE_MAP.get("totally_made_up") is None
    assert set(STATUS_EDGE_MAP.values()) <= {
        "supports_candidate", "partially_supports",
        "contradicts_candidate", "contextualizes", "references",
        "insufficient_evidence", "unassessed", "unresolved_reference"}


# -- sections 20-23: report trust separation, claim display, escaping --------

def _report_store(tmp_path):
    from global_library_mcp.workspace.store import WorkspaceStore
    store = WorkspaceStore(str(tmp_path / "ws.db"))
    pid = store.create_project("P # Evil\n## Injected")["project_id"]
    doc = store.save_document(pid, "ndl", "R1", {
        "title": "Doc [x](javascript:alert(1))", "authors": "A",
        "year": "1900"})
    return store, pid, doc


def test_report_imported_not_counted_and_zero_evidence_claim_shown(tmp_path):
    from global_library_mcp.synthesis import generate_research_report
    from global_library_mcp.workspace.research_artefacts import (
        import_artefact, save_artefact)
    store, pid, doc = _report_store(tmp_path)
    save_artefact(store, pid, "claim_assessment", "empty", {
        "claim": {"claim_id": "c-empty",
                  "original_statement": "No evidence yet."},
        "assessments": []})
    import_artefact(store, pid, "claim_assessment", "imp", {
        "claim": {"claim_id": "c-imp", "original_statement": "Imported."},
        "assessments": [{"claim_id": "c-imp",
                         "status": "supported_candidate",
                         "library_id": "ndl", "record_id": "R1"}]})
    rep = generate_research_report(store, pid)
    # imported support is NOT a current claim state
    assert all(cs["claim_id"] != "c-imp" for cs in rep["claim_states"])
    assert rep["historical_claim_states"][0]["counted_as_current_evidence"] is False
    by_id = {c["claim_id"]: c for c in rep["claims"]}
    assert by_id["c-empty"]["state"] == "not_checked"
    assert by_id["c-empty"]["evidence_registered"] is False
    assert "根拠未登録" in by_id["c-empty"]["display_note"]
    assert by_id["c-imp"]["assessment_counts"]["support"] == 0
    assert by_id["c-imp"]["assessment_counts"]["historical"] == 1


def test_report_citation_mismatch_downgrades(tmp_path):
    from global_library_mcp.synthesis import generate_research_report
    from global_library_mcp.workspace.research_artefacts import (
        save_artefact)
    store, pid, doc = _report_store(tmp_path)
    cit = store.save_citation(doc["saved_document_id"], {
        "page_id": "p1", "citation_key": "k",
        "quotation_verification_status": "imported_unverified",
        "page_mapping_status": "verified"})
    save_artefact(store, pid, "claim_assessment", "c", {
        "claim": {"claim_id": "c1", "original_statement": "S."},
        "assessments": [{"claim_id": "c1",
                         "status": "supported_candidate",
                         "library_id": "ndl", "record_id": "R1",
                         "citation_id": cit["citation_id"],
                         "page_id": "p1"}]})
    rep = generate_research_report(store, pid)
    assert rep["claim_states"][0]["state"] == "revalidation_required"
    assert rep["claims"][0]["references"][0]["title"].startswith("Doc")


def test_report_markdown_injection_escaped(tmp_path):
    from global_library_mcp.synthesis import generate_research_report
    from global_library_mcp.workspace.research_artefacts import (
        save_artefact)
    store, pid, doc = _report_store(tmp_path)
    save_artefact(store, pid, "research_question", "q", {
        "question": {"text": "Q?\n# Fake heading <script>x</script>"}})
    save_artefact(store, pid, "claim_assessment", "c", {
        "claim": {"claim_id": "c1",
                  "original_statement": "S ![img](https://evil.example/x)"},
        "assessments": [{"claim_id": "c1", "status": "supported_candidate",
                         "library_id": "ndl", "record_id": "R1"}]})
    md = generate_research_report(store, pid)["markdown"]
    assert "\n# Fake heading" not in md
    assert "<script>" not in md
    assert "![img]" not in md
    # the javascript: text survives only in ESCAPED (inert) form,
    # exactly the b7 export standard: brackets/parens are escaped
    # so no link can form.
    assert "](javascript:" not in md
    assert "](https://evil.example" not in md
    headings = [ln for ln in md.splitlines() if ln.startswith("# ")]
    assert len(headings) == 1  # only the real title heading


# -- sections 28-31: research API over real HTTP ------------------------------

def test_research_api_linking_assessment_and_validation(tmp_path):
    import re
    import threading
    import urllib.error
    import urllib.request
    from http.cookiejar import CookieJar
    from http.server import ThreadingHTTPServer

    import global_library_mcp.web.server as server_mod
    from global_library_mcp.web.workspace_api import WorkspaceWebRuntime
    from global_library_mcp.workspace.store import WorkspaceStore

    store = WorkspaceStore(str(tmp_path / "ws.db"))
    ws = WorkspaceWebRuntime(store)
    old_ws = server_mod.RUNTIME.ws
    server_mod.RUNTIME.ws = ws
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(base + "/", timeout=30) as res:
            html = res.read().decode()
        csrf = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)

        def call(method, path, body=None, raw=None):
            data = raw if raw is not None else (
                json.dumps(body).encode() if body is not None else None)
            headers = {}
            if method in ("POST", "PUT", "DELETE"):
                headers["X-GLM-CSRF"] = csrf
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(base + path, data=data,
                                         method=method, headers=headers)
            try:
                with opener.open(req, timeout=60) as res:
                    return res.status, json.loads(res.read().decode() or "{}")
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode() or "{}")

        status, proj = call("POST", "/api/workspace/projects",
                            {"title": "api-test"})
        assert status == 201
        pid = proj["project_id"]
        doc = store.save_document(pid, "ndl", "R1", {"title": "Doc"})
        cit = store.save_citation(doc["saved_document_id"], {
            "page_id": "p1", "citation_key": "ndl:R1:p1",
            "quotation_verification_status": "user_entered_unverified",
            "page_mapping_status": "unverified"})
        R = f"/api/workspace/projects/{pid}/research"
        status, q = call("POST", R + "/questions", {"question": "Q?"})
        assert status == 201
        qid = q["artefact"]["artefact_id"]
        status, cl = call("POST", R + "/claims",
                          {"statement": "1900年に東京で起きた。",
                           "question_id": qid})
        assert status == 201
        aid = cl["artefact"]["artefact_id"]
        assert cl["claim"]["question_id"] == qid
        # strict validation: dict statement is NOT str()-coerced
        status, _ = call("POST", R + "/claims", {"statement": {"x": 1}})
        assert status == 422
        # unknown field (a caller-supplied admitted flag) refused
        status, _ = call("POST", R + f"/claims/{aid}/assess",
                         {"citation_ids": [cit["citation_id"]],
                          "admitted": True})
        assert status == 422
        # NaN body refused as invalid JSON
        status, _ = call("POST", R + "/questions", raw=b'{"question": NaN}')
        assert status == 400
        # link citation, then assess: unverified citation stays
        # reference-only through the frozen gate semantics
        status, linked = call("POST", R + f"/claims/{aid}/citations",
                              {"citation_id": cit["citation_id"]})
        assert status == 200 and linked["linked"] is True
        status, assessed = call("POST", R + f"/claims/{aid}/assess", {})
        assert status == 200
        assert assessed["assessments"][0]["status"] == \
            "evidence_reference_only"
        # refresh vs revalidate_references are distinct operations
        status, fr = call("POST", R + "/refresh", {})
        assert status == 200 and fr["operation"] == "refresh"
        assert fr["original_refetched"] is False
        status, rr = call("POST", R + "/revalidate_references", {})
        assert status == 200 and rr["operation"] == "revalidate_references"
        assert rr["artefacts_checked"] >= 2
        status, claims = call("GET", R + "/claims")
        assert status == 200 and len(claims["claims"]) == 1
        assert claims["claims"][0]["payload"]["assessments"]
    finally:
        httpd.shutdown()
        server_mod.RUNTIME.ws = old_ws
