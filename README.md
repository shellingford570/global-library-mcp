# Global Library MCP

Global Library MCP is an evidence-first MCP gateway for official library and digital-archive APIs. The current Phase 1 slice provides live catalog search adapters for the Library of Congress, National Diet Library, and Gallica/BnF, plus a dependency-light Web UI that works without an LLM key.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

Open `http://127.0.0.1:8000`. To run the MCP stdio server, use `global-library-mcp mcp` and configure that command in your MCP client.

The Web UI exposes `/health`, `/manus-routes.json`, `/api/libraries`, and `/api/search?q=...`. The MCP server exposes `list_libraries`, `get_library_capabilities`, `search_catalog`, `search_across_libraries`, `get_citation`, and `get_rights`.

## Evidence and limits

Search is for discovery. Verify the original page and item-level rights before quoting or redistributing anything. The project does not infer rights from source code licenses. Unknown capabilities remain `unknown`. Detailed IIIF page analysis, OCR coordinate alignment, LLM answer generation, and additional live adapters are not complete in this slice.

See the [Japanese README](README.ja.md), [prior-art report](docs/prior-art.md), [API research](docs/api-research.md), and [library registry](libraries.yaml).
