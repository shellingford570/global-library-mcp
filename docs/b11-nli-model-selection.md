# b11 NLI Model Selection (sections 23-26)

Facts below were read from the official Hugging Face model API /
cards on 2026-11-28. **No model was downloaded in b11.**

## Candidates

| Item | MoritzLaurer/mDeBERTa-v3-base-mnli-xnli | joeddav/xlm-roberta-large-xnli | cross-encoder/nli-MiniLM2-L6-H768 |
|---|---|---|---|
| Revision | `8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c` | `b227ee8435ceadfa86dc1368a34254e2838bf242` | `b95119ce93d3e065de6214e38cd4a97b0f2f2c6d` |
| Training data | MultiNLI + XNLI (per card) | MultiNLI + XNLI (per card) | SNLI + MultiNLI (per card) |
| NLI languages (card) | en, ar, bg, de, el, es, fr, hi, ru, sw, th, tr, ur, vi, zh | en, fr, es, de, el, bg, ru, tr, ar, vi, th, zh, hi, sw, ur | en only |
| Japanese / Finnish NLI supervision | **not in XNLI's 15 languages** (base encoder is multilingual CC100, incl. ja/fi, but NLI fine-tuning did not include them) | same limitation | no |
| Parameters | 278.8M | 560.9M | 82.1M |
| ONNX | `onnx/model.onnx` + `onnx/model_quantized.onnx` in repo | none in repo file list | `onnx/model.onnx` + quint8 variants in repo |
| Max input | DeBERTa-v2 class: 512 tokens (premise+hypothesis must be chunked) | XLM-R class: 512 tokens | RoBERTa class: 512 tokens |
| License | MIT | MIT | Apache-2.0 |
| Redistribution | permitted under MIT (weights + card terms) | MIT | Apache-2.0 |
| Dependencies | transformers / ONNX Runtime; sentencepiece tokenizer | transformers; sentencepiece | sentence-transformers / ONNX Runtime |
| Remote code | none required (standard architectures) | none required | none required |

CPU speed: not measured (no download in b11). The MiniLM2
candidate is the only one small enough to be clearly CPU-cheap,
but it is English-only and therefore unsuitable as the primary
multilingual checker for ja/de/fr/fi material.

## Recommendation (for a future, separately approved step)
Primary candidate: **MoritzLaurer/mDeBERTa-v3-base-mnli-xnli**
(MIT, ONNX + quantized ONNX available, 278.8M params, already
the `DEFAULT_NLI_MODEL` constant since Phase 8). Known
limitation to state in any approval request: XNLI supervision
does not include Japanese or Finnish, so ja/fi shadow quality
must be evaluated before any reliance, and NLI stays a shadow
signal regardless.

## Approval proposal (section 25) - NOT requested in b11
A future download request must present: model ID
`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, revision
`8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c`, license MIT,
download size (quantized ONNX file size to be confirmed from the
repo file listing at request time; the full repo storage is
~3.7 GB across all formats, only the ONNX + tokenizer files
would be fetched), disk impact (model dir outside the repo,
like the MiniLM semantic model), memory estimate (base-size
encoder, ~1-2 GB RSS class - to be measured, not asserted), CPU
requirements (CPU-only ONNX Runtime, batch 1, premise truncated
to 2000 chars as in the existing checker), cost (0 - local
inference only), network use (one-time download from
huggingface.co), and the rationale (shadow-mode contradiction /
entailment signal for claim-evidence assessment, never a
governing verdict). **This proposal is documentation only; the
download itself needs tana's separate approval.**
