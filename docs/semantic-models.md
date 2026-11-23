# Semantic checker: method survey and selection (Phase 5-B)

## What the checker must decide

Given a question (with its analysis) and one OCR page: does the
page *support* the question's premise, *contradict* it, merely
*mention* the topic, or say nothing usable? The Phase 4 failure
class is narrow and well understood: era-bound existence /
occurrence / diffusion premises, defeated by negation ("did not
exist yet"), later onset ("began in the following era"), and
planning-only coverage.

## Candidates considered

| Method | Strengths | Limits | Cost / licence |
|---|---|---|---|
| Rule-based stance + temporal cues (shipped) | Deterministic, offline, explainable reasons, zero weights; directly encodes negation / planning / onset / diffusion phases and era anchoring | Only as good as its cue coverage; no opinion outside era-premise questions (returns `uncertain` by design) | No model, no licence burden |
| Multilingual sentence embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, Apache-2.0, ~470 MB, via sentence-transformers) | Good topical similarity JA/EN; CPU-feasible for tens of sentences | **Cannot detect negation or contradiction** — "radio did not exist" embeds close to "radio existed"; similarity is not support | Free; weights from Hugging Face, never committed to this repo |
| Multilingual NLI (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, MIT, ~700 MB) | True entailment/contradiction classes; the right shape for supports/contradicts | Heavier (transformers + torch), slower on shared CPU, zero-shot quality on period Japanese OCR is unverified; premise must be reformulated as a hypothesis sentence | Free; weights from Hugging Face, never committed |
| Hosted LLM API | Strongest judgement | Paid, needs approval, non-deterministic, keys must never touch the repo | Out of scope without approval (see Phase 5 §10 prep) |

## Decision

Ship the **hybrid interface with the rule-based checker as the
primary engine** (`semantics.py`, `SemanticChecker` protocol):

- `RuleBasedSemanticChecker` — deterministic; the only checker
  whose verdicts may promote/demote pages in Phase 5, because its
  failure modes are inspectable.
- `EmbeddingSemanticChecker` — implemented behind the same
  interface (`GLM_SEMANTIC_EMBED_MODEL`); by design it never
  returns supports/contradicts (embeddings cannot), only a
  similarity signal or `not_checked` when unavailable.
- An NLI checker can be added behind the same protocol later; the
  integration points (evidence `semantics` field, gate decisions,
  claim screening) do not change.

Safety rules, enforced in code and tests:

- `not_checked` is never treated as support.
- Model absence degrades to the lexical gate + rule checker, with
  the absence visible in the verdict's reasons.
- No model weights are committed; models load from the local
  Hugging Face cache only.

## Local verification status

Verified in this development environment (shared vCPU, ~8 GB RAM,
512 MB /tmp): the first `pip install sentence-transformers`
attempt failed with "No space left on device" because pip staged
the ~540 MB torch wheel in the small /tmp. With `TMPDIR` pointed
at the home filesystem the install succeeded (sentence-
transformers 6.3.0, torch 2.15.0), proving the stack *can* be
installed here; the model-weights download / inference smoke test
did not complete in this environment (an interrupted run left
only a stub in the Hugging Face cache), so the embedding checker
is verified at the interface level only — including its
`not_checked` behaviour when the stack is absent, which is the
path the pipeline takes by default. The stack was uninstalled
after the check; it is not a runtime dependency and is not in
`requirements.lock.txt`. Environments that have it can enable the
checker via `GLM_SEMANTIC_EMBED_MODEL` without code changes.
