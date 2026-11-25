# Global Library MCP

Global Library MCP is a research-materials search service
and MCP gateway for official library and digital-archive
APIs. It searches catalogs across institutions, reads
page-level OCR, extracts the passages a question touches,
and links every excerpt to the original page image (IIIF)
so you can verify it yourself. Search results are research
materials for your own investigation - they are never
presented as proof of an answer.

**Research Beta** is the product: library search, OCR,
original-image access, document comparison and citation
copying, working fully with **no LLM and no paid API**.
The AI answer features are a separate **experimental**
track (see below), disabled by default.

## Libraries and implementation status

Status labels: **verified** = exercised live end-to-end;
**implemented** = adapter exists, partial live coverage;
**unverified** = code exists but not confirmed from this
network; **research** = registry record only, no adapter.
Per-library detail lives in [libraries.yaml](libraries.yaml)
and [docs/implementation-status.md](docs/implementation-status.md).

| Library | Status | Search | Page OCR | Original images |
|---|---|---|---|---|
| National Diet Library (NDL, Japan) | verified | yes | yes | yes (IIIF) |
| Internet Archive | verified | yes | yes (open items) | yes |
| Library of Congress | implemented | yes | newspapers only (Chronicling America, verified) | yes |
| BSB / MDZ (Bavarian State Library) | verified | by ID (no official search API) | yes (hOCR) | yes (IIIF) |
| e-rara (ETH Library) | implemented | by ID (OAI-PMH) | no | no |
| Gallica / BnF | unverified (upstream 403 from this network) | yes | yes | yes (IIIF) |
| DDB | implemented | yes (aggregator) | no | links |
| Europeana | implemented | yes (aggregator) | no | links |
| 17 further institutions | research | - | - | - |

This project does **not** cover every library in the
world; the table above is the whole supported set.

## Quick start (local)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

Open `http://127.0.0.1:8000` (Japanese/English UI).

## Docker

```bash
docker compose up --build
```

The container runs as a non-root user and serves the same
web UI and API on port 8000.

## MCP connection

Run `global-library-mcp mcp` (stdio) and configure that
command in your MCP client. A local Streamable HTTP transport
is also available (`global-library-mcp mcp --transport
streamable-http`, bound to 127.0.0.1), and
`--profile research` exposes a read-only tool set for external
AI clients. See `docs/mcp-clients.md`. Tools include
`research_materials` (the beta's primary tool),
`search_across_libraries`, `search_catalog`,
`get_document`, `search_in_document`, `get_page_text`,
`get_page_image`, `get_citation`, `get_rights`,
`get_verified_evidence`, `verify_original_page`,
`compare_documents`, and the experimental
`research_question`.

## AI features (experimental)

AI answering is **disabled by default** and the beta works
fully without it. What exists for research:

- Claim-level verification: only claims screened as
  *supported* against the specific passage they cite may
  publish; uncertain/unverified claims are withheld, and
  conflicting claims are shown separately (Phase 10-B).
- Pluggable claim verifiers (lexical / NLI / LLM judge /
  hybrid) compared in shadow mode; an LLM never counts as
  independent verification of its own claims.
- Extractive answers (verbatim quotations) and generative
  answers are evaluated separately.
- Measured results: in the first approved real-LLM run
  (xAI grok-4.3, 20 questions), the LLM answered 4/20 vs
  the deterministic mock's 12/20 on the same subset - the
  binding constraint is claim verification, not the model.
  Full reports: [docs/evaluation-phase9.md](docs/evaluation-phase9.md),
  [docs/phase10-llm-audit.md](docs/phase10-llm-audit.md),
  [docs/phase10-experiment-plan.md](docs/phase10-experiment-plan.md).

To experiment locally, set `LLM_ENABLED=true`,
`LLM_API_KEY`, and optionally `LLM_API_BASE` / `LLM_MODEL`
for an OpenAI-compatible provider, or `LLM_PROVIDER=mock`
for the deterministic demo provider (clearly labelled in
the UI). Paid evaluations additionally require the
budget-approval hand-off described in the experiment plan;
there is no self-serve approve flag.

## Rights and attribution

Rights are per item and are shown verbatim from each
library. Material with unknown rights is never presented
as freely redistributable. The beta's default is short
excerpts plus a link to the original. Access-restricted
items (for example Internet Archive lending-only items)
are refused, never fetched. Per-library terms research:
[docs/phase10-library-terms.md](docs/phase10-library-terms.md).

## Privacy and security

Queries go to the library APIs you select; no account or
personal data is required, and no user data is sent to any
LLM in the beta configuration (a trap-route test proves
the beta paths make zero LLM calls). API errors are
sanitised; keys, when an operator configures them, come
from the environment only and are never logged. Audits:
[docs/phase9-security-audit.md](docs/phase9-security-audit.md),
[docs/phase10-security-audit.md](docs/phase10-security-audit.md).

## Known limits

- Search quality depends on each library's own index and
  OCR; a question with no evidence found within the
  request budget (Standard 25 by default) is reported as
  such - that never means the fact does not exist.
- OCR of historical materials contains recognition errors;
  quotations are verbatim OCR, and the original image is
  the ground truth.
- Semantic (NLI) verification is not available in the
  default environment (no model weights); it reports
  `not_checked` honestly rather than guessing.
- Gallica may be unreachable from some networks (upstream
  403); the project does not evade access controls.

## Contributing

Issues and pull requests are welcome. Please keep the
evidence-first rules: no claim without a resolvable
citation, no rights inference, no silent fallbacks - and
run `pytest` plus the Playwright suite
(`npm run test:e2e`) before submitting.

## Documentation

- Quickstart: [docs/quickstart.md](docs/quickstart.md) /
  [docs/quickstart.en.md](docs/quickstart.en.md)
- MCP client guide: [docs/mcp-clients.md](docs/mcp-clients.md)
- Release notes (1.0.0b2): [docs/release-notes-1.0.0b2.md](docs/release-notes-1.0.0b2.md)

## License and provenance

See [LICENSE](LICENSE) and [SECURITY.md](SECURITY.md).
Japanese README: [README.ja.md](README.ja.md).
