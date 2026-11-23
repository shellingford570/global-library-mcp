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
