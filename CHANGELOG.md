# Changelog

## 1.0.0b5 — Global Coverage

Final-review fixes (2026-11-26, docs/b5-final-review.md):
strict structural page mapping for BSB and LoC Chronicling
America (parsed identifiers, all signals required);
verify_original unified with page results and based on real
image responses; an upstream-URL safety layer (https-only,
exact host allowlists, per-hop redirect validation, DNS
pre-check with a stated scope); Retry-After extensions
honoured under one absolute send window; a multi-member
gzip loss bug at chunk boundaries found by the new tests and
fixed; BSB in-document results wired into the shared service
schema with partial-result reporting and page windows; IIIF
parser robustness; e-rara identity checks; printed page no
longer guessed from canvas labels; rights classification
distinguishes CC0 / Public Domain Mark / NoC-NC.


- New BSB/MDZ adapter: IIIF Presentation 2 manifests, per-page
  hOCR via the documented MDZ OCR API, IIIF Image 2 originals,
  per-item manifest rights, proven page mapping; ID-addressed
  (no official MDZ search API); bounded in-document search with
  explicit coverage. Live end-to-end verified 2026-11-25.
- LoC: Chronicling America newspaper page OCR (issue-JSON
  segments + text-services full text + IIIF image checks),
  live verified; general LoC remains bibliographic.
- New e-rara adapter: OAI-PMH metadata by ID, live verified;
  search/page OCR unsupported by design (no official interface).
- Shared IIIF module (Presentation v2/v3, ALTO, hOCR).
- Transport: explicit Accept-Encoding (gzip, deflate);
  unsupported encodings refused; truncated compressed streams
  are errors; multi-member gzip supported; adapter redirects
  restricted to the same registrable domain, each hop budgeted.
- Registry: duplicated top-level notes removed; the YAML loader
  refuses duplicate keys; per-capability status vocabulary;
  BSB and e-rara entries added (25 entries, 8 adapters).
- Multilingual discovery: German umlaut transliteration and
  German/French diacritic folding as search-only variants.
- Comparison: shared/unique terms now computed for 3-4
  documents (was silently empty beyond two).
- Web UI: registry-driven library directory with region /
  language / OCR-capable filters and per-capability statuses;
  opt-in checkboxes for the ID-addressed adapters.

## 1.0.0b4 — MCP Connectivity & Research Integration (2026-11-25)

- Streamable HTTP transport for local use (`mcp --transport
  streamable-http`, binds 127.0.0.1, DNS-rebinding protection on),
  sharing the same LibraryService as stdio; verified with the
  official SDK client and the MCP Inspector CLI.
- Read-only research profile (`--profile research`): the
  experimental research_question tool is not exposed; every tool
  carries read-only annotations.
- HTTP byte accounting is now incremental: bytes are charged as
  they stream, so concurrent responses share one cumulative total
  and aborted/cancelled transfers keep the bytes they received.
- A 429's Retry-After now raises a process-wide per-host gate, so
  other operations (and other users of the process) do not ignore
  a library's back-off instruction.
- The shared HTTP client is closed from the MCP server lifespan,
  inside the event loop that created it.
- Japanese discovery widened with historical script variants
  (old/new kanji); evidence admission rules unchanged.
- Materials responses carry a data notice (OCR text is untrusted
  external data, not instructions) and an explicit search scope
  with partial failures.
- Docs: ChatGPT connectivity preparation (Secure MCP Tunnel
  research), MCP security audit, IA fetch-efficiency research.
- Final review fixes: tool docstrings restored to the top of
  every tool (descriptions verified via tools/list); the
  research profile now fails startup if the tool allowlist does
  not match exactly, and generative answering is disabled under
  it even if an LLM is configured; the HTTP transport refuses
  non-loopback binds; Retry-After is re-checked immediately
  before sending and sends are refused beyond a 30s window;
  gzip/deflate responses are decoded incrementally with wire
  and decoded bytes recorded separately; data_notice now covers
  page text, in-document search and comparison results;
  search_scope reports per-library with-results / no-results /
  failed / skipped outcomes.

## 1.0.0b3 — Research Beta (2026-11-25)

Performance and review-hardening release. No new features.

- Review fixes (b3.1): the HTTP budget now reserves attempts
  atomically before sending (concurrent requests cannot race past
  the cap; timeouts, failures and cancellations are counted;
  request counts and received bytes are recorded separately;
  budget contexts are restored with try/finally). Response size
  is enforced while streaming (Content-Length pre-check, decoded-
  size counting so compressed bombs are caught, abort + close on
  overflow, cumulative per-operation byte cap).
