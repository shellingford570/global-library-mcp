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

## Acquisition application - concrete file manifest (final review section 34)

Measured from the Hugging Face API (`?blobs=true` and the tree
endpoint) on 2026-11-28 at revision
`8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c`. **Nothing was
downloaded; this section only makes a future approval request
decidable.** The full repository is 2,590,785,805 bytes across
12 files and is NOT the acquisition target.

Acquisition set (quantized ONNX path, mirroring the MiniLM
semantic model policy):

| File | Bytes | SHA-256 (LFS) / git blob |
|---|---|---|
| `onnx/model_quantized.onnx` | 338,679,133 | `27c39e884c14b03cf46cfc5485971b6db70ff330220d93dfe729c63fde43af0e` |
| `config.json` | 1,066 | git blob `25b875998a15441ca06ee6d96b4cae362514549d` |
| `spm.model` | 4,305,025 | `13c8d666d62a7bc4ac8f040aab68e942c861f93303156cc28f5c7e885d86d6e3` |
| `tokenizer.json` | 16,331,396 | `3aca3ce69a0a35aeb144a52c4f1d41c4246b8785f8f398315cc8fb6b24057810` |
| `tokenizer_config.json` | 1,256 | git blob `173d68ceeb1e02125bda27f0867401b1deaad258` |
| `special_tokens_map.json` | 286 | git blob `2c9cb07c8fdeeb5ac3ceafb170592e990b204dcd` |
| `added_tokens.json` | 23 | git blob `d8d263667449f525ae294e10a31b032d4b7eaf1b` |
| **Total** | **359,318,185** | |

- ONNX external data: **none** - the repo contains no
  `*.onnx_data` sibling; the quantized model is a single file.
  (The unquantized `onnx/model.onnx`, 1,116,115,065 bytes,
  SHA-256 `7d39629484bdad052176a0cff26ffe408d8c2b69c7abd242716fee320badd661`,
  is NOT in the acquisition set.)
- Architecture: `DebertaV2ForSequenceClassification`;
  label mapping from `config.json` `id2label`:
  0 = entailment, 1 = neutral, 2 = contradiction.
- Tokenizer: SentencePiece (`spm.model`) + fast tokenizer
  (`tokenizer.json`); no remote code.
- License: MIT (weights and card).
- Disk: ~360 MB in a model directory OUTSIDE the repo (same
  policy as the MiniLM semantic model); nothing is committed.
- Estimated RSS: not measured (no download); base-size encoder
  class, expected ~1-2 GB - to be measured at acquisition time,
  not asserted here.
- CPU: CPU-only ONNX Runtime, batch 1; premise truncated to
  2,000 chars by the existing checker; no GPU requirement.
- Japanese support basis and limit: the base encoder is
  multilingual (CC100 incl. Japanese), but the NLI fine-tuning
  (MultiNLI + XNLI) covers XNLI's 15 languages, which do NOT
  include Japanese or Finnish teacher signal. ja/fi shadow
  quality is therefore UNVERIFIED and must be evaluated before
  any reliance; NLI remains a shadow signal regardless.
- Cost: 0 (local inference; one-time HTTPS download from
  huggingface.co is the only network use).
