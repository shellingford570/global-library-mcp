"""b10 Stage 3 semantic-search evaluation (brief sections 17-21).

Setting: rank the WHOLE fixed corpus for each case query (a
harder setting than re-ranking the retrieved subset). Rankers:

- LEX: lexical TF-IDF (lexical.LexicalScorer)
- SEM: local model cosine only (paraphrase-multilingual-
  MiniLM-L12-v2, ONNX quint8, CPU, offline)
- HYB: reciprocal-rank fusion of LEX and SEM

Also records model load time and per-text encode time
(section 45). Requires GLM_SEMANTIC_MODEL_DIR; without it the
script reports the fallback state and exits 0 after the lexical
run. Labels are agent-assigned proxy labels.

Usage: GLM_SEMANTIC_MODEL_DIR=... python eval/b10_semantic_eval.py --out f.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.lexical import LexicalScorer  # noqa: E402
from global_library_mcp.semantic_local import (  # noqa: E402
    LocalSemanticBackend, SemanticBackendUnavailable, cosine_scores)


def _doc_text(rec: dict) -> str:
    return " ".join([rec.get("title") or "", rec.get("author") or "",
                     " ".join(rec.get("subjects") or [])])


def _metrics(order: list[str], rel: list[str]) -> dict:
    out = {}
    for k in (5, 10, 20):
        out[f"recall@{k}"] = len(set(order[:k]) & set(rel)) / len(rel)
    out["precision@5"] = len(set(order[:5]) & set(rel)) / 5
    ranks = [order.index(r) + 1 for r in rel if r in order]
    out["mrr"] = 1.0 / min(ranks) if ranks else 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(order[:10]) if r in rel)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), 10)))
    out["ndcg@10"] = dcg / idcg if idcg else 0.0
    return out


def _rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for i, rid in enumerate(ranking):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + i + 1)
    return sorted(scores, key=lambda r: -scores[r])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dataset", default="fixed")
    args = ap.parse_args()
    corpus = json.loads((ROOT / "eval/b6-corpus.json").read_text())
    cases = json.loads((ROOT / f"eval/b6-{args.dataset}.json").read_text())
    ids = [r["record_id"] for r in corpus]
    texts = [_doc_text(r) for r in corpus]
    scorer = LexicalScorer(texts)

    backend = None
    load_s = None
    encode_ms = None
    doc_vectors = None
    model_dir = os.getenv("GLM_SEMANTIC_MODEL_DIR")
    if model_dir:
        t0 = time.monotonic()
        try:
            backend = LocalSemanticBackend(model_dir)
            load_s = round(time.monotonic() - t0, 3)
            t1 = time.monotonic()
            doc_vectors = backend.encode(texts)
            encode_ms = round((time.monotonic() - t1) / len(texts) * 1000, 2)
        except SemanticBackendUnavailable as exc:
            print(f"semantic backend unavailable: {exc}")

    agg: dict[str, dict[str, list]] = {}
    for case in cases:
        rel = case.get("relevant_record_ids") or []
        if not rel or not all(isinstance(x, str) and ":" in x for x in rel):
            continue
        query = case["query"]
        lex_scores = scorer.score(query)
        lex_order = [ids[i] for i in sorted(range(len(ids)), key=lambda i: -lex_scores[i])]
        orders = {"LEX": lex_order}
        if backend is not None and doc_vectors is not None:
            qv = backend.encode([query])[0]
            sem_scores = cosine_scores(qv, doc_vectors)
            sem_order = [ids[i] for i in sorted(range(len(ids)), key=lambda i: -sem_scores[i])]
            orders["SEM"] = sem_order
            orders["HYB"] = _rrf([lex_order, sem_order])
        for name, order in orders.items():
            m = _metrics(order, rel)
            for key, value in m.items():
                agg.setdefault(name, {}).setdefault(key, []).append(value)
    report = {
        "evaluation_kind": "whole-corpus ranking (b6 simulation corpus)",
        "label_source": "agent_assigned",
        "dataset": args.dataset,
        "model": ({"id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                   "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
                   "file": "onnx/model_quint8_avx2.onnx",
                   "load_seconds": load_s,
                   "encode_ms_per_text": encode_ms}
                  if backend is not None else None),
        "rankers": {name: {k: round(sum(v) / len(v), 4) for k, v in ms.items()}
                    for name, ms in agg.items()},
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
