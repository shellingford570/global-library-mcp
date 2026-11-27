"""External transfer rights policy (b9 brief sections 12/15).

Independent of the workspace storage policy: a statement that
permits LOCAL storage does not permit transfer to an external
AI service, and this module never reads workspace state. It
decides from three inputs only:

1. the per-library transfer matrix (official API/terms level),
2. the item's own rights statement, classified here from its
   structured rights URI where one exists (free text is
   treated conservatively), and
3. the deployment's excerpt switch (default OFF).

Defaults (brief section 12): OCR full text is never
transferable; original-image binaries are never transferable;
in-copyright items transfer no text; CC BY-NC and similar are
NOT assumed to satisfy their NonCommercial condition for a
transfer to an AI service; a Public Domain Mark or a
RightsStatements.org label alone never settles transfer
permission (the matrix must also allow the content kind);
unknown rights yield reference-only output.
"""

from __future__ import annotations

import re
from typing import Any

from global_library_mcp.external.transfer_matrix import matrix_entry
from global_library_mcp.rights_uri import parse_rights_uri

# Item categories (this module's own classification).
PUBLIC_DOMAIN = "public_domain"
CC_BY = "cc_by"
CC_NC = "cc_nc"            # any NonCommercial-bearing CC licence
CC_OTHER = "cc_other"      # CC licences without NC (e.g. BY-SA, BY-ND)
NOC_NC = "noc_nc"          # RightsStatements No Copyright - Non-Commercial
COPYRIGHTED = "copyrighted"
RESTRICTED = "restricted"  # NoC-CR / NoC-OKLR / explicit restrictions
UNKNOWN = "unknown"

_EXCERPT_ITEM_OK = {PUBLIC_DOMAIN, CC_BY, CC_OTHER}

_ACCESS_RE = re.compile(
    r"lending|borrow|restricted access|access restricted|in-library|"
    r"閲覧のみ|貸出", re.IGNORECASE)


def classify_item_rights(statement: Any) -> str:
    """Classify ONE item rights statement for TRANSFER.

    Structured rights URIs decide; anything else - free text,
    missing statements, unrecognised URIs - is UNKNOWN, except
    explicit in-copyright / restriction signals which classify
    as such. A Public Domain Mark URI classifies as
    public_domain here, but transfer still requires the matrix
    to allow the content kind (see decide_transfer)."""
    if isinstance(statement, dict):
        statement = (statement.get("statement") or statement.get("status")
                     or statement.get("uri") or "")
    text = str(statement or "").strip()
    if not text:
        return UNKNOWN
    parsed = parse_rights_uri(text)
    if parsed is not None:
        label = str(parsed.get("label") or "")
        if parsed["kind"] == "cc_public_domain":
            return PUBLIC_DOMAIN  # CC0 or Public Domain Mark URI
        if parsed["kind"] == "cc_licence":
            if "-nc" in label or label.endswith("nc"):
                return CC_NC
            if label in ("cc-by",):
                return CC_BY
            return CC_OTHER
        if parsed["kind"] == "rights_statement":
            code = label.lower()
            if code == "inc":
                return COPYRIGHTED
            if code == "noc-nc":
                return NOC_NC
            if code in ("noc-cr", "noc-oklr"):
                return RESTRICTED
            if code.startswith("noc-"):
                return PUBLIC_DOMAIN
            return UNKNOWN  # UND / CNE / unrecognised
    low = text.lower()
    if "in copyright" in low or "著作権" in low and "なし" not in low:
        return COPYRIGHTED
    if "public domain" in low:
        return PUBLIC_DOMAIN
    return UNKNOWN


def is_access_restricted(statement: Any) -> bool:
    if isinstance(statement, dict):
        statement = statement.get("statement") or statement.get("status") or ""
    return bool(_ACCESS_RE.search(str(statement or "")))


def decide_transfer(library_id: str, statement: Any, *,
                    excerpt_enabled: bool = False,
                    matrix: dict[str, str] | None = None) -> dict[str, Any]:
    """Full transfer decision for one item.

    Returns the section-12 category labels plus the concrete
    per-kind permissions the projections enforce. ``matrix``
    may be injected (tests / future verified updates); by
    default the shipped matrix row for the library is used."""
    row = matrix if matrix is not None else matrix_entry(library_id)
    category = classify_item_rights(statement)
    access_restricted = is_access_restricted(statement)

    categories: list[str] = []
    metadata_ok = row.get("metadata") == "allowed" and not access_restricted
    if metadata_ok:
        categories.append("metadata_allowed")
    reference_ok = row.get("reference_url") == "allowed"
    if not metadata_ok:
        categories.append("reference_only")
    if category in (CC_BY, CC_OTHER, PUBLIC_DOMAIN) and category != PUBLIC_DOMAIN:
        categories.append("attribution_required")
    if category in (CC_NC, NOC_NC):
        categories.append("purpose_restricted")
        categories.append("redistribution_restricted")
    if access_restricted:
        categories.append("access_restricted")
    if row.get("third_party_ai") != "allowed":
        categories.append("terms_unconfirmed")
    if category == UNKNOWN:
        categories.append("rights_unknown")
    if category in (COPYRIGHTED, RESTRICTED):
        categories.append("external_transfer_denied")

    excerpt_ok = bool(
        excerpt_enabled
        and row.get("ocr_excerpt") == "allowed"
        and row.get("third_party_ai") == "allowed"
        and category in _EXCERPT_ITEM_OK
        and not access_restricted)
    if excerpt_ok:
        categories.append("excerpt_allowed")

    return {
        "library_id": library_id,
        "item_rights_category": category,
        "categories": categories,
        "metadata_allowed": metadata_ok,
        "reference_allowed": reference_ok,
        "excerpt_allowed": excerpt_ok,
        "image_url_allowed": bool(row.get("image_url") == "allowed"
                                  and not access_restricted),
        "image_binary_allowed": False,   # never (brief section 12)
        "full_text_allowed": False,      # never (brief section 12)
        "attribution": row.get("attribution", ""),
        "matrix_source": row.get("source", ""),
        "excerpt_denial_reasons": _excerpt_reasons(
            row, category, access_restricted, excerpt_enabled, excerpt_ok),
    }


def _excerpt_reasons(row: dict[str, str], category: str,
                    access_restricted: bool, excerpt_enabled: bool,
                    excerpt_ok: bool) -> list[str]:
    if excerpt_ok:
        return []
    reasons = []
    if not excerpt_enabled:
        reasons.append("external excerpt transfer is disabled in this deployment")
    if row.get("ocr_excerpt") != "allowed":
        reasons.append("the library's terms do not confirm OCR excerpt transfer")
    if row.get("third_party_ai") != "allowed":
        reasons.append("transfer to a third-party AI service is not confirmed by the library's terms")
    if category not in _EXCERPT_ITEM_OK:
        reasons.append(f"item rights category {category} does not permit excerpt transfer")
    if access_restricted:
        reasons.append("the item is access-restricted")
    return reasons
