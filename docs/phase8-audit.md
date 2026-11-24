# Phase 8-A — architecture audit and baseline

Audited at Phase 7 HEAD `cb0dd97`. Module map (actual layout):

| File | Lines | Role today |
|---|---|---|
| service.py | 972 | Everything: search merge/ranking, staged fetching, page gating, `admission_decision`, union promotion, answer flow, compare_documents |
| question.py | 367 | Query analysis (concepts, era, intent, requirements) |
| semantics.py | 383 | Rule checker + embedding signal + factory |
| relevance.py | 175 | Lexical family-fraction gate |
| temporal.py | 91 | Sentence era anchors, onset detection |
| numeric.py | 179 | Quantity extraction/binding (Phase 7-C) |
| claims.py | 163 | Claim screening (overlap, dates, numeric binding) |
| evidence.py | 169 | OCR quality, hit terms, page kinds |
| models.py | 108 | SearchResult / Evidence dataclasses |
| answer.py | 153 | Answer composition helpers |
| eval/run_evaluation.py | — | Live evaluation runner (MockProvider) |

## The conflation the audit confirms

One boolean, `Evidence.verified`, currently carries three
different facts: (1) the page's identity matches the catalog
record and its OCR passed the quality gate; (2) the page is
topically relevant; (3) the page may ground an answer. The
Phase 7 `admission_decision` unified *who may ground an
answer*, but its own paths are of two different kinds and are
not labelled as such:

**Discovery-side conditions** (may a candidate be fetched,
listed, used to deepen a search): candidate pool membership,
series dedupe, ranking, wave triggers, the related-pages list,
research-mode display. These need no truth standard.

**Certification-side conditions** (may this page ground a
factual answer): the era-anchored assertion rule, promotion
kind restrictions, union assertion requirement, claim
screening, numeric binding.

Two certification paths are weaker than the headline rule and
must be labelled honestly rather than silently trusted:

1. `uncertain`/`not_checked` + narrative kind admits a page
   whose stance was *never assessed* (dated-event and general
   demands). The page is a relevant candidate with an
   unassessed stance — not assessed evidence.
2. Era-free questions admit on lexical relevance alone. Fine
   for discovery; for answers, the claim screen is the only
   semantic check that runs.

`_union_promote` mixes both kinds: coverage (discovery) plus an
assertion requirement (certification) — Phase 7 separated them
in logic; Phase 8 separates them in the data model.

## Baseline (Phase 7, live NDL, MockProvider)

70q: answerable 0.591, false answers 0, insufficient handled
1.000, 32.8 requests/question (p90 65, max 85). Holdout:
0.304 / 2 / 0.667. Newset: 0.278 / 0 / 1.000. Newset2 (frozen):
0.300 / 0 / 1.000, Recall A 0.667, Recall B 0.300.

## Phase 8 design response

- 8-B: an explicit evidence-state record per page (discovered /
  accessible / source_verified / relevant_candidate /
  supporting_passage / assessed_evidence / rejected_for_answer,
  each with reasons), replacing the single flag's *meaning*
  while keeping the field for compatibility. A per-stage log
  records where each question's pipeline stopped and why.
- 8-C: passages become the unit of assessment and citation.
- 8-D: research-materials mode reuses the same pipeline output;
  candidates are displayed *as candidates*, with the reason
  each was not admitted.
- 8-E: checkers stay behind the SemanticChecker interface; an
  NLI checker joins as a hypothesis-based signal that can
  never auto-approve an answer.
- 8-I: a per-question request budget with honest
  "not confirmed within the configured budget" wording.
