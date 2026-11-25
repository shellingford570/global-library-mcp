# Changelog

## Unreleased — IA source accuracy (Section-1 fixes)

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
