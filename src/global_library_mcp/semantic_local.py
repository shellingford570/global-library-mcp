"""Local semantic embeddings (b10 Stage 3; final-review hardened).

Optional backend: a locally stored ONNX sentence-embedding model,
loaded only when GLM_SEMANTIC_MODEL_DIR points at a verified model
directory. Final-review additions (sections 4-6 of the b10 final
review brief):

- a fixed model MANIFEST (model id, pinned revision, SHA-256 of
  the ONNX graph and of tokenizer.json, size caps) is verified
  BEFORE the model is constructed; a mismatching file is refused;
- the backend is a process-wide SINGLETON: repeated
  get_local_backend() calls return the same instance, so the
  ~127 MB model is never reloaded per request;
- inference validates output shape and rejects NaN/Infinity;
- encode_async() runs inference in a thread executor so the
  event loop is not blocked;
- providers are limited to CPUExecutionProvider;
- synthetic test backends implement the same small protocol
  (model_id / model_revision / dimension / encode) and are
  clearly distinguishable from the real MiniLM backend.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import threading
from pathlib import Path
from typing import Any, Sequence

ENV_VAR = "GLM_SEMANTIC_MODEL_DIR"
_MODEL_FILE = "onnx/model_quint8_avx2.onnx"
_TOKENIZER_FILE = "tokenizer.json"

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_MANIFEST = {
    "model_id": MODEL_ID,
    "revision": MODEL_REVISION,
    "files": {
        _MODEL_FILE: {
            "sha256": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f",
            "max_bytes": 200_000_000,
        },
        _TOKENIZER_FILE: {
            "sha256": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8",
            "max_bytes": 50_000_000,
        },
    },
    "dimension": 384,
    "providers": ["CPUExecutionProvider"],
    "license": "Apache-2.0",
}
MAX_BATCH = 64
MAX_TEXT_CHARS = 2000
# b11 Stage 0 (section 12): inference resource management.
MAX_CONCURRENT_INFERENCE = 2
MAX_INFERENCE_QUEUE = 8
INFERENCE_ACQUIRE_TIMEOUT_S = 5.0
MAX_ENCODE_TEXTS = 256


def process_rss_bytes() -> int | None:
    """Current process RSS (bytes), for resource reporting."""
    try:
        import resource as _res
        peak = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB, macOS reports bytes.
        import sys as _sys
        return int(peak * 1024) if _sys.platform.startswith("linux") else int(peak)
    except Exception:
        return None


class SemanticBackendUnavailable(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_model_dir(model_dir: str | Path) -> dict[str, Any]:
    """Verify a model directory against the fixed manifest.

    Returns a report dict; raises SemanticBackendUnavailable with
    a precise reason on any mismatch. No network access."""
    root = Path(model_dir)
    report: dict[str, Any] = {"model_id": MODEL_ID,
                              "revision": MODEL_REVISION, "files": {}}
    for rel, spec in MODEL_MANIFEST["files"].items():
        path = root / rel
        if not path.exists():
            raise SemanticBackendUnavailable(f"model file missing: {rel}")
        if path.is_symlink():
            raise SemanticBackendUnavailable(f"model file is a symlink: {rel}")
        size = path.stat().st_size
        if size > spec["max_bytes"]:
            raise SemanticBackendUnavailable(
                f"model file too large: {rel} ({size} > {spec['max_bytes']})")
        digest = _sha256(path)
        if digest != spec["sha256"]:
            raise SemanticBackendUnavailable(
                f"model file hash mismatch: {rel}")
        report["files"][rel] = {"sha256": digest, "bytes": size}
    return report


class LocalSemanticBackend:
    model_id = MODEL_ID
    model_revision = MODEL_REVISION

    def __init__(self, model_dir: str | Path, *, verify: bool = True):
        self.model_dir = Path(model_dir)
        self.manifest_report = (verify_model_dir(self.model_dir)
                                if verify else None)
        model_path = self.model_dir / _MODEL_FILE
        tokenizer_path = self.model_dir / _TOKENIZER_FILE
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
        try:
            self._session = ort.InferenceSession(
                str(model_path), sess_options=options,
                providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise SemanticBackendUnavailable(
                f"invalid ONNX model: {type(exc).__name__}") from exc
        self._input_names = {i.name for i in self._session.get_inputs()}

    @property
    def dimension(self) -> int:
        return 384

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        if not texts:
            return []
        texts = [str(t)[:MAX_TEXT_CHARS] for t in texts]
        out_all: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            batch = texts[start:start + MAX_BATCH]
            enc = self._tokenizer.encode_batch(list(batch))
            input_ids = np.array([e.ids for e in enc], dtype=np.int64)
            attention = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds: dict[str, Any] = {"input_ids": input_ids,
                                     "attention_mask": attention}
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.array(
                    [e.type_ids for e in enc], dtype=np.int64)
            outputs = self._session.run(None, feeds)
            hidden = outputs[0]
            if hidden.ndim != 3 or hidden.shape[2] != self.dimension:
                raise SemanticBackendUnavailable(
                    f"unexpected model output shape {hidden.shape}")
            if not np.isfinite(hidden).all():
                raise SemanticBackendUnavailable(
                    "model output contains NaN or Infinity")
            mask = attention[..., None].astype(np.float32)
            summed = (hidden * mask).sum(axis=1)
            counts = mask.sum(axis=1).clip(min=1e-9)
            pooled = summed / counts
            norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
            out_all.extend((pooled / norms).tolist())
        for vec in out_all:
            if len(vec) != self.dimension or not all(
                    math.isfinite(v) for v in vec):
                raise SemanticBackendUnavailable("invalid embedding vector")
        return out_all

    async def encode_async(self, texts: Sequence[str]) -> list[list[float]]:
        if len(texts) > MAX_ENCODE_TEXTS:
            raise SemanticBackendUnavailable(
                f"too many texts for one inference call: {len(texts)}")
        gate = _inference_gate()
        global _gate_waiters
        if gate.locked() and _gate_waiters >= MAX_INFERENCE_QUEUE:
            raise SemanticBackendUnavailable(
                "inference queue full; falling back")
        _gate_waiters += 1
        try:
            await asyncio.wait_for(gate.acquire(),
                                   timeout=INFERENCE_ACQUIRE_TIMEOUT_S)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise SemanticBackendUnavailable(
                "inference queue deadline exceeded; "
                "falling back") from exc
        finally:
            _gate_waiters -= 1
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, self.encode, texts)

        def _release(_f: Any = None) -> None:
            try:
                gate.release()
            except ValueError:
                pass
        # The resource reservation is released only when the
        # THREAD actually finishes - cancelling the awaiting
        # caller does not stop ONNX inference, so the slot stays
        # reserved until the work is really done (section 12).
        future.add_done_callback(_release)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            raise


_gate: asyncio.Semaphore | None = None
_gate_loop: Any = None
_gate_waiters = 0


def _inference_gate() -> asyncio.Semaphore:
    global _gate, _gate_loop
    loop = asyncio.get_running_loop()
    if _gate is None or _gate_loop is not loop:
        _gate = asyncio.Semaphore(MAX_CONCURRENT_INFERENCE)
        _gate_loop = loop
    return _gate


_singleton: LocalSemanticBackend | None = None
_singleton_dir: str | None = None
_singleton_lock = threading.Lock()
_last_error: str | None = None


def get_local_backend() -> LocalSemanticBackend | None:
    """The configured local backend (process-wide singleton), or
    None when unavailable. The failure reason is available via
    backend_unavailable_reason()."""
    global _singleton, _singleton_dir, _last_error
    model_dir = os.getenv(ENV_VAR)
    if not model_dir:
        _last_error = "model not configured (GLM_SEMANTIC_MODEL_DIR unset)"
        return None
    with _singleton_lock:
        if _singleton is not None and _singleton_dir == model_dir:
            return _singleton
        try:
            _singleton = LocalSemanticBackend(model_dir)
            _singleton_dir = model_dir
            _last_error = None
            return _singleton
        except SemanticBackendUnavailable as exc:
            _last_error = str(exc)
            _singleton = None
            _singleton_dir = None
            return None


def backend_unavailable_reason() -> str | None:
    if _singleton is not None:
        return None
    return _last_error or "model not configured"


def reset_backend_cache() -> None:
    """Test hook: drop the singleton so a new directory is read."""
    global _singleton, _singleton_dir, _last_error
    with _singleton_lock:
        _singleton = None
        _singleton_dir = None
        _last_error = None


def cosine_scores(query_vector: Sequence[float],
                  doc_vectors: Sequence[Sequence[float]]) -> list[float]:
    if any(not math.isfinite(v) for v in query_vector):
        raise ValueError("query vector contains NaN or Infinity")
    out: list[float] = []
    for vec in doc_vectors:
        if len(vec) != len(query_vector):
            raise ValueError("embedding dimension mismatch")
        if any(not math.isfinite(v) for v in vec):
            raise ValueError("document vector contains NaN or Infinity")
        out.append(float(sum(a * b for a, b in zip(query_vector, vec))))
    peak = max(out) if out else 0.0
    if peak > 0:
        out = [max(v, 0.0) / peak for v in out]
    return out
