# Phase 8-E — semantic-understanding model comparison

Roles are kept separate (brief 7). No model's output is a
truth guarantee; in particular **an NLI verdict never approves
an answer by itself** — it is recorded as an auxiliary signal.

| Role | Candidate | Version / source | License | Size | Status in this repo |
|---|---|---|---|---|---|
| NLI (entailment / contradiction / neutral) | MoritzLaurer/mDeBERTa-v3-base-mnli-xnli | Hugging Face, updated 2024-01-08; mDeBERTa-v3-base fine-tuned on MNLI + XNLI; 100 languages incl. Japanese | MIT (model card) | ~0.3B params, weights ~558MB (safetensors, per the 2mil7 sibling card) | Interface implemented (`nli.py`); load attempted once, bounded — see results below |
| NLI (larger sibling) | MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 | HF, trained on multilingual-NLI-26lang-2mil7 (2.73M pairs, 26 languages) + XNLI | MIT (model card) | ~558MB | Candidate; not attempted (heavier download, same failure mode expected) |
| Embedding (topic similarity only) | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | HF / sentence-transformers | Apache-2.0 (per model card; re-verify at adoption) | ~470MB | Already wired as the optional similarity signal (Phase 5); weights download fails through this environment's proxy — degrades to `not_checked` by design |
| Reranker (query–document relevance) | BAAI/bge-reranker-v2-m3 | HF | MIT (per model card; re-verify at adoption) | ~2.3GB | Not integrated: too heavy for this VM (1.5 CPU / 6GB) alongside eval runs; relevance stays with the lexical gate until a deployment with more RAM adopts it |
| Local LLM | (none adopted) | — | — | — | No local LLM runtime is installed; the OpenAI-compatible provider path (8-G) covers API models behind explicit approval |
| Rule checker | in-repo `RuleBasedSemanticChecker` | this repository | project license | 0 | The governing checker: deterministic, auditable, CPU-trivial |

## What was verified here

- Hypothesis generation (`nli.build_hypothesis`): the claim is
  stated declaratively (era + concept + existence/diffusion)
  before any NLI call; the raw question is never the input.
- `NliChecker.check_passage` with an injected backend maps
  scores to entailment / contradiction / neutral with a 0.6
  threshold and returns the model name and scores.
- With no backend, the load is attempted **at most once** per
  process with a hard timeout (`GLM_NLI_LOAD_TIMEOUT_S`,
  default 120s); failure is final and recorded. Search, OCR
  display and the rule checker are unaffected.
- Comparison harness: `eval/compare_checkers.py` runs both
  checkers over the frozen Phase 7 fixtures
  (`eval/checker-comparison-phase8.json`).

## Historical-text caveats (why NLI stays a signal)

XNLI-style training data is modern text. Meiji-era kundoku
influenced prose, historical kana orthography and old
character forms are out of distribution; entailment scores on
such passages must be treated as weak evidence, and a neutral
verdict on genuine period prose is expected to be common. The
gold passage dataset (8-F) exists precisely so this can be
measured instead of assumed.
