# Real-LLM evaluation: preparation (Phase 5-F)

Status: **prepared, not run.** No paid API has been used. Running a
real-LLM evaluation requires the operator's prior approval of a
specific provider, model, and budget (brief §10).

## What is already in place

- **Swappable provider**: `LibraryService.answer(..., provider=...)`
  accepts any object implementing the answer protocol;
  `OpenAICompatibleProvider` is the production path and
  `MockProvider` the deterministic evaluation path. The evaluation
  runner injects the provider, so a real-LLM run changes one line.
- **Citation safety is provider-independent**: citation keys are
  whitelist-validated at the provider layer and again at the
  service layer; claims are screened against the cited OCR in
  `claims.py` regardless of provider. A real LLM cannot smuggle
  citations or unsupported claims past these gates — that is what
  the mock runs already measure.
- **Call caps**: `eval/run_evaluation.py --max-calls N` stops
  starting new questions once N HTTP requests have been made, and
  records `skipped_cap` for the rest. Per-question request counts
  and timings are recorded in every results file.
- **Separation of results**: every results file records
  `"provider": "mock"`. A real-LLM run must write to a distinct
  file (e.g. `results-phase5-llm-<model>.json`) and must never be
  merged into the mock metrics.

## What a real-LLM run must add before it starts

1. **Token and cost accounting**: wrap the provider to record
   prompt/completion tokens per question (the API response's usage
   block) and abort the run when a pre-agreed cost ceiling is
   reached — the request cap alone does not bound token cost.
2. **A fixed question subset**: run the 70-question set and the
   holdout unchanged (same files, same labels) so mock and real
   results are comparable question-by-question.
3. **Answer-vs-evidence comparison**: for each answered question,
   keep the existing claim-screening output, and add a manual
   sample review (at least the corrected-premise and withheld
   cases) comparing the prose against the cited OCR pages.
4. **Reporting**: real-LLM numbers are reported separately from
   mock numbers, with model name/version, date, token totals, and
   cost stated. Mock results measure the pipeline; they are not a
   prediction of real-LLM prose quality.
