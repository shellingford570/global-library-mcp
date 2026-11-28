"""b10 research artefacts in the Research Workspace.

Final-review hardened (b10 final review sections 17-19):

- Every artefact kind has a STRICT payload schema: field types
  are validated, unknown fields are rejected, and payload size,
  array length and nesting depth are capped.
- Envelopes are version 2 and carry provenance + an integrity
  hash over the canonical payload. Artefacts are TRUSTED as
  server-generated only when the envelope is intact; legacy v1
  envelopes and hand-written notes that merely look like
  artefacts are reported with trust="user_asserted" and never
  change verified tallies.
- Imported artefacts are downgraded (trust="imported_unverified")
  and their claimed statuses are not counted as verified.
- Artefacts reference saved citations/documents BY ID only.
  Raw OCR text is never stored through this path: fields that
  would carry original text (ocr_text / full_text / page_text)
  are rejected, and excerpt strings are capped well below the
  citation excerpt limit, so the note format cannot bypass the
  rights model or the 2,000-character citation cap.
- Referenced documents/citations must belong to the project.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

KINDS = (
    "claim_assessment", "contradiction", "authority_resolution",
    "ranking_explanation", "research_question", "comparison_b10",
)
_PREFIX = "b10_"
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_LIST_ITEMS = 100
MAX_DEPTH = 6
MAX_EXCERPT_CHARS = 200
_TEXT_BEARING_KEYS = {"ocr_text", "full_text", "page_text", "ocr",
                      "original_text", "image_url", "image_binary"}

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


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("artefact payload nesting too deep")
    if isinstance(value, dict):
        for v in value.values():
            _check_depth(v, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError("artefact payload list too long")
        for v in value:
            _check_depth(v, depth + 1)


def _check_text_bearing(value: Any, key: str = "") -> None:
    if key in _TEXT_BEARING_KEYS:
        raise ValueError(
            f"artefact payload may not carry original text field: {key} "
            "(reference saved citations by id instead)")
    if isinstance(value, dict):
        for k, v in value.items():
            _check_text_bearing(v, k)
    elif isinstance(value, list):
        for v in value:
            _check_text_bearing(v, key)
    elif isinstance(value, str) and key in ("excerpt", "quote") \
            and len(value) > MAX_EXCERPT_CHARS:
        raise ValueError("artefact excerpt exceeds the artefact cap")


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
    _check_depth(payload)
    _check_text_bearing(payload)
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
        known = {(d.get("library_id"), d.get("record_id"))
                 for d in store.list_documents(project_id)}
        known_ids = {d.get("saved_document_id")
                     for d in store.list_documents(project_id)}
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
    envelope = {"kind": _PREFIX + kind, "version": 2,
                "provenance": provenance, "trust": trust,
                "integrity": _integrity(payload), "payload": payload}
    note = store.save_note(
        project_id, json.dumps(envelope, ensure_ascii=False), title=title)
    return {"note_id": note["note_id"], "kind": _PREFIX + kind,
            "title": title, "trust": trust}


def import_artefact(store: Any, project_id: str, kind: str,
                    title: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Imported artefacts are always downgraded: their claimed
    statuses are data, not server observations."""
    return save_artefact(store, project_id, kind, title, payload,
                         provenance="imported")


def list_artefacts(store: Any, project_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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
        trust = "user_asserted"
        if envelope.get("version") == 2 and isinstance(payload, dict) \
                and envelope.get("integrity") == _integrity(payload):
            trust = envelope.get("trust") or "user_asserted"
            if trust not in ("server_generated", "imported_unverified"):
                trust = "user_asserted"
        out.append({"note_id": note["note_id"], "kind": kind,
                    "title": note.get("title", ""),
                    "payload": payload if isinstance(payload, dict) else {},
                    "trust": trust,
                    "created_at": note.get("created_at")})
    return out


def project_research_progress(store: Any, project_id: str) -> dict[str, Any]:
    """Progress summary. Only intact server-generated artefacts
    contribute candidate tallies; user-asserted or imported
    artefacts are counted separately and can never change the
    verified-adjacent numbers (section 19)."""
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
    """Relationship graph with hard caps (section 19). Large
    same-work/author groups are aggregated through a group node
    instead of quadratic pairwise edges; omitted counts are
    reported, and edges to documents outside the project are
    never emitted."""
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
