"""Per-library record_id grammars (b9 final review, P0).

Canonical base64url round-tripping proves an external id is
well-formed ENCODING; it says nothing about whether the decoded
record_id is a plausible identifier FOR THAT LIBRARY. Each
adapter has its own id space, so validation is per-library and
structural, derived from the adapters' own id handling:

- ndl: numeric PIDs only (the adapter's _safe_pid).
- internet-archive: the adapter's _ID_RE
  (``[A-Za-z0-9][A-Za-z0-9._-]*``), never containing ``..``.
- loc: a Chronicling America issue id
  (``<sn>/<yyyy-mm-dd>/ed-<n>``) or a plain item token.
- gallica: the full ark URL on gallica.bnf.fr, or the bare ark
  name the adapter also accepts.
- bsb: MDZ object ids (``bsb`` + digits).
- e-rara: numeric ids (optionally OAI-prefixed upstream; the
  record_id space itself is numeric).
- europeana: dataset-prefixed paths starting with ``/``.
- ddb: opaque item tokens.
- finna: dotted record ids (source prefix + local id).
- finland-nl-digi: numeric binding ids.
- kb-delpher: Delpher URNs (``<ns>:<id>:mpeg21:a|p<digits>``,
  the adapter's _URN_RE).
- japan-search: the adapter's _ID_RE (``<source>-<id>``).
- dpla: the adapter's record id pattern.

A grammar pass is NOT proof a document exists - it is a
structural gate that keeps URLs, paths, traversal fragments
and cross-library id confusion out of the service layer.
Existence and identity are confirmed by the fetch itself.
"""

from __future__ import annotations

import re

from global_library_mcp.external.ids import ExternalIdError

_TOKEN = r"[A-Za-z0-9][A-Za-z0-9._-]*"

_GRAMMARS: dict[str, re.Pattern[str]] = {
    "ndl": re.compile(r"^\d{1,20}$"),
    "internet-archive": re.compile(rf"^{_TOKEN}$"),
    "loc": re.compile(
        r"^([a-z0-9]+/\d{4}-\d{2}-\d{2}/ed-\d+|[A-Za-z0-9][A-Za-z0-9._-]*)$"),
    "gallica": re.compile(
        r"^(https://gallica\.bnf\.fr/ark:/12148/[A-Za-z0-9]+|[A-Za-z0-9]+)$"),
    "bsb": re.compile(r"^bsb\d{4,}$"),
    "e-rara": re.compile(r"^\d{1,20}$"),
    "europeana": re.compile(r"^/[A-Za-z0-9][A-Za-z0-9._/-]*$"),
    "ddb": re.compile(rf"^{_TOKEN}$"),
    "finna": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    "finland-nl-digi": re.compile(r"^\d{1,20}$"),
    "kb-delpher": re.compile(r"^[A-Za-z0-9]+:[0-9A-Za-z]+:mpeg21:[ap]\d+$"),
    "japan-search": re.compile(r"^[a-z][a-z0-9]*-[0-9a-z]+$"),
    "dpla": re.compile(rf"^{_TOKEN}$"),
}

KNOWN_LIBRARIES = frozenset(_GRAMMARS)


def validate_record_id(library_id: str, record_id: str) -> None:
    """Raise ExternalIdError unless ``record_id`` is a
    structurally valid identifier for ``library_id``."""
    pattern = _GRAMMARS.get(library_id)
    if pattern is None:
        raise ExternalIdError(f"unknown library {library_id!r}")
    if not isinstance(record_id, str) or not record_id:
        raise ExternalIdError("record id is empty")
    if ".." in record_id:
        raise ExternalIdError("record id contains a traversal fragment")
    if "://" in record_id and library_id != "gallica":
        raise ExternalIdError("record id is a URL, not an identifier")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in record_id):
        raise ExternalIdError("record id contains control characters")
    if not pattern.fullmatch(record_id):
        raise ExternalIdError(
            f"record id does not match the {library_id} identifier grammar")
