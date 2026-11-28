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
| KB / Delpher (Netherlands) | verified (search + article OCR fetch, live 2026-11-26; page identity unverified - OCR is article-level, title correspondence only) | yes (SRU) | article OCR (resolver) | unverified (resolver :image answered 404 live) |
| Japan Search (NDL, Japan) | verified (search + detail, live 2026-11-26) | yes (SPARQL) | no (aggregator) | no |
| Finna (Finland) | implemented, unverified from this network (upstream bot challenge 403) | yes | no (platform) | no |
| National Library of Finland (Digi) | implemented, live verification not achieved (OAI endpoint answered at protocol level in the final-review re-check; real-binding verification outstanding) | by ID (via Finna handoff) | yes (ALTO) | yes |
| DPLA (USA) | implemented, authentication required (no key issued) | yes (with API key) | no (aggregator) | no |
| 16 further institutions | research | - | - | - |

This project does **not** cover every library in the
world; the table above is the whole supported set.

### Multilingual discovery (1.0.0b6)

Ask in your own language: a local dictionary expands the
query into other languages' subject labels, author name
forms, original and translated titles, and historical
spellings (old kanji, historical kana, umlaut and accent
forms), routes variants to the libraries that hold such
materials, and reports every expansion with its reason.
Records gain candidate work/author links (with refusals
where identity is not established), DDB records can hand
off to BSB originals via their official URN, and LoC
newspaper issues are discoverable from a title's LCCN.
Expansion is discovery only - evidence admission is
unchanged, and no translation or LLM is involved. See
docs/b6-multilingual-research.md and docs/b6-evaluation.md.
The final-review round (docs/b6-final-review.md) made the
structured conditions apply in every mode including Quick,
moved filtering before OCR fetching, tightened author/work/
edition identification and DDB→BSB identifier validation,
and split the evaluation into a simulation and a
real-service fixture evaluation.

### Research workspace (1.0.0b7)

Searches can now feed a local research workspace: projects,
saved documents, page-level citations with provenance and
re-verification, research notes, opt-in search history,
saved comparisons, tags and collections, all in a local
SQLite database under your OS user data directory (override
with `GLM_WORKSPACE_PATH`). Enable it with
`global-library-mcp web --workspace`; the workspace web mode
binds to loopback only and refuses anything else. Exports:
BibTeX, RIS, CSL JSON, Markdown reports and a portable JSON
project format, plus online backup/restore. Rights are
handled conservatively: OCR full text and image bytes are
never stored, and excerpts are stored/exported only where
the rights category permits. MCP tools are unchanged and
have no access to the workspace. See
docs/b7-research-workspace.md and
docs/workspace-user-guide.md.
The final review hardened citation-to-document binding, the fail-closed rights policy, import/restore safety and session security; see docs/b7-final-review.md.

### Global Coverage II (1.0.0b8)

Five more adapters, all opt-in (default searches are
unchanged and never touch the new hosts): Finna (Finland's
discovery platform - provider, holding institution and the
Finna record itself are kept distinct, and its CC0 metadata
licence is never confused with item rights), the National
Library of Finland's Digi service (OAI-PMH identity, ALTO
page OCR with structural page identity, reached through a
validated Finna -> Digi handoff), KB / Delpher (Dutch
historical newspapers via SRU + resolver OCR - search and
article-OCR fetching live-verified; the OCR unit is the
article, and page identity is not strictly verified),
Japan Search (SPARQL search and
JSON-LD detail, with access restrictions surfaced verbatim
and NDL handoff candidates), and DPLA in an
authentication-pending state (no API key was issued; calls
report `authentication_required`). Finnish, Swedish and
Dutch join the multilingual expansion dictionary. The b7
workspace also gained a rights trust model: imported or
restored rights claims can restrict but never permit excerpt
storage. Live-verification status per library is recorded
honestly in docs/b8-live-verification.md - Finna and Digi
could not be reached from the development network and are
fixture-verified only. See docs/b8-global-coverage-ii.md.

### External MCP Readiness (1.0.0b9)

A separate **external-research** MCP profile for external AI
clients: a dedicated FastMCP server exposing only 9
allowlisted read-only tools (`search`/`fetch` in the OpenAI
shape, library listing/capabilities, rights, original
verification, a policy-gated excerpt tool, and external
materials/comparison projections), with OAuth 2.1 token
validation and per-tool scopes, server-side user consent,
per-user budgets and deadlines, and an **external transfer
rights policy** that is independent of the workspace storage
policy — OCR full text and image binaries never leave, and
excerpts are disabled by default. The Research Workspace is
structurally unreachable from this profile. Connection
runbooks for ChatGPT (via Secure MCP Tunnel) are prepared in
docs/chatgpt-connection.md, but **no tunnel has been created
and ChatGPT has not been connected**; official plan research
(2026-11-27) found full MCP documented for Business and
Enterprise/Edu and read/fetch connections for Pro, with no
documented custom-MCP route for Plus. See
docs/b9-external-mcp-readiness.md.

### Advanced Research Intelligence (1.0.0b10)

b10 deepens research capability on the b9 foundation. The
external profile's residual risks found in review were
reproduced and fixed (consent-expiry re-checks at send and
return time, per-data-class consent, send-level library
binding, budget ledgers that survive state eviction, per-user
session caps, typed external projections, per-library
reference-host allowlists, document identity states,
consent-file hardening, unified startup validation) — the
external profile itself is unchanged (5 tools, no original
text transfer) and real external connection remains disabled
(DNS pinning unimplemented, no production IdP). Multilingual
retrieval was diagnosed and repaired: b6 fixed F Recall@10
recovered to 0.9167 and challenge to 1.0000 in simulation.
New: an AuthorityResolver (local lexicon plus key-free
lobid GND / Wikidata clients; GND identifiers live-verified
for ten focus authors) that never certifies identity from a
name alone; a lexical TF-IDF scorer and an opt-in local
semantic backend (paraphrase-multilingual-MiniLM-L12-v2,
Apache-2.0, 127 MB, offline) that proved the strongest
cross-language discovery signal measured; structured research
questions and claims with candidate-level claim–evidence
mapping; rule-based contradiction candidates across sources
with document vs independent-source counts; and Research
Workspace artefacts, progress and candidate relationship
graphs. The new ResearchRanker was evaluated but NOT adopted
as the default (mixed results) and ships opt-in. See
docs/b10-advanced-research-intelligence.md. Final-review fixes and corrected measurements: docs/b10-final-review.md.

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
`--profile research` exposes a read-only tool set.
`--profile external-research` (b9) starts the separate
external server described above, on port 8002 by convention;
`global-library-mcp doctor` checks the configuration without
any network access. See `docs/mcp-clients.md`. Tools include
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
