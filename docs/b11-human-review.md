# b11 Human Review (sections 20-22)

## Package
`eval/b11_review.py` generates, from `eval/b11-cases.json`:
- `eval/b11-review/b11-review.csv` - blind review sheet
  (case material only; NO expected labels, NO provenance).
- `eval/b11-review/b11-review.html` - standalone local-only
  review page (no network calls, no labels embedded) exporting
  filled judgements as JSON.

Judgement options: correct / partially_correct / incorrect /
insufficient_evidence / cannot_judge / out_of_scope. Blank
judgements are never counted as reviewed.

## Agreement metrics
`eval/b11_agreement.py` computes percent agreement, Cohen's
kappa (two reviewers) and Krippendorff's alpha (nominal) from
filled review files. With fewer than two reviewers or no
overlapping judged cases it returns `unmeasured` with a reason.

## Status at b11 submission
**No human evaluation exists.** No reviewer was recruited (the
brief forbids unapproved recruitment and any fabrication of
human evaluation). Agreement metrics are therefore **unmeasured**.
Synthetic inputs used in unit tests are test fixtures, never
reported as human evaluation.
