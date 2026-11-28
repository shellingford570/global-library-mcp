"""Template-based knowledge synthesis (b11 sections 40-48).

No LLM is used.  Synthesis reorganises what the trusted
pipeline already produced; it NEVER fills gaps with unconfirmed
information and NEVER creates a confirmed fact: every output
state stays at candidate level (section 41).  Reports contain
metadata and the researcher's own claim statements only - no
upstream OCR text is inserted (section 48), rights are
re-evaluated from current store state at generation time, and
every evidence reference in a report must resolve to a real
document or citation in the same project.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

EVIDENCE_POLICY_VERSION = "b11-evidence-policy-1"
RIGHTS_POLICY_VERSION = "b11-rights-policy-1"
REPORT_SCHEMA_VERSION = "b11-report-1"

CLAIM_STATES = ("supported_candidate", "partially_supported",
                "conflicting_candidate", "contextual_only",
                "insufficient_evidence", "not_checked", "unresolved")
DATE_KINDS = ("event_date", "estimated_era", "publication_date",
              "reprint_date", "translation_publication_date",
              "acquisition_date", "verification_date")


def classify_claim_states(assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map assessments to synthesis claim states (section 41).

    The mapping is a pure relabelling into the synthesis
    vocabulary; unknown statuses become ``unresolved`` and no
    state is ever upgraded - in particular nothing here can
    produce a "confirmed" or "verified" state.
    """
    out = []
    for a in assessments:
        st = a.get("status")
        state = st if st in CLAIM_STATES else "unresolved"
        out.append({"claim_id": a.get("claim_id"),
                    "state": state,
                    "document_id": a.get("document_id"),
                    "independence": (
                        "confirmed" if a.get("independence_confirmed")
                        and a.get("independence_basis") else "unknown")})
    return out


def build_timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Order dated events without asserting causality (section 42).

    Date kinds stay distinct; an entry without a valid kind or
    year is reported under ``undated`` instead of being placed.
    """
    dated, undated = [], []
    for e in events:
        if e.get("date_kind") in DATE_KINDS and isinstance(
                e.get("year"), (int, float)):
            dated.append({"label": e.get("label", ""),
                          "year": e["year"], "date_kind": e["date_kind"],
                          "source_ref": e.get("source_ref")})
        else:
            undated.append(e)
    dated.sort(key=lambda x: (x["year"], x["date_kind"]))
    return {"events": dated, "undated_count": len(undated),
            "causality": "not_asserted",
            "note": "ordering alone never asserts causality"}


def numeric_synthesis(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Present numeric facts side by side (section 43).

    Original value/unit are preserved; a normalised value is
    included only when a same-family conversion exists, with the
    conversion stated.  No averages, sums or rates are computed
    across facts - comparability is the researcher's judgement.
    """
    from .research import _convert_value, _UNIT_FAMILIES

    out = []
    for f in facts:
        row = {"original_value": f.get("value"),
               "original_unit": f.get("unit"),
               "target": f.get("subject"), "region": f.get("place"),
               "era": f.get("era"), "definition": f.get("definition"),
               "scope": f.get("scope"),
               "approximate": bool(f.get("approximate"))}
        unit = (f.get("unit") or "")
        fam = _UNIT_FAMILIES.get(unit)
        if fam is not None:
            base = sorted(fam, key=lambda u: fam[u])[0]
            conv = _convert_value(f.get("value"), unit, base)
            if conv is not None:
                row["normalized_value"] = conv
                row["normalized_unit"] = base
                row["conversion"] = f"{f.get('value')} {unit} = {conv} {base}"
        out.append(row)
    return out


