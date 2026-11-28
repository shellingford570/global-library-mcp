# b11 Evaluation (sections 55-73)

All measurements on the b11 branch, 2026-11-28, development VM.
Baselines are the b10 final-review numbers; the same
evaluators, dictionary and corpus were used throughout.

## Regression battery
- pytest: **704 tests, 0 failures, 0 errors, 0 skipped**
  (b10 baseline 656; +48 b11 tests).
- Playwright (local, fixture upstreams, CI-equivalent setup):
  search journeys **17 passed / 0 skipped**, workspace
  journeys **6 passed / 0 skipped**.
- External security evaluation: **164/164 passed**
  (`eval/b9_security_eval.py`).
- Real-path integration suite: included in the pytest run
  (tests/test_b9_integration.py), passing.
- MCP profiles: full 15 / research 14 / external 5 (unchanged,
  covered by the b4/b9 suites in the run).

## Search regression (section 55)
- Semantic proxy eval (35 cases, whole-corpus, MiniLM local):
  lexical Recall@10 **0.7286**, semantic **1.0000**, hybrid
  **0.8905** - identical to the b10 baseline.
- b8 service eval: Standard Recall@10 **0.7667** (baseline
  0.7667), cross-language discovery **0.7500** (baseline
  0.7500); Quick 0.4583 on the b8 set.
- b6 simulation (same evaluator/dictionary/corpus, config F):
  fixed Recall@10 **0.9167** (baseline 0.9167), challenge
  Recall@10 **1.0000** (baseline 1.0000).
- b6 service eval over fixed HTTP fixtures (10 cases): Quick
  Recall@10 **0.4667** (avg HTTP 12.6), Standard **0.8667**
  (avg HTTP 22.1) - identical to the b10 baselines. Quick was
  examined for improvement; no per-case tuning was done and
  the number is unchanged.
- b10 final bundle re-run: label recount unchanged (260 cases,
  source-supported 21, agent_assigned 239, human 0);
  ResearchRanker timings unchanged in kind (10 docs 1.4 s).

## Known divergence (documented, not rewritten)
`eval/b10_final_eval.py` challenge probes: **7/10** under b11
(10/10 at b10). The three changed probes (kw_vs_mw,
km_m_conversion, different_place) are compare_facts cases
whose inputs omit predicate/object identity fields; b11
section 10 REQUIRES insufficient_context when identity
conditions are missing, so the stricter b11 behaviour is the
intended one. Per section 15 the frozen b10 expectations were
NOT rewritten; the divergence is recorded here instead. The
b11 dataset's own comparison cases carry full identity fields.

## Scenarios (sections 57-65)
- A question->search->save->cite: b7/b8 Playwright journeys +
  pytest integration (passing).
- B claim->evidence: Stage 0/3 tests; assessments require
  registry tokens (forged references refused).
- C contradiction: compare/claim tests; NLI shadow records
  contradiction_candidate only.
- D multilingual: b8 eval cross-language 0.7500; synthesis
  concept-vs-claim separation test.
- E report: Stage 4 tests + Stage 5 HTTP journey.
- F import->downgrade->graph/report: Stage 6 test
  (imported_artefacts=1, trust imported_unverified).
- G real HTTP: tests/test_b11_stage5.py runs the research
  routes over real HTTP inside the workspace boundary
  (unit-test success is not what is reported here - the
  journey itself is the HTTP test).
- H rights change: Stage 6 test - a later rights observation
  changes the regenerated report's rights state and snapshot.
- I review package: Stage 6 test - synthetic agreement input
  computes metrics as code behaviour while the dataset still
  records every case not_reviewed; no human evaluation exists.

## Research-quality metrics (section 66)
All b11 quality numbers are PROXY metrics (agent-assigned
labels) unless stated: NLI proxy agreement 0.857 (14 cases,
synthetic backend - a harness measurement, not a model
measurement); claim structuring extraction states are reported
per field; human evaluation = 0 and inter-reviewer agreement
is UNMEASURED.

## Report quality (section 67)
Reference integrity is enforced by construction and tested:
reports list unresolvable references under
unresolved_references and count them; in the Stage 4/5/6
fixture projects the generated reports contained 0 ungrounded
evidence references (every rendered reference resolved to a
project document/citation). Reproducibility fields are present
in every generated report (tested).

## Security negatives (section 69)
Stage 0 negative suite (18 tests): forged artefact envelopes
(correct hash), cross-project copies, import/restore forgery,
forged evidence references (complete ref, unadmitted text with
correct hash, offset mismatch, revoked, expired, foreign
record) - all refused; promotions measure 0. External
security stays 164/164; external session constraints
re-checked (docs/b11-live-verification.md).

## Frozen conditions (sections 71-72)
Evidence admission conditions were not loosened anywhere in
b11; `research_question` remains experimental. Paid API calls
in b11 development: **0**.
