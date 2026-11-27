"""External document/page identifiers (b9 brief section 11).

Internal identity stays ``(library_id, record_id)``. The
external form is an opaque, versioned, strictly parsed token:

    glm1.<library_id>.<base64url(record_id)>
    glm1p.<library_id>.<base64url(page_id)>

Rules enforced here:

- the library id must be a plain registry-style token
  (``[a-z0-9][a-z0-9-]*``) - the caller additionally checks it
  against the live registry;
- the payload is base64url WITHOUT padding and must decode to
  UTF-8 text of 1..512 characters with no control characters;
- URLs, file paths, ``..``, slashes and whitespace can never
  be a valid external id, so an id can never be reinterpreted
  as a fetch target or a path;
- an id is an identifier, not a credential: possession of an
  id grants nothing - every fetch re-checks authorisation,
  consent, budget and the transfer policy server-side.
"""

from __future__ import annotations

import base64
import binascii
import re

_DOC_PREFIX = "glm1"
_PAGE_PREFIX = "glm1p"
_LIBRARY_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_B64_RE = re.compile(r"[A-Za-z0-9_-]{1,1024}")
_MAX_RAW = 512


class ExternalIdError(ValueError):
    """Raised when an external identifier fails strict parsing."""


def _encode(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_RAW:
        raise ExternalIdError("identifier payload out of range")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
        raise ExternalIdError("identifier payload has control characters")
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(token: str) -> str:
    if not _B64_RE.fullmatch(token or ""):
        raise ExternalIdError("identifier payload is not base64url")
    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise ExternalIdError("identifier payload does not decode") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExternalIdError("identifier payload is not UTF-8") from exc
    if not text or len(text) > _MAX_RAW:
        raise ExternalIdError("identifier payload out of range")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise ExternalIdError("identifier payload has control characters")
    # Round-trip check: rejects non-canonical encodings (e.g.
    # padded or aliased forms of the same bytes).
    if _encode(text) != token:
        raise ExternalIdError("identifier payload is not canonical")
    return text


def _make(prefix: str, library_id: str, raw: str) -> str:
    if not _LIBRARY_RE.fullmatch(library_id or ""):
        raise ExternalIdError("library id is not a registry token")
    return f"{prefix}.{library_id}.{_encode(raw)}"


def _parse(prefix: str, value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ExternalIdError("identifier must be a string")
    parts = value.split(".")
    if len(parts) != 3 or parts[0] != prefix:
        raise ExternalIdError("identifier has the wrong shape or version")
    library_id = parts[1]
    if not _LIBRARY_RE.fullmatch(library_id):
        raise ExternalIdError("library id is not a registry token")
    return library_id, _decode(parts[2])


def make_document_id(library_id: str, record_id: str) -> str:
    return _make(_DOC_PREFIX, library_id, record_id)


def make_page_id(library_id: str, page_id: str) -> str:
    return _make(_PAGE_PREFIX, library_id, page_id)


def parse_document_id(value: str) -> tuple[str, str]:
    """Return ``(library_id, record_id)`` or raise ExternalIdError."""
    return _parse(_DOC_PREFIX, value)


def parse_page_id(value: str) -> tuple[str, str]:
    """Return ``(library_id, page_id)`` or raise ExternalIdError."""
    return _parse(_PAGE_PREFIX, value)
