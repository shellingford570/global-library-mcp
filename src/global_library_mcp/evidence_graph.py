"""Evidence Graph (b11 sections 31-39).

The graph is built ONLY from Stage-0-trusted material:

- workspace documents and citations (server-side rows);
- ``research_artefacts`` table rows whose stored trust is
  ``server_generated`` (claims/comparisons inside their
  schema-validated payloads).

Legacy note envelopes, arbitrary JSON, hand-written notes,
unverified lexicon entries, user-set "verified" flags, imported
artefacts and self-computed hashes NEVER produce
``confirmed_reference`` edges.  Imported/restored artefacts are
included only with their downgraded relation state.

Revalidation (section 39): the graph is rebuilt from current
store state on every read, so a citation whose verification was
downgraded or a document whose rights changed immediately loses
its confirmed edges; historical observations remain in the store
but are never rendered as currently valid.
"""
from __future__ import annotations

from typing import Any

NODE_TYPES = ("research_question", "claim", "evidence_candidate",
              "document", "page", "person", "work", "edition",
              "concept", "source", "comparison", "timeline_event",
              "report")
EDGE_TYPES = ("asks_about", "claims", "supported_by_candidate",
              "contradicted_by_candidate", "cites", "authored_by_candidate",
              "edition_of_candidate", "translation_of_candidate",
              "reprint_of_candidate", "same_source_family",
              "derived_from", "mentions", "part_of_report",
              "supersedes", "invalidated_by")
RELATION_STATES = ("confirmed_reference", "candidate", "user_asserted",
                   "imported_unverified", "restored_unverified",
                   "independently_reviewed", "invalidated", "unresolved")

MAX_GRAPH_NODES = 2000
MAX_GRAPH_EDGES = 5000
MAX_GRAPH_DEPTH = 32


def _node(nodes: dict, nid: str, ntype: str, label: str,
          provenance: str) -> dict:
    if nid not in nodes:
        nodes[nid] = {"node_id": nid, "type": ntype, "label": label[:200],
                      "provenance": provenance}
    return nodes[nid]


