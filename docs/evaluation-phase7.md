# Phase 7 evaluation — evidence-promotion safety

All runs live against NDL with the MockProvider, same conditions
as Phases 4–6. Files: `eval/results-phase7.json` (70 questions),
`eval/results-phase7-holdout.json`, `eval/results-phase7-newset.json`
(Phase 6's independent set), `eval/results-phase7-newset2.json`
(Phase 7's independent set, frozen in commit dcc5298 before any
run), `eval/record-recall-phase7.json` (Recall A).

## Headline numbers

| Metric | Phase 6 main | **Phase 7 main** | P6 holdout | **P7 holdout** | P6 newset | **P7 newset** | **P7 newset2** |
|---|---|---|---|---|---|---|---|
| Answerable success | 0.841 | **0.591** (26/44) | 0.652 | **0.304** (7/23) | 0.667 | **0.278** (5/18) | **0.300** (3/10) |
| Insufficient handled | 0.846 | **1.000** | 0.333 | **0.667** | 1.000 | **1.000** | **1.000** |
| False answers | 4 | **0** | 4 | **2** | 0 | **0** | **0** |
| Corrections (live) | 1 | 1 (q39) | 0 | 1 (h13) | 0 | 0 | 0 |
| Citation resolution | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Requests / question | 29.1 | 32.8 | 45.8 | 53.9 | 49.5 | 55.1 | 26.6 |
| Seconds / question (p50 / p90 / max) | — | 8.9 / 21.6 / 37.8 | — | — | — | — | — |

Recall, split as the brief requires (newset2, the only set with
frozen ground-truth records):

- **Recall A** (the recorded-correct *record* reaches the ranked
  pool): **0.667** at @3/@6/@10/@30 (4 of 6 verified records,
  all ranked 1–2 when reached). The two missed records are
  indexed under head nouns （郵便） that the term extractor does
  not split out of compounds （郵便制度）. A concept-variant
  query expansion was implemented, measured (no gain on this
  set), and reverted — not kept on faith.
- **Recall B** (a verified OCR page is actually obtained):
  0.300 on newset2 (the answerable success rate; every answered
  question is backed by verified pages by construction). The
  title-based proxy of earlier phases is retired.

## The tradeoff, stated plainly

Phase 7's first goal is met on three of four sets and on the
main set completely: **false answers 4 → 0, insufficient
handled 0.846 → 1.000**, with the q39 correction intact. The
eight Phase 6 fixture pages are all refused admission in unit
tests.

The cost is exactly the one the brief anticipated: answerable
success fell back to Phase 5 levels on every set (main
0.841 → 0.591; holdout 0.652 → 0.304; newset 0.667 → 0.278).
The admission rule now requires, for era-bound questions, an
*anchored assertion*; the rule checker is conservative on
genuine period prose (descriptive text without occurrence cues
reads as mentions_only), many NDL records carry no publication
year (so contemporaneity cannot rescue them), and Phase 6's
retrieval gains mostly fed the promotion/mention paths that
Phase 7 deliberately closed. Per the brief's instruction, the
tradeoff is reported as unresolved with safety prioritised —
not tuned away per question.

Two qualifications, also measured:

- **Holdout still has 2 false answers (h05, h22)** — via pages
  *outside* the fixture set: the live pipeline found other pages
  of other books with the same weaknesses. The mechanisms are
  narrowed, not eliminated; a checker that cannot bind stance
  to the asked event in unknown prose remains the root limit.
- **API load did not fall** (main 29.1 → 32.8 requests/question)
  despite the search cache and variant dedupe: refused
  questions now exhaust all three fetch waves instead of
  stopping at an early (wrong) success. The honest conclusion
  is that early termination for hopeless questions — not
  caching — is the load lever that matters, and it is in
  tension with recall. Distribution (main): requests p50 28,
  p90 65, max 85; seconds p50 8.9, p90 21.6, max 37.8.

## What the safety work changed (7-A…7-E, 7-G)

- One `admission_decision` for all paths: era answers need an
  anchored checker assertion (in-era textual anchor in a
  counted stance unit, or a contemporary source);
  mentions_only/insufficient never ground era answers;
  promotions require narrative page kinds; unions require an
  asserting member and the era condition on each promoted page
  itself. Every admitted page carries a structured promotion
  record (path + the §4.3 checks) into the answer payload.
- Checker: `anchored_support` in the verdict; establishment
  cues （設置され/に始まり）; unsegmented listing blobs (>300
  chars) yield no stance units; demonym modifiers （日本人による)
  no longer bind stance units; the による glue is stripped
  from concepts.
- Numeric demands: quantities are values across notations
  （二十三 == 23), and a numeric claim is supported only when
  the value occurs *bound* to the asked target; table-only
  values are reported unverified. The numeric insufficient
  case in newset2 （明治元年の自動車登録台数） was correctly
  withheld, as was q40.
- Page kinds: index / colophon / admin_list / title_page /
  damaged added, with a usage policy (bibliographic questions
  may use title/colophon pages; structure questions front
  matter; factual era questions get no bypass). Corrections
  rest on narrative pages only.
- NLI remains a candidate behind the SemanticChecker
  interface, deliberately not adopted: no freely reproducible
  model could be verified in this environment (weights
  download fails through the proxy, as with embeddings), and
  the brief puts reproducible rule fixes first.

## Regression & quality gates

- pytest: full suite passed (incl. the 8 fixture-prevention
  tests, admission positives for contemporary and retrospective
  anchored sources, numeric binding, page-kind policy).
- Playwright: 7 passed; e2e smoke passed.
- Docker: not installed in this environment; CI builds it.
