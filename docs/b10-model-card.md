# b10 model card — local semantic search model

Checked and downloaded 2026-11-28 under the brief's section 18
conditions (one model, ≤ 300 MiB, license verified, pinned
revision, offline inference, no remote code).

| Field | Value |
|---|---|
| Model ID | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Official source | Hugging Face repo of the sentence-transformers organisation |
| Revision (pinned) | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| License | Apache-2.0 (per the repo's model card metadata, checked via the HF API on 2026-11-28) |
| Artefact used | `onnx/model_quint8_avx2.onnx` (uint8-quantised ONNX, 118.5 MB) + tokenizer files |
| Total on disk | 127 MB (model dir, outside the git repository) |
| SHA-256 (ONNX file) | `98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f` |
| Architecture | Multilingual MiniLM-L12, 384-dim mean-pooled embeddings, 50+ languages incl. ja/en/de/fr/fi/sv/nl |
| Runtime | onnxruntime 1.32.0 (CPUExecutionProvider, 2 intra-op threads), `tokenizers` 0.23.3 |
| Remote code | None — plain ONNX graph; no `trust_remote_code` surface exists in this path |
| Telemetry | None — inference performs no network access; the loader reads only local files |
| Fallback | Without `GLM_SEMANTIC_MODEL_DIR`, or if files/runtime are missing, the backend reports unavailable and ranking falls back to lexical/strict signals; the UI must not claim semantic search ran (section 37) |

Measured on this VM (1.5 shared CPUs, ~6 GB RAM), 2026-11-28:
model load 2.77 s; encoding ≈ 12 ms per bibliographic record
(title+author+subjects). Whole-corpus ranking evaluation:
`docs/b10-semantic-search.md`.

Alternatives considered and not adopted:
- `intfloat/multilingual-e5-small` — MIT-licensed and strong,
  but the fp32 weights are ~448 MB, above the 300 MiB cap, and
  no official quantised ONNX artefact was confirmed.
- The same MiniLM in fp32 (~470 MB) — above the cap.
- A second model for NLI — not approved (brief section 32);
  recorded as an additional-approval item.

The weights live outside the repository
(`~/workspace/glm-models/…` on the development VM) and are never
committed, per section 18.

---

## Final-review addendum (2026-11-28)

This document describes the b10 candidate as submitted in
PR #21 (head `dc8d794`). The external final review reproduced
defects in several of the areas covered here; the fixes,
re-measurements and corrected claims are recorded in
`docs/b10-final-review.md`, which supersedes this document
wherever the two disagree (notably: semantic search is now
wired into the real service path as an opt-in ranking mode;
`authority_verified` can no longer be reached from the local
lexicon alone; editions are candidates; independent-source
counting was replaced; the Docker CI job is fixture-mandatory
with the live smoke separated as an informational job).
