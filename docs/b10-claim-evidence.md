# b10 Stage 4 — structured claims and claim–evidence mapping

Date: 2026-11-28. Brief sections 23–27, 29–31.
Implementation: `src/global_library_mcp/research.py`.
Evaluation: `eval/b10_claims_eval.py` over the frozen b10
dataset (agent_assigned labels — proxy evaluation).

## What was built

- **ResearchQuestion** (section 23): structured view derived
  from the existing question/discovery analyses — intent
  classification (fact check, numeric check, edition
  comparison, chronology, …), entities, era range, author/work
  constraints, numerical constraints, expected evidence type,
  and explicit unresolved ambiguities (e.g. a surname matching
  several persons). It feeds nothing into admission.
- **ResearchClaim** (section 24): era (with boundary-aware
  ranges from the existing temporal layer), explicit years,
  first bound quantity with its original unit, explicit place
  names, lexicon entities, qualifiers. Fields the text does not
  contain stay empty; the predicate/object remain textual —
  structuring is not truth judgement.
- **Claim–evidence mapping** (section 25):
  `assess_claim_evidence` accepts only candidates the caller
  marks as gate-admitted; anything else is reported
  `not_checked` and never assessed. Signals: subject/entity,
  time (specific-year agreement; era range), place, exact
  quantity+unit, negation. Statuses are candidate-level
  (`supported_candidate`, `partially_supported`,
  `conflicting_candidate`, `contextual_only`,
  `insufficient_evidence`, `not_checked`); the frozen claim
  verification remains the only path to a final verdict.
  Refinements driven by the dev split, all general rules:
  a different year is a conflict candidate only for the same
  event predicate about the same subject (a later line opening
  or another edition is context, not contradiction); a passage
  anchored outside the claim's era that discusses the era is
  `contextual_only` (retrospectives do not support, section
  26); a negated claim met by an affirmative passage is a
  conflict candidate.
- **Cross-source comparison** (sections 28–29):
  `compare_facts` classifies pairs as consistent_candidate /
  differing_unit / differing_time / differing_scope /
  contradiction_candidate / insufficient_context, with unit
  aliases across languages (馬力 = horsepower), a year-as-value
  rule (a disputed opening year is a contradiction candidate,
  not a time difference), and definitional scope from
  parenthetical qualifiers. Document count and independent
  source count (grouped by work) are always reported
  separately. No path produces `contradiction_confirmed`.
- **Original↔translation correspondence** (section 31) is
  served by the Stage 2 work resolution (shared work id +
  title forms); page-number agreement is never used as
  correspondence evidence.
- **NLI** (section 32): not implemented. A second model would
  need separate approval; the rule-based mapping above is the
  shipped behaviour, and NLI is recorded as an
  additional-approval item in the final report.

## Evaluation (frozen b10 dataset)

| Split | structure | snippet mapping | contradiction | false support promotions |
|---|---|---|---|---|
| dev | 8/8 | 4/7 | 8/10 | **0** |
| fixed | 7/7 | 5/8 | 6/6 | **0** |
| holdout | 5/5 | 2/5 | 4/4 | **0** |

The snippet-mapping misses are concentrated in borderline
signal-strength cases (a claim whose only support signals are a
matching year and a related place name scores
partially_supported where the dataset expects
supported_candidate). The thresholds were deliberately NOT
loosened: section 25 forbids promotion on weak signals, and
the safety metric — false promotions to supported_candidate —
is zero on every split. Structure extraction and contradiction
classification are at or near ceiling on this small proxy set.
