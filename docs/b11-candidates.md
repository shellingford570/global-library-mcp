# b11 candidates — Research Validation & Knowledge Synthesis

Tentative, written at the end of b10 (2026-11-28) for a future
decision; nothing here is approved or started.

## Candidates

1. **Independent human evaluation.** Recruit reviewers for the
   b10 dataset's review sheet (`eval/b10-review.csv`) so proxy
   labels can be replaced or validated; report inter-annotator
   agreement before quoting any accuracy figure.
2. **ChatGPT Controlled Pilot** (separate track, separate
   approval): only after DNS pinning is implemented, a
   production IdP is chosen, egress restrictions are verified,
   and the Plus/Pro connection route is re-confirmed from
   current official documentation.
3. **NLI shadow evaluation.** With separate approval for a
   second local model: shadow-score claim–evidence pairs
   against the rule-based mapping; adopt nothing automatically.
4. **Semantic search in the live path.** Move the opt-in local
   embeddings from whole-corpus evaluation into the retrieved-
   subset ranking with the strict tier, measured on the service
   fixture evaluation and live spot checks; keep the model
   optional and the fallback exact.
5. **Authority coverage growth.** NDL authority SPARQL as a
   first-class source (terms already verified), VIAF when the
   network path allows, BnF/LCNAF auxiliaries; grow the lexicon
   from authority data with per-entry provenance instead of
   hand compilation.
6. **Research Workspace synthesis.** Cross-project evidence
   maps, claim dossiers that gather a claim, its candidate
   evidence, contradictions and the researcher's own verdicts;
   export of dossiers to Markdown/CSL.
7. **Kant-class ranking problems.** The remaining live-pool
   noise (notably Internet Archive full-text search) suggests
   per-library result-quality weighting as a ranking input,
   evaluated like b10's ranker comparison before any adoption.

## Standing constraints carried forward

Frozen evidence conditions unchanged; paid LLM use only with
fresh per-run approval; external profile scope changes only
with a dedicated security review; every merge/tag/release a
separate decision.
