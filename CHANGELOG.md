# Changelog

All notable changes are recorded here. Dates are JST. Anything not
listed as verified was not live-verified; see
`docs/implementation-status.md` for the per-feature truth table.

## Phase 3 — research v3 (2026-11-22, branch `feat/global-library-research-v3`)

- Claim-level grounding: answers carry per-claim support screening
  (supported / uncertain / unsupported / conflicting / not_checked),
  shown in the Web UI with citation chips.
- Answer-quality evaluation harness: 30-question dataset
  (`eval/questions.json`) and live runner; first run and findings in
  `docs/evaluation.md` (discovery 1.00, OCR capture 0.94, image
  reachability 1.00, insufficient-evidence correctness 0.20 — the
  relevance gap is documented, not hidden).
- Internet Archive page-level evidence, live-verified: in-document
  search and page OCR from djvu.xml by leaf, original verification,
  access-restricted items refused.
- Gallica page methods implemented and unit-tested (texteBrut page
  text, IIIF manifest verification); upstream still returns 403 from
  the development network, so they are not live-verified.
- `compare_documents` MCP tool, service method and Web UI: verified
  pages compared aspect by aspect with citations, gaps and era notes.
- Web UI: IIIF image previews on evidence cards, query-language hint,
  per-IP API rate limiting (429 over 120 req/min by default).
- Release hygiene: `requirements.lock.txt`, CycloneDX SBOM
  (`sbom.cyclonedx.json`, generator in `scripts/`), pip-audit scan
  (no vulnerabilities in runtime dependencies; findings only in the
  venv's bundled pip and in pytest — see SECURITY.md).

## v2 — evidence (2026-11-22, branch `feat/global-library-evidence-v2`, PR #2)

- OCR evidence pipeline (`Evidence` model, OCR quality gate,
  `collect_evidence`, `get_verified_evidence`).
- IIIF original-page verification for NDL (manifest / canvas / image),
  with the three reference pages live-verified.
- Evidence-first answers: citation-key whitelist validation in the
  provider and service layers, `insufficient_evidence` handling,
  deterministic MockProvider (`LLM_PROVIDER=mock`).
- Web UI evidence view with citation jump, inline IIIF verification
  and a JA/EN toggle; `/api/evidence` and `/api/verify` endpoints.

## v1 — core (branch `feat/v1-core`, PR #1)

- MCP server and Web UI with cross-library catalog search
  (NDL, Library of Congress, Gallica, Internet Archive, DDB,
  Europeana), library registry (`libraries.yaml`), NDL Book/Page API
  page OCR and IIIF image URLs, Docker, GitHub Actions, pytest and
  Playwright suites.
