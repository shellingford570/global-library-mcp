# Global Library MCP

Global Library MCP is an evidence-first MCP gateway for official library and digital-archive APIs. It searches library catalogs across institutions, reads actual OCR page text, and answers questions only from pages whose identity has been cross-checked — every citation resolves to a record, a page, and an original IIIF image you can open. Anything that cannot be verified is shown as unverified, never hidden and never cited.

Adapters are implemented for the National Diet Library (Japan), Library of Congress, Internet Archive, Gallica/BnF, DDB, and Europeana. NDL supports the full evidence path: catalog search, in-document search, page OCR, and IIIF original verification. Live status per library is tracked in [libraries.yaml](libraries.yaml) and [docs/implementation-status.md](docs/implementation-status.md).

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

Open `http://127.0.0.1:8000`. To run the MCP stdio server, use `global-library-mcp mcp` and configure that command in your MCP client.

The Web UI exposes `/health`, `/api/libraries`, `/api/search?q=...`, `/api/evidence?q=...`, `/api/answer?q=...`, `/api/verify?library=ndl&id=...`, `/api/compare?docs=ndl:994120;ndl:1018770&aspects=...`, `/api/document`, and `/api/page`. The MCP server exposes `list_libraries`, `get_library_capabilities`, `search_catalog`, `search_across_libraries`, `get_document`, `search_in_document`, `get_page_text`, `get_page_image`, `get_citation`, `get_rights`, `get_verified_evidence`, `verify_original_page`, `research_question`, and `compare_documents`.

## Answers and evidence

`research_question` (and the Web UI's AI-answer button) runs the evidence pipeline: catalog search → in-document page search → page OCR with identity cross-checks and an OCR quality gate → answer generation → citation whitelist validation. When no verified OCR page can be collected, the result is `insufficient_evidence` and no answer is produced — bibliographic records alone never ground an answer. Answers also carry claim-by-claim grounding screening (each claim is checked against the pages it cites), and `compare_documents` contrasts two documents aspect by aspect using only verified pages. Internet Archive items provide the same page-level evidence path as NDL (djvu.xml OCR by leaf); access-restricted items are refused.

AI answer generation is disabled by default and the system works fully without an LLM. To opt in to an OpenAI-compatible provider, set `LLM_ENABLED=true`, `LLM_API_KEY`, and optionally `LLM_API_BASE`/`LLM_MODEL`. For offline demos and tests, `LLM_PROVIDER=mock` selects a deterministic mock provider that answers from the first evidence page. Search, evidence and original-source links never require an LLM key.

## Evidence and limits

Search is for discovery; the evidence pipeline is for citing. Verify the original page and item-level rights before quoting or redistributing anything. The project does not infer rights from source code licenses. Unknown capabilities remain `unknown`. See the [Japanese README](README.ja.md), [implementation status](docs/implementation-status.md), [evidence verification](docs/evidence-verification.md), [code review](docs/code-review.md), [API research](docs/api-research.md), and [library registry](libraries.yaml).

CI covers Python tests, Docker build/startup, Playwright Chromium E2E, and a Docker-backed API smoke test. External API success remains provider- and credential-dependent; per-library live results are dated in the registry rather than assumed.
