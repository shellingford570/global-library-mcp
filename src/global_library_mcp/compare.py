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
        return {"aspect": aspect, "shared_terms": [], "partial_terms": [], "unique_terms": {}}
    token_sets = {label: content_tokens(per_doc_texts[label]) for label in labels}
    shared_set = set.intersection(*(set(tokens) for tokens in token_sets.values())) if token_sets else set()
    shared = sorted(shared_set, key=lambda t: -sum(token_sets[label][t] for label in labels))[:top]
    unique: dict[str, list[str]] = {}
    for label in labels:
        others = set().union(*(set(token_sets[other]) for other in labels if other != label)) if len(labels) > 1 else set()
        unique[label] = sorted(set(token_sets[label]) - others, key=lambda t: -token_sets[label][t])[:top]
    # Terms shared by SOME but not all documents (3+ documents):
    # kept distinct from the all-documents shared set so a partial
    # overlap is never read as a consensus (final review S17).
    partial: list[dict[str, Any]] = []
    if len(labels) >= 3:
        presence: dict[str, list[str]] = {}
        for label in labels:
            for token in set(token_sets[label]):
                presence.setdefault(token, []).append(label)
        partial_candidates = {
            token: docs for token, docs in presence.items()
            if 2 <= len(docs) < len(labels)
        }
        partial = [
            {"term": token, "documents": docs}
            for token, docs in sorted(
                partial_candidates.items(),
                key=lambda item: -sum(token_sets[d][item[0]] for d in item[1]),
            )[:top]
        ]
    return {
        "aspect": aspect,
        "shared_terms": shared,
        "partial_terms": partial,
        "unique_terms": unique,
        "documents_compared": len(labels),
    }


def concept_overlap(per_doc_texts: dict[str, str]) -> dict[str, Any]:
    """Dictionary-based concept correspondence across documents
    (b6, section 25). A shared lexicon concept means the
    documents' texts both contain a label of the same dictionary
    concept - a lexical/dictionary signal only. It does NOT mean
    the documents agree in meaning, and the result always
    carries semantic_comparison: not_checked."""
    from global_library_mcp import lexicon as _lexicon

    per_doc: dict[str, list[str]] = {}
    for label, text in per_doc_texts.items():
        found = {entry["concept_id"] for entry in _lexicon.match_entries(text or "", "concepts")}
        per_doc[label] = sorted(found)
    counts: dict[str, int] = {}
    for concepts in per_doc.values():
        for concept_id in concepts:
            counts[concept_id] = counts.get(concept_id, 0) + 1
    shared = sorted(cid for cid, n in counts.items() if n >= 2)
    return {
        "dictionary_concept_overlap": shared,
        "per_document_concepts": per_doc,
        "possible_related_concepts": shared,
        "semantic_comparison": "not_checked",
        "note": "dictionary concept overlap is a lexical signal; it does not establish semantic agreement",
    }
