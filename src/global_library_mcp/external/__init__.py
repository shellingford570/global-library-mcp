"""External MCP readiness package (b9).

A separate, allowlist-only MCP surface for external AI
clients. This package never imports the Research Workspace
package and never receives workspace paths or state; its
tools project LibraryService responses through the external
transfer rights policy before anything leaves the process.
"""

from global_library_mcp.external.ids import (  # noqa: F401
    ExternalIdError,
    make_document_id,
    make_page_id,
    parse_document_id,
    parse_page_id,
)

__all__ = [
    "ExternalIdError",
    "make_document_id",
    "make_page_id",
    "parse_document_id",
    "parse_page_id",
]
