# b10 Stage 3 — local semantic search evaluation

Date: 2026-11-28. Brief sections 17–19, 21. Model card:
`docs/b10-model-card.md`. Setting: rank the WHOLE b6 simulation
corpus for each case query (harder than re-ranking a retrieved
subset; this isolates the ranking signal itself). Labels are
agent-assigned proxy labels over a small fixture corpus — the
numbers show the signal's behaviour here, not general
real-world performance.

| Dataset | Ranker | R@5 | R@10 | P@5 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|
| dev | lexical TF-IDF | — | 0.8158 | — | 0.8586 | — |
| dev | semantic (MiniLM-L12) | — | **1.0000** | — | 0.8333 | — |
| dev | hybrid RRF | — | 0.9474 | — | **0.9275** | — |
| fixed | lexical TF-IDF | 0.6310 | 0.7286 | 0.2457 | 0.8560 | 0.6994 |
| fixed | semantic | **0.9286** | **1.0000** | **0.3886** | **0.9238** | **0.9174** |
| fixed | hybrid RRF | 0.8048 | 0.8905 | 0.3314 | 0.8732 | 0.8110 |
| holdout | lexical TF-IDF | — | 0.9333 | — | 0.9000 | — |
| holdout | semantic | — | **0.9667** | — | 0.7856 | — |
| holdout | hybrid RRF | — | 0.9333 | — | **0.9222** | — |

Findings:
- The multilingual embedding model is the strongest single
  discovery signal for cross-language matching in this corpus
  (a Japanese query ranking German/French records it shares no
  tokens with). Lexical TF-IDF cannot cross that gap.
- RRF fusion trades a little recall for better top-rank
  precision (MRR) on dev/holdout, but dilutes the stronger
  ranker on fixed. No fusion is adopted as a new default on
  this evidence alone.
- Integration: `ResearchRanker` accepts semantic scores and
  fuses them under its strict tier when a local backend is
  configured (`GLM_SEMANTIC_MODEL_DIR`); without the model it
  reports lexical/strict only and never claims semantic search
  ran. Embeddings are computed per ranking call on
  bibliographic fields (Stage A scope, section 19); nothing is
  persisted, and no vector DB is created.
- Semantic similarity is a DISCOVERY signal only. It plays no
  part in evidence admission, claim support or citation
  verification (section 46).

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
