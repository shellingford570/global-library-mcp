# Phase 6 evaluation — retrieval reachability

All runs live against NDL with the MockProvider (no paid LLM),
same conditions as Phases 4–5. Files: `eval/results-phase6.json`
(70 questions), `eval/results-phase6-holdout.json` (Phase 5
holdout, now a tuning/diagnosis set), `eval/results-phase6-newset.json`
(the Phase 6 independent set, frozen in commit 265e0a3 before any
run), `eval/biblio-recall-phase6.json` (search-stage measurement,
`eval/biblio_recall.py`).

## Headline numbers

| Metric | Phase 5 main | **Phase 6 main** | Phase 5 holdout | **Phase 6 holdout** | **Phase 6 newset** |
|---|---|---|---|---|---|
| Answerable success | 0.591 | **0.841** (37/44) | 0.304 | **0.652** (15/23) | **0.667** (12/18) |
| Insufficient correct | 0.962 | 0.808 (21/26) | — | 0.333 (2/6) | 1.000 (2/2) |
| Insufficient handled | 1.000 | 0.846 | 0.667 | 0.333 | **1.000** |
| False answers | **0** | **4** | 2 | **4** | **0** |
| Corrections (live) | 1 | 1 | 0 | 0 | 0 |
| Evidence Recall@3 | 0.432 | **0.750** | — | 0.435 | 0.556 |
| Evidence Recall@6 | 0.591 | **0.841** | 0.304 | **0.609** | 0.611 |
| MRR | 0.410 | **0.662** | 0.199 | 0.405 | 0.436 |
| Bibliographic Recall@6 | — | 0.750 | — | 0.739 | 0.722 |
| Citation resolution | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Requests / question | 19.8 | 29.1 | 21.1 | 45.8 | 49.5 |
| Avg seconds / question | 6.6 | 16.4 | 7.1 | 20.7 | — |

Bibliographic Recall@K = first candidate whose *title* carries a
core concept within rank K (search stage alone). It is a lower
bound: evidence Recall@6 (0.841) exceeds it (0.750) because some
evidence-bearing books have concept-free titles. The @3/@6/@10
values coincide — a topical title is either ranked top-3 by
`rank_candidates` or absent from the pool.

## What improved, and why

The 6-A diagnosis (docs/phase6-diagnosis.md) split the 34
failures into gate rejects (15), candidate misses (10), budget
misses (6) and semantic rejects (3). Each got its own fix:
question cleanup and pool/ranking work (6-B) removed the
pseudo-concept dilution; staged fetching (6-C) reaches rank-7–15
candidates; page selection + document-level union promotion
(6-D) rescued split-coverage questions; English analysis (6-E)
made IA/NDL answer English questions end-to-end (the
hydroelectric reference question: IA 2 pages, NDL 3 pages, vs
zero from IA in Phase 5). Answerable success rose +0.25 (main)
and +0.35 (holdout); the frozen newset — never used for tuning —
lands at 0.667 with **zero false answers and handled 1.000**.

## The safety regression, stated plainly

The brief's first goal was *no new false answers*. On the two
tuning sets that goal was **not met**: main 0 → 4 (q31 TV, q35
Shinkansen, q40 waterfall count, q52 washing machine), holdout
2 → 4 (h03 internet, h05 steam locomotive, plus Phase 5
holdovers h22/h31). Deeper fetching exposes marginal pages to
paths that Phase 5 rarely reached:

- **Semantics promotion of enumerative/administrative pages**
  (q35 route listings, q40 staffing rules for a *numeric*
  question — the page contains numbers, just not the asked
  ones; claim screening cannot tell which number answers).
- **A contents page classified as body** (q52) whose
  mentions_only verdict does not block a relevant page outside
  retrospective sources.
- **Compound-halves relevance with no concept sentence** (h05)
  and **barely-passing OCR garbage** (h03's index page).

Two mitigations were implemented and *measured*, not assumed:
(1) demoting era-bound mentions_only/insufficient pages
unscoped — rejected by measurement (answerable 0.841 → 0.705,
false answers only 4 → 3: the checker is too conservative on
genuine contemporary prose); (2) the same demotion scoped to
enumerative page kinds (front_matter/photo_plate) plus
structural contents detection — kept; it is neutral on the main
set as run (the q52 page still classifies as body) and protects
the union path. Further per-case chasing was stopped
deliberately: it would overfit the tuning sets. The untouched
newset kept a clean safety profile, which is the least biased
reading of where the balance now sits — but the tuning-set
regression is real and is the first thing a Phase 7 should
attack (promotion-path anchoring requirements and numeric-
demand page screening are the two principled candidates).

## Run-to-run variance

The newset was run twice on the pre-tightening code: identical
metrics, identical false-refusal lists, identical request
counts (1,169) — the pipeline is effectively deterministic
against the live API within a day. The final-code newset run
(1,189 requests) reproduced the same headline rates.

## Costs

Requests per question rose ~1.5× (main) to ~2.3× (newset):
full query-variant pools plus three fetch waves. Latency rose
proportionally (16–21 s/question). Within consumer-API limits,
but the staged budget is the knob to trim first if load matters.

## Regression & quality gates

- pytest: 131 passed (incl. the six named Phase 6-F cases:
  subway/radio/TV/refrigerator/spaceflight premises still
  contradict; a contemporary late-Meiji hydro source still
  supports; bare-era-name anchors are no longer inherited).
- Playwright: 7 passed; e2e smoke passed (health, routes,
  two-library live search, NDL OCR/IIIF, disabled-AI path).
- Docker: not installed in this environment; the Dockerfile is
  unchanged and CI builds it.
- The documented `GLM_SEMANTIC_EMBED_MODEL` switch now actually
  activates the embedding checker as an attached signal (Phase 5
  left the factory ignoring it). The embedding model itself
  remains unverified here (weights download fails through the
  proxy; the checker degrades to `not_checked` by design).
