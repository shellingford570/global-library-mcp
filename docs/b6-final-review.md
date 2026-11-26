# b6 Final Review — external-review fixes for v1.0.0b6

This document records the final-review round on PR #17: the external
review findings, how each was reproduced against the submitted head
(`62c7118`), what was changed, and the post-fix measurements. No new
large features were added; the round makes the shipped b6 behaviour
match its documentation.

## Findings, reproduction, fixes

### Quick Search ignored the new options (brief §2) — reproduced, fixed
Reproduction: `research_materials("哲学", mode="quick", author=…,
year_from=…, languages=["en"])` issued only the raw query, returned a
record violating every condition, and reported `discovery=None`,
`filters=None`.
Fix: Quick now builds the same discovery plan as the other modes
(variant cap 3), always executes the original query, applies the
bibliographic filter, never fetches OCR/page text, runs under its own
HTTP budget (30 requests / 15 per host) and reports `discovery`
(planned/executed/variant_execution), `filters` and `http_stats`.
`ocr_required` in Quick is adapter-capability only and says so
(`confirmed_ocr: 0`).

### Author/title "filters" were only search hints (§3) — reproduced, fixed
Reproduction: with `author="Immanuel Kant"`, a Hegel record was kept;
the author string only fed plan generation.
Fix: explicit bibliographic filtering with per-record `filter_match`
(`author_match`: exact_or_variant / surname / fail; `title_match`:
exact / contains / fail). Lexicon name forms widen the match;
missing author/title metadata fails the condition and is counted in
`metadata_missing`. Upstream APIs with native author/title
parameters are not assumed; local filtering is the documented route.

### OCR was fetched before filtering (§4) — fixed structurally
The bibliographic filter now runs on the deduplicated candidate pool
inside `collect_evidence`, before ranking and before any page/OCR
fetching, and its report (`candidates_before/after`, stage
"bibliographic (before OCR fetching)") is what responses publish.
Filtered-out records cannot consume the page budget and cannot make
a result `answerable` (regression-tested both ways).

### Expansion toggles leaked (§5) — reproduced, fixed
Reproduction: with `expand_multilingual=False`, the original title
"Kritik der reinen Vernunft" still appeared as a variant.
Fix: one gating point in the expansion engine — historical variants
are blocked when historical expansion is off, and any variant whose
language is outside the allowed set (target languages ∪ query
language; all four when multilingual is on; query language only when
off) is blocked and recorded in `skipped` with a reason. Legacy b4
script variants follow `expand_historical`; latin variants follow
`expand_multilingual`. All four toggle combinations are tested
against the queries actually sent.
Live follow-up (§27 case 2): plan variants that duplicate legacy
script variants kept their late legacy position and were skipped
when the pool saturated. Plan variants now execute in plan order
regardless of duplication, and the live behaviour flipped: for
明治時代の水力発電 the historical forms now execute first and NDL
records dominate the top ranks.

### Author/work linking was over-permissive (§6) — reproduced, fixed
Reproduction: `resolve_work("Critique of Pure Reason", "")` returned
`linked` (empty author skipped the check);
`resolve_work("On the Origin of Species", "Darwin, Erasmus")`
returned `linked` (substring match).
Fix: resolution is equality-based. Work statuses:
`candidate_exact_title_and_author`, `candidate_title_only`,
`refused_author_mismatch`, `ambiguous`, `insufficient_metadata`,
`no_match`. Author statuses: `candidate_exact`,
`candidate_surname_only`, `refused_ambiguous_surname`, `ambiguous`,
`insufficient_metadata`, `no_match`. A lexicon title merely
contained in a longer record title (commentaries, studies, reviews)
yields `candidate_title_only` with `work_id` unset. Every result
carries `verification_status: "lexicon_unverified"` — the lexicon's
98 entries are all unverified, so nothing is ever presented as
authority-verified.

### Edition candidates (§7) — tightened
`same_edition_candidate` now requires a known agreeing year AND
language AND at least one agreeing edition-level field (publisher,
place, edition statement, translator, ISBN) with no conflicting
field; conflicts yield `same_work_different_edition_or_translation`;
insufficient metadata stays `same_work_candidate`. Records are
never merged.

### DDB→BSB identifier validation (§8) — reproduced, fixed
Reproduction: an MDZ URL embedded in another URL's query string
produced a `candidate`.
Fix: structural validation only. URNs must be complete tokens
matching `urn:nbn:de:bvb:12-bsb<8 digits>-<check>`; MDZ URLs are
parsed — https, host exactly `www.digitale-sammlungen.de` or
`digitale-sammlungen.de`, path `/view/bsb<8 digits>` (optional
language prefix). The provider must come from a structured
`provider_id` or the dataset label's parenthesised code
`(00005860)`. Multiple distinct ids are `refused_ambiguous`.
Upstream URLs are never fetched; only the validated id reaches the
official BSB endpoints. Title correspondence is a weak candidate
signal only (documented as such).

### Empty OCR vs verified mapping (§10) — separated
`get_page_text` responses now carry `ocr_state`:
`page_identity_verified`, `ocr_available`, `ocr_nonempty`,
`image_url_present`, `citation_available` (identity-based).
Materials expose `access_state.ocr_nonempty` and an `ocr_status`
block distinguishing adapter support, per-record availability
(true/false/unknown), fetched, and verified mapping (§12). Empty or
whitespace OCR is never usable original text. The b5 mapping checks
themselves were not loosened.

### Language filter normalisation (§11) — fixed
New `languages.py`: ISO 639-1/-2/T/B codes, English names, endonyms
and Japanese names normalise to ISO 639-1; string, list and compound
metadata values are handled; unknown stays unknown and never counts
as a match (`language_matches` returns True/False/None). The raw
metadata value is preserved; `language_normalized` is reported per
material.

