# Phase 6-A: failure diagnosis (Phase 5 run-3 code, live re-run)

Method: every evidence-labelled question in the Phase 5 run-3
results (70-question set + holdout) whose status was not
`answered` — 34 questions — was re-run through `collect_evidence`
and classified by the stage at which it died. Full per-question
records (candidate counts, topical ranks, page ids, verdict
reasons) are in `eval/diagnosis-phase6.json`; the classifier is
`eval/diagnose_failures.py`.

## Stage distribution

| Stage | Count | Meaning |
|---|---|---|
| S4 gate_reject | **15** | Topical documents fetched, pages pass OCR quality, but the relevance gate screens every page out |
| S1 candidate_miss | **10** | No candidate title carries a core concept (pool too small / title vocabulary mismatch) |
| S2 budget_miss | **6** | A topical candidate sits at rank 7–10; the document budget stopped at 6 (or 9) |
| S5 semantic_reject | **3** | Relevant pages demoted by the Phase 5 semantic layer (q06, q70, h08) |
| S0 / S3 / S6 | 0 | No question died at discovery, OCR quality, or generation in this sample |

The headline: **the largest single cause is not retrieval but
the per-page relevance gate (S4)**, followed by candidate-pool
coverage (S1) and budget depth (S2). "Search failure" is three
different problems.

## S4 sub-causes (from recorded gate reasons)

1. **Pseudo-concepts in the family fraction.** The question
   analysis promotes generic or modifier nouns to core concepts —
   対策 (q19), めぐる議論 (q21), 流行した原因 (q63), 横浜開港後
   (h09), 神戸 as a place modifier (q23), and even the debris
   fragment よう (q13). Pages that cover the real topic miss
   these, the matched fraction stays under the anchor rule, and
   everything caps at partially_relevant.
2. **Compound / old-form mismatches.** 横浜開港 (q05, q54) is
   split across sentences or written 橫濱； 写真術 (h26) appears
   as 寫眞 in period text — the variant table lacks 寫→写 and
   眞→真； 活動写真 (h16) is also 映画 in later sources.
3. **Coverage split across pages.** Multi-concept questions
   (q10 紡績業+機械化, q54 横浜開港+貿易, q58 富岡製糸場+製糸業,
   h24 自転車+輸入+国産化) have pages that each cover part of
   the question; no single page reaches the fraction, although
   the *document* covers the question.

## Consequences for Phase 6 design

- 6-B: enlarge and diversify the candidate pool (all query
  variants, query-multiplicity ranking, generic-title penalty) —
  targets S1; fix concept extraction (generic nouns, place
  demotion, 寫/眞 folding) — targets S4.1/S4.2.
- 6-C: staged fetching (more documents, shallow first) —
  targets S2 and the deeper half of S1.
- 6-D: page selection by hit multiplicity and page kind, plus
  **document-level union promotion**: when one document's pages
  jointly cover all concept families and the candidate page
  itself carries the anchor concept, promote it — targets S4.3
  without weakening per-page standards for single pages.
- 6-F: re-check the S5 three (q06, q70, h08) after the gate
  changes; the semantic layer itself is not loosened.
