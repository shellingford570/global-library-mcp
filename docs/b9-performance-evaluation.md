# b9 — External MCP performance evaluation

Synthetic in-process measurements (`eval/b9_perf.py`,
results in `eval/results-b9-perf.json`) on the development VM
(1.5 shared CPUs, ~6 GB RAM). Indicative only — not a
production benchmark, and no load was placed on any real
library API (brief section 37).

## Configurations

| Measurement | Median ms | Min ms | Max ms |
|---|---|---|---|
| A: local research core (LibraryService.search, stub adapter) | 0.13 | 0.11 | 0.43 |
| B: external tools/list | 0.05 | 0.03 | 0.08 |
| B: external search (5 results) | 0.2 | 0.17 | 1.21 |
| B: external search, per-user cache hit | 0.14 | 0.14 | 0.2 |
| B: external fetch | 0.2 | 0.19 | 0.31 |
| C: external excerpt (synthetic allow path) | 0.27 | 0.19 | 0.53 |
| Component: token validation (HS256 test signer) | 0.1 | 0.08 | 0.25 |
| Component: rights decision | 0.01 | 0.01 | 0.03 |

Response sizes: search 4511 bytes,
fetch 1664 bytes, excerpt
1151 bytes — all far below the
256 KiB internal cap and the tunnel's 10 MiB envelope limit.

## Concurrent synthetic users (D)

| Users | Wall ms | Per-user ms |
|---|---|---|
| 1 users | 1.07 | 1.07 |
| 2 users | 1.88 | 0.94 |
| 5 users | 2.67 | 0.53 |
| 10 users | 4.68 | 0.47 |
| 20 users | 8.21 | 0.41 |

Concurrency is capped at 2 simultaneous operations per user
by the per-user semaphore; the figures above are tool-call
latencies against an in-process fake service, so they measure
the external layer's overhead, not upstream latency. Real
upstream searches remain bounded by the existing per-library
deadlines, the 90-second external tool deadline and the
tunnel's 120-second absolute deadline.
