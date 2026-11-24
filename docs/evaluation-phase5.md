# Phase 5 evaluation: semantic grounding, temporal verification, retrieval

Provider: MockProvider throughout (pipeline measurement, not LLM
prose quality). Real-LLM evaluation is prepared but not run — see
`eval/real-llm-prep.md`. All runs are live against the NDL APIs.

## Headline results (final code, run 3)

| Metric | Phase 4 (final) | Phase 5 run 3 — 70 questions | Phase 5 run 3 — holdout (32) |
|---|---|---|---|
| Insufficient handled correctly | 0.808 (21/26) | **1.000 (26/26)** | 0.667 (4/6) |
| — of which grounded corrections | n/a | 1 (q39) | 0 |
| False answers on insufficient | 5 | **0** | 2 (h22, h31) |
| Answerable success | 0.682 (30/44) | 0.591 (26/44) | 0.304 (7/23) |
| Citation resolution | 1.00 | 1.00 | 1.00 |
| Recall@3 / Recall@6 | — | 0.432 / 0.591 | 0.174 / 0.304 |
| MRR | — | 0.410 | 0.199 |
| Requests per question | 18.8 | 19.8 | 21.1 |
| Avg seconds per question | 7.18 | 6.63 | 7.07 |

Brief targets: insufficient ≥ 0.90 **met on the 70-question set**,
not met on the holdout; answerable ≥ 0.90 **not met on either
set**, and the 70-question answerable rate is *below* Phase 4
(0.591 vs 0.682). Both facts are reported as measured.

## Run history (why three runs)

- **Run 1** (semantics wired, no temporal anchoring in the gate):
  identical headline numbers to Phase 4 (0.808 / 0.682). Diagnosis
  on q49 showed the fetched pages of the 1934 subway history
  contain no quotable onset sentence — their support came from
  undated occurrence sentences.
- **Run 2** (+ retrospective anchoring: undated stance in a
  post-era publication no longer counts as era support;
  retrospective mentions_only pages demoted): insufficient handled
  1.000, false answers 0 — but answerable fell to 0.523. Live
  diagnosis (q07, 『逓信事業史』) found three general defects:
  the occurrence vocabulary missed the era's institutional verbs
  (開局・開通・架設・操業・点灯・創刊・施行…), stance was read
  per isolated sentence while period prose uses zero anaphora
  (topic named once, event stated in the next sentence), and
  "later developments mentioned" was misread as contradiction.
- **Run 3** (vocabulary widened, discourse units = concept
  sentence + following sentence, contradiction narrowed to
  negation / explicitly later-dated onset, dated-event questions
  out of premise scope): insufficient handled stays 1.000 on the
  main set, answerable recovers to 0.591, and q39 （明治の自動車
  レース） produces the first live grounded correction
  (`corrected_premise`, quoting the contradicting page).

All three runs' raw files are kept: `results-phase5-run1.json`,
`-run2.json`, `results-phase5.json` (run 3), and the holdout
equivalents.

## Holdout set

`eval/holdout.json` — 32 questions, labels frozen from historical
facts and committed (0bb504c) *before* any holdout run; labels
were never adjusted. It includes three `correction`-labelled
questions (h01 television/Meiji, h02 atomic power/Taisho, h32
air passenger transport/Meiji): all three ended in safe refusals
(`correction_safe_rate` 1.0) but no grounded correction
(`correction_success_rate` 0.0) — the contradicting sentences were
not on the fetched pages. The two remaining false answers:

- h22 （大正の電気冷蔵庫の普及）: a post-era appliance history's
  undated diffusion sentences, anchored by an era-name mention in
  a neighbouring sentence, passed as support. The discourse-unit
  window that fixed anaphora also inherits anchors across
  sentence boundaries — the known cost of that fix.
- h31 （明治の宇宙飛行）: a modern spaceflight book mentioning
  Meiji as background; same mechanism.

The dominant holdout failure is retrieval, not grounding:
18 of 32 questions ended `no_relevant_pages` in run 1 terms, and
Recall@6 is 0.304 — for most answerable holdout questions the
right document never produced a gate-passing page within budget.
Document selection, not answer generation, is the bottleneck
(the runner records `retrieval_failure_reason` per question to
keep the two apart).

## Metric definitions

- **Insufficient handled**: status `insufficient_evidence`,
  `answer_withheld`, or `corrected_premise` on an
  insufficient-labelled question. Phase 4's
  `insufficient_correct_rate` (plain refusals only) is still
  reported for comparability: 0.962 main / 0.667 holdout in run 3.
- **Answerable success**: status `answered` on an
  evidence-labelled question.
- **Recall@K / MRR**: over evidence-labelled questions, using the
  rank (in the merged, Stage-1-ordered candidate list) of the
  first document that produced a gate-passing evidence page;
  questions with no such document score 0. This measures the
  retrieval pipeline end to end, not the catalog alone.
- **Correction success/safe**: on correction-labelled questions,
  `corrected_premise` = success; plus `insufficient_evidence` =
  safe.

## Regression checks

- Unit/integration: 113 pytest passed (was 92 at Phase 4),
  including the corrected-premise service test and the temporal /
  semantics suites. Playwright: 7 specs passed (was 6).
- NDL search / OCR / IIIF: exercised by every evaluation run
  (citation resolution 1.00; image reachability 0.9 on sampled
  pages, same as Phase 4).
- Internet Archive: adapter-level check on the Phase 3 reference
  item (`hydroelectricdev00koesrich`, term "dam") returned the
  same 20 djvu matches (leaves 11, 14, 20, 33, …) as Phase 3 — no
  adapter regression. A full-pipeline English query against IA
  yields no evidence: the question analysis is Japanese-oriented,
  and several surfaced IA items lack djvu.xml upstream (404,
  reported as unverified with reasons). English-query support is
  a Phase 6 item, measured honestly by holdout h29/h30 (both
  unanswered).
- compare_documents, citation whitelist, MCP tools, rate
  limiting, cache: covered by the unchanged unit suites.
- Gallica (upstream 403) and Europeana (API key) unchanged, as
  scoped.

## Security audit

- Branch diff vs `feat/global-library-reliability-v4` scanned for
  credential patterns: no keys, tokens, or passwords (one false
  positive: a regex variable named `token` in temporal.py).
- `pip-audit -r requirements.lock.txt`: no known vulnerabilities
  in the locked runtime dependency set (the project package itself
  is skipped as not-on-PyPI). The optional sentence-transformers
  stack is not in the lock file and is not a runtime dependency.
- No model weights committed; no API keys in source or logs.
