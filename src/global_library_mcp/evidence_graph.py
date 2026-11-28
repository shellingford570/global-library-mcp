"""b11 Evidence Graph (final-review rewrite, sections 12-19).

Graph over CURRENT store state: projects, saved documents
(joined through the real persisted field ``saved_document_id``),
saved citations, authors, works, sources, research questions,
claims, claim assessments, comparisons, timelines and research
reports.

Trust semantics (section 14): provenance (server_generated /
imported_unverified / restored_unverified) is an ATTRIBUTE, never
a confirmation. Assessment relations use the CLOSED status ->
edge-type mapping of section 13; an unknown status maps to
``unresolved_reference``, never to a support edge. A document's
verified identity never confirms author/work/edition/support
relations: those stay ``candidate``.

Current-state evaluation (section 18): each citation is shown
with its present verification state and the project's LATEST
rights observation, so a bibliographic reference can remain
while excerpt display is forbidden or revalidation is required.

Capacity (section 19): references are resolved through indexes
(O(N+M)-ish), generation is capped, edge ids are deterministic,
paging is over a stable sorted order, off-page endpoints are
returned as explicit stubs, and omitted node/edge counts are
exact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

NODE_TYPES = ("project", "document", "page", "citation", "person",
              "work", "edition", "concept", "question", "claim",
              "comparison", "timeline", "report", "source")
EDGE_TYPES = (
    "has_document", "has_page", "has_citation", "held_by",
    "work_candidate", "author_candidate", "derived_from", "quotes",
    "reprints", "translation_candidate", "same_source_family",
    "supports_candidate", "partially_supports",
    "contradicts_candidate", "contextualizes", "references",
    "insufficient_evidence", "unassessed", "unresolved_reference",
    "mentions", "asks_about", "reported_in", "source_family_candidate")
RELATION_STATES = ("confirmed_reference", "candidate", "invalidated",
                   "imported_unverified", "restored_unverified",
                   "user_asserted")

#: Section 13: closed mapping assessment status -> edge type.
STATUS_EDGE_MAP = {
    "supported_candidate": "supports_candidate",
    "partially_supported": "partially_supports",
    "conflicting_candidate": "contradicts_candidate",
    "contradiction_candidate": "contradicts_candidate",
    "contextual_only": "contextualizes",
    "evidence_reference_only": "references",
    "insufficient_evidence": "insufficient_evidence",
    "not_checked": "unassessed",
    "unresolved": "unresolved_reference",
    "revalidation_required": "unresolved_reference",
}
MAX_GRAPH_NODES = 2000
MAX_GRAPH_EDGES = 5000
MAX_DEPTH = 32
_RIGHTS_HIDDEN = {"in_copyright", "rights_reserved", "unknown"}


def _nid(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _eid(source: str, target: str, etype: str) -> str:
    digest = hashlib.sha256(
        f"{source}|{target}|{etype}".encode("utf-8")).hexdigest()[:16]
    return f"e_{digest}"


def _label(text: Any, limit: int = 120) -> str:
    return str(text or "")[:limit]


def build_project_graph(store: Any, project_id: str, *,
                        limit: int = MAX_GRAPH_NODES,
                        offset: int = 0) -> dict[str, Any]:
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    limit = max(1, min(int(limit), MAX_GRAPH_NODES))
    offset = max(0, int(offset))

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    unresolved_references = 0

    def add_node(kind: str, key: str, label: str, **attrs: Any) -> str:
        nid = _nid(kind, key)
        if nid not in nodes:
            nodes[nid] = {"node_id": nid, "type": kind,
                          "label": _label(label), **attrs}
        return nid

    def add_edge(source: str, target: str, etype: str,
                 state: str) -> None:
        eid = _eid(source, target, etype)
        if eid in seen_edges:
            return
        seen_edges.add(eid)
        edges.append({"edge_id": eid, "source": source,
                      "target": target, "type": etype, "state": state})

    # -- indexes (section 19) -----------------------------------
    docs = store.list_documents(project_id)
    docs_by_id = {d["saved_document_id"]: d for d in docs}
    docs_by_key = {(d["library_id"], d["record_id"]): d for d in docs}
    cits = store.list_citations(project_id)
    cits_by_id = {c["citation_id"]: c for c in cits}
    cits_by_doc: dict[str, list[dict[str, Any]]] = {}
    for cit in cits:
        cits_by_doc.setdefault(cit["saved_document_id"], []).append(cit)

    pid_node = add_node("project", project_id, project.get("name") or "")

    # -- documents, pages, citations, sources -------------------
    for doc in docs:
        latest = store.latest_rights_observation(
            doc["saved_document_id"])
        rights_cat = latest["category"] if latest else "unobserved"
        dnode = add_node(
            "document", doc["saved_document_id"],
            doc.get("title") or doc["record_id"],
            library_id=doc["library_id"], record_id=doc["record_id"],
            rights_category=rights_cat,
            excerpt_display=("forbidden" if rights_cat in _RIGHTS_HIDDEN
                             else "allowed"))
        add_edge(pid_node, dnode, "has_document", "confirmed_reference")
        snode = add_node("source", doc["library_id"], doc["library_id"],
                         role="holding_library")
        add_edge(dnode, snode, "held_by", "confirmed_reference")
        for cit in cits_by_doc.get(doc["saved_document_id"], []):
            pnode = add_node(
                "page", f"{doc['saved_document_id']}/{cit['page_id']}",
                cit["page_id"], page_id=cit["page_id"],
                unit=("newspaper_article"
                      if doc.get("source_type") == "newspaper"
                      else "digital_frame"))
            add_edge(dnode, pnode, "has_page", "confirmed_reference")
            cnode = add_node(
                "citation", cit["citation_id"],
                cit.get("citation_key") or cit["citation_id"],
                citation_key=cit.get("citation_key"),
                quotation_verification_status=cit.get(
                    "quotation_verification_status"),
                page_mapping_status=cit.get("page_mapping_status"),
                reference_available=True,
                excerpt_display=(
                    "forbidden" if rights_cat in _RIGHTS_HIDDEN
                    else "allowed"),
                revalidation_required=bool(
                    str(cit.get("quotation_verification_status") or "")
                    .endswith("unverified")
                    or str(cit.get("page_mapping_status") or "")
                    .endswith("unverified")))
            state = ("confirmed_reference"
                     if cit.get("page_mapping_status") == "verified"
                     else "candidate")
            add_edge(pnode, cnode, "has_citation", state)

    # -- artefacts: questions, claims, assessments, reports -----
    artefacts = store.list_artefact_rows(project_id)
    question_nodes: dict[str, str] = {}
    for art in artefacts:
        payload = art.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        trust = art.get("trust") or "server_generated"
        kind = art["kind"].removeprefix("b10_")
        if kind == "research_question":
            q = payload.get("question")
            text = (q.get("original_question") or q.get("text")
                    if isinstance(q, dict) else q) or art.get("title")
            question_nodes[art["artefact_id"]] = add_node(
                "question", art["artefact_id"], text or "",
                trust=trust, provenance=art.get("provenance"))
        elif kind == "claim_assessment":
            claim = payload.get("claim") or {}
            claim_id = (claim.get("claim_id")
                        or payload.get("claim_id")
                        or art["artefact_id"])
            assessments = payload.get("assessments") or []
            cnode_id = add_node(
                "claim", claim_id,
                claim.get("original_statement") or claim.get("statement")
                or art.get("title") or claim_id,
                trust=trust, provenance=art.get("provenance"),
                assessment_count=len(assessments),
                evidence_state=("assessed" if assessments
                                else "no_evidence_registered"))
            qid = claim.get("question_id") or claim.get(
                "research_question_id")
            if qid and qid in question_nodes:
                add_edge(question_nodes[qid], cnode_id, "asks_about",
                         "candidate")
            for a in assessments:
                if not isinstance(a, dict):
                    continue
                etype = STATUS_EDGE_MAP.get(a.get("status") or "",
                                            "unresolved_reference")
                state = "candidate" if trust == "server_generated" else trust
                target = None
                cit = cits_by_id.get(a.get("citation_id") or "")
                if cit is not None:
                    target = _nid("citation", cit["citation_id"])
                    downgraded = (
                        str(cit.get("quotation_verification_status") or "")
                        .endswith("unverified")
                        or str(cit.get("page_mapping_status") or "")
                        .endswith("unverified"))
                    if downgraded and trust == "server_generated":
                        etype = "unresolved_reference"
                        state = "invalidated"
                elif a.get("citation_id"):
                    etype, state = "unresolved_reference", "invalidated"
                    unresolved_references += 1
                    continue
                else:
                    doc = docs_by_key.get(
                        (a.get("library_id") or "", a.get("record_id") or ""))
                    if doc is not None:
                        target = _nid("document", doc["saved_document_id"])
                    elif a.get("library_id") or a.get("record_id"):
                        unresolved_references += 1
                        continue
                if target:
                    add_edge(cnode_id, target, etype, state)
        elif kind == "research_report":
            rnode = add_node("report", art["artefact_id"],
                             art.get("title") or "", trust=trust)
            add_edge(pid_node, rnode, "reported_in", "candidate")
        elif kind == "timeline":
            tnode = add_node("timeline", art["artefact_id"],
                             art.get("title") or "", trust=trust)
            add_edge(pid_node, tnode, "reported_in", "candidate")
        elif kind == "comparison_b10":
            cmp_node = add_node("comparison", art["artefact_id"],
                                art.get("title") or "", trust=trust)
            for ref in payload.get("record_refs") or []:
                doc = docs_by_key.get((ref.get("library_id") or "",
                                       ref.get("record_id") or ""))
                if doc is not None:
                    add_edge(cmp_node,
                             _nid("document", doc["saved_document_id"]),
                             "mentions", "candidate")

    # -- comparisons: authors, works, concepts (candidates) -----
    for comp in store.list_comparisons(project_id):
        result = comp.get("result") or {}
        cn = add_node("comparison", comp["comparison_id"],
                      comp.get("title") or "")
        for row in result.get("documents") or []:
            doc = docs_by_key.get((row.get("library_id") or "",
                                   row.get("record_id") or ""))
            if doc is None:
                continue
            dnode = _nid("document", doc["saved_document_id"])
            add_edge(cn, dnode, "mentions", "candidate")
            for author in row.get("authors") or []:
                anode = add_node("person", author, author)
                add_edge(dnode, anode, "author_candidate", "candidate")
            title = row.get("title") or ""
            if title:
                wnode = add_node("work", title, title)
                add_edge(dnode, wnode, "work_candidate", "candidate")
        for cid in result.get("dictionary_concept_overlap") or []:
            conode = add_node("concept", str(cid), str(cid))
            add_edge(cn, conode, "mentions", "candidate")

    # -- depth limit from question nodes (section 19) -----------
    adjacency: dict[str, list[str]] = {}
    for e in edges:
        adjacency.setdefault(e["source"], []).append(e["target"])
    roots = [n for n in nodes.values() if n["type"] in ("question", "project")]
    depth: dict[str, int] = {}
    frontier = [(r["node_id"], 0) for r in roots]
    while frontier:
        nid, d = frontier.pop(0)
        if nid in depth and depth[nid] <= d:
            continue
        depth[nid] = d
        if d < MAX_DEPTH:
            for nxt in adjacency.get(nid, []):
                frontier.append((nxt, d + 1))

    # -- stable paging with stubs (section 19) -------------------
    all_nodes = sorted(nodes.values(), key=lambda n: n["node_id"])
    total_nodes = len(all_nodes)
    total_edges = len(edges)
    page_nodes = all_nodes[offset:offset + limit]
    page_ids = {n["node_id"] for n in page_nodes}
    page_edges = [e for e in edges
                  if e["source"] in page_ids or e["target"] in page_ids]
    omitted_edges = 0
    if len(page_edges) > MAX_GRAPH_EDGES:
        omitted_edges = len(page_edges) - MAX_GRAPH_EDGES
        page_edges = page_edges[:MAX_GRAPH_EDGES]
    stub_ids = set()
    for e in page_edges:
        for endpoint in (e["source"], e["target"]):
            if endpoint not in page_ids:
                stub_ids.add(endpoint)
    stubs = [{"node_id": sid, "type": nodes[sid]["type"],
              "label": nodes[sid]["label"], "stub": True}
             for sid in sorted(stub_ids) if sid in nodes]
    out_nodes = page_nodes + stubs
    for n in out_nodes:
        if n["node_id"] in depth:
            n["depth"] = depth[n["node_id"]]
    return {
        "project_id": project_id,
        "nodes": out_nodes,
        "edges": page_edges,
        "node_count": len(out_nodes),
        "edge_count": len(page_edges),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "omitted_nodes": max(0, total_nodes - len(page_nodes)),
        "omitted_edges": omitted_edges,
        "unresolved_references": unresolved_references,
        "limit": limit, "offset": offset,
        "max_depth": MAX_DEPTH,
        "node_types": list(NODE_TYPES),
        "edge_types": list(EDGE_TYPES),
        "relation_states": list(RELATION_STATES),
        "provenance_note": (
            "server_generated is provenance, not confirmation; "
            "author/work/edition/support relations stay candidate "
            "until independently reviewed"),
    }
