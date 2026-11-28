"""Research artefacts in the Research Workspace.

b11 Stage 0 (sections 5-7): the trust boundary was rebuilt.

- Artefacts live in a DEDICATED table (schema v5) whose trust
  column is set only by server-side code paths. A payload hash
  is kept for tamper-evidence of the stored row only; it is
  NEVER proof of origin, and list/progress/graph code does not
  derive trust from any hash.
- Plain notes are NEVER artefacts. Legacy b10 note envelopes
  (v1/v2, including hand-forged ones with a correct
  self-computed SHA-256 and trust="server_generated") surface
  only as trust="user_asserted" data and cannot change
  verified tallies, progress, graphs or reports.
- Imported artefacts are stored as imported_unverified;
  restored databases downgrade server rows to
  restored_unverified (store.apply_restore_trust_downgrade).
- Payloads are validated by a RECURSIVE allowlist schema:
  per-kind top-level fields, closed nested key sets for
  assessments/pairs/claim/config/items/candidates, closed
  status vocabularies, string caps (free-text fields such as
  notes/reason/text/description/summary are capped at the
  excerpt cap so original text cannot be smuggled under
  another field name), finite numbers only, node/depth caps.
- Artefacts reference saved citations/documents BY ID only;
  original-text-bearing fields are rejected anywhere in the
  payload.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

KINDS = (
    "claim_assessment", "contradiction", "authority_resolution",
    "ranking_explanation", "research_question", "comparison_b10",
    # b11 additions (sections 42/46/49): timeline, research report
    # and semantic-search records are first-class artefacts now.
    "timeline", "research_report", "semantic_search",
)
_PREFIX = "b10_"
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_LIST_ITEMS = 100
MAX_DEPTH = 6
MAX_NODES = 2000
MAX_STR_CHARS = 2000
MAX_EXCERPT_CHARS = 200
_TEXT_BEARING_KEYS = {"ocr_text", "full_text", "page_text", "ocr",
                      "original_text", "image_url", "image_binary",
                      "raw_text", "passage_text", "image"}
_SHORT_TEXT_KEYS = {"excerpt", "quote", "notes", "note", "reason",
                    "description", "summary"}

# ---------------------------------------------------------------------------
# b11 final review (sections 8-10): COMPLETE recursive schemas.
#
# Every payload level is a closed key set (additionalProperties=
# false equivalent): unknown keys at ANY depth are refused, field
# types are exact, statuses are strings from a closed vocabulary,
# numbers are finite, and per-field string caps apply. An empty
# payload is never a valid artefact. Original-text-bearing keys
# are refused anywhere in the payload (section 10): server
# artefacts reference saved citations by id, they do not copy
# upstream text into free fields.
# ---------------------------------------------------------------------------

_STATUS_VOCAB = {
    "supported_candidate", "partially_supported",
    "conflicting_candidate", "contextual_only",
    "insufficient_evidence", "evidence_reference_only",
    "not_checked", "consistent_candidate", "differing_unit",
    "differing_time", "differing_scope", "contradiction_candidate",
    "insufficient_context", "authority_verified", "candidate",
    "ambiguous", "unresolved", "verified", "unverified",
    "revalidation_required", "reference_only",
    "confirmed_dependent", "suspected_dependent",
    "independence_unknown", "user_asserted_independence",
    "independently_reviewed_independence", "source_family_candidate",
    "imported_unverified", "restored_unverified", "user_asserted",
}
_DATE_KINDS = {"event_date", "estimated_era", "publication_date",
               "reprint_date", "translation_publication_date",
               "acquisition_date", "verification_date"}
_EXTRACTION_STATES = {"extracted", "not_extracted"}
_STR = ("str", MAX_STR_CHARS)
_STR200 = ("str", MAX_EXCERPT_CHARS)
_STRN = ("str?", MAX_STR_CHARS)
_NUM = ("num",)
_INT = ("int",)
_INTN = ("int?",)
_BOOL = ("bool",)
_STATUS = ("status",)


def _L(item: Any, max_items: int = MAX_LIST_ITEMS) -> tuple:
    return ("list", item, max_items)


def _D(keys: dict[str, Any], required: tuple[str, ...] = ()) -> tuple:
    return ("dict", keys, required)


_REF = _D({"library_id": _STR, "record_id": _STR,
           "saved_document_id": _STR}, ("library_id", "record_id"))
_EVIDENCE_REF = _D({
    "library_id": _STR, "record_id": _STR, "page_id": _STR,
    "citation_id": _STRN, "passage_id": _STRN,
    "excerpt_start": _INTN, "excerpt_end": _INTN,
    "excerpt_hash": _STR, "admission_state": _STR,
    "document_identity_state": _STR, "page_identity_state": _STR,
    "rights_state": _STRN},
    ("library_id", "record_id", "page_id", "excerpt_hash"))
_INDEPENDENCE_REVIEW = _D({"basis": _STR, "source": _STR},
                          ("basis", "source"))
_ASSESSMENT = _D({
    "claim_id": _STR, "status": _STATUS, "library_id": _STR,
    "record_id": _STR, "saved_document_id": _STR, "page_id": _STR,
    "citation_id": _STR, "document_id": _STR,
    "evidence_ref": ("dict?", _EVIDENCE_REF[1], ()),
    "signals": _L(_STR), "unconfirmed_signals": _L(_STR),
    "reason": _STR200, "independence_confirmed": _BOOL,
    "independence_basis": _STR,
    "independence_review": _INDEPENDENCE_REVIEW,
    "dependent_on": _STR}, ("status",))
_TIME = _D({"era": _STRN, "label": _STRN, "start": ("num?",),
            "end": ("num?",), "year": ("num?",),
            "years_mentioned": _L(_INT)})
_QUANTITY = _D({"value": _NUM, "raw": _STR, "unit": _STRN,
                "counter": _STRN, "start": _INT, "end": _INT})
_ENTITIES = _D({"authors": _L(_STR), "works": _L(_STR),
                "concepts": _L(_STR)})
_EXTRACTION = ("vocab_dict", set(), _EXTRACTION_STATES)
_CLAIM = _D({
    "claim_id": _STR, "original_statement": _STR, "statement": _STR,
    "text": _STR, "subject": _STR, "predicate": _STR, "object": _STR,
    "place": _STR, "unit": _STR, "value": _NUM, "relation": _STR,
    "status": _STATUS, "note": _STR200, "years": _L(_INT),
    "places": _L(_STR), "quantities": _L(_QUANTITY),
    "entities": _ENTITIES, "qualifiers": _L(_STR), "era": _STR,
    "negated": _BOOL, "time": _TIME, "quantity": _QUANTITY,
    "named_entities": _L(_STR), "source_type_required": _STR,
    "evidence_status": _STATUS, "event": _STR, "condition": _STR,
    "modality": _STR, "negation": _BOOL, "attribution": _STR,
    "uncertainty": _STR, "extraction": _EXTRACTION,
    "evidence_refs": _L(_EVIDENCE_REF), "record_refs": _L(_REF),
    "citation_refs": _L(_STR), "question_id": _STR,
    "research_question_id": _STR})
_QUESTION = _D({
    "original_question": _STR, "text": _STR, "claim_id": _STR,
    "detected_language": _STR, "research_intent": _STR,
    "subject": _STR, "predicate": _STR, "object": _STR,
    "place": _STR, "unit": _STR, "value": _NUM, "relation": _STR,
    "status": _STATUS, "note": _STR200, "entities": _ENTITIES,
    "time_range": _TIME, "author_constraints": _L(_STR),
    "work_constraints": _L(_STR),
    "numerical_constraints": _L(_QUANTITY),
    "requested_document_types": _L(_STR),
    "expected_evidence_type": _STR,
    "unresolved_ambiguities": _L(_STR)})
_PAIR = _D({
    "a": _STR, "b": _STR, "status": _STATUS, "value_a": _NUM,
    "value_b": _NUM, "unit_a": _STR, "unit_b": _STR,
    "converted": _D({"a_base": _NUM, "b_base": _NUM,
                     "family": _STR}),
    "reason": _STR200, "subject": _STR, "predicate": _STR,
    "object": _STR, "place": _STR, "year_a": _INT, "year_b": _INT,
    "library_id": _STR, "record_id": _STR}, ("status",))
_COUNTS_KEYS = {
    "evidence_item_count", "distinct_document_count",
    "distinct_library_record_count", "distinct_library_count",
    "source_family_candidate_count", "known_dependent_source_count",
    "independence_unknown_count", "independence_user_asserted_count",
    "independence_flag_conflicts",
    "independently_confirmed_source_count", "document_count",
    "independent_source_count"}
_CANDIDATE = _D({
    "name": _STR, "person_id": _STR, "author_id": _STR,
    "status": _STATUS, "score": _NUM, "birth_year": _INT,
    "death_year": _INT, "identifiers": ("str_dict",),
    "works": _L(_STR), "source": _STR, "authority_id": _STR,
    "preferred_name": _STR, "dates": _STR})
_RANKING = _D({
    "requested_ranking_mode": _STR, "effective_ranking_mode": _STR,
    "semantic_applied": _BOOL, "fallback_reason": _STRN,
    "model_id": _STRN, "model_revision": _STRN,
    "candidate_pool_size": _INT})
_ITEM = _D({
    "library_id": _STR, "record_id": _STR, "title": _STR,
    "reasons": _L(_STR), "subscores": ("num_dict",), "rank": _INT,
    "status": _STATUS, "score": _NUM})
_EVENT = _D({
    "label": _STR, "year": _NUM, "date_kind": ("vocab", _DATE_KINDS),
    "source_ref": _STR, "note": _STR200})
_SECTION = _D({"name": _STR, "title": _STR})
_CONFIG = _D({
    "ranking_mode": _STR, "model_id": _STRN,
    "model_revision": _STRN, "allocation": _STR, "version": _STR,
    "mode": _STR})
_MODEL = _D({"model_id": _STRN, "model_revision": _STRN,
             "kind": _STR})
_SETTINGS = _D({"code_version": _STR, "git_commit": _STR,
                "ranking_mode": _STR})
_STRUCT = _D({
    "intent": _STR, "research_intent": _STR, "entities": _ENTITIES,
    "era": _TIME, "constraints": _L(_STR), "ambiguities": _L(_STR),
    "subject": _STR, "predicate": _STR, "object": _STR})

_SCHEMAS: dict[str, tuple] = {
    "claim_assessment": _D({
        "claim_id": _STR, "claim": _CLAIM,
        "assessments": _L(_ASSESSMENT), "evaluated_at": _STR,
        "config": _CONFIG}, ("assessments",)),
    "contradiction": _D({
        "pairs": _L(_PAIR), "note": _STR200,
        "evaluated_at": _STR}, ("pairs",)),
    "authority_resolution": _D({
        "query": _STR, "status": _STATUS,
        "candidates": _L(_CANDIDATE), "notes": _L(_STR200),
        "evaluated_at": _STR}, ("status",)),
    "ranking_explanation": _D({
        "query": _STR, "ranking": _RANKING, "items": _L(_ITEM)},
        ("query",)),
    "research_question": _D({
        "question": ("either", [_STR, _QUESTION]),
        "structured": _STRUCT}, ("question",)),
    "comparison_b10": _D({
        "pairs": _L(_PAIR), "counts": ("num_dict", _COUNTS_KEYS),
        "note": _STR200}, ("pairs",)),
    "timeline": _D({"events": _L(_EVENT), "note": _STR200},
                   ("events",)),
    "research_report": _D({
        "report_id": _STR, "title": _STR, "sections": _L(_SECTION),
        "generated_at": _STR, "snapshot_id": _STR,
        "settings": _SETTINGS,
        "rights_observation_ids": _L(_STR)},
        ("report_id", "snapshot_id", "generated_at")),
    "semantic_search": _D({
        "query": _STR, "config": _CONFIG, "items": _L(_ITEM)},
        ("query", "items")),
}
_COMMON_FIELDS = {"record_refs": _L(_REF), "citation_refs": _L(_STR),
                  "rights_state": _STR, "model": _MODEL}
_CLAIM_FIELD_NAMES = set(_CLAIM[1].keys())


def _check(value: Any, spec: tuple, path: str, counter: list[int],
           depth: int) -> None:
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise ValueError("artefact payload has too many nodes")
    if depth > MAX_DEPTH:
        raise ValueError("artefact payload nesting too deep")
    kind = spec[0]
    if kind == "str" or kind == "str?":
        if value is None and kind == "str?":
            return
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected a string")
        if len(value) > spec[1]:
            raise ValueError(f"{path}: exceeds {spec[1]} chars")
    elif kind == "status":
        if not isinstance(value, str) or value not in _STATUS_VOCAB:
            raise ValueError(f"{path}: status outside the closed vocabulary")
    elif kind == "vocab":
        if not isinstance(value, str) or value not in spec[1]:
            raise ValueError(f"{path}: value outside the closed vocabulary")
    elif kind == "num" or kind == "num?":
        if value is None and kind == "num?":
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: expected a finite number")
        if not math.isfinite(float(value)):
            raise ValueError(f"{path}: numbers must be finite")
    elif kind == "int" or kind == "int?":
        if value is None and kind == "int?":
            return
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path}: expected an integer")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{path}: expected a boolean")
    elif kind == "list":
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected a list")
        if len(value) > spec[2]:
            raise ValueError(f"{path}: list too long")
        for i, item in enumerate(value):
            _check(item, spec[1], f"{path}[{i}]", counter, depth + 1)
    elif kind == "dict" or kind == "dict?":
        if value is None and kind == "dict?":
            return
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        keys, required = spec[1], spec[2]
        for k in value:
            if k in _TEXT_BEARING_KEYS:
                raise ValueError(
                    f"artefact payload may not carry original text "
                    f"field: {k} (reference saved citations by id)")
            if k not in keys:
                raise ValueError(f"{path}: unknown field: {k}")
        for req in required:
            if req not in value:
                raise ValueError(f"{path}: required field missing: {req}")
        for k, v in value.items():
            _check(v, keys[k], f"{path}.{k}", counter, depth + 1)
    elif kind == "either":
        for alt in spec[1]:
            try:
                _check(value, alt, path, [0], depth)
                return
            except ValueError:
                continue
        raise ValueError(f"{path}: matches no allowed shape")
    elif kind == "str_dict":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        for k, v in value.items():
            if not isinstance(v, str) or len(v) > MAX_STR_CHARS:
                raise ValueError(f"{path}.{k}: expected a string value")
    elif kind == "num_dict":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        allowed = spec[1] if len(spec) > 1 else None
        for k, v in value.items():
            if allowed is not None and k not in allowed:
                raise ValueError(f"{path}: unknown field: {k}")
            if v is not None:
                _check(v, _NUM, f"{path}.{k}", counter, depth + 1)
    elif kind == "vocab_dict":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        for k, v in value.items():
            if k not in _CLAIM_FIELD_NAMES:
                raise ValueError(f"{path}: unknown field: {k}")
            if v not in spec[2]:
                raise ValueError(f"{path}.{k}: outside the closed vocabulary")
    else:  # pragma: no cover
        raise ValueError(f"unknown schema spec {kind}")


def validate_payload(kind: str, payload: Any) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown b10 artefact kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("artefact payload must be an object")
    if not payload:
        raise ValueError("artefact payload must not be empty")
    keys = dict(_SCHEMAS[kind][1])
    keys.update(_COMMON_FIELDS)
    required = _SCHEMAS[kind][2]
    _check(payload, ("dict", keys, required), kind, [0], 0)
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("artefact payload too large")
    return payload


def reference_problems(store: Any, project_id: str,
                       payload: dict[str, Any],
                       _index: dict[str, Any] | None = None) -> list[str]:
    """Recursive reference integrity (section 9): EVERY
    reference in the payload - top level and nested inside
    assessments/pairs/events/items - must be consistent.

    - a citation_id must exist in THIS project, and any sibling
      library/record/page/saved_document fields must match the
      citation's own document and page;
    - a saved_document_id must belong to a document whose
      (library_id, record_id) equals the sibling fields (document
      A's id combined with document B's record id is refused);
    - bare (library_id, record_id) pairs without a saved id are
      upstream references and are allowed - the report/graph
      layers resolve them against the project and mark the rest
      unresolved."""
    problems: list[str] = []
    if _index is not None:
        docs = _index["docs"]
        by_id = _index["by_id"]
        cits = _index["cits"]
    else:
        docs = store.list_documents(project_id)
        by_id = {d["saved_document_id"]: d for d in docs}
        cits = {c["citation_id"]: c
                for c in store.list_citations(project_id)}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            cid = value.get("citation_id")
            if isinstance(cid, str) and cid:
                cit = cits.get(cid)
                if cit is None:
                    problems.append(f"{path}: citation {cid} is not in the project")
                else:
                    doc = by_id.get(cit["saved_document_id"]) or {}
                    if value.get("library_id") and value["library_id"] != doc.get("library_id"):
                        problems.append(f"{path}: citation's library does not match")
                    if value.get("record_id") and value["record_id"] != doc.get("record_id"):
                        problems.append(f"{path}: citation's record does not match")
                    if value.get("page_id") and value["page_id"] != cit.get("page_id"):
                        problems.append(f"{path}: citation's page does not match")
                    if value.get("saved_document_id") and \
                            value["saved_document_id"] != cit["saved_document_id"]:
                        problems.append(f"{path}: citation's document does not match")
            sid = value.get("saved_document_id")
            if isinstance(sid, str) and sid and not cid:
                doc = by_id.get(sid)
                if doc is None:
                    problems.append(f"{path}: saved_document_id is not in the project")
                elif value.get("library_id") and value["library_id"] != doc.get("library_id") \
                        or value.get("record_id") and value["record_id"] != doc.get("record_id"):
                    problems.append(f"{path}: saved_document_id belongs to a different document")
            for k, v in value.items():
                walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")

    walk(payload, "payload")
    for cid in payload.get("citation_refs") or []:
        if cid not in cits:
            problems.append(f"citation_refs: citation {cid} is not in the project")
    # Top-level record_refs are explicit WORKSPACE references:
    # each must resolve to a document of this project, and when
    # both the composite key and the saved id are present they
    # must name the SAME document.
    by_key = {(d["library_id"], d["record_id"]): d for d in docs}
    for ref in payload.get("record_refs") or []:
        if not isinstance(ref, dict):
            problems.append("record_refs: entries must be objects")
            continue
        doc = by_key.get((ref.get("library_id"), ref.get("record_id")))
        if doc is None:
            problems.append("record_refs: document is not in the project")
        elif ref.get("saved_document_id") and \
                ref["saved_document_id"] != doc["saved_document_id"]:
            problems.append("record_refs: saved_document_id belongs "
                            "to a different document")
    return problems


def _validate_refs(store: Any, project_id: str,
                   payload: dict[str, Any]) -> None:
    problems = reference_problems(store, project_id, payload)
    if problems:
        raise ValueError("artefact reference integrity: "
                         + "; ".join(problems[:5]))


def _integrity(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_artefact(store: Any, project_id: str, kind: str,
                  title: str, payload: dict[str, Any],
                  *, provenance: str = "server") -> dict[str, Any]:
    payload = validate_payload(kind, payload)
    _validate_refs(store, project_id, payload)
    trust = ("server_generated" if provenance == "server"
             else "imported_unverified")
    model = payload.get("model") or {}
    row = store.save_artefact_row(
        project_id, _PREFIX + kind, title,
        json.dumps(payload, ensure_ascii=False),
        trust=trust, provenance=provenance,
        operation_id="op_" + _integrity(payload)[:16],
        algorithm_version="b11",
        model_json=json.dumps(model, ensure_ascii=False))
    return {"artefact_id": row["artefact_id"], "note_id": row["artefact_id"],
            "kind": _PREFIX + kind, "title": title, "trust": trust}


def import_artefact(store: Any, project_id: str, kind: str,
                    title: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Imported artefacts are always downgraded: their claimed
    statuses are data, not server observations."""
    return save_artefact(store, project_id, kind, title, payload,
                         provenance="imported")


