"""Local semantic embeddings (b10 Stage 3, brief sections 17-19).

Optional backend: a locally stored ONNX sentence-embedding
model, loaded only when GLM_SEMANTIC_MODEL_DIR points at a
verified model directory. Design constraints (section 18):

- official distribution source and a pinned revision, recorded
  in docs/b10-model-card.md;
- weights are NEVER committed to the repository and never sent
  anywhere; inference is fully offline (the loader performs no
  network access);
- no remote code execution: the model is a plain ONNX graph run
  by onnxruntime, tokenisation by the `tokenizers` library from
  the local tokenizer.json;
- when the directory, files or runtime are missing, the backend
  reports itself unavailable and callers fall back to lexical
  ranking - the UI must never claim semantic search ran when it
  did not (section 37).

Scope (section 19): embeddings are computed on bibliographic
fields (title / author / subjects) and, in research use, on
short rights-cleared excerpts the caller supplies. No persistent
vector database is created; vectors live for the duration of a
ranking call.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

ENV_VAR = "GLM_SEMANTIC_MODEL_DIR"
_MODEL_FILE = "onnx/model_quint8_avx2.onnx"
_TOKENIZER_FILE = "tokenizer.json"


class SemanticBackendUnavailable(RuntimeError):
    pass


class LocalSemanticBackend:
    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        model_path = self.model_dir / _MODEL_FILE
        tokenizer_path = self.model_dir / _TOKENIZER_FILE
        if not model_path.exists() or not tokenizer_path.exists():
            raise SemanticBackendUnavailable(
                f"model files missing under {self.model_dir}")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except Exception as exc:
            raise SemanticBackendUnavailable(
                f"onnx runtime unavailable: {exc}") from exc
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(max_length=128)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self._session = ort.InferenceSession(
            str(model_path), sess_options=options,
            providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self._session.get_inputs()}

    @property
    def dimension(self) -> int:
        return 384

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        if not texts:
            return []
        enc = self._tokenizer.encode_batch(list(texts))
        input_ids = np.array([e.ids for e in enc], dtype=np.int64)
        attention = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds: dict[str, Any] = {"input_ids": input_ids,
                                 "attention_mask": attention}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.array(
                [e.type_ids for e in enc], dtype=np.int64)
        outputs = self._session.run(None, feeds)
        hidden = outputs[0]  # (batch, seq, dim)
        mask = attention[..., None].astype(np.float32)
        summed = (hidden * mask).sum(axis=1)
        counts = mask.sum(axis=1).clip(min=1e-9)
        pooled = summed / counts
        norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
        return (pooled / norms).tolist()


def get_local_backend() -> LocalSemanticBackend | None:
    """The configured local backend, or None (fallback mode)."""
    model_dir = os.getenv(ENV_VAR)
    if not model_dir:
        return None
    try:
        return LocalSemanticBackend(model_dir)
    except SemanticBackendUnavailable:
        return None


def cosine_scores(query_vector: Sequence[float],
                  doc_vectors: Sequence[Sequence[float]]) -> list[float]:
    out: list[float] = []
    for vec in doc_vectors:
        out.append(float(sum(a * b for a, b in zip(query_vector, vec))))
    peak = max(out) if out else 0.0
    if peak > 0:
        out = [max(v, 0.0) / peak for v in out]
    return out