def build_project_graph(store: Any, project_id: str, *,
                        limit: int = 500, offset: int = 0) -> dict[str, Any]:
    """Build the project Evidence Graph from trusted store state."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def edge(src: str, dst: str, etype: str, state: str,
             provenance: str) -> None:
        edges.append({"edge_id": f"e{len(edges)}", "source": src,
                      "target": dst, "type": etype, "state": state,
                      "provenance": provenance})

    project = store.get_project(project_id)
    if project is None:
        return {"project_id": project_id, "nodes": [], "edges": [],
                "node_count": 0, "edge_count": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "error": "project_not_found"}

    docs = store.list_documents(project_id)
    doc_nodes: dict[tuple[str, str], str] = {}
    for d in docs:
        nid = f"document:{d['library_id']}:{d['record_id']}"
        verified = d.get("verification_status") == "verified"
        _node(nodes, nid, "document",
              d.get("title") or d["record_id"], "workspace_document")
        doc_nodes[(d["library_id"], d["record_id"])] = nid
        src = f"source:{d['library_id']}"
        _node(nodes, src, "source", d["library_id"], "registry")
        edge(nid, src, "same_source_family", "confirmed_reference",
             "workspace_document")
        if d.get("author_id_candidate"):
            pid = f"person:{d['author_id_candidate']}"
            _node(nodes, pid, "person", d["author_id_candidate"],
                  "document_field")
            state = "confirmed_reference" if verified else "candidate"
            edge(nid, pid, "authored_by_candidate", state,
                 "document_field")
        if d.get("work_id_candidate"):
            wid = f"work:{d['work_id_candidate']}"
            _node(nodes, wid, "work", d["work_id_candidate"],
                  "document_field")
            edge(nid, wid, "edition_of_candidate",
                 "confirmed_reference" if verified else "candidate",
                 "document_field")

    for cit in store.list_citations(project_id):
        doc_key = None
        for d in docs:
            if d["document_id"] == cit.get("document_id"):
                doc_key = (d["library_id"], d["record_id"])
                break
        if doc_key is None or doc_key not in doc_nodes:
            continue  # cross-project / dangling citation refused
        cnid = f"evidence_candidate:citation:{cit['citation_id']}"
        _node(nodes, cnid, "evidence_candidate",
              cit.get("locator_text") or cit["citation_id"], "citation")
        verified = cit.get("verification_status") == "verified"
        edge(doc_nodes[doc_key], cnid, "cites",
             "confirmed_reference" if verified else "candidate",
             "citation_row")

    artefact_state = {"server_generated": "confirmed_reference",
                      "imported_unverified": "imported_unverified",
                      "restored_unverified": "restored_unverified"}
    for art in store.list_artefact_rows(project_id):
        state = artefact_state.get(art["trust"], "unresolved")
        payload = art.get("payload") or {}
        if art["kind"] == "research_question":
            qid = f"research_question:{art['artefact_id']}"
            _node(nodes, qid, "research_question",
                  art.get("title") or art["artefact_id"], art["trust"])
        elif art["kind"] == "claim_assessment":
            seen_claims: set[str] = set()
            for a in payload.get("assessments") or []:
                cid = a.get("claim_id") or "claim"
                cnid = f"claim:{art['artefact_id']}:{cid}"
                if cid not in seen_claims:
                    _node(nodes, cnid, "claim", cid, art["trust"])
                    seen_claims.add(cid)
                key = (a.get("library_id"), a.get("record_id"))
                if key in doc_nodes:
                    etype = ("contradicted_by_candidate"
                             if a.get("status") in (
                                 "contradiction_candidate",
                                 "conflicting_candidate")
                             else "supported_by_candidate")
                    edge(cnid, doc_nodes[key], etype, state, art["trust"])
        elif art["kind"] == "comparison":
            cmpid = f"comparison:{art['artefact_id']}"
            _node(nodes, cmpid, "comparison",
                  art.get("title") or art["artefact_id"], art["trust"])
            for ref in payload.get("record_refs") or []:
                key = (ref.get("library_id"), ref.get("record_id"))
                if key in doc_nodes:
                    edge(cmpid, doc_nodes[key], "mentions", state,
                         art["trust"])
        elif art["kind"] == "research_report":
            rid = f"report:{art['artefact_id']}"
            _node(nodes, rid, "report",
                  art.get("title") or art["artefact_id"], art["trust"])
            for ref in payload.get("record_refs") or []:
                key = (ref.get("library_id"), ref.get("record_id"))
                if key in doc_nodes:
                    edge(rid, doc_nodes[key], "part_of_report", state,
                         art["trust"])

    all_nodes = list(nodes.values())
    omitted_nodes = max(0, len(all_nodes) - MAX_GRAPH_NODES)
    kept_nodes = all_nodes[:MAX_GRAPH_NODES]
    kept_ids = {n["node_id"] for n in kept_nodes}
    kept_edges = [e for e in edges
                  if e["source"] in kept_ids and e["target"] in kept_ids]
    omitted_edges = max(0, len(kept_edges) - MAX_GRAPH_EDGES)
    kept_edges = kept_edges[:MAX_GRAPH_EDGES]
    page_nodes = kept_nodes[offset:offset + limit]
    page_edges = [e for e in kept_edges
                  if e["source"] in {n["node_id"] for n in page_nodes}
                  or e["target"] in {n["node_id"] for n in page_nodes}]
    return {"project_id": project_id, "nodes": page_nodes,
            "edges": page_edges, "node_count": len(kept_nodes),
            "edge_count": len(kept_edges),
            "omitted_nodes": omitted_nodes,
            "omitted_edges": omitted_edges,
            "limit": limit, "offset": offset}