- MCP: `research_materials` could not execute at all (an
  `async with` on a non-context-manager left from the b3 refactor)
  - fixed to the shared-service call pattern, verified end-to-end
  with the official Python SDK client (quick and standard modes);
  the shared HTTP client is closed on server shutdown.
- Cancellation is now effective server-side: investigations run
  under client-chosen operation ids, `/api/cancel` cancels the
  server task, states distinguish completed / failed / cancelled
  / timeout, and the UI shows "cancelled" only after the server
  confirms the stop. Bibliographic results stay on screen during
  and after an investigation (separate materials container).
- Budgets now apply to every path (quick search, catalog search,
  document/page fetch, verification, comparison), each reporting
  `http_stats`; the concurrency cap is shared across proxy and
  direct transports. Retry-After is honoured in full (seconds and
  HTTP-date); a wait beyond the retry deadline is not retried and
  surfaces as a partial failure; 429s feed the circuit breaker.
- Cache safety with the shared service: IA metadata cache TTL
  300s / OCR cache TTL 3600s with count and byte bounds; the
  access-restriction check runs against current metadata before
  cached pages are served, so newly restricted items stop being
  served; concurrent fetches of the same page/metadata are
  deduplicated; partial-failure searches are cached only 30s;
  per-search timings travel with each response so concurrent
  searches never mix measurements.

- Search: per-library deadline (default 10s, `GLM_SEARCH_DEADLINE_S`)
  and a cross-request circuit breaker (3 failures → 60s pause); a
  slow library is reported as a partial failure instead of gating
  the whole search. Measured cause: LoC consumed 168s of a 209s
  question (see docs/b3-performance.md).
- Real HTTP request budget: every wire request is counted per
  operation (Standard 80 / Deep 200, per-host caps, 25MB response
  cap, concurrency 8) and reported as `http_stats`; the older
  service-unit budget remains as the processing budget. This
  addresses the limitation recorded in 1.0.0b2 below: the budget
  now caps actual HTTP requests, retries and redirect hops
  included, for traffic through the standard client.
- Modes: `research_materials` accepts `mode` = quick (bibliographic
  only) / standard (variant early-stop once enough candidates are
  pooled) / deep (full sweep). Web UI offers the same modes with
  staged display, run states (processing/complete/partial/failed/
  cancelled), a cancel button, and elapsed/HTTP-request display.
- Web and MCP servers now share one long-lived service per
  process, so the bibliographic cache (TTL 300s), page cache and
  circuit breaker persist across requests.
- Materials carry `access_state` (bibliographic / OCR fetched /
  mapping confirmed / passage found / assessed as evidence).
- Docs: rights guide (docs/rights-guide.md); Europeana limits
  re-verified (API key required; no official numeric daily cap
  currently published); Claude Code recorded as a verified MCP
  client (health check).

## 1.0.0b2 — Research Beta (2026-11-25)

- Internet Archive: `get_page_text` now reports the OCR file
  actually fetched (name, format, URL) as its source instead of
  a guessed `{identifier}_djvu.txt`; `search_in_document`
  names the real format and file.
- Multi-volume items: page-to-image correspondence is marked
  unverified (`verified_mapping=false`, `mapping_status`,
  `mapping_note`) and `verify_original` no longer returns
  `status=verified` for them; single-file items keep the
  verified mapping.
- OCR file names from metadata are treated as untrusted:
  names with path separators or traversal are never selected,
  and download URLs percent-encode the file name.
- Note on page mapping: even for single-file items, a verified
  mapping means the OCR leaf order is consistent with the
  item's page-image sequence as far as the metadata shows; it
  is not a pixel-level collation against the original image,
  so quotations should still be checked against the original
  page image before scholarly use.

## 1.0.0b1 — Research Beta release candidate (2026-11-24)

Integration of Phases 1–10 (PRs #1–#10, merge commits into
`master`). Research Beta is the product: library materials
search, page-level OCR, original-page viewing (IIIF), document
comparison and verifiable citations — usable with no LLM and
no API key. AI answering remains a separate experimental
track, disabled by default.

Release-prep changes on this branch:

- Internet Archive: djvu OCR file names are resolved from the
  item's metadata file list instead of a guessed
  `{identifier}_djvu.xml`, which returned 404 for multi-volume
  and renamed items (found in live integration checks).
  Multi-volume items currently expose the first volume's OCR.
- Package version aligned to 1.0.0b1 (PEP 440).

Known limitations (verified at integration time):

- The per-question request budget counts service-level units;
  most units are one outbound HTTP request, but retries and
  multi-request adapter operations can exceed the unit count.
  The evaluation harness counts actual HTTP requests.
