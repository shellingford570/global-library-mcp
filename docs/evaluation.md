# Answer-quality evaluation

Evaluation harness: `eval/run_evaluation.py` over `eval/questions.json`
(30 questions: Japanese history, history of science/technology,
hydroelectric/electrical engineering, history of medicine,
geography/culture, and deliberately unanswerable questions).
Raw results: `eval/results-phase3.json`.

## What is measured — and what is not

The default run uses the deterministic **MockProvider**. It measures the
*pipeline* (discovery, OCR capture, citation resolution, claim-grounding
screening, insufficient-evidence behaviour, cost) — **not** the prose
quality of a real LLM. Mock claims quote OCR sentences verbatim, so a
100% claim-supported rate is expected by construction and proves only
that the checker accepts genuinely grounded text. Real-LLM answer
quality requires an operator-approved API key and has **not** been
measured yet.

## Live run, 2026-11-22 (NDL, mock provider)

| Metric | Result |
|---|---|
| Questions | 30 |
| Discovery rate (expected-evidence questions with ≥1 verified page) | **1.00** (25/25) |
| OCR capture rate (verified / attempted pages) | 0.94 |
| Original-image reachability (10 sampled evidence pages, full IIIF verify) | 1.00 |
| Citation resolution rate | 1.00 |
| Claims screened | 87, all `supported` (see caveat above) |
| Insufficient-evidence correctness (5 unanswerable questions) | **0.20** (1/5) |
| Average time per question | 6.5 s |
| Total external API requests | 444 |

## Findings

1. **Grounding holds; topical relevance is the weak point.** Four of the
   five "unanswerable" questions (smartphones in the Meiji era, the
   history of the Internet, quantum computing, the exact population of
   Yokohama village in 1853) still produced answers, because term
   extraction falls back to generic terms (通信, 歴史, 原理, 人口) that
   match loosely related period documents. The answers were grounded in
   real pages — citations resolved and claims were lexically supported —
   but the pages do not actually answer the question. A citation being
   real is not the same as an answer being right.
2. **Run-to-run variance is material.** A duplicate run on the same day
   scored discovery 0.84 and insufficient-correctness 0.6 with 620
   requests: live catalog results and term fallbacks fluctuate, so
   single-run numbers should be read as samples, not constants.
3. **OCR misrecognition propagates into evidence excerpts** (e.g. mixed
   old/new character forms, broken tokens in Meiji-era print). The
   quality gate filters empty/broken pages, not subtle misreadings;
   claims screening is lexical, so a misread token can pass. The
   original image link is therefore kept on every citation.

## Improvement backlog (in order)

1. Relevance gate: require the question's most specific term(s) to
   appear in a page's OCR before the page can ground an answer, and
   expose a per-evidence relevance signal next to the grounding status.
2. Real-LLM evaluation with an approved key, scoring claim support on
   paraphrased (not quoted) claims.
3. Era-mismatch checks: compare the question's era tokens with the
   document's publication era and flag answers that bridge them silently.

## Unit-level coverage of the failure cases

The brief's failure cases are covered deterministically in tests:
no matching documents, page-id mismatch, missing OCR, low-quality OCR
(`tests/test_evidence.py`, `tests/test_verify.py`); claims with no
citation, unrelated claims, unverified date tokens, provider-flagged
conflicts (`tests/test_claims.py`); invented citation keys withheld at
the service layer (`tests/test_research.py`).
