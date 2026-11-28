# b10 Stage 3 — ranking, hybrid search, adaptive planning

Date: 2026-11-28. Brief sections 10, 17–22, 44.

## The fixed-set gap was retrieval, not ranking

Stage 1 had left b6 fixed F Recall@10 at 0.8819 against the
0.9097 target. Per-case diagnosis in Stage 3 showed the missing
records were never retrieved: the simulation routed variants by
detecting language from variant TEXT, misrouting single words
("Dampfmaschine" → English route → never sent to ddb). The
harness now uses the expansion plan's language field, exactly
like production routing; a missing lexicon label
(`Wasserkraft` for hydroelectric power, German) was added.
Result under the adopted allocation A: **fixed 0.9167,
challenge 1.0000, b8 standard 0.7667, cross-language 0.7500** —
all section-43 multilingual targets met; simulated attempts
fell from ~40 to 33.4. Full record:
`docs/b10-multilingual-routing.md` addendum.

## Ranker comparison (retrieval held constant)

`eval/b10_ranking_compare.py` over the b6 simulation corpora
(config F retrieval), rankers: R0 = incumbent
`service.rank_candidates`, R1 = b6 discovery scorer,
R2 = new `ResearchRanker` (strict tier + lexical TF-IDF fusion,
OCR demoted to a usability subscore).

| Corpus | Ranker | R@5 | R@10 | P@5 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|
| fixed | R0 | 0.9167 | 0.9167 | 0.3944 | 0.8519 | 0.8266 |
| fixed | R1 | 0.9028 | 0.9167 | 0.3889 | 0.8657 | 0.8423 |
| fixed | R2 | 0.8889 | 0.9167 | 0.3833 | 0.8565 | 0.8501 |
| challenge | R0 | 1.0000 | 1.0000 | 0.2444 | 0.8611 | 0.9000 |
| challenge | R2 | 1.0000 | 1.0000 | 0.2444 | 0.9074 | 0.9347 |
| dev | R0 | 0.9474 | 1.0000 | 0.2421 | 0.9263 | 0.9243 |
| dev | R2 | 0.9342 | 1.0000 | 0.2421 | 0.8831 | 0.8964 |
| holdout | R0 | 0.9375 | 0.9375 | 0.2375 | 0.8594 | 0.8618 |
| holdout | R2 | 0.9062 | 0.9375 | 0.2250 | 0.8125 | 0.8309 |

Recall@10 is identical everywhere (retrieval-bound). R2 wins
nDCG on fixed/challenge but loses Recall@5 and holdout MRR.
**Decision (section 44): the incumbent ranker stays the
default.** ResearchRanker ships as an opt-in component
(`GLM_RESEARCH_RANKER=1` in the service search path) that also
attaches per-item `ranking_reasons` (section 22) when enabled;
its strict-tier rule and reasons are unit-tested. This is
reported as a non-adoption, not dressed up as an improvement.

## Adaptive search planning (section 10)

Implemented in `LibraryService.collect_evidence` alongside the
existing pool-saturation early stop: in standard mode, once the
pool holds a strict title-tier match (exact original/translated
title or full-query title hit) and at least 3 candidates, with
no engine variants still pending, the remaining expansion
variants are skipped and the stop is recorded as
`adaptive_stop` in the coverage report. The original query
always runs; the stop never asserts that no more relevant
records exist. Effect measured on the fixture service
evaluation (see `docs/b10-evaluation.md`): HTTP attempts and
recall reported before/after; the fixture queries are mostly
concept questions, so strict matches are rare there and the
saving is correspondingly small — the mechanism matters for
author/work-shaped live queries.

## Historical notation (section 16)

The expansion engine's historical layer (b6) already covers
旧字体・歴史的仮名遣い (ja), umlaut/transcription and compound
forms (de), accent/ligature folding (fr) and英米綴り (en);
Stage 2 added katakana name forms, hiragana readings and
old/new-script author forms to the lexicon. Normalisation is
search-side only: stored OCR text, original titles and verbatim
quotes are never rewritten.

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
