# Phase 10-F: next real-LLM experiment plan (NOT yet approved)

## Dataset

`eval/balanced-v1.json` - 40 fixed-evidence cases, labels
fixed on 2026-11-24 BEFORE any run, derived from the gold
v2 admission-independent relation labels and from passage
texts, never from pipeline outputs. Composition: support
12 (7 hypothesis-style entailment + 5 verbatim-style),
insufficient 8, related-but-not-supporting 8, contradiction
6 (5 gold + 1 transparently constructed era-shift), partial
multi-claim 6. `human_verified: false` throughout - no
human has hand-checked these cases yet, and any report must
say so. Fixed evidence separates retrieval quality from
semantic verification quality.

## Offline verifier comparison (already run, no cost)

`eval/run_fixed_eval.py` over the fixed set
(`eval/results-balanced-v1-verifiers.json`):

| verifier | entail. precision | entail. recall | false support | false rejection | contradiction detection |
|---|---|---|---|---|---|
| lexical | 1.000 | 0.208 | 0.000 | 0.792 | 0.000 |
| NLI | n/a (not_checked) | 0.000 | 0.000 | 1.000 | 0.000 |
| hybrid | n/a (not_checked) | 0.000 | 0.000 | 1.000 | 0.000 |

Reading: the lexical checker NEVER falsely supports, but
rejects 79% of genuinely entailed claims (it cannot verify
paraphrase/hypothesis-style claims) and detects no
contradictions. This is the measured explanation of the
first grok run's 7 withholdings being unresolvable from
lexical data alone. NLI is unavailable in this environment
(no weights, libraries absent) - recorded as not_checked,
not as a method failure.

## The experiment that needs NEW approval

Purpose: measure (a) an LLM judge's entailment quality on
the same fixed cases, and (b) generative answering over
fixed evidence, separately from retrieval.

- Provider / endpoint: xAI, https://api.x.ai/v1 (same
  connector-held key route as the first run; the key never
  enters the process, only a surrogate does)
- Judge model: grok-4.3 (producer/judge separation: claims
  under judgement are the FIXED dataset claims and, for the
  generative arm, claims produced by the same model are
  judged by the deterministic+lexical layer, NOT by itself -
  self-judging is refused by LlmJudgeVerifier by design;
  if a same-model judge arm is wanted for comparison, it is
  reported as non-independent)
- Cases: the 40 fixed cases (64 claims total)
- Arms: C LLM judge over fixed claims; D generative answer
  over fixed evidence for the 26 question-bearing cases
- Max calls: 40 judge + 26 generative = 66, hard-capped by
  UsageLedger (reserve/settle) at the approved ceiling
- Estimated cost at grok-4.3 prices ($1.25/$2.50 per MTok):
  ~$0.35 expected, worst case ~$1.19 at the per-call maxima
- **Requested cap: $1.50** (covers the worst case; the
  ledger refuses any call that could breach it)
- Data sent: question texts, fixed passage excerpts from
  public-domain historical materials, claim texts. No
  personal data, no API keys.
- Metrics: the brief 10-F list - entailment precision /
  recall, contradiction detection, false-support rate,
  false-rejection rate, grounded-correction success,
  answer accuracy and adequacy (human spot-check of the
  answered subset, marked as such), partial-answer success,
  citation accuracy, cost (ledger), latency.

Approval state: **NOT APPROVED**. The Phase 9 grok-4.3
approval does not carry over (brief 10-F). Nothing in this
plan runs until the operator approves provider, model,
endpoint, data, case count, call cap and cost cap.
