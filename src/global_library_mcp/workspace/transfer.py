"""Project JSON export / import (b7; final review sections
5, 6, 15, 16, 17, 18, 26).

Export reads one consistent snapshot (store.export_bundle)
and re-gates every excerpt against the CURRENT effective
rights (save-time statement AND latest observation): a
restriction learned after saving applies to exports too.
Verification observations and rights observations are part
of the export - dropping them would lose the research
history the migration exists to preserve.

Import treats the file as untrusted input:
- size / record / string / depth limits, duplicate JSON
  keys and non-finite numbers rejected at parse time;
- EVERY reference is validated before insertion, with a
  separate id map per entity type; an unknown reference
  rejects the whole file (nothing is silently dropped or
  nulled);
- the storage policy is applied to imported excerpts
  exactly as to UI-saved ones (rights gate + length cap),
  for citations AND comparison excerpts; the file's rights
  statements are unverified CLAIMS: they are recorded as
  claims, never as confirmed rights, and omissions are
  counted and reported;
- imported verification state is downgraded: current
  statuses become imported_unverified, verified_at is
  cleared, and the claimed values survive only inside an
  imported_claim observation; the file's own observation
  history is restored as history, never as current state;
- original timestamps (saved_at, created_at, retrieved_at,
  observed_at) are preserved; the migration time is recorded
  in the imported_claim observations, not by overwriting
  the records' own times;
- insertion happens in ONE transaction; any error rolls
  the whole import back.

Exports larger than the import limits carry an explicit
warning; very large projects should migrate via the SQLite
backup instead (docs/project-import-export.md).
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

try:
    from importlib.metadata import version as _pkg_version
    APP_VERSION = _pkg_version("global-library-mcp")
except Exception:  # pragma: no cover - source checkout without install
    APP_VERSION = "unknown"
from .policy import MAX_EXCERPT_CHARS
from .policy import effective_decision
from .policy import evaluate as evaluate_rights
from .policy import trusted_decision
from .store import SCHEMA_VERSION, WorkspaceStore, new_id, now_iso, search_text

FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 250_000            # JSON objects walked (structure cap)
MAX_RESEARCH_RECORDS = 60_000    # actual research records
MAX_STRING = 100_000
MAX_DEPTH = 32
MAX_COMPARISON_EXCERPT_BYTES = 1_000_000

_URL_OK = re.compile(r"^https?://", re.IGNORECASE)
_SECRET_KEYS = {"api_key", "apikey", "token", "password", "secret",
                "session", "authorization", "cookie"}
_KEY_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]{0,99}$")
_CLAIMED_RESOLUTION_OK = {"candidate_match", "probable_match", "unverified",
                          "not_checked", "unresolved", "imported_unverified", None}


class ImportError_(ValueError):
    pass


# --------------------------------------------------------------------- export
def export_project(store: WorkspaceStore, project_id: str) -> dict[str, Any]:
    bundle = store.export_bundle(project_id)
    project = bundle["project"]
    documents = bundle["documents"]
    citations = bundle["citations"]
    docs_by_id = {d["saved_document_id"]: d for d in documents}

    def _trust_for(cit: dict[str, Any]) -> str:
        # b8 trust model: only citations this server fetched
        # itself carry server-observed rights; everything else
        # inherits the document's trust state.
        if cit.get("provenance") == "system_fetched":
            return "server_observed"
        if cit.get("provenance") == "imported":
            return "imported_claim"
        doc = docs_by_id.get(cit["saved_document_id"]) or {}
        return doc.get("rights_trust") or "server_observed"

    omissions: list[dict[str, Any]] = []
    export_citations = []
    for cit in citations:
        item = dict(cit)
        statement = (cit.get("rights_at_save") or {}).get("statement")
        decision = trusted_decision(
            statement, _trust_for(cit),
            bundle["rights_observations"].get(cit["saved_document_id"]) or [])
        if item.get("original_excerpt") and not decision["excerpt_export"]:
            item["original_excerpt"] = None
            item["excerpt_omitted_reason"] = "omitted at export: " + decision["reason"]
            omissions.append({"kind": "citation_excerpt",
                              "citation_id": cit["citation_id"],
                              "reason": item["excerpt_omitted_reason"]})
        item["verification_observations"] = item.pop("observations", [])
        export_citations.append(item)
    export_comparisons = []
    for comp in bundle["comparisons"]:
        item = dict(comp)
        excerpts = {}
        for doc_id, value in (comp.get("original_excerpts") or {}).items():
            if isinstance(value, list):
                doc = docs_by_id.get(doc_id, {})
                statement = (doc.get("rights_snapshot") or {}).get("statement")
                decision = trusted_decision(
                    statement, doc.get("rights_trust") or "server_observed",
                    bundle["rights_observations"].get(doc_id) or [])
                if decision["excerpt_export"]:
                    excerpts[doc_id] = value
                else:
                    excerpts[doc_id] = {"omitted": "omitted at export: " + decision["reason"],
                                        "count": len(value)}
                    omissions.append({"kind": "comparison_excerpt",
                                      "comparison_id": comp["comparison_id"],
                                      "saved_document_id": doc_id,
                                      "reason": decision["reason"]})
            else:
                excerpts[doc_id] = value
        item["original_excerpts"] = excerpts
        export_comparisons.append(item)
    payload = {
        "format": "global-library-mcp-project",
        "format_version": FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "application_version": APP_VERSION,
        "exported_at": now_iso(),
        "project": {k: project.get(k) for k in
                    ("title", "description", "created_at", "updated_at", "tags")},
        "saved_documents": documents,
        "saved_citations": export_citations,
        "research_notes": bundle["notes"],
        "search_history": bundle["history"],
        "saved_comparisons": export_comparisons,
        "collections": [{**c, "saved_document_ids":
                         bundle["collection_members"].get(c["collection_id"], [])}
                        for c in bundle["collections"]],
        "rights_observations": bundle["rights_observations"],
        "export_omissions": omissions,
    }
    records = sum(len(payload[k]) for k in
                  ("saved_documents", "saved_citations", "research_notes",
                   "search_history", "saved_comparisons", "collections"))
    size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    warnings = []
    if records > MAX_RESEARCH_RECORDS or size > MAX_IMPORT_BYTES:
        warnings.append(
            f"this export ({records} records, {size} bytes) exceeds the JSON "
            f"import limits ({MAX_RESEARCH_RECORDS} records, {MAX_IMPORT_BYTES} "
            "bytes); migrate this project with the SQLite backup instead")
    payload["record_count"] = records
    payload["export_warnings"] = warnings
    return payload


# --------------------------------------------------------------------- import
def parse_import_json(raw: bytes) -> Any:
    """Strict JSON parse for imports: duplicate keys and
    non-finite numbers are rejected, not silently accepted."""
    def no_dupes(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ImportError_(f"duplicate JSON key: {key}")
            obj[key] = value
        return obj

    def no_nonfinite(name):
        raise ImportError_(f"non-finite number in import: {name}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes,
                          parse_constant=no_nonfinite)
    except ImportError_:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise ImportError_(f"invalid JSON: {exc}") from exc


def _walk_limits(node: Any, depth: int, counters: dict[str, int]) -> None:
    if depth > MAX_DEPTH:
        raise ImportError_("JSON nesting too deep")
    if isinstance(node, str):
        if len(node) > MAX_STRING:
            raise ImportError_("string too long")
    elif isinstance(node, float):
        if not math.isfinite(node):
            raise ImportError_("non-finite number")
    elif isinstance(node, dict):
        counters["records"] += 1
        for key, value in node.items():
            if key.lower() in _SECRET_KEYS:
                raise ImportError_(f"secret-like field is not importable: {key}")
            _walk_limits(value, depth + 1, counters)
    elif isinstance(node, list):
        for value in node:
            _walk_limits(value, depth + 1, counters)
    if counters["records"] > MAX_RECORDS:
        raise ImportError_("too many JSON objects")


def _check_url(value: Any, field: str) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str) or not _URL_OK.match(value):
        raise ImportError_(f"invalid URL in {field}")


def _require_list(payload: dict[str, Any], key: str) -> list:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ImportError_(f"{key} must be a list")
    return value


def _ts(value: Any, fallback: str) -> str:
    """Preserve an original timestamp when it is a plausible
    ISO string; never invent one silently - fall back to the
    import time only when absent/invalid."""
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", value) \
            and len(value) <= 40:
        return value
    return fallback


def import_project(store: WorkspaceStore, payload: Any) -> dict[str, Any]:
    """Validate everything first, then insert in ONE transaction
    with fresh internal ids and per-type id maps."""
    if not isinstance(payload, dict):
        raise ImportError_("top level must be an object")
    if payload.get("format") != "global-library-mcp-project":
        raise ImportError_("unsupported format")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ImportError_(f"unsupported format_version: {payload.get('format_version')}")
    if int(payload.get("schema_version") or 0) > SCHEMA_VERSION:
        raise ImportError_("file schema is newer than this build")
    counters = {"records": 0}
    _walk_limits(payload, 0, counters)

    project_in = payload.get("project")
    if not isinstance(project_in, dict) or not str(project_in.get("title") or "").strip():
        raise ImportError_("project.title is required")
    documents = _require_list(payload, "saved_documents")
    citations = _require_list(payload, "saved_citations")
    notes = _require_list(payload, "research_notes")
    history = _require_list(payload, "search_history")
    comparisons = _require_list(payload, "saved_comparisons")
    collections = _require_list(payload, "collections")
    rights_obs_in = payload.get("rights_observations") or {}
    if not isinstance(rights_obs_in, dict):
        raise ImportError_("rights_observations must be an object")
    research_records = (len(documents) + len(citations) + len(notes)
                        + len(history) + len(comparisons) + len(collections))
    if research_records > MAX_RESEARCH_RECORDS:
        raise ImportError_(
            f"too many research records: {research_records} > {MAX_RESEARCH_RECORDS}")

    # -- validate every reference BEFORE inserting anything ----------------
    doc_ids: set[str] = set()
    citation_keys: set[str] = set()
    for doc in documents:
        if not isinstance(doc, dict):
            raise ImportError_("saved_documents entries must be objects")
        did = doc.get("saved_document_id")
        if not isinstance(did, str) or not did or len(did) > 200 or did in doc_ids:
            raise ImportError_("duplicate or invalid saved_document_id")
        doc_ids.add(did)
        if not doc.get("library_id") or not doc.get("record_id"):
            raise ImportError_("document requires library_id and record_id")
        _check_url(doc.get("landing_url"), "landing_url")
        key = doc.get("citation_key")
        if key is not None:
            if not isinstance(key, str) or not _KEY_OK.match(key):
                raise ImportError_(f"invalid citation_key: {key!r}")
            if key in citation_keys:
                raise ImportError_(f"duplicate citation_key: {key}")
            citation_keys.add(key)
    cit_ids: set[str] = set()
    for cit in citations:
        if not isinstance(cit, dict):
            raise ImportError_("saved_citations entries must be objects")
        cid = cit.get("citation_id")
        if not isinstance(cid, str) or not cid or cid in cit_ids:
            raise ImportError_("duplicate or invalid citation_id")
        cit_ids.add(cid)
        if cit.get("saved_document_id") not in doc_ids:
            raise ImportError_("citation references an unknown document")
        _check_url(cit.get("source_url"), "source_url")
        _check_url(cit.get("image_url"), "image_url")
    for note in notes:
        if not isinstance(note, dict):
            raise ImportError_("research_notes entries must be objects")
        if note.get("saved_document_id") is not None \
                and note.get("saved_document_id") not in doc_ids:
            raise ImportError_("note references an unknown document")
        if note.get("citation_id") is not None \
                and note.get("citation_id") not in cit_ids:
            raise ImportError_("note references an unknown citation")
    for comp in comparisons:
        if not isinstance(comp, dict):
            raise ImportError_("saved_comparisons entries must be objects")
        comp_docs = comp.get("saved_document_ids") or []
        if not isinstance(comp_docs, list) or not comp_docs:
            raise ImportError_("comparison requires saved_document_ids")
        for did in comp_docs:
            if did not in doc_ids:
                raise ImportError_("comparison references an unknown document")
        excerpts = comp.get("original_excerpts") or {}
        if not isinstance(excerpts, dict):
            raise ImportError_("comparison original_excerpts must be an object")
        for did in excerpts:
            if did not in doc_ids:
                raise ImportError_("comparison excerpt references an unknown document")
    coll_ids: set[str] = set()
    for coll in collections:
        if not isinstance(coll, dict) or not coll.get("name"):
            raise ImportError_("collections entries require a name")
        cid = coll.get("collection_id")
        if cid is not None:
            if cid in coll_ids:
                raise ImportError_("duplicate collection_id")
            coll_ids.add(cid)
        for did in coll.get("saved_document_ids") or []:
            if did not in doc_ids:
                raise ImportError_("collection references an unknown document")
    for did in rights_obs_in:
        if did not in doc_ids:
            raise ImportError_("rights observation references an unknown document")

    ts = now_iso()
    doc_map: dict[str, str] = {}
    cit_map: dict[str, str] = {}
    omissions: list[dict[str, Any]] = []
    imported_claims = 0
    conn = store._conn  # single-transaction import on the store connection
    with store._lock, conn:
        new_project_id = new_id()
        conn.execute(
            "INSERT INTO projects (project_id, title, description, created_at, updated_at, schema_version)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (new_project_id, str(project_in["title"])[:500],
             str(project_in.get("description") or "")[:20000],
             _ts(project_in.get("created_at"), ts), _ts(project_in.get("updated_at"), ts),
             SCHEMA_VERSION))
        for name in project_in.get("tags") or []:
            if isinstance(name, str):
                store._attach_project_tag(new_project_id, name)
        for doc in documents:
            new_doc_id = new_id()
            doc_map[doc["saved_document_id"]] = new_doc_id
            values = {k: doc.get(k) for k in WorkspaceStore._DOC_FIELDS}
            if values.get("resolution_status") not in _CLAIMED_RESOLUTION_OK:
                values["resolution_status"] = "imported_unverified"
            conn.execute(
                "INSERT INTO saved_documents (saved_document_id, project_id, library_id, record_id,"
                " identifiers, rights_snapshot, saved_at, updated_at, search_text, citation_key,"
                " rights_trust, "
                + ", ".join(WorkspaceStore._DOC_FIELDS) + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                + ", ".join("?" for _ in WorkspaceStore._DOC_FIELDS) + ")",
                (new_doc_id, new_project_id, str(doc["library_id"])[:100],
                 str(doc["record_id"])[:500],
                 json.dumps(doc.get("identifiers") or {}, ensure_ascii=False),
                 json.dumps({**(doc.get("rights_snapshot") or {}),
                             "trust": "imported_claim"}, ensure_ascii=False),
                 _ts(doc.get("saved_at"), ts), _ts(doc.get("updated_at"), ts),
                 search_text(values.get("title"), values.get("author"),
                             values.get("publication_date"), doc.get("library_id")),
                 doc.get("citation_key"), "imported_claim",
                 *[values[k] for k in WorkspaceStore._DOC_FIELDS]))
            for name in doc.get("tags") or []:
                if isinstance(name, str):
                    row = conn.execute("SELECT tag_id FROM tags WHERE name = ?", (name,)).fetchone()
                    tag_id = row["tag_id"] if row else new_id()
                    if not row:
                        conn.execute("INSERT INTO tags (tag_id, name) VALUES (?, ?)", (tag_id, name))
                    conn.execute(
                        "INSERT OR IGNORE INTO document_tags (saved_document_id, tag_id) VALUES (?, ?)",
                        (new_doc_id, tag_id))
        for cit in citations:
            new_cit_id = new_id()
            cit_map[cit["citation_id"]] = new_cit_id
            values = {k: cit.get(k) for k in WorkspaceStore._CIT_FIELDS}
            claimed = {
                "claimed_status": values.get("quotation_verification_status"),
                "claimed_mapping": values.get("page_mapping_status"),
                "claimed_image_status": values.get("image_verification_status"),
                "claimed_verified_at": values.get("verified_at"),
                "imported_at": ts,
            }
            # b8 section 2: an imported file's rights statement
            # is an unverified claim and can NEVER permit excerpt
            # storage by itself. Excerpt texts are withheld on
            # import regardless of the claimed category; the
            # reference information (page, offsets, hash) is kept
            # so re-verification against the live source can
            # re-admit the excerpt later.
            rights = values.get("rights_at_save")
            rights_dict = rights if isinstance(rights, dict) else {}
            excerpt = values.get("original_excerpt")
            if excerpt:
                omissions.append({
                    "kind": "citation_excerpt",
                    "citation_id": cit["citation_id"],
                    "reason": ("withheld on import: imported rights claims "
                               "are not independently verified; reference "
                               "information only until re-verification")})
                values["original_excerpt"] = None
                values["excerpt_omitted_reason"] = (
                    "withheld on import: imported rights claims are not "
                    "independently verified; reference information only "
                    "until re-verification")
            values["rights_at_save"] = json.dumps(
                {**rights_dict, "imported_claim": True,
                 "trust": "imported_claim",
                 "claim_source": "imported_file"}, ensure_ascii=False)
            values["provenance"] = "imported"
            values["quotation_verification_status"] = "imported_unverified"
            values["page_mapping_status"] = "imported_unverified"
            values["image_verification_status"] = "imported_unverified"
            values["verified_at"] = None
            values["retrieved_at"] = _ts(values.get("retrieved_at"), ts) \
                if values.get("retrieved_at") else None
            conn.execute(
                "INSERT INTO saved_citations (citation_id, saved_document_id, saved_at, search_text, "
                + ", ".join(WorkspaceStore._CIT_FIELDS) + ") VALUES (?, ?, ?, ?, "
                + ", ".join("?" for _ in WorkspaceStore._CIT_FIELDS) + ")",
                (new_cit_id, doc_map[cit["saved_document_id"]],
                 _ts(cit.get("saved_at"), ts),
                 search_text(values.get("original_excerpt"), values.get("page_id")),
                 *[values[k] for k in WorkspaceStore._CIT_FIELDS]))
            if any(claimed[k] for k in ("claimed_status", "claimed_mapping",
                                         "claimed_image_status", "claimed_verified_at")):
                imported_claims += 1
                conn.execute(
                    "INSERT INTO verification_observations (observation_id, citation_id, status, detail, observed_at)"
                    " VALUES (?, ?, 'imported_claim', ?, ?)",
                    (new_id(), new_cit_id, json.dumps(claimed, ensure_ascii=False), ts))
            for obs in cit.get("verification_observations") or cit.get("observations") or []:
                if not isinstance(obs, dict) or not obs.get("status"):
                    continue
                detail = obs.get("detail")
                if isinstance(detail, str):
                    try:
                        detail = json.loads(detail)
                    except json.JSONDecodeError:
                        detail = {"text": detail[:2000]}
                conn.execute(
                    "INSERT INTO verification_observations (observation_id, citation_id, status, detail, observed_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (new_id(), new_cit_id, str(obs["status"])[:100],
                     json.dumps({**(detail or {}), "imported": True}, ensure_ascii=False),
                     _ts(obs.get("observed_at"), ts)))
        for note in notes:
            conn.execute(
                "INSERT INTO research_notes (note_id, project_id, saved_document_id, citation_id,"
                " title, content, created_at, updated_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), new_project_id,
                 doc_map.get(note["saved_document_id"]) if note.get("saved_document_id") else None,
                 cit_map.get(note["citation_id"]) if note.get("citation_id") else None,
                 str(note.get("title") or "")[:500], str(note.get("content") or ""),
                 _ts(note.get("created_at"), ts), _ts(note.get("updated_at"), ts),
                 search_text(note.get("title"), note.get("content"))))
        for entry in history:
            if not isinstance(entry, dict):
                raise ImportError_("search_history entries must be objects")
            conn.execute(
                "INSERT INTO search_history (search_id, project_id, original_query, search_parameters,"
                " planned_variants, executed_variants, searched_libraries, skipped_libraries,"
                " result_summary, http_stats, search_status, created_at, provenance)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported')",
                (new_id(), new_project_id, str(entry.get("original_query") or "")[:2000],
                 json.dumps(entry.get("search_parameters") or {}, ensure_ascii=False),
                 json.dumps(entry.get("planned_variants") or [], ensure_ascii=False),
                 json.dumps(entry.get("executed_variants") or [], ensure_ascii=False),
                 json.dumps(entry.get("searched_libraries") or {}, ensure_ascii=False),
                 json.dumps(entry.get("skipped_libraries") or {}, ensure_ascii=False),
                 json.dumps(entry.get("result_summary") or {}, ensure_ascii=False),
                 json.dumps(entry.get("http_stats") or {}, ensure_ascii=False),
                 str(entry.get("search_status") or "completed")[:50],
                 _ts(entry.get("created_at"), ts)))
        docs_rights = {d["saved_document_id"]:
                       (d.get("rights_snapshot") or {}).get("statement")
                       for d in documents}
        for comp in comparisons:
            mapped = [doc_map[d] for d in comp.get("saved_document_ids") or []]
            excerpts_in = comp.get("original_excerpts") or {}
            excerpts_out: dict[str, Any] = {}
            total_bytes = 0
            for old_id, value in excerpts_in.items():
                new_id_ = doc_map[old_id]
                if isinstance(value, dict):  # already an omission record
                    excerpts_out[new_id_] = value
                    continue
                texts = value if isinstance(value, list) else []
                if texts:
                    # b8 section 2: comparison excerpts in an
                    # imported file rest on unverified rights
                    # claims; they are withheld on import exactly
                    # like citation excerpts.
                    excerpts_out[new_id_] = {
                        "omitted": ("withheld on import: imported rights "
                                    "claims are not independently verified"),
                        "count": len(texts)}
                    omissions.append({
                        "kind": "comparison_excerpt",
                        "saved_document_id": old_id,
                        "reason": ("withheld on import: imported rights "
                                   "claims are not independently verified")})
            conn.execute(
                "INSERT INTO saved_comparisons (comparison_id, project_id, title, saved_document_ids,"
                " comparison_aspects, original_excerpts, lexical_overlap, dictionary_concept_overlap,"
                " shared_by_all, shared_by_some, semantic_status, insufficient_evidence, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), new_project_id, str(comp.get("title") or "")[:500],
                 json.dumps(mapped), json.dumps(comp.get("comparison_aspects") or {}, ensure_ascii=False),
                 json.dumps(excerpts_out, ensure_ascii=False),
                 json.dumps(comp.get("lexical_overlap") or {}, ensure_ascii=False),
                 json.dumps(comp.get("dictionary_concept_overlap") or {}, ensure_ascii=False),
                 json.dumps(comp.get("shared_by_all") or [], ensure_ascii=False),
                 json.dumps(comp.get("shared_by_some") or [], ensure_ascii=False),
                 "not_checked", json.dumps(comp.get("insufficient_evidence") or [], ensure_ascii=False),
                 _ts(comp.get("created_at"), ts)))
        for coll in collections:
            new_coll_id = new_id()
            conn.execute(
                "INSERT INTO collections (collection_id, project_id, name, created_at) VALUES (?, ?, ?, ?)",
                (new_coll_id, new_project_id, str(coll["name"])[:200],
                 _ts(coll.get("created_at"), ts)))
            for did in coll.get("saved_document_ids") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO collection_documents (collection_id, saved_document_id)"
                    " VALUES (?, ?)", (new_coll_id, doc_map[did]))
        for old_doc_id, rows in rights_obs_in.items():
            if not isinstance(rows, list):
                continue
            for obs in rows:
                if not isinstance(obs, dict):
                    continue
                source = str(obs.get("source") or "")
                conn.execute(
                    "INSERT INTO rights_observations (observation_id, saved_document_id, statement,"
                    " category, source, observed_at, change_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (new_id(), doc_map[old_doc_id], obs.get("statement"),
                     obs.get("category"),
                     f"imported:{source}"[:200] if source else "imported",
                     _ts(obs.get("observed_at"), ts),
                     obs.get("change_status") or "observed"))
    project = store.get_project(new_project_id)
    return {"project": project,
            "id_map_size": len(doc_map) + len(cit_map),
            "imported": {"documents": len(documents), "citations": len(citations),
                         "notes": len(notes), "history": len(history),
                         "comparisons": len(comparisons),
                         "collections": len(collections)},
            "imported_verification_claims": imported_claims,
            "excerpt_omissions": omissions,
            "note": "imported verification states and rights statements are "
                    "historical claims, not current verification"}


def dumps_export(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
