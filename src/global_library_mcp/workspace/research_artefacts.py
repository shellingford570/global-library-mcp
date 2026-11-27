"""b10 research artefacts in the Research Workspace (section 34).

Structured b10 results — claim assessments, contradiction
candidates, authority resolutions, ranking explanations — are
saved as research notes carrying a versioned JSON envelope:

    {"kind": "b10_<kind>", "version": 1, "payload": {...}}

No schema change is required (the notes table already stores
title + content), so existing projects, documents, citations
and their rights-trust state are untouched, and no existing
record is reclassified, deleted or sent anywhere. The envelope
version leaves a clean migration path if a future release gives
artefacts their own tables.
"""
from __future__ import annotations

import json
from typing import Any

KINDS = (
    "claim_assessment", "contradiction", "authority_resolution",
    "ranking_explanation", "research_question", "comparison_b10",
)
_PREFIX = "b10_"


def save_artefact(store: Any, project_id: str, kind: str,
                  title: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown b10 artefact kind: {kind}")
    envelope = {"kind": _PREFIX + kind, "version": 1, "payload": payload}
    note = store.save_note(
        project_id, json.dumps(envelope, ensure_ascii=False), title=title)
    return {"note_id": note["note_id"], "kind": _PREFIX + kind,
            "title": title}


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
        if kind.startswith(_PREFIX) and envelope.get("version") == 1:
            out.append({"note_id": note["note_id"], "kind": kind,
                        "title": note.get("title", ""),
                        "payload": envelope.get("payload") or {},
                        "created_at": note.get("created_at")})
    return out


def project_research_progress(store: Any, project_id: str) -> dict[str, Any]:
    """Section 35 progress summary: counts that distinguish
    candidates from verified material, computed from the live
    workspace state (nothing is cached or reclassified)."""
    project = store.get_project(project_id)
    if project is None:
        return {"project_id": project_id, "found": False}
    counts = project.get("counts") or {}
    artefacts = list_artefacts(store, project_id)
    by_kind: dict[str, int] = {}
    claims_insufficient = 0
    contradiction_candidates = 0
    unverified_authorities = 0
    for art in artefacts:
        by_kind[art["kind"]] = by_kind.get(art["kind"], 0) + 1
        payload = art.get("payload") or {}
        if art["kind"] == "b10_claim_assessment":
            for row in payload.get("assessments") or []:
                if row.get("status") == "insufficient_evidence":
                    claims_insufficient += 1
        if art["kind"] == "b10_contradiction":
            for pair in payload.get("pairs") or []:
                if pair.get("status") == "contradiction_candidate":
                    contradiction_candidates += 1
        if art["kind"] == "b10_authority_resolution":
            if payload.get("status") not in ("authority_verified",):
                unverified_authorities += 1
    return {
        "project_id": project_id,
        "found": True,
        "saved_documents": counts.get("documents", 0),
        "saved_citations": counts.get("citations", 0),
        "research_notes": counts.get("notes", 0),
        "comparisons": counts.get("comparisons", 0),
        "b10_artefacts": by_kind,
        "claims_with_insufficient_evidence": claims_insufficient,
        "contradiction_candidates": contradiction_candidates,
        "unverified_authority_candidates": unverified_authorities,
    }


def project_relationship_graph(store: Any, project_id: str) -> dict[str, Any]:
    """Section 35 relationship graph over saved documents and
    b10 artefacts. Edges are typed candidate vs confirmed:
    sharing a library record id is a fact; sharing a work or
    author is a CANDIDATE relation and is labelled as such."""
    documents = store.list_documents(project_id)
    nodes = [{"id": f"doc:{d['saved_document_id']}",
              "type": "document",
              "label": d.get("title") or d["record_id"]}
             for d in documents]
    edges: list[dict[str, Any]] = []
    by_work: dict[str, list[dict]] = {}
    by_author: dict[str, list[dict]] = {}
    for doc in documents:
        # The workspace stores authority links as CANDIDATES
        # (work_id_candidate / author_id_candidate, b7); the graph
        # keeps that certainty level.
        work_id = doc.get("work_id_candidate")
        author_id = doc.get("author_id_candidate")
        if work_id:
            by_work.setdefault(str(work_id), []).append(doc)
        if author_id:
            by_author.setdefault(str(author_id), []).append(doc)
    for work_id, docs in by_work.items():
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                edges.append({
                    "source": f"doc:{docs[i]['saved_document_id']}",
                    "target": f"doc:{docs[j]['saved_document_id']}",
                    "relation": "same_work_candidate", "certainty": "candidate",
                    "basis": work_id})
    for author_id, docs in by_author.items():
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                edges.append({
                    "source": f"doc:{docs[i]['saved_document_id']}",
                    "target": f"doc:{docs[j]['saved_document_id']}",
                    "relation": "same_author_candidate", "certainty": "candidate",
                    "basis": author_id})
    for art in list_artefacts(store, project_id):
        if art["kind"] == "b10_contradiction":
            for pair in (art.get("payload") or {}).get("pairs") or []:
                if pair.get("status") == "contradiction_candidate":
                    edges.append({
                        "source": f"doc:{pair.get('a')}",
                        "target": f"doc:{pair.get('b')}",
                        "relation": "contradiction_candidate",
                        "certainty": "candidate", "basis": art["note_id"]})
    return {"nodes": nodes, "edges": edges,
            "note": "candidate relations are hypotheses for the "
                    "researcher, not established facts"}
