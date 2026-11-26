"""b8 Stage 5: MCP integration - the tool set is unchanged
(15 full / 14 research), and the new libraries are reachable
through the existing common tools by library_id.
"""

import asyncio

import httpx
import pytest

from global_library_mcp.service import LibraryService as _LS  # noqa: F401  (import order)
from global_library_mcp import mcp_server
from global_library_mcp.adapters.finna import FinnaAdapter

FINNA_SEARCH = {
    "resultCount": 1,
    "records": [
        {
            "id": "helle.687105",
            "title": "Suomen historia",
            "usageRights": [],
            "languages": ["fin"],
            "formats": [{"value": "0/Book/", "translated": "Kirja"}],
            "buildings": [{"value": "0/Helle/", "translated": "Helle-kirjastot"}],
            "year": 2020,
        }
    ],
    "status": "OK",
}


def test_full_and_research_profile_tool_counts_unchanged():
    names = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]
    assert len(names) == 15  # full profile
    assert "research_question" in names
    # The research profile is applied at run time; exercise the
    # real _apply_profile path in a subprocess so the shared
    # module-level server is not mutated for other tests.
    import subprocess
    import sys

    code = (
        "from global_library_mcp import mcp_server\n"
        "import asyncio\n"
        "mcp_server._apply_profile(mcp_server.mcp, 'research')\n"
        "names = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]\n"
        "print(len(names))\n"
        "print('research_question' in names)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert out.stdout.strip().endswith("14\nFalse"), (out.stdout, out.stderr[-300:])


def test_list_libraries_includes_new_institutions():
    entries = mcp_server.list_libraries()
    by_id = {entry["id"]: entry for entry in entries}
    assert len(entries) == 31
    for library_id in ("finna", "finland-nl-digi", "dpla", "kb-delpher", "japan-search", "bne", "onb-anno"):
        assert library_id in by_id, library_id
    assert by_id["finna"]["implementation_status"] == "implemented"
    assert by_id["bne"]["implementation_status"] == "research_only"
    assert by_id["onb-anno"]["implementation_status"] == "research_only"
    capabilities = mcp_server.get_library_capabilities("dpla")
    assert capabilities["capability_status"]["catalog_search"] == "authentication_required"
    kb = mcp_server.get_library_capabilities("kb-delpher")
    assert kb["capability_status"]["page_ocr"] == "live_page_verified"


@pytest.mark.asyncio
async def test_search_catalog_reaches_finna_by_library_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FINNA_SEARCH)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = _LS(client)
    service.adapters = {"finna": FinnaAdapter(client)}
    previous = mcp_server._shared
    mcp_server._shared = (client, service)
    try:
        result = await mcp_server.search_catalog("Suomen historia", "finna", 5)
    finally:
        mcp_server._shared = previous
        await client.aclose()
    assert result["results"][0]["record_id"] == "helle.687105"
    assert result["results"][0]["library_id"] == "finna"
