"""Japan Search adapter (b8, section 9) - the National Diet
Library's cross-search platform for Japanese cultural
resources, via its official SPARQL endpoint and per-item
JSON-LD.

Access model (official developer documentation
https://jpsearch.go.jp/static/developer/introduction/en.html,
checked and probed live 2026-11-26):

- Search: fixed-template SPARQL against
  ``https://jpsearch.go.jp/rdf/sparql`` matching
  ``schema:name`` literals. The user's text is embedded ONLY
  as an escaped string literal (backslash / quote / control
  characters escaped or rejected); no user input can change
  the query structure. No API key.
- Detail: the item's own JSON-LD at
  ``https://jpsearch.go.jp/data/<id>.json`` (fetched through
  the validated fetcher; identity = the graph's main node @id
  must equal that exact URL). The graph separates the item
  node from its ``#sourceinfo`` node (provider, source data)
  and its ``#accessinfo`` node (licence, access restrictions,
  provider URLs) - all three are kept distinct here.

Japan Search is an AGGREGATOR: page OCR and originals live at
the providers. When an item's identifiers carry an NDL
permanent id (``info:ndljp/pid/<digits>``) it is reported as
an NDL handoff candidate for the existing NDL adapter; the
identifier is parsed structurally, never guessed from titles.
Provider URLs from accessInfo are data, never fetched.

Rights: the accessInfo licence is typically a
RightsStatements.org URI and is classified structurally; the
accessInfo descriptions also carry access restrictions (e.g.
NDL-only / library-and-personal transmission), which are
surfaced verbatim - an item can be metadata-visible while the
original is restricted, and this adapter says so.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from global_library_mcp.adapters.base import AdapterError, LibraryAdapter
from global_library_mcp.http import fetch_validated, sanitize_error
from global_library_mcp.languages import normalize_language
from global_library_mcp.models import Rights, SearchResult

SPARQL_URL = "https://jpsearch.go.jp/rdf/sparql"
DATA_BASE = "https://jpsearch.go.jp/data"
ITEM_BASE = "https://jpsearch.go.jp/item"
_HOST = "jpsearch.go.jp"
_ID_RE = re.compile(r"^[a-z][a-z0-9]*-[0-9a-z]+$")
_NDL_PID_RE = re.compile(r"^info:ndljp/pid/(\d+)$")
_MAX_JSON = 10_000_000

_SPARQL_TEMPLATE = """SELECT ?s ?name WHERE {{
  ?s <http://schema.org/name> ?name .
  FILTER(CONTAINS(LCASE(STR(?name)), LCASE("{literal}")))
}} LIMIT {limit}"""


def _sparql_literal(text: str) -> str:
    """Escape a string for embedding as a SPARQL string
    literal. Control characters are rejected outright: they
    have no legitimate place in a search term and are the
    classic route out of a literal."""
    out: list[str] = []
    for char in text:
        if ord(char) < 0x20:
            raise ValueError("control character in search term")
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        else:
            out.append(char)
    return "".join(out)


def _rights_classification(url: str | None) -> str | None:
    if not url:
        return None
    lowered = url.lower()
    if "publicdomain/zero" in lowered or lowered.rstrip("/").endswith("cc0"):
        return "cc0"
    if "publicdomain/mark" in lowered:
        return "public-domain-mark"
    if "creativecommons.org/licenses/" in lowered:
        return "creative-commons-licence"
    if "rightsstatements.org/vocab/inc/" in lowered:
        return "rightsstatements-in-copyright"
    if "rightsstatements.org/vocab/noc-" in lowered:
        return "rightsstatements-no-copyright"
    if "rightsstatements.org/vocab/" in lowered:
        return "rightsstatements-other"
    return "other"


def _entity_name(uri: Any) -> str | None:
    if not isinstance(uri, str) or not uri:
        return None
    tail = unquote(uri.rstrip("/").rsplit("/", 1)[-1])
    return tail or None


def _name_values(value: Any) -> list[tuple[str, str | None]]:
    """(text, language) pairs from a JSON-LD name field."""
    out: list[tuple[str, str | None]] = []
    if isinstance(value, str):
        out.append((value, None))
    elif isinstance(value, list):
        for item in value:
            out.extend(_name_values(item))
    elif isinstance(value, dict):
        text = value.get("@value")
        if isinstance(text, str):
            out.append((text, value.get("@language")))
    return out


class JapanSearchAdapter(LibraryAdapter):
    library_id = "japan-search"
    library_name = "Japan Search (National Diet Library)"
    supports_in_document_search = False

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        terms = (query or "").strip()
        if not terms:
            raise AdapterError(self.library_id, "empty search query", retryable=False)
        try:
            literal = _sparql_literal(terms)
        except ValueError as exc:
            raise AdapterError(self.library_id, str(exc), retryable=False) from exc
        row_limit = min(max(limit, 1) * 3, 100)
        sparql = _SPARQL_TEMPLATE.format(literal=literal, limit=row_limit)
        try:
            response = await self.client.get(
                SPARQL_URL,
                params={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        bindings = (
            payload.get("results", {}).get("bindings")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(bindings, list):
            raise AdapterError(self.library_id, "Japan Search SPARQL returned an unexpected payload", retryable=False)
        grouped: dict[str, list[tuple[str, str | None]]] = {}
        order: list[str] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            uri = (binding.get("s") or {}).get("value")
            name = binding.get("name") or {}
            if not isinstance(uri, str) or not uri.startswith(f"{DATA_BASE}/"):
                continue
            record_id = uri[len(DATA_BASE) + 1 :]
            if not _ID_RE.match(record_id):
                continue
            if record_id not in grouped:
                grouped[record_id] = []
                order.append(record_id)
            text = name.get("value")
            if isinstance(text, str) and text:
                grouped[record_id].append((text, name.get("xml:lang")))
        results: list[SearchResult] = []
        for record_id in order[:limit]:
            names = grouped[record_id]
            title = None
            for text, lang in names:
                if lang in ("ja", None):
                    title = text
                    break
            if title is None and names:
                title = names[0][0]
            results.append(
                SearchResult(
                    library_id=self.library_id,
                    library_name=self.library_name,
                    record_id=record_id,
                    title=title or "Untitled",
                    landing_url=f"{ITEM_BASE}/{record_id}",
                    fulltext_status="unknown",
                    rights=Rights(statement="unknown", source="rights are per-item; see the item detail (accessInfo licence)"),
                    source_protocol="Japan Search SPARQL (JPS-RDF)",
                    raw={"data_uri": f"{DATA_BASE}/{record_id}", "names": names},
                )
            )
        return results

    async def get_document(self, record_id: str) -> dict[str, Any]:
        record_id = (record_id or "").strip()
        if not _ID_RE.match(record_id):
            raise AdapterError(self.library_id, f"invalid Japan Search item id: {record_id!r}", retryable=False)
        url = f"{DATA_BASE}/{record_id}.json"
        try:
            response = await fetch_validated(self.client, url, allowed_hosts={_HOST})
            response.raise_for_status()
            if len(response.content) > _MAX_JSON:
                raise AdapterError(self.library_id, "item JSON exceeds the size bound", retryable=False)
            payload = response.json()
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(self.library_id, sanitize_error(exc), retryable=True) from exc
        graph = payload.get("@graph") if isinstance(payload, dict) else None
        if not isinstance(graph, list):
            raise AdapterError(self.library_id, "Japan Search item JSON has no @graph", retryable=False)
        main = next((n for n in graph if isinstance(n, dict) and n.get("@id") == f"{DATA_BASE}/{record_id}"), None)
        if main is None:
            raise AdapterError(
                self.library_id,
                f"Japan Search item identity not established: no graph node with @id {DATA_BASE}/{record_id}",
                retryable=False,
            )
        access = next((n for n in graph if isinstance(n, dict) and n.get("@id") == f"{DATA_BASE}/{record_id}#accessinfo"), {}) or {}
        source = next((n for n in graph if isinstance(n, dict) and n.get("@id") == f"{DATA_BASE}/{record_id}#sourceinfo"), {}) or {}

        names = _name_values(main.get("name"))
        title = main.get("label")
        if not isinstance(title, str) or not title:
            title = next((t for t, lang in names if lang in ("ja", None)), None) or (names[0][0] if names else None)
        creators = [
            name
            for name in (_entity_name(uri) for uri in (main.get("creator") if isinstance(main.get("creator"), list) else [main.get("creator")]))
            if name
        ]
        language = None
        in_language = main.get("inLanguage")
        if isinstance(in_language, str):
            codes = normalize_language(in_language.rstrip("/").rsplit("/", 1)[-1])
            language = codes[0] if codes else None
        identifiers = main.get("identifier") if isinstance(main.get("identifier"), list) else []
        ndl_pid = None
        for identifier in identifiers:
            match = _NDL_PID_RE.match(str(identifier).strip())
            if match:
                ndl_pid = match.group(1)
                break
        licence = access.get("license") if isinstance(access.get("license"), str) else None
        access_descriptions = access.get("description") if isinstance(access.get("description"), list) else []
        restrictions = [
            str(item) for item in access_descriptions if isinstance(item, str) and "アクセス制限" in item
        ]
        provider_urls: list[str] = []
        raw_urls = access.get("url")
        for item in raw_urls if isinstance(raw_urls, list) else [raw_urls]:
            if isinstance(item, str) and item:
                provider_urls.append(item)
        return {
            "library_id": self.library_id,
            "record_id": record_id,
            "platform": "japan-search",
            "data_uri": f"{DATA_BASE}/{record_id}",
            "title": title,
            "author": "; ".join(creators) or None,
            "date": main.get("datePublished") if isinstance(main.get("datePublished"), str) else None,
            "language": language,
            "type": _entity_name(main.get("@type")),
            "identifiers": [str(item) for item in identifiers],
            "provider": _entity_name(source.get("provider") or access.get("provider")),
            "landing_url": f"{ITEM_BASE}/{record_id}",
            "provider_urls": provider_urls,
            "access_restrictions": restrictions,
            "ndl_pid": ndl_pid,
            "handoff_candidates": (
                [{"library_id": "ndl", "record_id": ndl_pid, "basis": "info:ndljp/pid identifier in the Japan Search record"}]
                if ndl_pid
                else []
            ),
            "rights": {
                "statement": licence or "unknown",
                "url": licence,
                "source": "Japan Search accessInfo license" if licence else "no licence in the item's accessInfo",
                "classification": _rights_classification(licence),
            },
            "source_protocol": "Japan Search JSON-LD (JPS-RDF)",
            "note": (
                "Aggregated record from Japan Search. The provider holds the original; "
                "provider_urls are reported, not fetched. access_restrictions are the "
                "provider's own statements and are surfaced verbatim. Page OCR belongs "
                "to the provider (for NDL items, the NDL adapter via ndl_pid)."
            ),
        }
