# b10 performance evaluation

Date: 2026-11-28. Brief section 45. Measured on the
development VM (1.5 shared CPUs, ~6 GB RAM); medians of 30 runs
for local components (`eval/b10_perf.py`,
`eval/results-b10-perf.json`). These are this-machine numbers,
not guarantees.

| Component | Median |
|---|---|
| Question analysis | 0.03 ms |
| Discovery analysis | 2.16 ms |
| Expansion plan (standard) | 0.26 ms |
| Lexical fit + score (30 docs) | 1.62 ms |
| ResearchRanker (30 items) | 9.26 ms |
| ResearchQuestion structuring | 2.30 ms |
| ResearchClaim structuring | 1.29 ms |
| Claim–evidence assessment (per candidate) | 0.01 ms |
| Fact comparison (per pair set) | 0.002 ms |

Semantic model (separate, opt-in): load 2.77 s; encode ≈ 12 ms
per bibliographic record on CPU. Model load time is reported,
never hidden inside per-query numbers (section 45).

Service level (fixture transport, `b6_service_eval`): quick
mode mean 11.7 s per case / 12.6 HTTP requests; standard mode
mean 15.3 s / 22.1 HTTP requests (Stage 1 baseline 15.9 s /
22.9 — the adaptive stop and routing alignment reduced
attempts without raising the budget; the HttpBudget caps are
unchanged). Warm-cache rerun hits: 8 (standard). Fixture
timings exercise local code paths over a fake transport; they
are not live-network timings. Live timings depend on upstream
libraries (the live Kant run took ~109 s wall-clock including
slow upstream responses and the per-library deadlines).

Memory: the semantic model adds ~130 MB on disk and its ONNX
runtime footprint when explicitly enabled; the default process
(no model) is unchanged from b9.

---

## Final-review addendum (2026-11-28)

This document describes the b10 candidate as submitted in
PR #21 (head `dc8d794`). The external final review reproduced
defects in several of the areas covered here; the fixes,
re-measurements and corrected claims are recorded in
`docs/b10-final-review.md`, which supersedes this document
wherever the two disagree (notably: semantic search is now
wired into the real service path as an opt-in ranking mode;
`authority_verified` can no longer be reached from the local
lexicon alone; editions are candidates; independent-source
counting was replaced; the Docker CI job is fixture-mandatory
with the live smoke separated as an informational job).
