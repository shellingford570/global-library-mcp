# Phase 10 evaluation: extractive vs generative, beta posture

## Extractive mode, main 70-question set (live NDL)

Run 2026-11-24 with the Phase 10 defaults in force
(request budget Standard 25, no LLM configured):
`eval/results-phase10-main-extractive.json`

| metric | extractive (Phase 10) | generative MockProvider (Phase 8, unbounded) |
|---|---|---|
| answerable success | 0.591 (26/44) | 0.591 (26/44) |
| false answers | 0 | 0 |
| insufficient handled | 1.000 | 1.000 |
| claim supported rate | 0.992 | - |
| citation resolution | 1.000 | 1.000 |
| requests / question | 25.2 | 32.8 |
| seconds / question | 6.35 | 18.77 |

Reading: the extractive mode - verbatim quotations only,
no provider call at all - matches the mock generative
path's success rate exactly on this set, at lower request
cost. Its answers carry no paraphrase risk: a quote is
wrong only where the OCR is wrong, and the original image
is linked beside it. The binding constraint for BOTH modes
is upstream (43 of 70 questions ended at
insufficient_evidence - the evidence-admission layer), not
the answer layer. One corrected-premise answer (q39) was
produced by the shared correction path.

Caveat: the generative comparison number is the
deterministic MockProvider (which quotes OCR sentences),
not a real LLM. The real-LLM generative measurement
remains the grok-4.3 run (4/20 on its subset) plus the
planned follow-up in docs/phase10-experiment-plan.md,
which needs fresh approval.

## Verifier comparison (fixed evidence, offline)

See docs/phase10-experiment-plan.md: lexical precision
1.000 / recall 0.208 / false-support 0.000 / contradiction
detection 0.000 over eval/balanced-v1.json; NLI and hybrid
not_checked in this environment.

## Beta posture verification

- LLM blockade test passes (zero LLM calls under beta
  defaults) - tests/test_phase10_beta_security.py.
- Materials mode, search, OCR and comparison all run with
  no LLM configured (the extractive run above used the
  same no-LLM process configuration for retrieval).
