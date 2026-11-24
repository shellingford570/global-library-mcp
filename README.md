# Global Library MCP

Global Library MCP is an evidence-first MCP gateway for official library and digital-archive APIs. The current slice provides live search adapters for the National Diet Library, Internet Archive, Library of Congress, and Gallica/BnF, plus configured adapters for DDB and Europeana. NDL Book/Page OCR and IIIF image links are supported, and the dependency-light Web UI works without an LLM key.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

Open `http://127.0.0.1:8000`. To run the MCP stdio server, use `global-library-mcp mcp` and configure that command in your MCP client.

The Web UI exposes `/health`, `/manus-routes.json`, `/api/libraries`, `/api/search?q=...`, `/api/document`, `/api/page`, and `/api/answer`. The MCP server exposes `list_libraries`, `get_library_capabilities`, `search_catalog`, `search_across_libraries`, `get_document`, `search_in_document`, `get_page_text`, `get_page_image`, `get_citation`, and `get_rights`.

AI answer generation is disabled by default. To explicitly opt in to an OpenAI-compatible provider, set `LLM_ENABLED=true`, `LLM_API_KEY`, and optionally `LLM_API_BASE`/`LLM_MODEL`. Search and original-source links do not require an LLM key.

## Evidence and limits

Search is for discovery. Verify the original page and item-level rights before quoting or redistributing anything. The project does not infer rights from source code licenses. Unknown capabilities remain `unknown`. Detailed IIIF page analysis, OCR coordinate alignment, LLM answer generation, and additional live adapters are not complete in this slice.

The repository contains release-candidate CI for Python tests, Docker build/startup, Playwright Chromium E2E, and a Docker-backed API smoke test. External API success remains provider- and credential-dependent; LoC, Gallica, and Europeana must not be treated as live-successful without a current contract run. See the [Japanese README](README.ja.md), [implementation status](docs/implementation-status.md), [code review](docs/code-review.md), [prior-art report](docs/prior-art.md), [API research](docs/api-research.md), and [library registry](libraries.yaml).
