"""Rights policy for persistent storage (b7; final-review
revision of brief sections 3, 19, 20 and review sections 4, 6).

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
- OCR full text: never bulk-stored;
- original images: never stored as bytes (URLs only);
- external transfer: no feature performs it.

Classification is FAIL-CLOSED (final review section 4):
- official licence URIs are parsed structurally;
- exact licence names are matched strictly, and an
  unrecognised CC combination is UNKNOWN, never CC BY;
- negated statements ("not in the public domain", "CC0 does
  not apply", "status has not been established") are never
  read as grants;
- contradictory statements classify as unknown;
- a licence that covers only the METADATA of a record is
  not a licence for its OCR text and classifies as unknown
  for excerpt purposes.

Categories keep distinct legal concepts distinct: a public
domain dedication (CC0), a Public Domain Mark (a label, not
a licence), a CC licence grant, a NoC-NC restriction
statement (not a licence), contractual restrictions and
current access restrictions are not interchangeable.

Non-commercial CC categories (BY-NC, BY-NC-SA) permit
excerpt storage as a default because the workspace is a
personal, non-commercial research tool; the system cannot
verify the user's actual purpose, so any commercial use is
outside this default and the reason text says so. NoC-NC is
a restriction statement rather than a grant, so it does NOT
permit excerpt storage by default.

A licence name alone does not decide everything (purpose,
jurisdiction and scope matter in law); the policy is a
conservative engineering default, not a legal guarantee.
The 2,000-character excerpt cap is a system limit, not a
statement about lawful quotation length. The user's own
notes are their writing and are never gated.
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

# Categories whose terms grant reuse broadly enough for the
# default excerpt storage of a personal research workspace.
_EXCERPT_OK = {"public_domain", "cc_by", "cc_by_sa", "cc_by_nc", "cc_by_nc_sa"}

_CC_COMBOS = {"": "cc_by", "sa": "cc_by_sa", "nc": "cc_by_nc", "nd": "cc_by_nd",
              "nc-sa": "cc_by_nc_sa", "nc-nd": "cc_by_nc_nd"}

_CC_URI = re.compile(
    r"creativecommons\.org/licenses/(by(?:-(?:nc|sa|nd|nc-sa|nc-nd))?)/", re.IGNORECASE)
_CC_NAME = re.compile(
    r"\bcc[ -](by(?:-(?:nc|sa|nd|nc-sa|nc-nd))?)(?:\s+\d\.\d)?(?![-\w])", re.IGNORECASE)
_RS_URI = re.compile(r"rightsstatements\.org/vocab/([A-Za-z-]+)/", re.IGNORECASE)
_NEGATION = re.compile(
    r"(not (in|released|under|part of)|does not apply|do not apply|"
    r"has not been established|not been established|not established|"
    r"status (is )?unknown|undetermined|パブリックドメインではない|"
    r"権利処理未了)", re.IGNORECASE)


def _cc_category(flags: str) -> str | None:
    return _CC_COMBOS.get(flags.lower())


def classify_rights(statement: str | dict | None) -> str:
    """Map a rights statement to a policy category, fail-closed.
    Accepts the service's Rights dict shape as well as a string."""
    if isinstance(statement, dict):
        statement = statement.get("statement") or statement.get("status") or ""
    text = (statement or "").strip()
    if not text:
        return "unknown"
    low = text.lower()
    if low in ("unknown", "不明", "rights unknown", "undetermined"):
        return "unknown"

    found: set[str] = set()

    # -- structured identifiers first -------------------------------------
    if "creativecommons.org/publicdomain/zero/" in low:
        found.add("public_domain")  # CC0 dedication (URI form)
    if "creativecommons.org/publicdomain/mark/" in low:
        found.add("public_domain")  # Public Domain Mark (URI form)
    m = _CC_URI.search(low)
    if m:
        cat = _cc_category(m.group(1)[2:].lstrip("-") if m.group(1) != "by" else "")
        if cat:
            found.add(cat)
    m = _RS_URI.search(low)
    if m:
        code = m.group(1).lower()
        if code == "inc":
            found.add("copyrighted")
        elif code == "noc-nc":
            found.add("noc_nc")
        elif code in ("noc-cr", "noc-oklr"):
            found.add("restricted")
        elif code == "noc-us":
            found.add("public_domain")
        else:  # UND, CNE and anything unrecognised
            found.add("unknown")
    m = _CC_NAME.search(low)
    if m:
        cat = _cc_category(m.group(1)[2:].lstrip("-") if m.group(1) != "by" else "")
        if cat:
            found.add(cat)
        elif "cc" in low:
            # A CC-looking name whose combination is not one of
            # the six licences: never fall back to CC BY.
            found.add("unknown")

    # -- negations veto any positive reading of the same text --------------
    negated = bool(_NEGATION.search(low))

    # -- explicit restrictive markers ---------------------------------------
    if ("access restricted" in low or "restricted access" in low
            or "貸出制限" in text or "アクセス制限" in text):
        found.add("restricted")
    if "in copyright" in low or "all rights reserved" in low:
        found.add("copyrighted")

    if not negated:
        spaced = low.replace("-", " ")
        if "public domain mark" in spaced:
            found.add("public_domain")
        elif "public domain" in spaced or "パブリックドメイン" in text \
                or "著作権保護期間満了" in text:
            found.add("public_domain")
        if re.search(r"\bcc0\b", low) and "metadata" not in low:
            found.add("public_domain")
        if "no copyright" in spaced and "non commercial" in spaced or "noc-nc" in low:
            found.add("noc_nc")
        if "noc_nc" not in found:
            # the bare word "copyright" also appears inside
            # "No Copyright ..." statements, which are handled
            # above; only use it as a marker otherwise
            if "著作権" in text and "満了" not in text:
                found.add("copyrighted")
            elif "copyright" in low or "©" in text:
                found.add("copyrighted")
    else:
        # A negated grant leaves the status unestablished unless
        # an explicit restrictive marker above already said more.
        found.add("unknown")

    # A licence for the metadata alone says nothing about the
    # OCR text of the item.
    if "metadata" in low and found & (_EXCERPT_OK | {"public_domain"}):
        if not (_CC_URI.search(low) or "publicdomain" in low):
            return "unknown"

    found.discard("unknown") if len(found) > 1 else None
    if len(found) == 1:
        return found.pop()
    if not found:
        return "unknown"
    # Contradictory statements: fail closed.
    return "unknown"