def list_artefacts(store: Any, project_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    _ref_index: dict[str, Any] | None = None
    for row in store.list_artefact_rows(project_id):
        try:
            raw_payload = row.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) \
                else json.loads(raw_payload or "{}")
        except ValueError:
            payload = {}
        entry = {"artefact_id": row["artefact_id"],
                 "note_id": row["artefact_id"], "kind": row["kind"],
                 "title": row.get("title", ""),
                 "payload": payload if isinstance(payload, dict) else {},
                 "trust": row["trust"],
                 "provenance": row.get("provenance"),
                 "created_at": row.get("created_at")}
        # Read-time re-check (section 9): references are
        # revalidated against CURRENT store state on every read;
        # a row whose references no longer resolve is flagged
        # and the graph/report layers treat it as unresolved.
        if isinstance(payload, dict) and payload:
            if _ref_index is None:
                _docs = store.list_documents(project_id)
                _ref_index = {
                    "docs": _docs,
                    "by_id": {d["saved_document_id"]: d for d in _docs},
                    "cits": {c["citation_id"]: c
                             for c in store.list_citations(project_id)}}
            problems = reference_problems(store, project_id, payload,
                                          _index=_ref_index)
            entry["reference_integrity"] = "ok" if not problems else "broken"
            if problems:
                entry["reference_problems"] = problems[:5]
        out.append(entry)
    # Legacy b10 note envelopes (any version, any claimed trust,
    # any hash) are plain user data now: surfaced for the
    # researcher's own reference, never trusted.
    for note in store.list_notes(project_id):
        content = note.get("content") or ""
        try:
            envelope = json.loads(content)
        except (ValueError, TypeError):
            continue
        if not isinstance(envelope, dict):
            continue
        kind = envelope.get("kind") or ""
        if not kind.startswith(_PREFIX):
            continue
        payload = envelope.get("payload")
        out.append({"note_id": note["note_id"], "kind": kind,
                    "title": note.get("title", ""),
                    "payload": payload if isinstance(payload, dict) else {},
                    "trust": "user_asserted",
                    "created_at": note.get("created_at")})
    return out


