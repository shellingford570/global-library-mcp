# Phase 9 evaluation — AI-validation readiness

Branch `feat/global-library-ai-validation-v9`. All live runs
below are **MockProvider** (live NDL) unless stated; no
real-LLM run was approved or made in Phase 9.

## 9-A: the double-compaction bug (fixed, regression-tested)

`service.answer` compacted evidence, then the OpenAI provider
compacted the payload again; the second pass read the missing
`ocr_text` and sent an empty body. Compaction now happens
exactly once inside the provider layer, is passage-aware and
idempotent, and providers receive the raw evidence. The
published answer text is composed from verified claims; a
claim citing an unsupplied passage ID is marked unsupported.
`tests/test_phase9_llm_payload.py` captures the actual request
JSON via a mock transport and asserts the OCR body, passage
IDs and model reach the endpoint; 429/500/timeout/garbage all
become sanitised unavailability with no key material anywhere.

## 9-B: runtime cost enforcement

`UsageLedger` refuses a call whose worst case could exceed
the remaining budget; unreported usage is booked at the worst
case, never zero. `run_evaluation --provider openai` exits 2
without the approval hand-off (no `--approve` flag exists on
the runner). `real_llm_run` forces the executed model to the
approved one and blocks on an environment mismatch. Price
table re-verified 2026-11-24 against OpenAI's published API
pricing (values unchanged).

## 9-C: gold data audit (the phase's hardest finding)

Re-labelling v1's 44 cases from each passage's own properties
(page kind, asserting sentences, era-anchored quantities),
independent of the pipeline admission that created them: of
36 "supporting" cases, **7 re-derive as entailment**, 15 stay
**unverified** (conservative labeller; human verification
still outstanding), the rest are neutral listing/mention
pages or ambiguous. v2 totals **71 cases** (pipeline-rejected
pages as neutrals, fresh-search cases, constructed era-shift
contradictions and topic-swap neutrals), split by record
group. Strict scoring (supports only; the old evaluator also
counted `uncertain`): entailment recognition dev 1.000 (1/1),
eval **0.667** (4/6) — the legacy counting showed 6/6 on the
same split. Negative certification refusal: dev 0.955, eval
0.833 — harder negatives than v1's fixtures, reported as
measured. v1 is kept unchanged.

## 9-D: NLI — still not_checked, with evidence

Caches inspected first (68K total, no weights; transformers /
torch / onnxruntime / sentence-transformers all absent). No
repeat download attempted. The interface, hypothesis builder
and one-attempt bound are unchanged and ready for an
environment that can hold the weights.

## 9-F: shadow analysis (rule checker vs audited labels)

agree_support 5 · under_recognition 2/7 · agree_refuse 34 ·
anchor_saved 7 · **over_acceptance 5** · excluded 18.
The era anchor refuses 7 raw supports verdicts; 5 cases would
still be certified against the audited label — the residual
risk set any future checker must shrink.

## 9-H: request budget on all sets (GLM_REQUEST_BUDGET=25)

| Set | Answerable unlim → 25 | False answers unlim → 25 | Handled unlim → 25 | req/q unlim → 25 | sec p50 unlim → 25 |
|---|---|---|---|---|---|
| 70q | 0.591 → **0.591** | 0 → 0 | 1.000 → 1.000 | 32.8 → 24.0 | 15.96 → 4.80 |
| Holdout | 0.304 → 0.261 | **0.333 → 0.000** | 0.667 → **1.000** | 53.3 → 35.0 | 20.59 → 8.49 |
| Newset 24 | 0.278 → 0.222 | 0 → 0 | 1.000 → 1.000 | 55.0 → 37.2 | 13.59 → 10.71 |
| Newset2 16 | 0.300 → **0.300** | 0 → 0 | 1.000 → 1.000 | 53.5 → 36.8 | 11.45 → 12.81 |

Reading: the cap costs at most one answered question per set
and, on this holdout run, cut off the deep fetch waves that
had produced the h05/h22 false answers (single live run —
a measured outcome, not a guarantee). Request p90 fell from
65–75 to 40–48 everywhere.

**Budget tiers proposed**: Quick = 10 units (discovery),
**Standard = 25 (recommended default — measured above)**,
Deep = unlimited (explicit research dives). The budget counts
service-level units (in-document searches + gated pages);
retries and original-verification calls ride on the same
HTTP client and are visible in the request totals.

## 9-G: materials mode

Citation copy button, record-page link, admitted-only filter
added; excerpts, state chips, not-admitted reasons, rights
lines and original-image links were already per-card. E2E
covers the new controls (8 Playwright tests pass).

## 9-K: release-candidate verdict

- **A. Research-materials search beta — READY** (subject to
  the PR stack being merged): cross-library search, OCR
  excerpts, original viewing, comparison, rights display and
  honest candidate labelling all work without any LLM.
- **B. AI-answer experimental — NOT YET**: the plumbing is
  now correct and cost-guarded, but no real-LLM quality
  measurement exists. The approval request in
  `docs/phase9-llm-experiment-plan.md` is the gate.
- **C. Formal research-support AI — NOT YET**: requires B's
  measurements, an independently (human-) verified gold set,
  NLI or LLM semantic checking proven in shadow mode, and
  operational monitoring.

## Quality gates

- pytest: full suite passed on the final code.
- Playwright: 8 passed.
- Local integration check (9-J): master + v9 head merged on a
  temporary branch — full suite green; branch deleted.
- GitHub Actions: verified on PR #9.
- Security audit: `docs/phase9-security-audit.md` (secret
  scan over tracked files: no hits).

## Addendum (2026-11-24): the approved real-LLM run

Executed after the report above, as amended by the operator
(xAI grok-4.3, 20 questions, $1.00 cap): answerable 0.200
(4/20) vs MockProvider 0.600 on the same subset; ledger-booked
cost $0.2133 (real charge ≈ $0.05; see
`docs/phase9-llm-experiment-plan.md`). The LLM's abstractive
claims mostly fail the verbatim-overlap screening — verdict B
remains NOT YET, with the constraint now measured rather than
assumed.
