# Phase 10-E / 10-G Audit

Scope: read-only analysis. Sources: `eval/results-phase9-llm-grok-4.3.json`,
`eval/run_evaluation.py`, `eval/run_llm_via_connector.py`,
`src/global_library_mcp/llm_budget.py`, `src/global_library_mcp/answer.py`,
`src/global_library_mcp/claims.py`, `src/global_library_mcp/service.py`.
Branch at time of audit: `feat/global-library-research-beta-v10` @ `c9574a2`.
No paid API was called for this audit.

---

# Part 1 — Phase 10-E: Audit of the first real-LLM run (grok-4.3, 20 questions)

## 1.1 What the saved file actually contains

Top-level keys: `dataset_version`, `run_at`, `metrics`, `llm_usage`, `records`.

Per-record keys (union over all 20 records):
`id, category, question, expect, llm_usage, status, evidence, unverified,
citations, related, related_statuses, reason, claims, citations_resolve,
search_errors, first_evidence_rank, retrieval_failure_reason,
premise_contradictions, correction_quotes, seconds, requests`, plus
`image_check` on 11 records.

Critical limitations of the saved data:

- **`claims` contains only `{support, overlap}` per claim** — no claim text,
  no per-claim citations, no passage IDs, no `support_detail` reason string.
  (`eval/run_evaluation.py` line 133 deliberately reduces each claim to
  those two fields.)
- **`evidence` is an integer count**, not the evidence records. The evidence
  excerpts actually sent to the model (the `compact_evidence` payload) were
  not saved in any form — no text, no passage list, no hash.
- **No answer text** is saved for any record, answered or withheld.
- **`citations` is the published citation list after pipeline processing**,
  not the model's raw citation list. Withheld records show `citations: []`
  because the service clears them; what the model originally cited is lost.
- **No `llm_called` flag is saved.** Whether the provider was invoked must
  be inferred from `status`/`reason`/`llm_usage`, which is ambiguous for
  q16 (see below).
- Per-record `llm_usage` is only `{prompt_tokens, completion_tokens}` when
  present. No `total_tokens`, no reasoning-token detail, no per-record cost.
- All 20 questions have `expect: "evidence"`. The subset contains **zero**
  insufficient-labelled and zero correction-labelled questions, so the
  false-answer rate is unmeasurable from this run (the file's
  `false_answer_rate: 0.0` is vacuous, computed over an empty set).

## 1.2 Headline numbers (from the file)

| Item | Value |
|---|---|
| Records | 20 (all `expect: evidence`) |
| Status: `insufficient_evidence` | 8 (q01, q03, q06, q07, q09, q11, q14, q20) |
| Status: `answer_withheld` | 7 (q05, q08, q10, q12, q15, q17, q19) |
| Status: `answered` | 4 (q02, q04, q13, q18) |
| Status: `llm_unavailable` | 1 (q16) |
| Status: `answered_partial` | 0 (`partial_answer_rate: 0.0`) |
| Claims total | 19 — supported 5, uncertain 4, unsupported 10, conflicting 0, not_checked 0 |
| `claim_supported_rate` | 0.263 (5/19) |
| `answerable_success_rate` | 0.200 (4/20) — a status rate, **not** human-verified correctness |
| `false_refusal_rate` | 0.75 (15/20 evidence questions not answered) |
| `retrieval_failure_counts.no_relevant_pages` | 8 |
| Total HTTP requests (NDL etc.) | 499 (24.9/question), avg 18.71 s/question |
| Ledger summary | calls 20, input 144,374 tok, output 13,151 tok, spent **$0.213345** of $1.00 cap, usage_reported 11, usage_estimated 9 |
| Reported-usage portion | 11 records, 36,374 prompt + 2,351 completion tokens → **$0.051345** at table prices |
| Estimated portion | 9 × worst case (12,000 in / 1,200 out @ $1.25/$2.50) = 9 × $0.018 = **$0.162** |
| Check | $0.051345 + $0.162 = $0.213345 = booked total, exactly |

The actual xAI invoice was never reconciled; $0.051345 is the cost of the
usage the provider *reported*, $0.213345 is the ledger's conservative
booking. Neither is a verified invoice figure.

## 1.3 Classification of all 20 records

Taxonomy labels are not mutually exclusive; the primary label is listed
first. "LLM invoked" is only asserted where the saved data proves it
(usage present, or a provider-originated reason string).