def project_research_progress(store: Any, project_id: str) -> dict[str, Any]:
    """Progress summary. Only artefacts in the dedicated table
    with server-side trust contribute candidate tallies; note
    lookalikes and imported/restored artefacts are counted
    separately and can never change the verified-adjacent
    numbers."""
    project = store.get_project(project_id)
    if project is None:
        return {"project_id": project_id, "found": False}
    counts = project.get("counts") or {}
    artefacts = list_artefacts(store, project_id)
    by_kind: dict[str, int] = {}
    claims_insufficient = 0
    contradiction_candidates = 0
    unverified_authorities = 0
    untrusted = 0
    for art in artefacts:
        if art.get("trust") != "server_generated":
            untrusted += 1
            continue
        by_kind[art["kind"]] = by_kind.get(art["kind"], 0) + 1
        payload = art.get("payload") or {}
        if art["kind"] == "b10_claim_assessment":
            for row in payload.get("assessments") or []:
                if isinstance(row, dict) and row.get("status") == "insufficient_evidence":
                    claims_insufficient += 1
        if art["kind"] == "b10_contradiction":
            for pair in payload.get("pairs") or []:
                if isinstance(pair, dict) and pair.get("status") == "contradiction_candidate":
                    contradiction_candidates += 1
        if art["kind"] == "b10_authority_resolution":
            if payload.get("status") != "authority_verified":
                unverified_authorities += 1
    return {
        "project_id": project_id,
        "found": True,
        "saved_documents": counts.get("documents", 0),
        "saved_citations": counts.get("citations", 0),
        "research_notes": counts.get("notes", 0),
        "comparisons": counts.get("comparisons", 0),
        "b10_artefacts": by_kind,
        "untrusted_artefacts": untrusted,
        "claims_with_insufficient_evidence": claims_insufficient,
        "contradiction_candidates": contradiction_candidates,
        "unverified_authority_candidates": unverified_authorities,
    }


