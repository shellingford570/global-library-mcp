"""b11 final-review regression tests.

Each test reproduces one external-review finding (brief section
number in the name/docstring) and pins the fixed behaviour.
"""
from __future__ import annotations

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
