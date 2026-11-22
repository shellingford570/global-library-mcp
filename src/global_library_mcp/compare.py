"""Deterministic cross-document comparison helpers.

The comparison is textual, not interpretive: for each aspect it shows
what each document's verified OCR pages actually say (excerpts with
citations), which content tokens the documents share for that aspect,
and which appear in only one of them. Presence/absence of words is a
signal for a human reader, not a semantic verdict; era and context
notes are attached so the reader can judge.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{3,}")
_JA_RUN = re.compile(r"[ぁ-んァ-ヶ一-龥]{2,}")
_LATIN_STOP = {
    "that", "this", "with", "from", "have", "been", "were", "which", "their",
    "there", "would", "about", "other", "these", "those", "under", "after",
    "before", "between", "through", "where", "while", "being", "shall",
}


def content_tokens(text: str) -> Counter:
    """Content tokens: latin words (>=4 chars, minus stopwords) and
    Japanese character bigrams from kanji/kana runs."""
    tokens: Counter = Counter()
    for word in _LATIN_WORD.findall(text or ""):
        lowered = word.lower()
        if lowered not in _LATIN_STOP:
            tokens[lowered] += 1
    for run in _JA_RUN.findall(text or ""):
        for i in range(len(run) - 1):
            gram = run[i:i + 2]
            # Pure-hiragana bigrams are grammatical glue in Japanese
            # prose (particles, auxiliaries); they drown the content
            # signal, so they are skipped. Kanji, katakana and mixed
            # bigrams are kept.
            if all("ぁ" <= ch <= "ん" for ch in gram):
                continue
            tokens[gram] += 1
    return tokens


def compare_aspect(aspect: str, per_doc_texts: dict[str, str], top: int = 8) -> dict[str, Any]:
    """Shared and unique content tokens across exactly two documents."""
    labels = list(per_doc_texts)
    if len(labels) != 2:
        return {"aspect": aspect, "shared_terms": [], "unique_terms": {}}
    a, b = labels
    tokens_a = content_tokens(per_doc_texts[a])
    tokens_b = content_tokens(per_doc_texts[b])
    shared = sorted(set(tokens_a) & set(tokens_b), key=lambda t: -(tokens_a[t] + tokens_b[t]))[:top]
    unique = {
        a: sorted(set(tokens_a) - set(tokens_b), key=lambda t: -tokens_a[t])[:top],
        b: sorted(set(tokens_b) - set(tokens_a), key=lambda t: -tokens_b[t])[:top],
    }
    return {"aspect": aspect, "shared_terms": shared, "unique_terms": unique}