# Rights trust states (b8 section 2). A rights statement may
# PERMIT excerpt storage only when this server observed it from
# the upstream source itself. Statements that arrived inside an
# imported project file or a restored backup database are claims:
# they are preserved as history and can only ever restrict, never
# permit, until a server-side observation (a fresh fetch or a
# re-verification) confirms them.
TRUST_SERVER_OBSERVED = "server_observed"
TRUST_IMPORTED_CLAIM = "imported_claim"
TRUST_RESTORED_CLAIM = "restored_claim"

NC_CATEGORIES = {"cc_by_nc", "cc_by_nc_sa"}


def is_server_source(source: Any) -> bool:
    """True when a rights observation was made by this server
    (live fetch / reverify), not carried in by an import file or
    a restored backup."""
    if not isinstance(source, str) or not source:
        return False
    return not source.startswith("imported") and source != "restored_backup"


def evaluate(statement: str | dict | None) -> dict[str, Any]:
    """Policy decision for one rights statement."""
    if isinstance(statement, dict):
        statement = statement.get("statement") or statement.get("status") or ""
    category = classify_rights(statement)
    excerpt_ok = category in _EXCERPT_OK
    if category in NC_CATEGORIES:
        reason = ("excerpt storage under a NonCommercial licence requires "
                  "the user to confirm a non-commercial research purpose "
                  "for each save; the system cannot verify the purpose "
                  "itself (b8 section 2)")
    elif excerpt_ok:
        reason = "excerpt storage allowed for this rights category"
    else:
        reason = ("excerpt storage withheld by default: rights are "
                  f"{category}; the citation reference is kept without the text")
    return {
        "category": category,
        "statement": statement or "unknown",
        "metadata_storage": True,
        "excerpt_storage": excerpt_ok,
        "excerpt_export": excerpt_ok,
        "excerpt_requires_confirmation": category in NC_CATEGORIES,
        "fulltext_storage": False,
        "image_storage": False,
        "metadata_export": True,
        "external_transfer": False,
        "access_recheck_required": category not in _EXCERPT_OK,
        "reason": reason,
    }


