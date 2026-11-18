from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from global_library_mcp.registry import Registry
from global_library_mcp.service import LibraryService


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "libraries.yaml"
mcp = FastMCP("Global Library MCP")


def _registry() -> Registry:
    return Registry(REGISTRY_PATH)


@mcp.tool()
def list_libraries() -> list[dict[str, Any]]:
    """Return the configured library and archive registry."""
    return _registry().list()


@mcp.tool()
def get_library_capabilities(library_id: str) -> dict[str, Any]:
    """Return verified capabilities and unknown fields for one institution."""
    return _registry().capabilities(library_id)


@mcp.tool()
async def search_across_libraries(query: str, libraries: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
    """Search live LoC, NDL, and Gallica adapters and preserve partial errors."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"User-Agent": "global-library-mcp/0.1 (+https://github.com/shellingford570/global-library-mcp)"}) as client:
        response = await LibraryService(client).search(query, libraries, min(max(limit, 1), 20))
    return response.to_dict()


@mcp.tool()
async def search_catalog(query: str, library_id: str, limit: int = 10) -> dict[str, Any]:
    """Search one supported live library."""
    return await search_across_libraries(query, [library_id], limit)


@mcp.tool()
def get_citation(result: dict[str, Any]) -> dict[str, Any]:
    """Build a conservative citation without inventing missing page or rights data."""
    return {
        "library": result.get("library_name") or result.get("library_id"),
        "title": result.get("title"),
        "author": result.get("author"),
        "date": result.get("date"),
        "record_id": result.get("record_id"),
        "landing_url": result.get("landing_url"),
        "page": result.get("page", "unknown"),
        "image_frame": result.get("image_frame", "unknown"),
        "rights": result.get("rights", {"statement": "unknown"}),
        "retrieved_at": result.get("retrieved_at"),
        "citation_status": "page-level verification required" if not result.get("page") else "record-level",
    }


@mcp.tool()
def get_rights(result: dict[str, Any]) -> dict[str, Any]:
    """Return item-level rights and never infer redistribution permission."""
    return result.get("rights") or {"statement": "unknown"}


def run() -> None:
    mcp.run(transport="stdio")