### Routing (§13) — fixed
Europeana is routed only when `EUROPEANA_API_KEY` is configured;
otherwise it is omitted and `routing_skipped.europeana` records
"authentication pending". ID-only libraries are never
keyword-routed. Routed dispatches respect libraries already tripped
by repeated failures in the same search.

### Planned vs executed (§14) — fixed
Responses distinguish `planned_variants`, `executed_variants` and
per-variant `variant_execution` (text, status
executed/cached/skipped, libraries, new records, errors, skip
reason). The Web UI marks each planned variant 実行済み/未実行 and
lists routing skips.

### Lexicon quality gates (§23) — added
Load-time validation: unique ids, valid language keys, no empty
surfaces, no duplicate surfaces within one list, `source` required,
`verification_status` ∈ {unverified, verified}, work→author
reference integrity, author surnames present, original languages
normalisable, no concept self-reference. The gates caught one real
data bug (a duplicated 日本語 label in `concept:linguistics`),
fixed in the data. Candidates generated from the lexicon inherit
its verification status.

### Comparison (§24)
`concept_overlap` now also reports `shared_by_all_documents` vs
`shared_by_some_documents` for 3–4 document comparisons.
`semantic_comparison: "not_checked"` is unchanged.

## Evaluation after the fixes

Two evaluations are kept strictly separate (see
docs/b6-evaluation.md for full tables, denominators and hashes):

- **Evaluation A** (variant-generation simulation over the fixed
  51-record corpus, agent-assigned labels): shipped configuration F
  on the fixed set — Recall@10 0.9097 (denominator 36 of 40 cases;
  4 negative cases), MRR 0.8657, cross-language discovery 0.6111,
  average simulated attempts 38.2 (b5 baseline A: 27.4; +39% — the
  +20% effort target is still not met; the production HTTP budget
  is unchanged and hard). The experimental discovery ranker (Gx)
  remains unshipped: MRR 0.8528 fixed / 0.8276 dev / 0.7552 holdout,
  below the shipped ordering on all three sets, now reproducible
  from `eval/b6_engine_configs.py`.
- **Evaluation B** (the real `LibraryService` over fixed HTTP
  fixtures, 10 fixed-set cases): Quick Recall@10 0.500 at 12.6 real
  HTTP requests per case; Standard Recall@10 0.7667 at 24.6
  requests; warm-cache rerun produced 5 bibliographic cache hits in
  Standard (Quick does not use the bibliographic cache). The
  author-filter check passes under production filter semantics
  (an earlier naive substring check in the harness itself was the
  §15-class defect; it was fixed to read the production
  `filter_match` record). Fixture elapsed times (≈11.7s Quick /
  ≈19.8s Standard per case) are dominated by per-library deadline
  waits against fixtures and are not live timings.
- **Challenge set** (20 cases fixed before the fixes, including
  same-surname authors, original vs commentary, same-year different
  editions, wrong-premise and no-material negatives): F Recall@10
  0.9167, attempts 36.6 (pre-fix 39.6), false_candidate_rate 0.5
  (1 of 2 negative cases retrieves candidates — discovery retrieves;
  premise certification remains the frozen admission layer's job).

## Live re-verification (limited, §27)

- German steam (case 1): `Dampfmaschine` executed against DDB;
  DDB records enter the pool; top ranks are taken by NDL
  historical-script hits and IA (ranking is the unchanged b5
  order). LoC hit its 10s search deadline (partial); Gallica 403
  (not retried).
- Historical Japanese (case 2): after the ordering fix, historical
  variants execute first; NDL materials dominate (発電水力…,
  新編水力発電, 松花江水力發電計畫概要).
- Kant (cases 3/4): variants executed in four languages; NDL Kant
  studies are not work-linked; an IA commemoration volume was
  `refused_author_mismatch`. The Kritik itself did not reach the
  top 10 in the sampled run — a ranking limitation, recorded as
  such.
- Wrong author (case 7): author=Hegel filter cut 70 candidates to
  the 3 Hegel records (6 missing-author records counted and
  excluded); `resolve_work` refuses Kant+Hegel.
- DDB→BSB (case 5): bsb11650472 (Reuleaux, Kurzgefaßte Geschichte
  der Dampfmaschine, 92 pages) — document retrieval, page identity
  verified on pages 1–6, OCR non-empty on 5 of 6 (page 4 empty),
  `verify_page` = verified including a real image fetch (HTTP 200,
  JPEG). Identifier handoff, bibliographic correspondence, page
  identity, OCR presence and image reachability are reported as
  separate facts; the earlier candidate run's checked page had
  empty OCR, so no end-to-end OCR claim is made for that page.
- LoC chain (case 6, §21): New-York Tribune — 45 issues found via
  the official LoC search API; issue sn83030214/1917-09-02/ed-1
  (12 pages); page seq-1 OCR non-empty (901 chars), identity
  verified, image service reachable and identity-verified,
  citation available; `verify_page` = verified. Search-to-evidence
  admission remains unverified (the frozen admission layer is a
  separate step).

## Not changed

Evidence admission, temporal anchoring, numeric binding, page
kind, relevance gate, citation/claim verification — all frozen.
`QuestionAnalysis` untouched. No paid LLM or translation calls
(0). MCP tool counts unchanged (15 full / 14 research).

## Remaining limitations

Lexicon is initial-scale and unverified; ranking is the b5 order
(the discovery ranker was rejected on measured MRR); live top-rank
quality varies by library responsiveness (LoC deadlines, Gallica
403 from this network); Europeana awaits an API key; BSB/e-rara
are ID-centred; IA in-document search still downloads full djvu
files; the fixed-corpus evaluations use agent-assigned labels and
are not live-search accuracy.
