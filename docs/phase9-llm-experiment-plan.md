# Phase 9-E: real-LLM small-scale evaluation — plan and approval request

Status: **planned, NOT approved, NOT run.** No paid API call
has been made. This document is the approval request the
brief requires before any real-LLM evaluation.

## Design (fixed evidence, small first)

- **Cases**: 20, drawn from `eval/gold-passages-v2.json` with
  the passage text FIXED (no live search): entailment cases,
  contradiction cases, neutral cases, plus cases whose correct
  behaviour is correction / partial / refusal, mirroring the
  v2 label mix.
- **Methods compared on identical inputs**:
  - A: rule checker (existing baseline, already measured)
  - B: local NLI (only if a backend becomes loadable; currently
    `not_checked` in this environment)
  - C: real LLM as evidence judge (verdict per passage)
  - D: real LLM structured answer (the Phase 9-A payload path)
  - E: rule + LLM combined (LLM verdict recorded, rule governs)
- **Recorded per method**: answer accuracy, false answers,
  false refusals, latency, measured token usage, cost (from
  the UsageLedger summary written into the results file).
- Results go to a separate file
  (`results-phase9-llm-<model>.json`); MockProvider numbers are
  never merged with real-LLM numbers.

## Approval request (the decision needed)

| Item | Value |
|---|---|
| Provider | OpenAI (OpenAI-compatible API) |
| Model | `gpt-4o-mini` (priced in the table; note: third-party trackers flagged the 4o-mini/4.1-mini generation as deprecated in Nov 2026 — if it is unavailable at run time, the run stops and approval is re-sought for the replacement) |
| Endpoint | `https://api.openai.com/v1` (fixed; the plan prints the base URL and a mismatch with the environment blocks the run) |
| Cases | 20 questions, at most 1 provider call per question per method (C and D are separate runs; total cap below covers both) |
| Max calls | 40 |
| Max input tokens | 12,000 per call (ledger worst case) |
| Max output tokens | 1,200 per call (also sent as the request's max_tokens) |
| Estimated cost | ~$0.03 at expected sizes (2,500 in / 400 out per call) |
| **Maximum cost (hard cap)** | **$1.00** — the UsageLedger refuses any call whose worst case could exceed the remaining budget |
| Data sent externally | The question text and short OCR excerpts (≤1,500 chars per page, ≤8 pages) from public-domain historical materials in NDL / Internet Archive. No personal data, no credentials, no user information. |
| Purpose | Measure whether a real LLM's semantic judgement beats the rule checker on fixed evidence, before any production adoption. |

## How approval is executed (no self-approval)

The agent never adds `--approve` itself. If the operator
approves, the run is:

```
LLM_API_KEY=... LLM_ENABLED=true \
python -m eval.real_llm_run --model gpt-4o-mini --questions 20 \
    --max-cost-usd 1.00 --approve
```

`real_llm_run.py` re-checks every precondition (key, opt-in,
priced model, estimate ≤ cap, environment model match), forces
the executed model to the approved one, and hands the approval
+ cap to the evaluation process, whose own gate re-verifies
them and whose UsageLedger enforces the cap during the run.
Running `eval/run_evaluation.py --provider openai` directly
exits 2 without the hand-off.

## Phase 9-F shadow results (already measured, no LLM)

Shadow analysis over gold v2 (rule checker run beside the
audited labels, influencing nothing): agree_support 5,
under_recognition 2 of 7 entailments, agree_refuse 34,
anchor_saved 7 (raw supports verdicts the era anchor refuses —
the anchor is load-bearing), **over_acceptance 5** (checker +
anchor would certify against the audited label — the residual
risk set for any future checker change), excluded 18.
`eval/shadow-analysis-phase9.json`. The pipeline also gained
an env-gated shadow stage (`GLM_SHADOW_NLI=1`) that records
NLI verdicts beside governing decisions without consulting
them; with no NLI backend loadable here it records nothing.
h05/h22 note: their frozen fixture pages are refused by the
checker; the live holdout false answers arrive via *other*
pages, so the fix must be a general admission property, not a
fixture-shaped rule — none was added.

## Addendum (2026-11-24): provider switched to xAI at the operator's request

The operator approved the run and then asked to use the Grok
API instead of OpenAI. Amended approval parameters, everything
else unchanged (20 cases, at most 40 calls, hard cap $1.00,
public-domain OCR excerpts only):

| Item | Amended value |
|---|---|
| Provider | xAI |
| Model | `grok-4-fast` (list price $0.20 in / $0.50 out per 1M tokens, verified 2026-11-24; added to the price table) |
| Endpoint | `https://api.x.ai/v1` (OpenAI-compatible; the same provider class is used with `LLM_API_BASE` set) |
| Estimated cost | ~$0.03 at expected sizes |

The xAI API is billed separately from any Grok/X consumer
subscription; the key is issued at console.x.ai.

## Result (2026-11-24, executed as amended)

- Approved by the operator: first for gpt-4o-mini, then
  switched to xAI at the operator's request; grok-4-fast was
  not available on the key, and the operator chose
  **grok-4.3** under the same $1.00 cap.
- Run: first 20 questions of the main set (all
  evidence-labelled), live NDL + live xAI, via
  `eval/run_llm_via_connector.py` (connector-held key; only a
  surrogate entered the process). Results:
  `eval/results-phase9-llm-grok-4.3.json`, provider recorded
  as `openai-compatible:grok-4.3`.
- **Cost**: ledger-booked **$0.2133** of the $1.00 cap
  (conservative: 9 of the 20 ledger entries were questions
  that never reached the provider or returned no usage and
  were booked at worst case; the usage-reported portion
  implies a real charge of roughly $0.05). 11 provider calls
  reported usage; 1 call ended `llm_unavailable` (sanitised).
  A follow-up fix makes the ledger record only actual
  provider calls.
- **Quality on this subset**: answered 4/20
  (answerable_success 0.200) vs MockProvider 12/20 (0.600) on
  the same questions. 8 questions never reached the LLM (the
  rule pipeline admitted no evidence). 7 answers were
  withheld because the LLM's claims failed the verbatim
  overlap screening (supported claims 5/19; the LLM
  paraphrases where the screening expects quotation).
  No insufficient-labelled questions are in this subset, so
  the false-answer rate is unmeasured here (0 observed).
- **Conclusion**: the binding constraint is no longer the
  judge's semantics but the lexical claim verification (and,
  upstream, evidence admission). Release verdict B stays
  NOT YET, now with evidence. Next step candidates: claim
  screening that accepts verified paraphrase (e.g. an
  entailment check on claims), and a subset that includes
  insufficient/correction questions.
