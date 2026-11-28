"""Local lexical relevance (b10 Stage 3, brief section 17).

A dependency-free TF-IDF scorer over word tokens and character
3-grams, fitted per result set. It is the always-available local
baseline for hybrid ranking: no model download, no network, no
telemetry. Character n-grams make it robust to historical
spellings, OCR noise and German compounds; word tokens keep
exact-term matches sharp.

Scores are relative to the fitted candidate set (0..1 after
max-normalisation) and mean "lexically close to the query within
this result set" — never factual support (brief section 46).
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

_FOLD = str.maketrans({
    "ä": "a", "ö": "o", "ü": "u", "ß": "ss", "é": "e", "è": "e",
    "ê": "e", "à": "a", "â": "a", "î": "i", "ô": "o", "û": "u",
    "ç": "c", "ñ": "n", "ø": "o", "å": "a", "æ": "ae", "œ": "oe",
    "ō": "o", "ū": "u", "ā": "a", "ī": "i", "ē": "e",
})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().translate(_FOLD)
    return re.sub(r"\s+", " ", text).strip()


def _features(text: str) -> Counter:
    text = normalize(text)
    feats: Counter = Counter()
    tokens = [t for t in re.split(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]+", text)
              if len(t) >= 2]
    for tok in tokens:
        feats[f"w:{tok}"] += 1
        # CJK text has no word boundaries; character bigrams are
        # the working unit there.
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", tok):
            for i in range(len(tok) - 1):
                feats[f"c:{tok[i:i + 2]}"] += 1
    compact = re.sub(r"[^a-z0-9]", "", text)
    for i in range(len(compact) - 2):
        feats[f"g:{compact[i:i + 3]}"] += 1
    return feats


class LexicalScorer:
    """TF-IDF cosine over a fixed document set."""

    def __init__(self, documents: list[str]):
        self._docs = [_features(d) for d in documents]
        df: Counter = Counter()
        for doc in self._docs:
            for feat in doc:
                df[feat] += 1
        n = max(len(documents), 1)
        self._idf = {f: math.log((n + 1) / (c + 1)) + 1.0 for f, c in df.items()}
        self._norms = [self._norm(d) for d in self._docs]

    def _vec(self, feats: Counter) -> dict[str, float]:
        return {f: (1.0 + math.log(c)) * self._idf.get(f, 1.0)
                for f, c in feats.items()}

    def _norm(self, feats: Counter) -> float:
        vec = self._vec(feats)
        return math.sqrt(sum(v * v for v in vec.values())) or 1.0

    def score(self, query: str) -> list[float]:
        q = self._vec(_features(query))
        qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
        out: list[float] = []
        for doc, dn in zip(self._docs, self._norms):
            dv = self._vec(doc)
            dot = sum(q[f] * dv.get(f, 0.0) for f in q)
            out.append(dot / (qn * dn))
        peak = max(out) if out else 0.0
        if peak > 0:
            out = [v / peak for v in out]
        return out


def item_text(item: Any) -> str:
    parts = [getattr(item, "title", "") or "",
             getattr(item, "author", "") or ""]
    subjects = getattr(item, "subjects", None)
    if subjects:
        parts.append(" ".join(subjects))
    else:
        parts.append(getattr(item, "description", "") or "")
    return " ".join(p for p in parts if p)
