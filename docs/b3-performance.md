# b3: Search performance and research-materials usability

Branch `feat/research-beta-performance-b3` (candidate; not a release).

## 1. Measurement first (Section 5)

`research_materials(limit=5)` was instrumented per stage, per
adapter method and per HTTP host (2026-11-25, this environment):

| Question | Total | Bibliographic search phase | Dominant cost |
|---|---|---|---|
| 明治時代の水力発電 | 208.9s | 169.2s (81%), 3 query variants | **www.loc.gov: 6 requests / 167.7s** |
| Darwin (evolution) | 141.1s | 109.9s (78%), 5 query variants | LoC 21.7s + IA in-document 26.6s |

Findings:

1. The bibliographic search phase dominates. Query variants run
   sequentially, each waiting for ALL libraries (`asyncio.gather`),
   so the slowest library gates every variant round. LoC took up to
   ~28s per request here and contributed nothing to a Japanese
   query, yet consumed 168s of a 209s run.
2. Second cost: Internet Archive in-document search (~30s) — each
   candidate downloads the full djvu.xml.
3. A single question issues ~50 actual HTTP requests, while the
   service-layer budget counted 25 "units" — the known limitation
   recorded since Phase 10, now addressed (Section 9 below).
4. The web server and the MCP server built a fresh client and
   service per request/call, so the search cache, page cache and
   the per-question circuit breaker never persisted across calls.

## 2. What changed

- **Per-library search deadline** (`service.search`,
  `GLM_SEARCH_DEADLINE_S`, default 10s): a slow library is cut off
  and reported as a partial failure instead of gating the round.
- **Cross-request circuit breaker**: 3 consecutive failures pause a
  library for 60s (in addition to the existing per-question one).
- **Variant early-stop (Standard mode)**: variant expansion stops
  once ≥8 in-document-capable candidates are pooled (the full
  question always runs; the stop is recorded in `stage_log`). Deep
  mode keeps the full sweep.
- **Real HTTP budget** (`http.HttpBudget` + `BudgetedTransport`):
  counts every wire request per operation (standard 80 / deep 200,
  per-host caps), caps response size (25MB), caps concurrency (8),
  and is reported back as `http_stats`. A fixed-fixture test proves
  the cap cannot be exceeded. `get_json` now honours Retry-After
  (capped at 5s) before its single retry; 403/429 are never
  bypassed.
- **Modes (Section 7)**: `research_materials(mode=...)` —
  `quick` (bibliographic only, no OCR fetching), `standard`,
  `deep`. The web UI offers the same three modes.
- **Shared service runtime**: the web server now runs one
  long-lived service on its own event-loop thread; the MCP server
  shares one client/service per process. Caches and the breaker
  now persist: bibliographic cache TTL 300s (rights/access status
  can change), page/OCR cache unchanged (FIFO 256).
- **Staged UI (Section 6)**: bibliographic search renders first,
  then the reader triggers the detailed investigation; the run
  shows processing / complete / partial / failed / cancelled
  states, a cancel button (AbortController; server-side work is
  cancelled with the request), and elapsed time + actual HTTP
  request count on completion.
- **Material states (Section 11)**: every material now carries
  `access_state` — bibliographic / OCR fetched / mapping confirmed
  / passage found / assessed as evidence — as five separate
  booleans. Unadmitted pages keep their landing and image URLs so
  the researcher can check them directly.
- **Rights (Section 12)**: new `docs/rights-guide.md` (per-licence
  guide; CC BY-NC-ND is not public domain; unknown rights are not
  shown as freely usable); Europeana limits re-verified against
  Europeana's own Knowledge Base (API key required since
  2025-05-28; no official numeric daily cap currently published).

## 3. Before / after (same 5 field-test topics, live, 2026-11-25)

| Topic | Before total | After: stage-1 search | After: Standard total | Materials | Admitted | HTTP requests |
|---|---|---|---|---|---|---|
| Evolution (Darwin) | 141–174s | 10.0s | 64.1s | 14 | 1 | 30 |
| 明治の水力発電 | 209–255s | 1.5s | 23.9s | 10 | 0 | 23 |
| 日本の鉄道史 | 77.7s | 10.0s | 45.4s | 14 | 0 | 33 |
| 哲学史 | 18.2s | 0.9s | 7.1s | 12 | 4 | 16 |
| 科学史 | 23.7s | 0.6s | 17.7s | 11 | 4 | 10 |

Notes:

- Stage-1 (bibliographic) results now arrive within the 10s
  per-library deadline on every topic (two topics hit exactly the
  deadline because LoC did not answer in time; it is reported as a
  partial error, not hidden). Gallica returns its longstanding
  upstream 403 from this network and is likewise reported.
- Totals improved roughly 3–10×. Remaining time is dominated by
  IA djvu.xml downloads and NDL page search, both now bounded by
  the HTTP budget (10–33 actual requests per question, vs ~50
  before, none exceeding the cap).
- Admitted counts vary between runs with upstream availability
  and the (now explicit) budgets; admission, citation and safety
  logic is unchanged. 明治の水力発電 admitted 0 both before and
  after (known recall limit).

## 4. Known limitations

- IA in-document search still downloads full djvu.xml files
  (tens of MB per question observed); a streaming/partial reader
  is future work.
- The search deadline is per library per variant round; a question
  with many variants can still take variants × deadline in the
  worst case (Standard's early-stop bounds this in practice).
- Cancellation in the web UI aborts the browser request; the
  server cancels the coroutine when the handler wait ends, but a
  disconnected client may leave work running until the current
  upstream call returns (bounded by the 30s client timeout).