MAX_GRAPH_NODES = 200
MAX_GRAPH_EDGES = 500


def project_relationship_graph(store: Any, project_id: str) -> dict[str, Any]:
    """Relationship graph with hard caps. Large same-work/author
    groups are aggregated through a group node instead of
    quadratic pairwise edges; omitted counts are reported, and
    edges to documents outside the project are never emitted."""
    documents = store.list_documents(project_id)
    doc_ids = {d["saved_document_id"] for d in documents}
    nodes = [{"id": f"doc:{d['saved_document_id']}",
              "type": "document",
              "label": d.get("title") or d["record_id"]}
             for d in documents[:MAX_GRAPH_NODES]]
    nodes_truncated = max(0, len(documents) - MAX_GRAPH_NODES)
    edges: list[dict[str, Any]] = []
    omitted = 0

    def add_edge(edge: dict[str, Any]) -> None:
        nonlocal omitted
        if len(edges) >= MAX_GRAPH_EDGES:
            omitted += 1
            return
        edges.append(edge)

    by_work: dict[str, list[dict]] = {}
    by_author: dict[str, list[dict]] = {}
    for doc in documents:
        if doc.get("work_id_candidate"):
            by_work.setdefault(str(doc["work_id_candidate"]), []).append(doc)
        if doc.get("author_id_candidate"):
            by_author.setdefault(str(doc["author_id_candidate"]), []).append(doc)
    for relation, groups in (("same_work_candidate", by_work),
                             ("same_author_candidate", by_author)):
        for basis, docs in groups.items():
            if len(docs) > 8:
                gid = f"group:{relation}:{basis}"
                nodes.append({"id": gid, "type": "group",
                              "label": basis, "members": len(docs)})
                for doc in docs:
                    add_edge({"source": f"doc:{doc['saved_document_id']}",
                              "target": gid, "relation": relation,
                              "certainty": "candidate", "basis": basis})
                continue
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    add_edge({
                        "source": f"doc:{docs[i]['saved_document_id']}",
                        "target": f"doc:{docs[j]['saved_document_id']}",
                        "relation": relation, "certainty": "candidate",
                        "basis": basis})
    for art in list_artefacts(store, project_id):
        if art["kind"] == "b10_contradiction" and art.get("trust") == "server_generated":
            for pair in (art.get("payload") or {}).get("pairs") or []:
                if not isinstance(pair, dict):
                    continue
                a, b = pair.get("a"), pair.get("b")
                if pair.get("status") == "contradiction_candidate" \
                        and a in doc_ids and b in doc_ids:
                    add_edge({
                        "source": f"doc:{a}", "target": f"doc:{b}",
                        "relation": "contradiction_candidate",
                        "certainty": "candidate", "basis": art["note_id"]})
    return {"nodes": nodes, "edges": edges,
            "omitted_edges": omitted,
            "nodes_truncated": nodes_truncated,
            "note": "candidate relations are hypotheses for the "
                    "researcher, not established facts"}
