# b10 evaluation summary

Date: 2026-11-28. All figures name their corpus, denominator
and evidence kind. Labels are agent-assigned or
bibliographic-source-supported proxy labels throughout — no
independent human evaluation exists yet (the b10 dataset ships
`eval/b10-review.csv` for future human review; 0 of 260 labels
are independent_human_verified).

## Headline results against section-43 targets

| Target | Result | Kind |
|---|---|---|
| b6 fixed F Recall@10 ≥ 0.9097 | **0.9167** | simulation, 36 relevant-bearing cases |
| b6 challenge F Recall@10 ≥ 0.9167 | **1.0000** | simulation, 18 cases |
| b8 Standard Recall@10 ≥ 0.7500 | **0.7667** (policy A) | simulation |
| b8 cross-language ≥ 0.6667 | **0.7500** | simulation |
| Kant original in live Top 10 | **#1 (fr translation, IA) and #10 (de original, DDB)** | live, single run 2026-11-28 |
| Same-name false confirmations | **0** | authority eval, all splits |
| Original vs secondary misidentification | **0** false verifications | authority eval |
| Edition false merges | **0** (unknown years rejected) | authority eval + tests |
| Wrong document/page identity certifications | **0** (Stage 0 identity states) | pytest |
| Rights-bypassing saves/transfers | **0** | pytest + security eval |
| Paid API calls | **0** | — |

Service-fixture evaluation (real LibraryService over fixture
HTTP): Quick Recall@10 0.4667 (Stage 1 baseline 0.5000 — one
record in one case, F08, moved out of the quick-mode top 10
after the Stage 2 lexicon growth changed variant composition;
disclosed, not tuned away), Standard Recall@10 **0.8667**
(baseline 0.8333), mean HTTP requests 22.1 (baseline 22.9).

## Ablation (section 44)

| Element | Before → after | Evidence |
|---|---|---|
| Multilingual allocation | diagonal 0.8819 → legacy **0.9167** fixed; challenge 0.8611 → **0.9167** (Stage 1), then 1.0000 after the routing fix | allocation compare |
| Simulation routing (plan language) | fixed 0.8819 → 0.9167; attempts ~40 → 33.4 | Stage 3 diagnosis |
| Historical notation | retained from b6; Wasserkraft label added (F19 retrieval) | lexicon |
| Author authority (resolver) | surname-only false confirmations: possible in principle → **0** measured; ambiguity surfaced instead | authority eval |
| Work/edition authority | edition false merges 0; A/B and 1st/6th kept distinct | authority eval |
| Lexical search | whole-corpus R@10 0.7286 (fixed) | semantic eval |
| Semantic search | whole-corpus R@10 **1.0000** (fixed), 0.9667 (holdout) | semantic eval |
| Hybrid (RRF) | R@10 0.8905 fixed — below semantic alone; MRR better on dev/holdout | semantic eval |
| ResearchRanker | nDCG up on fixed/challenge, Recall@5 and holdout MRR down → **not adopted as default** (opt-in) | ranking compare |
| Adaptive planning | standard-mode attempts 22.9 → 22.1 mean on fixture eval; recall up (0.8333 → 0.8667, jointly with routing/lexicon fixes) | service eval |

## Research quality (section 42)

From the Stage 4 evaluation (frozen b10 dataset): structure
extraction 20/20 across splits; contradiction classification
18/20; snippet mapping 11/20 with **0 false promotions** to
supported_candidate — the misses are under-promotions
(partially_supported where the proxy label expects
supported_candidate), the safe direction under section 25.
Temporal errors, numeric-binding errors and page-identity
errors in the frozen pipeline: unchanged from b9 (the frozen
gates were not modified; their suites are part of the 628
passing pytest tests).

## Regression state

pytest **628 passed / 0 skipped** (b9 baseline 570 + 58 new);
Playwright search 17/17; workspace journeys 6/6; b9 synthetic
security evaluation **164/164** re-run at the b10 head; real
MCP integration suite passes inside pytest; stdio smoke: full
profile 15 tools, research profile 14 tools (external profile
is HTTP-only, 5 tools, covered by the integration suite).

## CI note (2026-11-28, final head)

GitHub Actions on the b10 branch: **test, workspace,
workspace-live, external-mcp and external-security all pass.**
The docker-playwright job's Playwright suite passes (17/17
in-job, including against the Docker image), but its appended
live smoke step fails at the live NDL page request
(`/api/page?library=ndl&id=974405_2` → 502 from the web layer).
Root cause, verified from two independent networks: NDL's page
API (`lab.ndl.go.jp/dl/api/page/...`) returns **500** today,
while its search and IIIF manifest endpoints answer normally;
the identical smoke passed on the b9 master run the day
before. This is an upstream availability condition — exactly
the dependency brief section 48 says mandatory CI should not
have — not a b10 regression (the page code path is unchanged
except the Stage 0 library-binding context). The smoke script
was NOT modified to hide the failure; whether to make that
live step informational is left as a decision for the
maintainer, recorded here and on PR #21.
