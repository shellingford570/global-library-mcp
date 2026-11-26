# b6 — Multilingual Research (1.0.0b6 candidate)

Goal: a user asking in their own language discovers materials
recorded in other languages, eras and notations in the
libraries already connected. No new libraries; discovery
quality over coverage counts. Design and evaluation:
docs/multilingual-search-architecture.md, docs/b6-evaluation.md,
docs/search-lexicon.md, docs/author-title-resolution.md,
docs/b6-live-verification.md.

## What shipped

- **Discovery language model** (`discovery.py`):
  `DiscoveryQueryAnalysis`, separate from the admission-side
  `QuestionAnalysis` (untouched). Query language with
  confidence / mixed / unknown states; short proper nouns are
  reported unknown, never forced. Unicode-aware German/French
  concept extraction (the old English path was ASCII-only).
- **Search lexicon** (`data/search_lexicon.json`, loader in
  `lexicon.py`): 61 concepts, 22 authors, 15 works (98
  entries), each with sources and verification status; labels
  in ja/en/de/fr, historical variants, related concepts and
  excluded confusions kept distinct (hydroelectric power vs
  water power are related, never identical).
- **QueryExpansionEngine** (`expansion.py`): typed, reasoned,
  priority-ordered variants (original/translated titles,
  author name forms, concept translations, historical
  spellings incl. kyujitai and historical kana, English
  hyphen/UK-US forms, conservative German compound splits).
  Caps per mode (quick 3 / standard 8 / deep 14) applied after
  priority sort. Ambiguous authors (shared surnames) are
  skipped with the reason recorded. Users can disable
  multilingual or historical expansion.
- **Routing** (service): when the user has not pinned the
  library set, variants are dispatched by language (ja ->
  NDL+IA, en -> LoC+IA+Europeana, de -> DDB+IA+Europeana,
  fr -> Gallica+IA+Europeana); the original query always goes
  everywhere; user-specified libraries are respected in full;
  ID-only libraries are never keyword-searched.
- **Variant ordering fix (live finding)**: engine variants
  run immediately after the full query. Appended last, the
  standard-mode early stop starved them - a live run for
  "19th-century German steam engines" returned only
  same-language noise; after the fix the same run returns
  steam-engine treatises and DDB records found by the English
  variants (36 HTTP requests, inside the standard budget).
- **Resolution** (`resolution.py`): records gain candidate
  work/author links with their basis; author-mismatch and
  shared-surname cases are refused, never linked. Records are
  grouped by linked work for presentation (same-edition
  candidate vs same-work-different-edition/translation);
  records are never merged.
- **DDB -> BSB handoff** (`handoff.py`): a candidate BSB
  object id is extracted only from the official URN in a DDB
  record whose provider is the BSB (00005860); live-verified
  end to end (see b6-live-verification.md). Titles must
  correspond before the link is meaningful, and the BSB
  adapter's strict identity checks still decide at fetch time.
- **LoC newspaper discovery** (`LocAdapter.find_ca_issues`):
  the retired Chronicling America title JSON now redirects
  into loc.gov, so issues are discovered through the official
  LoC search API, keeping only item ids that are structurally
  `<lccn>/<date>/ed-<n>` with the title item as identity
  anchor. Live-verified (45 issues on the first page for
  sn83030214, with the incompleteness stated).
- **Filters**: structured options on research_materials
  (languages, author, title, year range, OCR required) are
  applied locally to fetched candidates and reported with
  metadata-missing counts; unsupported filters are named, not
  silently dropped.
- **Multilingual comparison**: rows now carry
  `dictionary_concept_overlap` (lexicon concepts shared across
  documents) with `semantic_comparison: not_checked` - a
  dictionary signal, never a semantic verdict.
- **Explainability**: the response's `discovery` block lists
  every variant with kind/relation/reason; each material
  names `matched_variant` and `discovery_reasons`. The Web UI
  shows the expansion panel, advanced condition fields
  (author/title/years/document languages/toggles), per-material
  reasons, work candidates, duplicate groups and a BSB handoff
  button wired to the ID-lookup panel.

## Decisions taken on evidence

- **Discovery ranking replacement is opt-in, not default.**
  The ablation (docs/b6-evaluation.md) showed the new scorer
  keeps Recall@10 but lowers MRR against the incumbent
  `rank_candidates` on all three datasets, so the incumbent
  ordering stays and the scorer serves explanations
  (`ranking.score_item`). The replacement remains available
  in `ranking.rank_discovery` for future work.
- **Fixture HTTP attempts grow +51%** (27.4 -> 41.4 dispatches
  per question, fixed set) - the <=+20% provisional aim was
  not met; routing already cut the unrouted figure (64.8) by
  a third. Production wire requests remain hard-capped by the
  unchanged HttpBudget (standard 80 / deep 200), which is the
  operative guarantee. Recorded here per the brief's rule on
  revising targets with reasons.

## Frozen, as required

Evidence admission, temporal anchoring, numeric binding,
page kinds, relevance gate, citation and claim verification
are untouched: question.py's admission analysis, the
admission rule and all Phase 7-10 logic are unchanged, and
the full pre-b6 suite (309 tests) passes unmodified.
No paid LLM/translation calls (0), no external AI
transmission, no new external APIs.

## Final-review round

An external review of the submitted code found release-
blocking defects (Quick ignoring the new options, filters
that were only hints, OCR fetched before filtering, toggle
leaks, permissive linking, string-pattern handoff
identifiers, simulation/production divergence). All were
reproduced, fixed and regression-tested; the full record is
docs/b6-final-review.md, and the evaluation was split into
simulation (A) and real-service fixture evaluation (B) in
docs/b6-evaluation.md. A live follow-up also fixed plan
variants being starved by pool saturation when they
duplicated legacy script variants (明治時代の水力発電 now
surfaces NDL materials at the top).
