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

_SCHEMAS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "claim_assessment": {
        "claim_id": str, "assessments": list, "evaluated_at": str,
        "config": dict, "claim": dict},
    "contradiction": {"pairs": list, "note": str, "evaluated_at": str},
    "authority_resolution": {
        "query": str, "status": str, "candidates": list,
        "notes": list, "evaluated_at": str},
    "ranking_explanation": {
        "query": str, "ranking": dict, "items": list},
    "research_question": {"question": (dict, str), "structured": dict},
    "comparison_b10": {"pairs": list, "counts": dict, "note": str},
}
_COMMON_FIELDS = {"record_refs": list, "citation_refs": list,
                  "rights_state": str, "model": dict}

_STATUS_VOCAB = {
    "supported_candidate", "partially_supported",
    "conflicting_candidate", "contextual_only",
    "insufficient_evidence", "evidence_reference_only",
    "not_checked", "consistent_candidate", "differing_unit",
    "differing_time", "differing_scope", "contradiction_candidate",
    "insufficient_context", "authority_verified", "candidate",
    "ambiguous", "unresolved", "verified", "unverified",
}
_NESTED_KEYS: dict[str, set[str]] = {
    "assessments": {"claim_id", "status", "library_id", "record_id",
                    "page_id", "citation_id", "passage_id", "signals",
                    "unconfirmed_signals", "reason", "signals_used",
                    "signals_missing"},
    "pairs": {"a", "b", "status", "value_a", "value_b", "unit_a",
              "unit_b", "converted", "reason", "subject", "predicate",
              "object", "place", "year_a", "year_b"},
    "claim": {"claim_id", "text", "subject", "predicate", "object",
              "years", "places", "quantities", "entities",
              "qualifiers", "era", "negated"},
    "config": {"ranking_mode", "model_id", "model_revision",
               "allocation", "version", "mode"},
    "items": {"library_id", "record_id", "title", "reasons",
              "subscores", "rank", "status"},
    "candidates": {"name", "person_id", "status", "score",
                   "birth_year", "death_year", "identifiers", "works",
                   "source", "authority_id"},
    "counts": {"evidence_item_count", "distinct_document_count",
               "distinct_library_record_count",
               "source_family_candidate_count",
               "known_dependent_source_count",
               "independence_unknown_count",
               "independently_confirmed_source_count",
               "document_count", "independent_source_count"},
    "ranking": {"requested_ranking_mode", "effective_ranking_mode",
                "semantic_applied", "fallback_reason", "model_id",
                "model_revision", "candidate_pool_size"},
    "model": {"model_id", "model_revision", "kind"},
    "structured": {"intent", "entities", "era", "constraints",
                   "ambiguities", "subject", "predicate", "object"},
    "question": {"claim_id", "text", "subject", "predicate", "object",
                 "years", "places", "quantities", "entities",
                 "qualifiers", "era", "negated"},
}


def _walk(value: Any, key: str, depth: int, counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise ValueError("artefact payload has too many nodes")
    if depth > MAX_DEPTH:
        raise ValueError("artefact payload nesting too deep")
    if isinstance(value, dict):
        if key in _TEXT_BEARING_KEYS:
            raise ValueError(f"original-text field not allowed: {key}")
        allowed = _NESTED_KEYS.get(key)
        if allowed is not None:
            for k in value:
                if k not in allowed:
                    raise ValueError(
                        f"unknown nested field in {key}: {k}")
        for k, v in value.items():
            if k in _TEXT_BEARING_KEYS:
                raise ValueError(
                    f"artefact payload may not carry original text "
                    f"field: {k} (reference saved citations by id)")
            if k == "status" and isinstance(v, str) \
                    and v not in _STATUS_VOCAB:
                raise ValueError(f"status outside the closed vocabulary: {v}")
            _walk(v, k, depth + 1, counter)
    elif isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError("artefact payload list too long")
        for v in value:
            _walk(v, key, depth + 1, counter)
    elif isinstance(value, str):
        cap = MAX_EXCERPT_CHARS if key in _SHORT_TEXT_KEYS else MAX_STR_CHARS
        if len(value) > cap:
            raise ValueError(
                f"artefact string field {key!r} exceeds {cap} chars")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("artefact payload numbers must be finite")
    elif value is not None and not isinstance(value, (int, bool)):
        raise ValueError("artefact payload contains an unsupported type")


def validate_payload(kind: str, payload: Any) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown b10 artefact kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("artefact payload must be an object")
    schema = {**_SCHEMAS[kind], **_COMMON_FIELDS}
    for field_name in payload:
        if field_name not in schema:
            raise ValueError(f"unknown field for {kind}: {field_name}")
    for field_name, value in payload.items():
        if not isinstance(value, schema[field_name]):
            raise ValueError(f"field {field_name} has the wrong type")
    _walk(payload, "", 0, [0])
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("artefact payload too large")
    return payload


def _integrity(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_refs(store: Any, project_id: str,
                   payload: dict[str, Any]) -> None:
    refs = payload.get("record_refs") or []
    if refs:
        docs = store.list_documents(project_id)
        known = {(d.get("library_id"), d.get("record_id")) for d in docs}
        known_ids = {d.get("saved_document_id") for d in docs}
        for ref in refs:
            if isinstance(ref, dict):
                key = (ref.get("library_id"), ref.get("record_id"))
                if key not in known and ref.get("saved_document_id") not in known_ids:
                    raise ValueError(
                        "artefact references a document outside the project")
            else:
                raise ValueError("record_refs entries must be objects")
    cit_refs = payload.get("citation_refs") or []
    if cit_refs:
        known_c = {c.get("citation_id") for c in store.list_citations(project_id)}
        for cid in cit_refs:
            if cid not in known_c:
                raise ValueError(
                    "artefact references a citation outside the project")


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
    for row in store.list_artefact_rows(project_id):
        try:
            raw_payload = row.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) \
                else json.loads(raw_payload or "{}")
        except ValueError:
            payload = {}
        out.append({"artefact_id": row["artefact_id"],
                    "note_id": row["artefact_id"], "kind": row["kind"],
                    "title": row.get("title", ""),
                    "payload": payload if isinstance(payload, dict) else {},
                    "trust": row["trust"],
                    "provenance": row.get("provenance"),
                    "created_at": row.get("created_at")})
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
