# Phase 5 baseline and failure classification (5-A, 2026-11-23)

Baseline = Phase 4 final live run (NDL, MockProvider, 70 questions),
preserved verbatim as `eval/results-phase4-baseline-for-phase5.json`
(identical to `eval/results-phase4.json` at branch point 0aae58a).

| Metric | Phase 4 final |
|---|---|
| Insufficient-evidence correctness | 0.808 (21/26) |
| Answerable success rate | 0.682 (30/44) |
| Citation resolution | 1.00 |
| Requests | 1,318 (18.8/question) |
| Avg seconds/question | 7.18 |
| pytest at branch point | 92 passed |

## False answers (5) — one class

**S1 · Retrospective mention.** The adopted page mentions both the
concept and the asked era, but the era relation is background,
negation, or planning — not occurrence/diffusion in that era. A
lexical gate cannot separate "mentioned" from "covered".

| ID | Question | Adopted source character |
|---|---|---|
| q31 | テレビ放送の開始（大正） | broadcasting history, era as background |
| q32 | ラジオ放送の影響（明治） | broadcasting history, era as background |
| q39 | 自動車レースの優勝者（明治） | motoring history, era as background |
| q49 | 地下鉄の建設（明治） | 『東京地下鉄道史』(1934), Meiji-era precursors |
| q52 | 電気洗濯機の普及（大正） | 『すぐまにあふ電気学』(1947), appliance coverage |

Phase 5 target: 5-B semantic relation + 5-C temporal-phase
classification (existence / planning / introduction / diffusion,
negation and retrospective cues), and 5-E `corrected_premise`
answers when a page *contradicts* the premise with grounding.

## False refusals (14) — two classes, split by related-page data

**R2 · Gate-side (8).** Related pages reached `partially_relevant`
but were never promoted: q10 紡績， q13 発電水力調査， q19 コレラ対策，
q21 脚気議論， q54 横浜開港と貿易， q66 蒸気機関と工場， q23 神戸居留地，
q58 富岡製糸場. The pages matched part of the question; the missing
part may be genuinely absent from the sampled pages or only
lexically invisible. Phase 5 target: 5-B semantic assessment as a
second opinion on partially relevant pages (promotion only on
positive semantic support, never on model absence).

**R1 · Retrieval-side (6).** All 8 related pages screened
`irrelevant`: q03 日露戦争， q05 横浜開港， q24 地震記録， q62 水力発電の
比較， q63 脚気と軍隊， q67 コレラ（明治）. Either the right documents
never entered the document budget, or concept matching failed on
the tried pages. Phase 5 target: 5-D two-stage ranking, dynamic
budget, dedupe, and retrieval metrics (Recall@K / MRR over the
candidate order, defined in the Phase 5 evaluation section).

## What Phase 5 must not do

- No per-question exceptions for q31/q32/q39/q49/q52; temporal rules
  must be general.
- No score tuning against the holdout set (5-F); its labels are
  frozen before the final run.
- Semantic model output is screening evidence, never proof of
  truth; when the model is unavailable the pipeline must say so
  (`not_checked`) instead of treating pages as supported.
