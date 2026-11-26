# b6 evaluation (sections 4, 27-29)

## Datasets

Fixed before implementation, unchanged since:
`eval/b6-dev.json` (40, development), `eval/b6-fixed.json`
(40, fixed evaluation), `eval/b6-holdout.json` (20, unseen
cases), against the fixed fixture corpus
`eval/b6-corpus.json` (51 records modelled on real holdings
across NDL/IA/LoC/Gallica/DDB). Every case records query
language, tags, expected works/authors/languages, relevant
record ids and a rationale. **Labels are agent-assigned**
(`label_source: agent_assigned`); there is no independent
human-labelled gold set, so all metrics below are PROXY
metrics from a simulated keyword search over the fixture
corpus - they measure variant generation, routing and
ranking behaviour, not live catalogue recall. Live behaviour
additionally differs in pool dynamics (see the variant
ordering finding in docs/b6-multilingual-research.md).

Harness: `eval/b6_eval.py` (+ `eval/b6_engine_configs.py`).
Results: `eval/results-b6-ablation-{fixed,dev,holdout}.json`,
baselines in `eval/results-b6-baseline-*.json`.

## Evaluation B — the real LibraryService (final review §15)

Evaluation A above is a simulation. Evaluation B
(`eval/b6_service_eval.py`, results in
`eval/results-b6-service-eval.json`) runs the actual
`LibraryService.research_materials` over fixed HTTP fixtures
served through the production `BudgetedTransport`, for the 10
fixed-set cases whose relevant records live in the default
libraries. It exercises the real search plan, routing, variant
order, HTTP budget, early stop, filters and ranking.

| Mode | Recall@10 | Avg HTTP requests | Avg bytes (decoded) | Warm-cache hits |
|---|---|---|---|---|
| quick | 0.500 | 12.6 | 624 | 0 (Quick does not use the bibliographic cache) |
| standard | 0.7667 | 24.6 | 1,386 | 5 |

Author-filter check through the real pipeline: F03 with
`author="Immanuel Kant"` keeps exactly the 3 Kant-authored
records (candidates 4 → 3 at the bibliographic stage).
Fixture elapsed times (≈11.7s quick / ≈19.8s standard per
case) are dominated by per-library deadline waits against
fixtures and are NOT live timings. Differences from live
behaviour: fixture responses are instantaneous and complete;
live libraries time out, 403, and paginate differently.

## Challenge set (final review §18)

`eval/b6-challenge.json` (20 cases) + `eval/b6-challenge-corpus.json`
(14 records), fixed BEFORE the final-review fixes, all
agent-assigned labels: same-surname authors (Erasmus vs
Charles Darwin; Max vs Alfred Weber), original vs commentary,
same-year different-publisher editions, wrong-premise and
no-material negatives. Shipped F: Recall@10 0.9167,
attempts 36.6 (pre-fix 39.6), false_candidate_rate 0.5
(1 of 2 negative cases retrieves candidates; discovery
retrieves, admission decides). Baseline A: Recall@10 0.5278.
The pre-existing dev/fixed/holdout sets have been used for
configuration decisions and are regression sets, not unused
holdouts.

## Ablation (fixed set, 40 cases / 36 with relevant records)

| Config | Recall@5 | Recall@10 | Recall@20 | Prec@5 | MRR | nDCG@10 | Cross-lang | Attempts |
|---|---|---|---|---|---|---|---|---|
| A b5 baseline | 0.486 | 0.486 | 0.500 | 0.178 | 0.701 | 0.508 | 0.028 | 27.4 |
| B +historical | 0.544 | 0.544 | 0.558 | 0.206 | 0.785 | 0.571 | 0.056 | 31.2 |
| C +authors | 0.748 | 0.764 | 0.778 | 0.306 | 0.808 | 0.724 | 0.389 | 40.0 |
| D +titles | 0.750 | 0.764 | 0.778 | 0.306 | 0.826 | 0.737 | 0.389 | 46.4 |
| E +concepts | 0.938 | 0.944 | 0.944 | 0.400 | 0.877 | 0.859 | 0.611 | 64.8 |
| F +routing (shipped) | 0.896 | 0.910 | 0.910 | 0.372 | 0.866 | 0.829 | 0.611 | 38.2 |
| G +explanations (shipped form) | = F | = F | = F | = F | = F | = F | = F | = F |
| Gx experimental ranker (NOT shipped) | 0.861 | 0.910 | 0.910 | 0.361 | 0.853 | 0.832 | 0.611 | 38.2 |
| H +grouping | = F | = F | = F | = F | = F | = F | = F | = F |

Dev set, F vs A: Recall@10 1.000 vs 0.790; cross-language
0.316 vs 0.053. Holdout, F vs A: Recall@10 0.938 vs 0.875;
cross-language 0.250 vs 0.125.

## Reading the ablation honestly

- Historical expansion (B) helps modestly; author variants
  (C) and concept translations (E) are the large gains.
- Work titles (D) raise MRR/nDCG slightly but not recall on
  this corpus, at +6 attempts - kept, because title search is
  a primary researcher behaviour and the live Kant run
  surfaced the original title path; the cost is recorded.
- Routing (F) trades ~3.5 points of Recall@10 for a 36%
  attempt reduction and keeps cross-language discovery.
- Ranking replacement (Gx, `engine_rank_experimental`)
  lowered MRR on all three datasets (fixed 0.853 vs 0.866
  shipped; dev 0.828; holdout 0.755) and was NOT shipped;
  G in the shipped pipeline is F + explanation attachment.
  The experiment is reproducible from the shipped code:
  `python eval/b6_eval.py --config Gx` (final-review §16).
- Grouping (H) is presentational: it changes no ranked
  metric. Its correctness is covered by resolution tests
  (0 false merges: author-mismatch and shared-surname cases
  refuse).

## Tag-based success (fixed set, config F) — separate denominators

Each tag is reported with its own denominator; combined
figures must not be read as per-tag rates (final-review §17).

- Original-title cases (2): any-hit 2/2, full recall 2/2.
- Translated-title cases (6): any-hit 6/6, full recall 6/6.
- Cross-language cases (8): any-hit 8/8, full recall 5/8.
- Negative cases (4 of the 40): false_candidate_rate 0.75 —
  discovery retrieves candidates for 3 of the 4 no-relevant
  cases; irrelevant_retrieval_rate 0.075 overall. Discovery
  is not premise certification; admission is unchanged.

## Provisional targets (section 28) - assessment

- Fixed-set Recall@10 relative +15%: **met** (+87% proxy).
- Author/title success >= 80%: **met** on the proxy set
  (14/14 any-hit).
- False identifications in evaluation: **0** (resolution
  refusals hold in tests; no case merged distinct authors,
  works or editions).
- Fixture attempts <= +20%: **not met** (+39% after the
  final-review plan clean-up: 38.2 vs baseline 27.4; +51%
  before it; +137% before routing). Reason recorded in
  docs/b6-multilingual-research.md; production wire requests
  remain hard-capped by the unchanged HTTP budget.

## Safety metrics

False author identifications: 0 (ambiguous surnames refused
in analysis, expansion and resolution). False premise cases
(F37/F38, H15/H16): the pipeline returns materials for the
corrected concepts without asserting the false premise;
admission is unchanged, so nothing about them can be
answered from discovery alone. Non-existent-material cases
return no relevant records by construction of the corpus;
live behaviour for such queries is "materials may exist,
premise not certified" - the materials note states this.
