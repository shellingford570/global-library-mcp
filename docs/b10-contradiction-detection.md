# b10 Stage 4 — contradiction candidate detection

Date: 2026-11-28. Brief section 28. Implementation:
`compare_facts` in `src/global_library_mcp/research.py`;
evaluation in `eval/b10_claims_eval.py` (see
`docs/b10-claim-evidence.md` for the full Stage 4 record).

Rule-based pair classification over extracted facts
(value, unit, year, scope, definition, concept):

- same value and unit → `consistent_candidate` (including
  cross-language unit aliases: 馬力 = horsepower = PS, and
  notation variants of the same concept);
- different values in different units → `differing_unit`
  (conversion may reconcile them; never a contradiction);
- same measurement anchored to different years →
  `differing_time` — unless the year IS the claimed value
  (unit 年), where disagreement is the contradiction
  candidate itself;
- different aggregation scope or definitional scope
  (parenthetical qualifiers such as 水力のみ vs 火力を含む) →
  `differing_scope`;
- no quantities and different concepts, or missing values →
  `insufficient_context`;
- otherwise, differing values under the same unit, time and
  scope → `contradiction_candidate`.

There is deliberately no `contradiction_confirmed` state:
semantic contradiction requires independent verification the
rule layer does not perform (section 28). OCR-suspect pairs
(digit-level differences) surface as contradiction candidates
for human review, with OCR error as one of the possible causes
the researcher weighs.

Results on the frozen b10 contradiction set (20 pairs across
splits): dev 8/10, fixed 6/6, holdout 4/4 — the two dev misses
are recorded in `eval/results-b10-claims-dev.json`.
