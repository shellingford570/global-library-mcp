# Phase 8 evaluation — research-engine restructure

Run: 2026-11-24 (live NDL, **MockProvider** throughout; no
real LLM was used). Five runs, all on the Phase 8 code at
`feat/global-library-research-engine-v8` HEAD `1ba7495` plus
the evaluation doc itself. Files:
`eval/results-phase8.json` (70q), `results-phase8-holdout.json`
(32q), `results-phase8-newset.json` (24q),
`results-phase8-newset2.json` (16q),
`results-phase8-main-budget.json` (70q, `GLM_REQUEST_BUDGET=25`).

**MockProvider measures citation and pipeline behaviour, not
real-LLM answer quality.** Nothing below is a real-LLM result.

## Search quality and answer quality, separately

| Set | n | Answerable (of evidence) | False answers (of insufficient) | Insufficient handled | Recall@6 | MRR | req/q | s/q |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 70q (P7: 0.591 / 0 / 1.000 / 0.591 / 0.564 / 32.8) | 70 | **0.591** (26/44) | **0** (0/26) | 1.000 | 0.591 | 0.564 | 32.8 | 18.77 |
| Holdout (P7: 0.304 / 2 / 0.667 / 0.304 / - / 53.9) | 32 | **0.304** | **2** (h05, h22; 0.333) | 0.667 | 0.304 | 0.181 | 53.3 | 27.23 |
| Newset 24 (P6: 0.667) | 24 | **0.278** | **0** | 1.000 | 0.278 | 0.204 | 55.0 | 12.40 |
| Newset2 16 (P7: 0.300) | 16 | **0.300** (3/10) | **0** | 1.000 | 0.200 | 0.214 | 53.5 | 11.37 |
| 70q budget=25 | 70 | **0.591** | **0** | 1.000 | 0.591 | 0.564 | **24.0** | **4.84** |

Denominators: answerable = evidence-labelled questions;
false answers = insufficient-labelled questions answered;
handled = insufficient-labelled questions refused or
corrected. Correction: q39 (main) and h13 (holdout) as
`corrected_premise`.

## What the numbers say

- **Phase 8 was a restructure, not a relaxation.** Answerable
  rates are essentially unchanged from Phase 7 on every set
  (0.591 / 0.304 / 0.278 / 0.300). The seven success
  conditions of the brief (separation of search and
  certification; useful research mode when answers are
  withheld; passage-level evidence; gold data; search-free
  comprehension measurement; real-LLM readiness; maintained
  citation/safety behaviour) are met as *capabilities*, not
  as a higher score.
- **The budget cap works.** At `GLM_REQUEST_BUDGET=25` the
  main set loses *nothing* (answerable 0.591, false answers
  0, handled 1.000, corrections 1, claims 73/73 supported)
  while requests fall 32.8 → 24.0/q (−27%) and time 18.77 →
  4.84 s/q (−74%). The cap binds on hopeless questions, not
  on answerable ones.
- **h05 / h22 remain.** Both holdout false answers go through
  pages outside the Phase 7 fixture set; the admission rule
  blocks the frozen mechanisms, but new pages with the same
  shapes (compound halves, mentions-only) still slip through.
- **The cost concentration moved, not away.** Holdout and the
  new sets run 53–55 requests/question: refused questions
  still exhaust the fetch waves. The budget cap (now proven
  safe on the main set) is the tool to bring those down.
- **No partial answers were observed** in any regression run
  (partial rate 0.0 everywhere). The mechanism is implemented
  and unit-tested, but the MockProvider rarely produces mixed
  supported/unsupported claim sets, so it is unexercised live.
- **Claims**: 73 supported / 0 unsupported / 0 conflicting /
  0 uncertain on the main set; citation resolution 1.000.

## Gold passage dataset (8-F, search-free measurement)

`eval/gold-passages.json`, 44 cases (36 supporting, 8
must_reject), dev/eval split. Type A (passage given, search
excluded): the rule checker recognises 0.611 (dev) / 0.500
(eval) of genuine supporting passages — the binding limit on
recall is checker precision on descriptive period prose, now
measured independently of search. Type D (wrong evidence
given): certification refused 1.000 on both splits.

## Model comparison (8-E)

NLI (MoritzLaurer/mDeBERTa-v3-base-mnli-xnli, MIT) could not
be loaded here — `transformers` is not installed and the
weights cannot be fetched through this environment's proxy;
the comparison harness records `not_checked` honestly, with
the rule checker's verdicts on the same 8 fixtures beside it
(`eval/checker-comparison-phase8.json`). The embedding
checker remains an unloaded similarity signal. Neither is
used for truth judgements anywhere in the pipeline.

## Real-LLM readiness (8-G)

`eval/real_llm_run.py` + `llm_budget.BudgetPlan` block an
unapproved run (no key / no opt-in / unpriced model / estimate
over cap / no --approve) with exit 2 and no call; verified
blocking. No paid call was made in Phase 8. The remaining
decision for tana: provider, model, question count, cost cap.

## Quality gates

- pytest: full suite passed on the final code.
- Playwright: 8 passed (incl. the new materials-mode test).
- Docker: Dockerfile unchanged; not rebuilt here (no Docker
  in this environment) — CI builds it.
- GitHub Actions: to be verified on PR #8.
