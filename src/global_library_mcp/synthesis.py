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
    produce a "confirmed" or "verified" state. Independence is
    "confirmed" only for an explicit reviewed record (final
    review section 7); a caller's basis string alone never
    confirms it.
    """
    from .research import independence_state

    out = []
    for a in assessments:
        st = a.get("status")
        state = st if st in CLAIM_STATES else "unresolved"
        out.append({"claim_id": a.get("claim_id"),
                    "state": state,
                    "document_id": a.get("document_id"),
                    "independence": (
                        "confirmed" if independence_state(a)
                        == "independently_reviewed_independence"
                        else "unknown")})
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
    from .research import _convert

    out = []
    for f in facts:
        row = {"original_value": f.get("value"),
               "original_unit": f.get("unit"),
               "target": f.get("subject"), "region": f.get("place"),
               "era": f.get("era"), "definition": f.get("definition"),
               "scope": f.get("scope"),
               "approximate": bool(f.get("approximate")),
               "comparability": (
                   "heuristic_only: numeric closeness (including any "
                   "+/-10% tolerance) is a comparison heuristic and "
                   "never by itself establishes consistency")}
        try:
            value = float(f.get("value"))
        except (TypeError, ValueError):
            value = None
        if value is not None:
            conv = _convert(value, f.get("unit"))
            if conv is not None:
                family, base_value = conv
                base_unit = {"power": "W", "length": "m",
                             "mass": "kg"}.get(family, family)
                if base_unit != f.get("unit"):
                    row["normalized_value"] = base_value
                    row["normalized_unit"] = base_unit
                    row["conversion"] = (
                        f"{f.get('value')} {f.get('unit')} = "
                        f"{base_value} {base_unit}")
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
    """Content hash over the FULL normalized report inputs
    (final review section 25): project metadata, document
    content, citation content and references, artefact payloads
    and trust states, latest rights observation ids, evidence
    verification states, policies and generation settings.
    Secrets, session data and temporary tokens are never part of
    the inputs and never enter the hash."""
    project = store.get_project(project_id) or {}
    docs = store.list_documents(project_id)
    cits = store.list_citations(project_id)
    arts = store.list_artefact_rows(project_id)

    def doc_norm(d: dict[str, Any]) -> Any:
        latest = store.latest_rights_observation(
            d["saved_document_id"]) or {}
        return [d["saved_document_id"], d["library_id"],
                d["record_id"], d.get("title"), d.get("authors"),
                d.get("year"), d.get("verification_status"),
                d.get("rights_trust"), latest.get("observation_id"),
                latest.get("category")]

    def cit_norm(c: dict[str, Any]) -> Any:
        return [c["citation_id"], c["saved_document_id"],
                c.get("page_id"), c.get("citation_key"),
                c.get("excerpt_hash"),
                c.get("quotation_verification_status"),
                c.get("page_mapping_status")]

    def art_norm(a: dict[str, Any]) -> Any:
        return [a["artefact_id"], a["kind"], a["trust"],
                json.dumps(a.get("payload") or {}, sort_keys=True,
                           ensure_ascii=False, default=str)]

    basis = json.dumps({
        "project": [project.get("name"), project.get("created_at")],
        "docs": sorted(doc_norm(d) for d in docs),
        "cits": sorted(cit_norm(c) for c in cits),
        "arts": sorted(art_norm(a) for a in arts),
        "policies": [EVIDENCE_POLICY_VERSION, RIGHTS_POLICY_VERSION,
                     REPORT_SCHEMA_VERSION],
        "settings": {"code_version": "1.0.0b11",
                     "ranking_mode": "not_applicable",
                     "model_id": None},
    }, sort_keys=True, default=str, ensure_ascii=False)
    return "snap_" + hashlib.sha256(basis.encode()).hexdigest()[:24]


_SUPPORT = {"supported_candidate"}
_OPPOSE = {"conflicting_candidate", "contradiction_candidate"}
_CONTEXT = {"contextual_only", "partially_supported"}
_STATE_RANK = ["supported_candidate", "conflicting_candidate",
               "partially_supported", "contextual_only",
               "insufficient_evidence", "evidence_reference_only",
               "not_checked"]


def _aggregate_state(rows: list[dict[str, Any]]) -> str:
    states = {r["state"] for r in rows}
    for candidate in _STATE_RANK:
        if candidate in states:
            return candidate
    return "not_checked"


def generate_research_report(store: Any, project_id: str, *,
                             code_version: str = "1.0.0b11",
                             git_commit: str = "") -> dict[str, Any]:
    """Build a research report (Markdown + JSON) for a project.

    Final-review semantics:

    - trust separation (section 20): assessments from
      imported_unverified / restored_unverified artefacts are
      HISTORICAL ASSERTIONS - shown in their own section, never
      counted as current support, independent evidence or
      verified results;
    - citation integrity (section 21): an assessment bound to a
      saved citation is re-checked against the citation's CURRENT
      document, page, excerpt hash and verification state; any
      mismatch downgrades it to unresolved /
      revalidation_required, never leaving it supported;
    - every claim is displayed (section 22), including claims
      with zero assessments ("no evidence registered");
    - claim -> document traceability (section 24): each claim
      lists title/author/year/citation key/URL/page of its
      references in both Markdown and JSON;
    - the snapshot hash covers the full normalized inputs
      (section 25) read under the store lock so one report never
      mixes points in time.
    """
    from .evidence_graph import build_project_graph
    from .workspace.research_artefacts import (
        list_artefacts, project_research_progress)

    lock = getattr(store, "_lock", None)
    if lock is not None:
        with lock:
            return _generate_locked(store, project_id,
                                    code_version=code_version,
                                    git_commit=git_commit,
                                    build_project_graph=build_project_graph,
                                    list_artefacts=list_artefacts,
                                    project_research_progress=project_research_progress)
    return _generate_locked(store, project_id,
                            code_version=code_version,
                            git_commit=git_commit,
                            build_project_graph=build_project_graph,
                            list_artefacts=list_artefacts,
                            project_research_progress=project_research_progress)


def _generate_locked(store: Any, project_id: str, *,
                     code_version: str, git_commit: str,
                     build_project_graph: Any, list_artefacts: Any,
                     project_research_progress: Any) -> dict[str, Any]:
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    doc_rows = store.list_documents(project_id)
    docs = {(d["library_id"], d["record_id"]): d for d in doc_rows}
    docs_by_id = {d["saved_document_id"]: d for d in doc_rows}
    cit_rows = store.list_citations(project_id)
    cits_by_id = {c["citation_id"]: c for c in cit_rows}
    progress = project_research_progress(store, project_id)
    graph = build_project_graph(store, project_id, limit=2000)

    questions: list[str] = []
    current_rows: list[dict[str, Any]] = []       # server artefacts
    historical_rows: list[dict[str, Any]] = []    # imported/restored
    claim_entries: dict[str, dict[str, Any]] = {}
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

    def resolve_assessment(a: dict[str, Any]) -> dict[str, Any]:
        """Effective state after CURRENT citation/document
        integrity checks (section 21)."""
        state = a.get("status") or "unresolved"
        if state not in CLAIM_STATES and state != "revalidation_required":
            state = "unresolved"
        problems: list[str] = []
        cit = None
        if a.get("citation_id"):
            cit = cits_by_id.get(a["citation_id"])
            if cit is None:
                problems.append("citation_missing")
            else:
                cdoc = docs_by_id.get(cit["saved_document_id"]) or {}
                if a.get("library_id") and a["library_id"] != cdoc.get("library_id"):
                    problems.append("citation_library_mismatch")
                if a.get("record_id") and a["record_id"] != cdoc.get("record_id"):
                    problems.append("citation_record_mismatch")
                if a.get("page_id") and a["page_id"] != cit.get("page_id"):
                    problems.append("citation_page_mismatch")
                ref = a.get("evidence_ref") or {}
                if ref.get("excerpt_hash") and cit.get("excerpt_hash") and \
                        ref["excerpt_hash"] != cit["excerpt_hash"]:
                    problems.append("citation_excerpt_hash_mismatch")
                if str(cit.get("quotation_verification_status") or "").endswith("unverified") or \
                        str(cit.get("page_mapping_status") or "").endswith("unverified"):
                    problems.append("citation_revalidation_required")
        elif a.get("library_id") and a.get("record_id"):
            if (a["library_id"], a["record_id"]) not in docs:
                problems.append("document_missing")
        if problems:
            state = ("revalidation_required"
                     if "citation_revalidation_required" in problems
                     and len(problems) == 1 else "unresolved")
        return {"claim_id": a.get("claim_id"), "state": state,
                "stored_status": a.get("status"),
                "document_id": a.get("document_id"),
                "integrity_problems": problems,
                "independence": (
                    "confirmed" if (a.get("independence_review") or {}).get("basis")
                    else "unknown")}

    def claim_entry(claim: dict[str, Any], art: dict[str, Any]) -> dict[str, Any]:
        cid = claim.get("claim_id") or art["artefact_id"]
        entry = claim_entries.get(cid)
        if entry is None:
            entry = {"claim_id": cid,
                     "statement": claim.get("original_statement")
                     or claim.get("statement") or "",
                     "question_id": claim.get("question_id")
                     or claim.get("research_question_id"),
                     "trust": art["trust"],
                     "artefact_id": art["artefact_id"],
                     "last_evaluated_at": art.get("created_at"),
                     "rows": [], "historical_rows": [],
                     "references": []}
            claim_entries[cid] = entry
        return entry

    for art in list_artefacts(store, project_id):
        if art["trust"] == "user_asserted":
            continue  # note envelopes never feed a report
        payload = art.get("payload") or {}
        kind = art["kind"].removeprefix("b10_")
        server = art["trust"] == "server_generated"
        if kind == "research_question":
            q = payload.get("question") or {}
            text = q if isinstance(q, str) else (
                q.get("original_question") or q.get("text"))
            if text:
                questions.append(text)
        elif kind == "claim_assessment":
            claim = payload.get("claim") or {}
            if not claim and payload.get("claim_id"):
                claim = {"claim_id": payload["claim_id"]}
            entry = claim_entry(claim, art)
            for a in payload.get("assessments") or []:
                row = resolve_assessment(a)
                row["trust"] = art["trust"]
                if server:
                    current_rows.append(row)
                    entry["rows"].append(row)
                else:
                    historical_rows.append(row)
                    entry["historical_rows"].append(row)
                if a.get("library_id") and a.get("record_id"):
                    add_ref({"library_id": a["library_id"],
                             "record_id": a["record_id"]}, "assessment")
                    doc = docs.get((a["library_id"], a["record_id"]))
                    if doc is not None:
                        cit = cits_by_id.get(a.get("citation_id") or "")
                        reference = {
                            "library_id": doc["library_id"],
                            "record_id": doc["record_id"],
                            "saved_document_id": doc["saved_document_id"],
                            "title": doc.get("title"),
                            "authors": doc.get("authors"),
                            "year": doc.get("year"),
                            "citation_key": (
                                cit.get("citation_key") if cit else
                                f"{doc['library_id']}:{doc['record_id']}"),
                            "landing_url": doc.get("landing_url")
                            or doc.get("url"),
                            "page_id": a.get("page_id")
                            or (cit.get("page_id") if cit else None),
                            "citation_id": a.get("citation_id"),
                            "citation_verification": (
                                cit.get("quotation_verification_status")
                                if cit else None),
                            "excerpt_display": "reference_only"}
                        if reference not in entry["references"]:
                            entry["references"].append(reference)
                if a.get("citation_id"):
                    if a["citation_id"] in cits_by_id:
                        if a["citation_id"] not in citation_refs:
                            citation_refs.append(a["citation_id"])
                    else:
                        unresolved_refs.append(
                            {"where": "assessment_citation",
                             "ref": a["citation_id"]})
        elif kind == "comparison_b10":
            comparisons.append(payload)
            for ref in payload.get("record_refs") or []:
                add_ref(ref, "comparison")
        elif kind == "timeline":
            for e in payload.get("events") or []:
                timeline_events.append(e)

    claims_out: list[dict[str, Any]] = []
    for entry in claim_entries.values():
        rows = entry.pop("rows")
        hist = entry.pop("historical_rows")
        counts = {
            "support": sum(1 for r in rows if r["state"] in _SUPPORT),
            "oppose": sum(1 for r in rows if r["state"] in _OPPOSE),
            "context": sum(1 for r in rows if r["state"] in _CONTEXT),
            "other": sum(1 for r in rows
                         if r["state"] not in _SUPPORT | _OPPOSE | _CONTEXT),
            "historical": len(hist)}
        entry["assessment_counts"] = counts
        entry["evidence_registered"] = bool(rows or hist)
        entry["state"] = (_aggregate_state(rows) if rows else
                          "not_checked")
        entry["display_note"] = (
            None if rows else
            "no current evidence registered （根拠未登録）"
            if not hist else
            "only historical (imported/restored) assertions; "
            "not current evidence")
        entry["independence"] = (
            "confirmed" if any(r["independence"] == "confirmed"
                                for r in rows) else "unknown")
        claims_out.append(entry)

    claim_states = [
        {"claim_id": r["claim_id"], "state": r["state"],
         "document_id": r["document_id"],
         "independence": r["independence"],
         "integrity_problems": r["integrity_problems"]}
        for r in current_rows]
    historical_claim_states = [
        {"claim_id": r["claim_id"], "state": r["state"],
         "trust": r["trust"],
         "counted_as_current_evidence": False}
        for r in historical_rows]
    timeline = build_timeline(timeline_events)
    rights_rows = []
    for d in docs.values():
        latest = store.latest_rights_observation(d["saved_document_id"])
        rights_rows.append({
            "library_id": d["library_id"], "record_id": d["record_id"],
            "rights_trust": (latest or {}).get("trust")
                            or d.get("rights_trust"),
            "rights_status": (latest or {}).get("category"),
            "rights_statement": (latest or {}).get("statement"),
            "rights_observation_id": (latest or {}).get("observation_id")})
    documents_out = [{
        "library_id": d["library_id"], "record_id": d["record_id"],
        "saved_document_id": d["saved_document_id"],
        "title": d.get("title"), "authors": d.get("authors"),
        "year": d.get("year"),
        "landing_url": d.get("landing_url") or d.get("url")}
        for d in docs.values()]
    report = {
        "report_id": "rep_" + uuid.uuid4().hex[:16],
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_kind": "current_regeneration",
        "saved_report_note": (
            "a saved report record freezes the state observed at "
            "save time; this report is a CURRENT regeneration - "
            "compare snapshot_id values to detect differences. "
            "Re-display never bypasses current rights: excerpt "
            "display follows the latest rights observation while "
            "bibliographic references remain visible."),
        "project_id": project_id,
        "project_title": project.get("name") or project.get("title"),
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
            "documents": len(docs), "citations": len(cits_by_id),
            "progress": progress,
            "graph_nodes": graph["node_count"],
            "graph_edges": graph["edge_count"]},
        "questions": questions,
        "claims": claims_out,
        "claim_states": claim_states,
        "historical_claim_states": historical_claim_states,
        "documents": documents_out,
        "comparisons": comparisons,
        "timeline": timeline,
        "numeric_note": (
            "numeric closeness (including any +/-10% tolerance) "
            "is a comparison heuristic only and never by itself "
            "establishes consistency"),
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
    """Render the report with b7-level Markdown escaping
    (section 23): every stored/user-derived string passes
    through the shared ``_md`` escaper, so project names,
    questions, claim ids/statements, timeline labels, document
    ids and unresolved references cannot inject headings, links,
    images, raw HTML, code fences or javascript: URLs."""
    from .workspace.exports import _md, _md_url

    lines = [f"# Research Report {_md(report['report_id'])}", "",
             f"- Project: {_md(report.get('project_title'))} "
             f"({_md(report['project_id'])})",
             f"- Snapshot: {_md(report['snapshot_id'])}",
             f"- Generated: {_md(report['generated_at'])}",
             f"- Code: {_md(report['code_version'])} "
             f"commit {_md(report['git_commit'] or 'unknown')}",
             f"- Evidence policy: {_md(report['evidence_policy_version'])}; "
             f"rights policy: {_md(report['rights_policy_version'])}",
             f"- Sources: {report['source_count']}; "
             f"unresolved references: {report['unresolved_count']}",
             "", "## Research questions"]
    lines += [f"- {_md(q)}" for q in report["questions"]] or ["- (none)"]
    lines += ["", "## Claims"]
    for c in report.get("claims") or []:
        counts = c["assessment_counts"]
        lines.append(
            f"- {_md(c['claim_id'])}: {c['state']} "
            f"(support {counts['support']}, oppose {counts['oppose']}, "
            f"context {counts['context']}, other {counts['other']}, "
            f"historical {counts['historical']}; "
            f"independence: {c['independence']}; "
            f"trust: {_md(c['trust'])})")
        if c.get("statement"):
            lines.append(f"  - statement: {_md(c['statement'])}")
        if c.get("display_note"):
            lines.append(f"  - note: {_md(c['display_note'])}")
        for ref in c.get("references") or []:
            url = _md_url(ref.get("landing_url"))
            lines.append(
                f"  - ref: {_md(ref.get('title'))} "
                f"({_md(ref.get('authors'))}, {_md(ref.get('year'))}) "
                f"[{_md(ref.get('citation_key'))}] "
                f"doc {_md(ref.get('record_id'))} "
                f"page {_md(ref.get('page_id'))}"
                + (f" {url}" if url else ""))
    if not report.get("claims"):
        lines.append("- (none)")
    if report.get("historical_claim_states"):
        lines += ["", "## Historical assertions (imported/restored, "
                  "not current evidence)"]
        for h in report["historical_claim_states"]:
            lines.append(f"- {_md(h['claim_id'])}: {_md(h['state'])} "
                         f"(trust: {_md(h['trust'])})")
    lines += ["", "## Timeline (ordering does not assert causality)"]
    for e in report["timeline"]["events"]:
        lines.append(f"- {e['year']} [{_md(e['date_kind'])}] "
                     f"{_md(e['label'])}")
    if not report["timeline"]["events"]:
        lines.append("- (none)")
    lines += ["", "## Rights state"]
    for r in report["rights"]:
        lines.append(f"- {_md(r['library_id'])}/{_md(r['record_id'])}: "
                     f"trust={_md(r['rights_trust'])} "
                     f"status={_md(r['rights_status'])}")
    lines += ["", "## Unresolved references"]
    for u in report["unresolved_references"]:
        ref = u["ref"]
        rendered = (_md(ref) if isinstance(ref, str) else
                    _md(json.dumps(ref, ensure_ascii=False, default=str)))
        lines.append(f"- {_md(u['where'])}: {rendered}")
    if not report["unresolved_references"]:
        lines.append("- (none)")
    lines += ["", "## Reproducibility",
              f"- report_id: {_md(report['report_id'])}",
              f"- schema_version: {_md(report['schema_version'])}",
              f"- snapshot_id: {_md(report['snapshot_id'])}"]
    return "\n".join(lines) + "\n"