def effective_decision(statement_at_save: str | None,
                       latest_statement: str | None) -> dict[str, Any]:
    """Current effective decision: an excerpt is shown/exported
    only if BOTH the save-time rights and the latest observed
    rights permit it (final review section 6). A later, more
    restrictive observation can never be undone by the older
    snapshot, and a failed recheck never upgrades anything."""
    base = evaluate(statement_at_save)
    if latest_statement is None:
        return base
    latest = evaluate(latest_statement)
    if base["excerpt_storage"] and not latest["excerpt_storage"]:
        return {**base, "excerpt_storage": False, "excerpt_export": False,
                "category": latest["category"],
                "reason": ("excerpt withheld: the latest rights observation "
                           f"({latest['category']}) is more restrictive than "
                           "the rights at save time"),
                "rights_changed": True}
    return base


def trusted_decision(save_statement: str | None, save_trust: str | None,
                     observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Effective decision under the trust model (b8 section 2).

    ``observations`` are rights observations oldest to newest,
    each with ``statement`` and ``source``. A claim-trust save
    (imported file / restored backup) can permit excerpt use
    only through a later server-side observation; every later
    observation, whatever its source, can still restrict."""
    latest = observations[-1].get("statement") if observations else None
    if (save_trust or TRUST_SERVER_OBSERVED) == TRUST_SERVER_OBSERVED:
        return effective_decision(save_statement, latest)
    server_statements = [o.get("statement") for o in observations
                         if is_server_source(o.get("source"))]
    if not server_statements:
        base = evaluate(save_statement)
        return {**base, "excerpt_storage": False, "excerpt_export": False,
                "trust": save_trust,
                "reason": ("excerpt withheld: the rights information is an "
                           "unverified claim (imported file or restored "
                           "backup) and no server-side rights observation "
                           "confirms it; reference information only until "
                           "re-verification")}
    decision = effective_decision(server_statements[-1], latest)
    return {**decision, "trust": save_trust,
            "reason": decision["reason"] + " (permitted via a server-side "
                      "rights observation; the original claim itself "
                      "grants nothing)"}


def gate_excerpt(excerpt: str | None, statement: str | None,
                 *, nc_confirmed: bool = False) -> tuple[str | None, dict[str, Any]]:
    """Apply the excerpt policy. Returns (stored_excerpt, decision).
    Oversize excerpts are WITHHELD, never silently truncated:
    stored text, offsets and hash must always agree (the save
    API rejects oversize selections outright; other paths
    withhold and report). NonCommercial categories additionally
    require an explicit per-save purpose confirmation (b8)."""
    decision = evaluate(statement)
    if excerpt is None:
        return None, decision
    if not decision["excerpt_storage"]:
        return None, decision
    if decision["excerpt_requires_confirmation"] and not nc_confirmed:
        return None, {**decision, "excerpt_storage": False,
                      "excerpt_export": False,
                      "reason": ("excerpt withheld: this licence is "
                                 "NonCommercial and no non-commercial "
                                 "research purpose was confirmed for this "
                                 "save")}
    if len(excerpt) > MAX_EXCERPT_CHARS:
        return None, {**decision,
                      "reason": (f"excerpt exceeds the {MAX_EXCERPT_CHARS}-character "
                                 "storage limit (a system limit, not a legal "
                                 "quotation limit); withheld rather than truncated")}
    return excerpt, decision
