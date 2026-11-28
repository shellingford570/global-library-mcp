# b11 Performance Evaluation (section 68)

Measured on the development VM (1.5 shared CPUs, ~6 GB RAM),
2026-11-28. Unmeasured items are stated as such, never filled
with estimates.

## Evidence Graph build (eval/b11_graph_scale.py)
| Documents | Nodes | Edges | Build time |
|---|---|---|---|
| 100 | 101 | 100 | 0.004 s |
| 1,000 | 1,001 | 1,000 | 0.042 s |
| 10,000 | 2,000 (cap; 8,001 omitted) | 1,999 | 0.498 s |

## Semantic backend resource gate (Stage 0)
Concurrency cap 2 / queue 8 verified by test (6 concurrent
calls, observed peak 2). Process RSS is measurable via
`semantic_local.process_rss_bytes()`; a long-run memory profile
of the real MiniLM backend under the b11 harness was NOT run
in b11 (the model directory is unchanged from b10) - stated
as unmeasured rather than estimated.

## Existing baselines (re-measured in Stage 6)
pytest wall time, Playwright durations, the b9 performance
evaluation and the ResearchRanker timings from the b10 final
bundle (10 docs 1.4 s / 30 docs 3.37 s / 50 docs 5.47 s,
unchanged code path) are recorded in docs/b11-evaluation.md.

## Not measured in b11
- Real NLI model latency/memory (no model downloaded).
- Zotero import time (no application).
- Live-upstream end-to-end research journeys beyond the
  informational smoke (NDL page API still failing upstream).
