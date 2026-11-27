# b10 candidates — Advanced Research Intelligence (design only)

Status: **design document only.** b10 implementation has not
started and needs its own approval. Candidate version:
v1.0.0b10 "Advanced Research Intelligence".

## Purpose

Deepen research quality on top of the b1–b9 foundation:
discovery across languages and eras, authority control for
authors/works/editions, and structured claim–evidence
verification — without loosening the frozen evidence-admission
conditions and without paid/external services unless
separately approved.

## Candidate features

1. **Multilingual semantic search** — cross-language retrieval
   beyond the current lexicon expansion (e.g. a local
   embedding model), evaluated against the fixed corpora.
2. **Re-ranking of search candidates** with measured
   before/after Recall@10 on BOTH the b6 and b8 fixed sets.
3. **Multilingual expansion rebalance (carried from b9
   section 5.4)** — the b8 lexicon additions (fi/sv/nl)
   compete with ja/en/de/fr under the unchanged variant caps
   in the default mode; b6 fixed F Recall@10 measured 0.8819
   at b8 (b6 release: 0.9097). Any fix must not raise HTTP
   budgets or caps silently, must preserve the guarantee that
   the original query always runs, and must be validated on
   both corpora plus the b8 set before adoption — the b8
   section-19 experiment showed reorderings trade one corpus
   against another.
4. **Authority verification for authors / works / editions** —
   link records to NDL authorities, GND, VIAF where official
   APIs and terms permit.
5. **Original-title / translated-title discovery** improvements
   (the Kant 『純粋理性批判』 ranking limitation is the standing
   test case).
6. **Historical orthography search** — variant forms for
   historical scripts and spellings.
7. **Local embedding model** evaluation (no external embedding
   API without approval).
8. **Multilingual document comparison** across languages.
9. **Structured historical claims** — claim objects with
   subject/predicate/time/place, matched to evidence.
10. **Claim–evidence correspondence and strict verification**
    of era, numerals and proper nouns (within the frozen
    admission rules).
11. **Contradiction detection between documents.**
12. **Original/translation alignment** at page level.
13. **Staged integration of investigation results** and
    **search-plan auto-optimisation** under the existing HTTP
    budgets.
14. **Multi-document evidence verification.**
15. **Zotero real-application import verification** (the b7
    leftover: exports were format-checked only).

## Explicitly not authorised by this document

Paid LLM use, external translation APIs, public deployment,
external-AI submission of research data, and any loosening of
evidence admission, temporal anchoring, numeric binding, page
kind, relevance gate, citation/claim verification,
insufficient_evidence or answer_withheld.
