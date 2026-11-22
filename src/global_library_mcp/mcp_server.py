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


async def _with_service():
    client = httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"User-Agent": "global-library-mcp/0.1 (+https://github.com/shellingford570/global-library-mcp)"})
    return client, LibraryService(client)


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
    """Search configured live adapters and preserve partial errors."""
    client, service = await _with_service()
    try:
        response = await service.search(query, libraries, min(max(limit, 1), 20))
        return response.to_dict()
    finally:
        await client.aclose()


@mcp.tool()
async def search_catalog(query: str, library_id: str, limit: int = 10) -> dict[str, Any]:
    """Search one supported live library."""
    return await search_across_libraries(query, [library_id], limit)


@mcp.tool()
async def get_document(library_id: str, record_id: str) -> dict[str, Any]:
    """Retrieve a document record where the adapter supports it."""
    client, service = await _with_service()
    try:
        return await service.get_document(library_id, record_id)
    finally:
        await client.aclose()


@mcp.tool()
async def search_in_document(library_id: str, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Search within a document, returning page-level matches when supported."""
    client, service = await _with_service()
    try:
        return await service.search_in_document(library_id, record_id, query, min(max(limit, 1), 100))
    finally:
        await client.aclose()


@mcp.tool()
async def get_page_text(library_id: str, page_id: str) -> dict[str, Any]:
    """Return OCR text, coordinates, and an original-image link for a page/frame."""
    client, service = await _with_service()
    try:
        return await service.get_page_text(library_id, page_id)
    finally:
        await client.aclose()


@mcp.tool()
def get_page_image(library_id: str, book_pid: str, page: int) -> dict[str, Any]:
    """Return an image URL without downloading or redistributing the original."""
    if library_id != "ndl":
        return {"library_id": library_id, "image_url": None, "status": "unknown", "message": "Page image URL generation is not implemented for this adapter"}
    if page < 1:
        raise ValueError("page must be a positive integer")
    from global_library_mcp.adapters.ndl import NdlAdapter
    return {"library_id": library_id, "book_pid": book_pid, "digital_frame": page, "image_url": NdlAdapter.image_url(book_pid, page), "status": "link_only"}


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
        "citation_status": "page-level" if result.get("page") or result.get("page_id") else "record-level",
    }


@mcp.tool()
def get_rights(result: dict[str, Any]) -> dict[str, Any]:
    """Return item-level rights and never infer redistribution permission."""
    return result.get("rights") or {"statement": "unknown"}


@mcp.tool()
async def get_verified_evidence(query: str, libraries: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
    """Collect page-level OCR evidence for a question.

    Runs a cross-library search, then in-document search and page OCR
    retrieval for adapters that support it. Only pages whose identity
    cross-check passed and whose OCR passed the quality gate are
    returned under ``evidence``; the rest are listed under
    ``unverified`` with reasons and must not be cited as page evidence.
    """
    client, service = await _with_service()
    try:
        return await service.collect_evidence(query, libraries, min(max(limit, 1), 20))
    finally:
        await client.aclose()


@mcp.tool()
async def verify_original_page(library_id: str, page_id: str) -> dict[str, Any]:
    """Verify a page against its original image via IIIF.

    Checks, as separate results: page payload identity, OCR presence,
    IIIF manifest, the canvas for the digital frame, the canvas image
    URL, and actual reachability of the original image. Status is
    ``verified`` only when every check passes, ``failed`` when a check
    fails, and ``unsupported`` for adapters without verification.
    """
    client, service = await _with_service()
    try:
        return await service.verify_page(library_id, page_id)
    finally:
        await client.aclose()


def run() -> None:
    mcp.run(transport="stdio")