| ID | Classification | Evidence in the file |
|---|---|---|
| q01 | **Evidence-acquisition failure** → **LLM never invoked** | `evidence: 0`, `retrieval_failure_reason: "no_relevant_pages"`, `llm_usage: null`, `claims: []`. 8 pages were found "relevant" but none admitted as evidence. |
| q02 | LLM invoked → normal model response → **verified answer** (pipeline's own screening) | usage 1344/157; 1 claim, supported, overlap 1.0; citation resolves. |
| q03 | **Evidence-acquisition failure** → **LLM never invoked** | As q01; all 8 related pages "irrelevant". |
| q04 | LLM invoked → normal response → **verified answer** | usage 2426/359; 2 claims, both supported, overlap 1.0. |
| q05 | LLM invoked → normal response → **claim verification failure** | usage 6459/52; evidence 4; 1 claim unsupported, **overlap null**. |
| q06 | **Evidence-acquisition failure** → **LLM never invoked** | As q01 (`unverified: 3`). |
| q07 | **Evidence-acquisition failure** → **LLM never invoked** | As q01. |
| q08 | LLM invoked → normal response → **claim verification failure** | usage 3093/69; 1 claim unsupported, **overlap null**. |
| q09 | **Evidence-acquisition failure** → **LLM never invoked** | As q01. |
| q10 | LLM invoked → normal response → **claim verification failure** | usage 3876/66; 1 claim unsupported, **overlap null**. |
| q11 | **Evidence-acquisition failure** → **LLM never invoked** | As q01. |
| q12 | LLM invoked → normal response → **claim verification failure** | usage 3589/214; 2 claims unsupported, overlaps **0.008 / 0.073** (bigram screening actually ran and scored near zero). Published citations present (2 keys, resolve). |
| q13 | LLM invoked → normal response → answered, **but not fully verified** | usage 2294/524; 3 claims: supported / **uncertain (overlap 1.0)** / supported. The published answer includes an uncertain claim — the Phase 10-B defect, visible in saved data. |
| q14 | **Evidence-acquisition failure** → **LLM never invoked** | As q01. |
| q15 | LLM invoked → normal response → **claim verification failure** | usage 2862/60; 1 claim unsupported, **overlap null**. |
| q16 | LLM invoked → **malformed response** (recorded as model unavailable) | `status: "llm_unavailable"`, `reason: "LLM returned an invalid structured answer"`, evidence 4, `llm_usage: null`, `claims: []`. The provider received and JSON-parsed a response whose `answer` field was not a string (`answer.py` final shape check). This is a malformed-response failure, not a transport outage. Its token usage was dropped by the provider's early return and is **not** in the per-record data. |
| q17 | LLM invoked → normal response → **claim verification failure** | usage 3684/89; 1 claim unsupported, **overlap null**. |
| q18 | LLM invoked → normal response → **answered without verified claims** | usage 2158/339; 3 claims, **all uncertain** (overlaps 0.467 / 0.324 / 0.484), yet status is `answered`. No claim reached "supported". This record must not be counted as a verified answer. |
| q19 | LLM invoked → normal response → **claim verification failure** | usage 4589/422; 3 claims unsupported, overlaps **0.0 / 0.009 / 0.0**. |
| q20 | **Evidence-acquisition failure** → **LLM never invoked** | As q01. |

Category totals: evidence-acquisition failure 8; LLM never invoked 8 (the
same 8); LLM invoked 12 (11 with reported usage + q16); normal model
response 11; malformed response 1; model unavailable (transport/HTTP) 0 —
no record shows a timeout or HTTP-error reason; claim verification failure
7 (all `answer_withheld`); citation validation failure 0 recorded
(`citations_resolve: true` on all 20 records, and no record carries the
service's `citation_validation_failed` status — but see §1.4: a citation
failure on a withheld answer could not be distinguished in this file);
partial answer 0; fully verified answer 2 (q02, q04); answered with
uncertain claims mixed in 1 (q13); answered with only uncertain claims 1
(q18).

## 1.4 Were the 7 withheld answers false rejections by the lexical checker?

**Verdict: cannot be determined from the saved data — for any of the 7.**

Reasoning, per sub-group:

- **q05, q08, q10, q15, q17 (overlap `null`):** In `claims.py`, the bigram
  overlap is only computed after three early returns — claim has no
  citation (line ~55), citations do not resolve to supplied evidence
  (~58), or cited text unavailable / claim too short (`not_checked`,
  ~62–68). Only the fall-through path sets `overlap` (line 156). A saved
  `overlap: null` therefore means the claim **never reached lexical
  screening at all**; it was rejected on citation structure, not on word
  overlap. Which of the early returns fired is recorded in the claim's
  `support_detail` string at runtime, but `run_evaluation.py` does not
  save `support_detail`. So for these 5 records it is not even correct to
  say "the lexical checker rejected them" — and whether the underlying
  claim was true is unknowable without the claim text.
- **q12, q19 (overlap 0.008/0.073 and 0.0/0.009/0.0):** Here the bigram
  screening did run and found essentially no shared bigrams between claim
  text and cited OCR. That is consistent with two opposite explanations:
  (a) the model paraphrased a genuinely supported statement (checker false
  rejection), or (b) the model wrote text unrelated to the cited pages
  (correct rejection). Distinguishing them requires the claim text and
  the cited OCR excerpt side by side. **Neither was saved.** Judgement:
  indeterminate.
- General: because no claim text, no sent evidence, and no checker reason
  strings were persisted, **no statement about the correctness of any
  individual withheld answer — in either direction — can be supported
  from this file.** Any claim that "the lexical checker falsely rejected
  N of 7" would be speculation. The only defensible statement is the
  aggregate one: the screening is lexical (bigram overlap over the cited
  pages' full OCR), so paraphrase-shaped claims are structurally at risk,
  and this run's design cannot measure how often that risk materialised.

## 1.5 What `eval/run_evaluation.py` currently saves — and what future runs must add

Currently saved per record (lines 117–150): identifiers and question text;
`status`; evidence/unverified **counts**; published citation keys;
related count + relevance statuses; `reason`; claims reduced to
`{support, overlap}`; `citations_resolve` boolean; `search_errors`;
`first_evidence_rank`; `retrieval_failure_reason`; premise-contradiction
count; correction quotes; optional `image_check`; `seconds`; `requests`;
and `llm_usage` (`{prompt_tokens, completion_tokens}`) only when the
service reported it. Run level: full `metrics` block and the ledger
`summary()`.

Future real-LLM runs must additionally save (all already exist at runtime;
they are dropped, not unavailable):

1. **Sent evidence**: the exact compacted payload per question — citation
   keys, passage IDs and the excerpt text actually sent (or, where rights
   restrict retention, the excerpt's citation key + char offsets + a hash).
2. **Model claim texts**: full claim objects — `text`, per-claim
   `citations`, `evidence_passage_ids`, plus the checker's `support`,
   `support_detail`, `overlap`, and numeric-binding detail.
3. **Answer text** as composed/published, and the accept/withhold decision
   with its machine-readable reason (which claim(s) caused withholding).
4. **The model's raw citation list** before pipeline clearing/validation,
   so citation-validation failures are distinguishable from claim failures.
5. **`llm_called` boolean per record**, so "never invoked" vs "invoked but
   no usage reported" (the q16 case) is explicit rather than inferred.
6. **Provider failure detail**: the sanitised reason already produced by
   the provider (timeout / HTTP status / malformed / invalid citations),
   as a structured code, per record.
7. **Model identity per record** (not only in run-level metrics), plus
   endpoint host (not the full URL with any parameters), temperature and
   `max_tokens` used.
8. **Full usage object**: `prompt_tokens`, `completion_tokens`,
   `total_tokens`, and any detail fields the provider returns (e.g.
   reasoning-token counts), stored verbatim minus nothing — it contains
   no secrets.
9. **Call count per record** (including any retries) and **per-record
   booked cost** with a flag whether it was reported or worst-case
   estimated.
10. **Dataset labelling provenance**: label source and whether a human
    verified the evidence (the Phase 10-F requirement) — as dataset
    metadata, not per-record free text.

Must never be saved: API keys or surrogates, Authorization headers, raw
request headers, or any personal data. None of the items above requires
any of those.

---

# Part 2 — Phase 10-G: Cost-management audit

Code examined: `src/global_library_mcp/llm_budget.py` (UsageLedger,
BudgetPlan), `src/global_library_mcp/answer.py` (OpenAICompatibleProvider,
compact_evidence), `src/global_library_mcp/service.py` (answer path),
`eval/run_evaluation.py`, `eval/run_llm_via_connector.py`.

## Q1. Is a max input-token limit enforced against the real payload?

**No — it is estimated/projected, never enforced against the payload.**
`UsageLedger.max_input_tokens` (default 12,000, `llm_budget.py:53`) is used
only in `worst_case_next_usd()` (line 73) for the pre-call projection and
as the fallback booking amount in `record()` (line 91). Nothing counts the
tokens of the actual request. The only real bound on input size is
indirect and in different units: `compact_evidence` caps the payload at
8 evidence items × 1,500 **characters** of text each (`answer.py:13–14,
40–53`), plus metadata fields, the system prompt and the question — none
of it token-counted. Characters are not tokens (Japanese text tokenises
at roughly ≥1 token per character with typical tokenisers), so the
12,000-token figure is not a guaranteed bound on the real payload.
Empirically in the audited run the largest reported prompt was 6,459
tokens (q05) — under 12,000 — but that is an observation, not an
enforcement.

## Q2. Does the budget's max output tokens match the `max_tokens` sent?

**They agree by default coincidence, not by construction.**
The provider sends `max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS",
"1200"))` (`answer.py:176`). The ledger's default is
`max_output_tokens=1200` (`llm_budget.py:53`), and `run_evaluation.py`
constructs the ledger with defaults (line ~91), never reading
`LLM_MAX_OUTPUT_TOKENS`. If that env var is set to anything else, the
sent limit and the budget's worst-case diverge silently. Separately,
BudgetPlan's pre-run *estimate* uses yet another pair of numbers
(2,500 in / 400 out, `llm_budget.py:34–35`) — the estimate, the ledger
worst case, and the wire payload are three independent configurations.

## Q3. Does the price table match the executed model?

**Yes, for this run.** `PRICE_TABLE_USD_PER_MTOK["grok-4.3"] = (1.25,
2.50)` (`llm_budget.py:28`); the executed model is recorded as
`openai-compatible:grok-4.3` in metrics and `grok-4.3` in the ledger
summary; `UsageLedger._cost` prices by `self.model`, and the runner
constructs the ledger from the same `LLM_MODEL` env the provider reads.
Arithmetic verification against the saved file: reported usage
36,374 × $1.25/M + 2,351 × $2.50/M = $0.051345; 9 estimated bookings ×
$0.018 = $0.162; total $0.213345 = the booked `spent_usd`, exactly.
Caveat: the prices are list prices verified 2026-11-24 from secondary
trackers; the actual invoice was never reconciled, and an unlisted model
blocks the run by design (fail-closed).

## Q4. Are reasoning tokens / other billable classes accounted for?

**Only partially, and the gap is structural.** The provider extracts
exactly two fields from the response `usage` object —
`prompt_tokens` and `completion_tokens` (`answer.py:188–192`) — and
discards everything else, including `total_tokens` and any detail
breakdowns (e.g. `completion_tokens_details.reasoning_tokens`). If the
provider bills reasoning tokens *inside* `completion_tokens` (the
OpenAI convention), they are captured. If a provider bills any class
*outside* those two fields, it is invisible to the ledger. From the
saved data it **cannot be determined** whether grok-4.3's reported
`completion_tokens` (52–524 per call) included reasoning tokens. The
ledger has no field for them.

## Q5. Are timed-out calls costed?

**In the ledger: yes, conservatively. In the per-record data: no.**
On timeout the provider returns `available: False` with no usage
(`answer.py:181–182`). The service still sets `llm_called = True`
(`service.py:451`), so the eval runner calls `ledger.record(None)`,
which books the full worst case (12,000/1,200 tokens) and increments
`usage_estimated` (`llm_budget.py:90–94`). Whether the provider actually
charges for a timed-out request is unknown; the booking is a deliberate
over-estimate, not a measurement. Note the same path applies to
malformed responses (q16): booked at worst case in the ledger, invisible
in the record's `llm_usage: null`. In the audited run, no timeout
occurred; the 9 estimated bookings were 8 never-invoked questions
(pre-fix behaviour, see Q6) + q16.

## Q6. Are questions that never reached the LLM excluded from booking?

**Yes, after the fix — and the audited file itself proves it was not so
during the run.** Current code: `service.answer` sets
`base["llm_called"] = True` only after `provider.answer` is invoked
(`service.py:451`); questions that stop at evidence admission return
before that point. `run_evaluation.py` (line ~127) records to the ledger
only `if result.get("llm_called")`. The saved run, however, shows
`calls: 20, usage_estimated: 9` = 8 never-invoked questions + q16 — i.e.
the run executed with the pre-fix recording behaviour, and the fix was
committed afterwards in the same commit (`c9574a2`) as the results. A
re-run under current code would book 12 calls (11 reported + q16
estimated), not 20. Residual imperfection: `llm_called` is also set when
`provider.answer` returns early *without a network call* (e.g. LLM
disabled or no key configured — `answer.py:155–160`); in the eval path
those preconditions are set, so this does not arise there, but the flag
means "provider invoked", not "HTTP request made".

## Q7. Does accumulated cost survive a resumed run?

**No.** `UsageLedger` is a plain in-memory object (counters as instance
attributes, `llm_budget.py:52–64`); there is no persistence, no load/save,
and neither `run_evaluation.py` nor `run_llm_via_connector.py` reads any
prior state. The results file's `llm_usage` summary is write-only. Every
new process starts at `spent_usd = 0`, so the $ cap is a **per-process**
cap, not a per-campaign cap: re-running the same evaluation twice costs
up to 2× the cap while each run individually "respects" it.

## Q8. Can concurrent calls overspend?

**Not in the current eval runner; the class itself offers no concurrency
guarantee.** `run_evaluation.py` is strictly sequential: one question at
a time, `can_afford()` checked before each (line ~105), `record()` after
it completes. `can_afford` is check-then-act with no lock
(`llm_budget.py:75–79`); two concurrent callers could both pass the check
and jointly overspend. No concurrent caller exists today — the
production service path does not use a ledger at all (see Q9) — so this
is a latent, not an active, risk. It must be closed (lock, or reserve-on-
check) before the ledger is reused in any concurrent setting.

## Q9. Are evaluation and production cost controls separated?

**They are separate in the sense that production has none.** The whole
control stack — BudgetPlan pre-run gate, the `GLM_LLM_APPROVED` /
`GLM_LLM_MAX_COST_USD` / `LLM_MODEL` hand-off, and the UsageLedger —
exists only in the evaluation path (`run_evaluation.py` provider
`openai` branch; `run_llm_via_connector.py`; `eval/real_llm_run.py`).
`LibraryService.answer` (the production/MCP/Web path) contains no ledger,
no cap and no per-call cost check; its only LLM gates are `LLM_ENABLED`,
key presence, and base-URL validation in the provider. So: evaluation
spend is capped per process; production spend, if the LLM is ever
enabled there, is **uncapped by this code** and would rely entirely on
the provider account's own limits. This separation is by absence, not by
design of two control regimes.

## Verified facts vs estimates

Verified from code + saved file: the ledger arithmetic reproduces the
booked $0.213345 exactly; 11 calls have provider-reported usage totalling
$0.051345 at table prices; output `max_tokens` defaults agree (1200 =
1200); the post-run fix excludes never-invoked questions; the ledger is
in-memory only; the eval loop is sequential with a pre-call
`can_afford()` check.

Estimates / unverified: the actual xAI invoice amount (never reconciled);
whether timed-out or malformed calls were/would be charged by xAI;
whether reported `completion_tokens` included reasoning tokens; the
12,000-token input figure as a bound on real payloads (empirically held
in this run — max prompt 6,459 — but not enforced).

## Preconditions under which the budget guarantee holds

The statement "this run cannot exceed the cap" is valid only when **all**
of the following hold:

1. Calls go through the evaluation runner (the only path with a ledger),
   in a **single, sequential process** — no concurrency, no restart/
   resume mid-campaign (a restart resets spend to zero).
2. The executed model is in the price table and the table prices are
   correct and current.
3. Each call's actual cost is ≤ the ledger's worst case: output is
   bounded by the sent `max_tokens` (default 1,200, matching the ledger
   default only while `LLM_MAX_OUTPUT_TOKENS` is unset), and input
   stays ≤ 12,000 tokens — which is **assumed, not enforced** (only
   character caps bound it).
4. All billable token classes are contained in `prompt_tokens` /
   `completion_tokens` as reported by the provider.
5. Provider-reported usage, when present, is accurate; when absent, the
   worst-case booking covers the real charge.

If any precondition fails, the ledger still *books* conservatively, but
the hard guarantee degrades to a best-effort estimate.
