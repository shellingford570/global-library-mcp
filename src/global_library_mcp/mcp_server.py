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


_shared: tuple[httpx.AsyncClient, LibraryService] | None = None


async def _with_service():
    # b3: one shared budgeted client + service for the process, so
    # caches and the circuit breaker persist across tool calls
    # (previously rebuilt per call and never effective).
    global _shared
    if _shared is None:
        from global_library_mcp.http import make_client

        client = make_client(timeout=30)
        _shared = (client, LibraryService(client))
    return _shared


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
    response = await service.search(query, libraries, min(max(limit, 1), 20))
    return response.to_dict()


@mcp.tool()
async def search_catalog(query: str, library_id: str, limit: int = 10) -> dict[str, Any]:
    """Search one supported live library."""
    return await search_across_libraries(query, [library_id], limit)


@mcp.tool()
async def get_document(library_id: str, record_id: str) -> dict[str, Any]:
    """Retrieve a document record where the adapter supports it."""
    client, service = await _with_service()
    return await service.get_document(library_id, record_id)


@mcp.tool()
async def search_in_document(library_id: str, record_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Search within a document, returning page-level matches when supported."""
    client, service = await _with_service()
    return await service.search_in_document(library_id, record_id, query, min(max(limit, 1), 100))


@mcp.tool()
async def get_page_text(library_id: str, page_id: str) -> dict[str, Any]:
    """Return OCR text, coordinates, and an original-image link for a page/frame."""
    client, service = await _with_service()
    return await service.get_page_text(library_id, page_id)


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
    return await service.collect_evidence(query, libraries, min(max(limit, 1), 20))


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
    return await service.verify_page(library_id, page_id)


@mcp.tool()
async def research_question(query: str, libraries: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
    """Answer a question from verified OCR page evidence.

    Collects verified evidence (see get_verified_evidence), lets the
    configured answer provider respond from those pages only, and
    whitelist-validates every citation against the evidence. When no
    verified OCR evidence exists, the status is
    ``insufficient_evidence`` and no answer is produced.
    """
    client, service = await _with_service()
    return await service.answer(query, libraries, min(max(limit, 1), 20))


@mcp.tool()
async def research_materials(query: str, libraries: list[str] | None = None, limit: int = 10, mode: str = "standard") -> dict[str, Any]:
    """Research-materials mode: related sources with excerpts,
    original images, evidence states and the reason each
    candidate was or was not admitted as answer evidence.
    Candidates are presented for the reader's own judgment,
    never as proof of an answer."""
    client, service = await _with_service()
    return await service.research_materials(query, libraries, limit, mode=mode)


@mcp.tool()
async def compare_documents(documents: list[dict[str, str]], aspects: list[str] | None = None, question: str | None = None) -> dict[str, Any]:
    """Compare 2-4 documents aspect by aspect on verified OCR pages.

    ``documents`` is a list like ``[{"library_id": "ndl", "record_id": "994120"}]``.
    For each aspect, returns per-document excerpts from verified pages
    with citation keys and original-image URLs, shared and unique
    content terms, explicit gaps where a document has no verified page
    for the aspect, and era-difference notes. The comparison is
    textual; it never invents differences the pages do not show.
    """
    client, service = await _with_service()
    return await service.compare_documents(documents, aspects=aspects, question=question)


def run() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        # Close the shared HTTP client on server shutdown.
        global _shared
        if _shared is not None:
            client, _service = _shared
            _shared = None
            try:
                import asyncio as _asyncio

                _asyncio.run(client.aclose())
            except Exception:
                pass