- Gallica/BnF: adapter implemented, upstream returns 403 from
  the development network; not live-verified.
- Europeana's current numeric daily API limit is unverified;
  see docs/phase10-library-terms.md for the per-library terms
  posture before any public deployment.
- Page and search caches are size-capped (FIFO) with no TTL.

## Phase 9 — AI validation readiness (2026-11-24)

- Critical fix (9-A): the real-LLM path compacted evidence
  twice and sent an empty OCR body; compaction now happens
  exactly once, passage-aware and idempotent, with the actual
  HTTP payload under test. Published answers are composed
  from verified claims; unsupplied passage IDs invalidate a
  claim.
- Runtime cost enforcement (9-B): UsageLedger refuses a call
  whose worst case could exceed the remaining budget; the
  evaluation runner cannot be driven directly (approval
  hand-off required); approved/priced/executed/recorded
  models are forced identical.
- Gold data v2 (9-C): audited labels (entailment /
  contradiction / neutral / ambiguous / unverified),
  group-wise splits, strict scoring (uncertain no longer
  counts as recognition).
- Shadow mode (9-F): auxiliary checker verdicts recorded,
  never consulted by admission.
- Materials mode (9-G): citation copy, record-page links,
  admitted-only filter.
- Security audit and PR integration plan (9-I / 9-J) under
  docs/. Real-LLM evaluation remains unapproved and unrun;
  the approval request is docs/phase9-llm-experiment-plan.md.

## Phase 8 — research-engine restructure (2026-11-24)

- Architecture audit (8-A, docs/phase8-audit.md): the single
  `verified` flag conflated discovery, identity and factual
  certification; two weaker certification paths named honestly.
- Evidence states + stage log (8-B): discovery, access,
  identity, relevance, passage support and answer
  certification are separate per-page facts with reasons.
- Passage extraction (8-C): verbatim, char-located passages
  are the unit of evidence; quotations re-verified against
  the fetched OCR.
- Research-materials mode (8-D): the answer pipeline's output
  presented as materials for the reader's own judgment - MCP
  tool, `/api/materials`, Web UI mode - with no duplicate API
  calls and explicit not-admitted reasons.
- NLI (8-E): hypothesis-based checker interface; verdicts are
  auxiliary signals that never approve an answer; model load
  attempted once, bounded - unavailable in this environment,
  recorded `not_checked` (docs/phase8-models.md).
- Gold passage dataset (8-F): `eval/gold-passages.json` -
  pipeline-admitted supporting passages plus the frozen
  Phase 7 must-reject fixtures, dev/eval split, agent-verified.
- Real-LLM readiness (8-G): budget guard (key, opt-in, priced
  model, estimate <= cap, explicit approval) - blocks with
  reasons and makes no call otherwise; results stay separate.
- Structured claims + partial answers (8-H): claims carry ids,
  passage links, temporal scope, numeric values and support
  status; unverifiable claims are removed and the verified
  remainder published as `answered_partial`.
- Load (8-I): per-question request budget with honest
  budget-limited wording, per-library circuit breaker,
  FIFO-bounded search cache, `libraries=None` cache-key fix.
- Web UI (8-J): materials mode with state chips; MockProvider
  output badged as demo/test mode; partial-answer badge.
- Measured outcome: see docs/evaluation-phase8.md.

## Phase 7 — evidence-promotion safety (2026-11-23)

- The eight Phase 6 false answers reproduced as fixed fixtures
  (7-A); four generalised mechanisms (docs/phase7-diagnosis.md).
- One admission rule for every evidence path (7-B): era-bound
  answers require anchored assertions; mentions_only /
  insufficient never ground era answers; unions need an
  asserting member and per-page era conditions; structured
  promotion records on admitted pages.
- Numeric binding (7-C): kanji-numeral quantities, target-bound
  claim screening, table-only values unverified.
- Page kinds v2 (7-D): index/colophon/admin_list/title_page/
  damaged + per-question-kind usage policy. Corrections rest
  on narrative pages only (7-E).
- Independent set v2 frozen before any run (7-F); Recall split
  into A (record reached: 0.667) and B (verified page obtained).
- Load (7-G): search cache + variant dedupe; refused questions
  still exhaust the fetch waves, so totals rose - documented
  in docs/evaluation-phase7.md.
- Measured outcome: main-set false answers 4 -> 0 and handled
  1.000, at answerable 0.841 -> 0.591 (the brief's safety-first
  tradeoff, reported unresolved); holdout keeps 2 false answers
  via non-fixture pages.

## Phase 6 — retrieval reachability (2026-11-23)