def multilingual_comparison(concept_links: list[dict[str, Any]],
                            claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate concept alignment from claim alignment (section 44).

    Two records sharing a concept are concept-aligned ONLY; a
    claim alignment additionally requires matching structured
    subject/predicate/quantity fields, and is still a candidate.
    """
    concept_pairs = [c for c in concept_links if c.get("concept_id")]
    claim_pairs = []
    for c in claims:
        if c.get("subject") and c.get("predicate") and c.get("object"):
            claim_pairs.append({"claim_id": c.get("claim_id"),
                                "alignment": "claim_candidate"})
    return {"concept_alignments": len(concept_pairs),
            "claim_alignments": claim_pairs,
            "note": "same concept does not mean same scholarly claim"}


def further_research_candidates(gaps: list[str]) -> list[dict[str, Any]]:
    """Phrase open gaps as research candidates (section 45).

    A generated candidate is a suggestion to search, never a
    claim that a source exists; extra searches run only on an
    explicit user action or inside the existing HTTP budget.
    """
    return [{"gap": g, "existence": "unconfirmed",
             "action": "search_on_explicit_user_action"}
            for g in gaps if g]


def _snapshot_id(store: Any, project_id: str) -> str:
    docs = store.list_documents(project_id)
    cits = store.list_citations(project_id)
    arts = store.list_artefact_rows(project_id)
    basis = json.dumps({
        "docs": sorted((d["library_id"], d["record_id"],
                        d.get("verification_status"),
                        d.get("rights_trust")) for d in docs),
        "cits": sorted((c["citation_id"], c.get("verification_status"))
                       for c in cits),
        "arts": sorted((a["artefact_id"], a["trust"]) for a in arts),
    }, sort_keys=True, default=str)
    return "snap_" + hashlib.sha256(basis.encode()).hexdigest()[:24]


def generate_research_report(store: Any, project_id: str, *,
                             code_version: str = "1.0.0b11",
                             git_commit: str = "") -> dict[str, Any]:
    """Build a research report (Markdown + JSON) for a project.

    Sections (section 46): summary, questions, claims by state,
    supporting candidates, contradicting candidates, source
    dependence, timeline, numeric comparison, unresolved items,
    rights state, reproducibility.  Evidence references are
    validated against the project's documents/citations;
    unresolvable references are listed as unresolved and never
    rendered as evidence.  No upstream text is inserted.
    """
    from .evidence_graph import build_project_graph
    from .workspace.research_artefacts import (
        list_artefacts, project_research_progress)

    project = store.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    docs = {(d["library_id"], d["record_id"]): d
            for d in store.list_documents(project_id)}
    cit_ids = {c["citation_id"] for c in store.list_citations(project_id)}
    progress = project_research_progress(store, project_id)
    graph = build_project_graph(store, project_id, limit=2000)

    questions: list[str] = []
    claims: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    record_refs: list[dict[str, str]] = []
    citation_refs: list[str] = []
    unresolved_refs: list[dict[str, Any]] = []
    timeline_events: list[dict[str, Any]] = []

    def add_ref(ref: dict[str, Any], where: str) -> None:
        key = (ref.get("library_id"), ref.get("record_id"))
        if key in docs:
            entry = {"library_id": key[0], "record_id": key[1]}
            if entry not in record_refs:
                record_refs.append(entry)
        else:
            unresolved_refs.append({"where": where, "ref": ref})

    for art in list_artefacts(store, project_id):
        if art["trust"] == "user_asserted":
            continue  # note envelopes never feed a report
        payload = art.get("payload") or {}
        kind = art["kind"]
        if kind == "b10_research_question" or kind == "research_question":
            q = payload.get("question") or {}
            text = q if isinstance(q, str) else (
                q.get("original_question") or q.get("text"))
            if text:
                questions.append(text)
        elif kind in ("b10_claim_assessment", "claim_assessment"):
            for a in payload.get("assessments") or []:
                claims.append(a)
                if a.get("library_id") and a.get("record_id"):
                    add_ref({"library_id": a["library_id"],
                             "record_id": a["record_id"]}, "assessment")
                if a.get("citation_id"):
                    if a["citation_id"] in cit_ids:
                        if a["citation_id"] not in citation_refs:
                            citation_refs.append(a["citation_id"])
                    else:
                        unresolved_refs.append(
                            {"where": "assessment_citation",
                             "ref": a["citation_id"]})
        elif kind in ("b10_comparison", "comparison"):
            comparisons.append(payload)
            for ref in payload.get("record_refs") or []:
                add_ref(ref, "comparison")
        elif kind in ("b10_timeline", "timeline"):
            for e in payload.get("events") or []:
                timeline_events.append(e)

    claim_states = classify_claim_states(claims)
    timeline = build_timeline(timeline_events)
    rights_rows = [{"library_id": d["library_id"],
                    "record_id": d["record_id"],
                    "rights_trust": d.get("rights_trust"),
                    "rights_status": d.get("rights_status")}
                   for d in docs.values()]
    report = {
        "report_id": "rep_" + uuid.uuid4().hex[:16],
        "schema_version": REPORT_SCHEMA_VERSION,
        "project_id": project_id,
        "project_title": project.get("title"),
        "snapshot_id": _snapshot_id(store, project_id),
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "code_version": code_version,
        "git_commit": git_commit,
        "ranking_mode": "not_applicable",
        "model_id": None, "model_revision": None,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "rights_policy_version": RIGHTS_POLICY_VERSION,
        "source_count": len(docs),
        "unresolved_count": len(unresolved_refs),
        "summary": {
            "documents": len(docs), "citations": len(cit_ids),
            "progress": progress,
            "graph_nodes": graph["node_count"],
            "graph_edges": graph["edge_count"]},
        "questions": questions,
        "claim_states": claim_states,
        "comparisons": comparisons,
        "timeline": timeline,
        "rights": rights_rows,
        "record_refs": record_refs,
        "citation_refs": citation_refs,
        "unresolved_references": unresolved_refs,
        "further_research": further_research_candidates(
            [u.get("where", "") for u in unresolved_refs]),
    }
    report["markdown"] = render_report_markdown(report)
    return report


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Research Report {report['report_id']}", "",
             f"- Project: {report.get('project_title')} "
             f"({report['project_id']})",
             f"- Snapshot: {report['snapshot_id']}",
             f"- Generated: {report['generated_at']}",
             f"- Code: {report['code_version']} "
             f"commit {report['git_commit'] or 'unknown'}",
             f"- Evidence policy: {report['evidence_policy_version']}; "
             f"rights policy: {report['rights_policy_version']}",
             f"- Sources: {report['source_count']}; "
             f"unresolved references: {report['unresolved_count']}",
             "", "## Research questions"]
    lines += [f"- {q}" for q in report["questions"]] or ["- (none)"]
    lines += ["", "## Claims by state"]
    for c in report["claim_states"]:
        lines.append(f"- {c['claim_id']}: {c['state']} "
                     f"(independence: {c['independence']})")
    if not report["claim_states"]:
        lines.append("- (none)")
    lines += ["", "## Timeline (ordering does not assert causality)"]
    for e in report["timeline"]["events"]:
        lines.append(f"- {e['year']} [{e['date_kind']}] {e['label']}")
    if not report["timeline"]["events"]:
        lines.append("- (none)")
    lines += ["", "## Rights state"]
    for r in report["rights"]:
        lines.append(f"- {r['library_id']}/{r['record_id']}: "
                     f"trust={r['rights_trust']} status={r['rights_status']}")
    lines += ["", "## Unresolved references"]
    for u in report["unresolved_references"]:
        lines.append(f"- {u['where']}: {u['ref']}")
    if not report["unresolved_references"]:
        lines.append("- (none)")
    lines += ["", "## Reproducibility",
              f"- report_id: {report['report_id']}",
              f"- schema_version: {report['schema_version']}",
              f"- snapshot_id: {report['snapshot_id']}"]
    return "\n".join(lines) + "\n"
