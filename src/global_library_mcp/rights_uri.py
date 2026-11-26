"""Strict structural parsing of rights URIs, shared by the
adapters (display classification) and the workspace rights
policy (storage decisions) - b8 final review section 15.

A URI is recognised only when it stands on the EXACT official
host (creativecommons.org / rightsstatements.org) with the
official path grammar and a well-formed version. A licence
URI embedded in another host's path or query string, a
lookalike host, userinfo, an abnormal port, or a malformed
version yields None. Recognition here never grants anything:
what a recognised URI means for storage is decided by the
workspace policy on statements this server observed.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_CC_LICENCE_PATH = re.compile(
    r"/licenses/(by(?:-(?:nc|sa|nd|nc-sa|nc-nd))?)/(\d\.\d)(/.*)?")
_CC_PD_PATH = re.compile(r"/publicdomain/(zero|mark)/(\d\.\d)(/.*)?")
_RS_PATH = re.compile(r"/vocab/([A-Za-z-]+)/(\d\.\d)/?")


def parse_rights_uri(url: Any) -> dict[str, Any] | None:
    """{kind, label, version} for a structurally valid rights
    URI, else None."""
    if not isinstance(url, str) or not url.strip():
        return None
    if any(ord(ch) < 0x20 for ch in url):
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port not in (None, 80, 443):
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "creativecommons.org":
        m = _CC_LICENCE_PATH.fullmatch(path)
        if m:
            return {"kind": "cc_licence", "label": f"cc-{m.group(1).lower()}",
                    "version": m.group(2)}
        m = _CC_PD_PATH.fullmatch(path)
        if m:
            return {"kind": "cc_public_domain", "label": f"cc-{m.group(1)}",
                    "version": m.group(2)}
        return None
    if host == "rightsstatements.org":
        m = _RS_PATH.fullmatch(path)
        if m:
            return {"kind": "rights_statement", "label": m.group(1),
                    "version": m.group(2)}
        return None
    return None


def rights_uri_label(url: Any) -> str | None:
    """Coarse DISPLAY label for a rights URI (never a storage
    decision): cc0 / public-domain-mark / creative-commons-
    licence / rightsstatements-in-copyright /
    rightsstatements-no-copyright / rightsstatements-other /
    other / None."""
    if not url or not isinstance(url, str):
        return None
    parsed_ok = parse_rights_uri(url)
    if parsed_ok is None:
        # Not a structurally valid rights URI on an official
        # host: it may still be some other rights reference,
        # but it is never classified as a known licence.
        return "other"
    if parsed_ok["kind"] == "cc_public_domain":
        return "cc0" if parsed_ok["label"] == "cc-zero" else "public-domain-mark"
    if parsed_ok["kind"] == "cc_licence":
        return "creative-commons-licence"
    label = str(parsed_ok["label"]).lower()
    if label == "inc":
        return "rightsstatements-in-copyright"
    if label.startswith("noc-"):
        return "rightsstatements-no-copyright"
    return "rightsstatements-other"