- Failure diagnosis (6-A): the 34 failed answerable questions
  split into gate rejects 15 / candidate misses 10 / budget
  misses 6 / semantic rejects 3 — three different problems, three
  different fixes (docs/phase6-diagnosis.md).
- Search (6-B): full query-variant pool (no early stop), series
  dedupe, multiplicity-aware bibliographic ranking; question
  analysis drops aspect pseudo-concepts, demotes bare city
  names, folds 寫眞/橫濱-type period spellings, and the
  hiragana-fragment filter now uses a real Unicode range.
- Fetching (6-C/6-D): three waves (screen / deepen / extend),
  hit-multiplicity page selection, adjacent pages, page-kind
  classification, document-level union promotion.
- English (6-E): phrase concepts, word-century eras; IA + NDL
  verified live. Phrase families match on all content words.
- Semantics (6-F): onset cues 開通/実現, scoped bare negation,
  per-sentence onset detection, year-gated anchor inheritance;
  GLM_SEMANTIC_EMBED_MODEL now actually activates the embedding
  signal. Era-bound enumerative pages that only mention a topic
  no longer ground answers.
- Evaluation (6-G): answerable 0.591 -> 0.841 (main), 0.304 ->
  0.652 (holdout), 0.667 on a new frozen independent set with
  zero false answers; false answers on the tuning sets rose
  0 -> 4 / 2 -> 4 (mechanisms and rejected mitigations in
  docs/evaluation-phase6.md). Requests/question ~1.5-2.3x.

# Changelog

All notable changes are recorded here. Dates are JST. Anything not
listed as verified was not live-verified; see
`docs/implementation-status.md` for the per-feature truth table.

## Phase 5 — semantic grounding (branch feat/global-library-semantic-v5)

- Semantic grounding checker (semantics.py): replaceable
  SemanticChecker interface; deterministic rule-based primary
  engine classifying a page's stance toward the question premise
  (supports / contradicts / mentions_only / insufficient /
  uncertain / not_checked). Optional embedding checker behind the
  same interface; never a pipeline dependency.
- Temporal verification (temporal.py): era-name / western-year /
  era-year anchors per sentence, onset-after-era detection, and
  retrospective-source anchoring (undated stance in post-era
  publications does not support an era premise).
- Gate integration: contradicting pages become correction
  material; retrospective mentions-only pages are demoted;
  semantically supported partially-relevant pages are promoted.
- New answer status corrected_premise: grounded premise
  corrections quoting the contradicting page verbatim.
- Search: graded Stage-1 candidate scoring, one-shot dynamic
  budget extension, retrieval summary (candidate ranks, failure
  reasons) feeding Recall@K / MRR in the evaluation runner.
- Evaluation: 70-question set — insufficient handled 1.000
  (Phase 4: 0.808), false answers 0, answerable 0.591 (Phase 4:
  0.682); frozen 32-question holdout — answerable 0.304,
  correction cases safely refused. See docs/evaluation-phase5.md
  for the full run history and honest trade-off analysis.

## Phase 4 — reliability v4 (2026-11-22, branch `feat/global-library-reliability-v4`)

- Question understanding (`question.py`): rule-based analysis —
  core concepts vs generic terms (old-form/synonym normalisation),
  era detection incl. era-year conversion, regions, intent, and
  structured requirements. No LLM required.
- Relevance gate (`relevance.py`): every quality-passed page is
  screened against the question (relevant / partially_relevant /
  irrelevant / uncertain, with reasons). Only relevant pages ground
  answers; the rest are returned as related reference material.
  Era-distance, numeric-requirement, compound and anchor rules are
  documented in `docs/evaluation.md`.
- Answer withholding: answers whose claims screen unsupported or
  conflicting are withheld whole (`answer_withheld`); refusals name
  the missing core concepts and attach related documents. Claims
  with invented quantities are now screened unsupported.
- Evaluation v2: 70-question dataset + deterministic fixture suite.
  Live NDL/mock runs (see `docs/evaluation.md`): insufficient-
  evidence correctness 0.20 → 0.808, answerable success 0.682,
  citation resolution 1.00; targets of 0.90 are not yet met and the
  residual failure classes (retrospective era mentions; retrieval
  misses) are documented with examples. One label (q27) was
  corrected with disclosed rationale.
- Web UI: relevance badges and reasons on evidence cards, a related
  documents section, withheld-answer display; efficiency: query
  deduplication, per-instance page caching, early termination on
  document-level search failure (requests/question 26.1 → 18.8).
- IA catalog search excludes lending-only items; English function
  words no longer become search terms or core concepts.

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
