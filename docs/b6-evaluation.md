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

## Ablation (fixed set, 40 cases / 36 with relevant records)

| Config | Recall@5 | Recall@10 | Recall@20 | Prec@5 | MRR | nDCG@10 | Cross-lang | Attempts |
|---|---|---|---|---|---|---|---|---|
| A b5 baseline | 0.486 | 0.486 | 0.500 | 0.178 | 0.701 | 0.508 | 0.028 | 27.4 |
| B +historical | 0.544 | 0.544 | 0.558 | 0.206 | 0.785 | 0.571 | 0.056 | 31.2 |
| C +authors | 0.748 | 0.764 | 0.778 | 0.306 | 0.808 | 0.724 | 0.389 | 40.0 |
| D +titles | 0.750 | 0.764 | 0.778 | 0.306 | 0.826 | 0.737 | 0.389 | 46.4 |
| E +concepts | 0.938 | 0.944 | 0.944 | 0.400 | 0.877 | 0.859 | 0.611 | 64.8 |
| F +routing (shipped) | 0.896 | 0.910 | 0.910 | 0.372 | 0.866 | 0.829 | 0.611 | 41.4 |
| G +explanations | = F | = F | = F | = F | = F | = F | = F | = F |
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
- Ranking replacement (the original G) lowered MRR on all
  three datasets (e.g. dev 0.926 -> 0.808 in the replacement
  experiment) and was NOT shipped as the default; G in the
  shipped pipeline is F + explanation attachment.
- Grouping (H) is presentational: it changes no ranked
  metric. Its correctness is covered by resolution tests
  (0 false merges: author-mismatch and shared-surname cases
  refuse).

## Tag-based success (fixed set, config F vs A)

- Author / original-title / translated-title cases (14):
  any-hit 14/14 (A: 13/14), full recall 14/14 (A: 3/14).
- Historical-script cases (5): any-hit 5/5 (A: 4/5), full
  recall 3/5 (A: 3/5) - partial recall remains where the
  corpus holds the material under a different concept.
- Cross-language tagged cases (8): any-hit 8/8 (A: 2/8),
  full recall 5/8 (A: 0/8).

## Provisional targets (section 28) - assessment

- Fixed-set Recall@10 relative +15%: **met** (+87% proxy).
- Author/title success >= 80%: **met** on the proxy set
  (14/14 any-hit).
- False identifications in evaluation: **0** (resolution
  refusals hold in tests; no case merged distinct authors,
  works or editions).
- Fixture attempts <= +20%: **not met** (+51% after routing;
  +137% before). Reason recorded in
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
