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
    """Shared and unique content tokens across 2-4 documents.

    Shared terms occur in EVERY compared document; a document's
    unique terms occur in that document and in no other. This is a
    lexical signal only - it does not establish that the documents
    agree or disagree in meaning (b5, section 15)."""
    labels = list(per_doc_texts)
    if len(labels) < 2:
        return {"aspect": aspect, "shared_terms": [], "unique_terms": {}}
    token_sets = {label: content_tokens(per_doc_texts[label]) for label in labels}
    shared_set = set.intersection(*(set(tokens) for tokens in token_sets.values())) if token_sets else set()
    shared = sorted(shared_set, key=lambda t: -sum(token_sets[label][t] for label in labels))[:top]
    unique: dict[str, list[str]] = {}
    for label in labels:
        others = set().union(*(set(token_sets[other]) for other in labels if other != label)) if len(labels) > 1 else set()
        unique[label] = sorted(set(token_sets[label]) - others, key=lambda t: -token_sets[label][t])[:top]
    return {"aspect": aspect, "shared_terms": shared, "unique_terms": unique, "documents_compared": len(labels)}
