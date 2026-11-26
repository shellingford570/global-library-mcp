"""Rights policy for persistent storage (b7, brief sections 3, 19, 20).

Being able to FETCH a text is not permission to STORE, EXPORT
or REDISTRIBUTE it. This module classifies a record's rights
statement and decides, per storage category, what the
workspace may do by default:

- bibliographic metadata and links: storable (the workspace's
  basic function);
- short OCR excerpts: stored/exported only for public-domain
  and permissive-CC material by default. Unknown,
  unverified, copyrighted or access-restricted material is
  NOT auto-saved: the citation reference (ids, page, URLs,
  verification states) is kept and the excerpt is omitted
  with the reason recorded;
- OCR full text: never bulk-stored in b7;
- original images: never stored as bytes in b7 (URLs only);
- external transfer: no feature performs it.

A licence name alone does not decide everything (purpose,
jurisdiction and scope matter in law); the policy is a
conservative engineering default, not a legal guarantee.
The user's own notes are their writing and are never gated.
"""
from __future__ import annotations

import re
from typing import Any

MAX_EXCERPT_CHARS = 2000

CATEGORIES = (
    "public_domain", "cc_by", "cc_by_sa", "cc_by_nc", "cc_by_nd",
    "cc_by_nc_sa", "cc_by_nc_nd", "noc_nc", "copyrighted",
    "restricted", "unknown",
)

_PERMISSIVE = {"public_domain", "cc_by", "cc_by_sa"}
_NONCOMMERCIAL_OK = {"cc_by_nc", "cc_by_nc_sa", "noc_nc"}


def classify_rights(statement: str | dict | None) -> str:
    """Map a free-text rights statement to a policy category.
    Accepts the service's Rights dict shape as well as a string."""
    if isinstance(statement, dict):
        statement = statement.get("statement") or statement.get("status") or ""
    text = (statement or "").strip().lower()
    if not text or text in ("unknown", "不明", "rights unknown"):
        return "unknown"
    if "access restricted" in text or "restricted access" in text or "lending" in text \
            or "アクセス制限" in text or "in copyright" in text and "restricted" in text:
        return "restricted"
    if "public domain" in text or "public domain mark" in text or text.startswith("pdm") \
            or "著作権保護期間満了" in text or "パブリックドメイン" in text:
        return "public_domain"
    if text.startswith("cc0") or "cc0" in text:
        return "public_domain"
    m = re.search(r"cc[ -]by(?:[ -](nc|sa|nd)){0,2}", text)
    if m or "creativecommons.org/licenses/by" in text:
        flags = set(re.findall(r"(nc|sa|nd)", text.split("licenses/by", 1)[-1][:12])) \
            if "licenses/by" in text else set(re.findall(r"\b(nc|sa|nd)\b", text))
        combo = "_".join(sorted(flags))
        mapping = {"": "cc_by", "sa": "cc_by_sa", "nc": "cc_by_nc", "nd": "cc_by_nd",
                   "nc_sa": "cc_by_nc_sa", "nc_nd": "cc_by_nc_nd"}
        return mapping.get(combo, "cc_by")
    if "noc-nc" in text or "no copyright - non-commercial" in text:
        return "noc_nc"
    if "copyright" in text or "著作権" in text or "all rights reserved" in text \
            or "©" in text:
        return "copyrighted"
    return "unknown"


def evaluate(statement: str | dict | None) -> dict[str, Any]:
    """Policy decision for one rights statement."""
    if isinstance(statement, dict):
        statement = statement.get("statement") or statement.get("status") or ""
    category = classify_rights(statement)
    excerpt_ok = category in _PERMISSIVE or category in _NONCOMMERCIAL_OK
    return {
        "category": category,
        "statement": statement or "unknown",
        "metadata_storage": True,
        "excerpt_storage": excerpt_ok,
        "excerpt_export": excerpt_ok,
        "fulltext_storage": False,
        "image_storage": False,
        "metadata_export": True,
        "external_transfer": False,
        "access_recheck_required": category in ("unknown", "restricted", "copyrighted"),
        "reason": (
            "excerpt storage allowed for this rights category"
            if excerpt_ok else
            "excerpt storage withheld by default: rights are "
            f"{category}; the citation reference is kept without the text"),
    }


def gate_excerpt(excerpt: str | None, statement: str | None) -> tuple[str | None, dict[str, Any]]:
    """Apply the excerpt policy. Returns (stored_excerpt, decision)."""
    decision = evaluate(statement)
    if excerpt is None:
        return None, decision
    if not decision["excerpt_storage"]:
        return None, decision
    if len(excerpt) > MAX_EXCERPT_CHARS:
        return excerpt[:MAX_EXCERPT_CHARS], {**decision, "truncated": True}
    return excerpt, decision
