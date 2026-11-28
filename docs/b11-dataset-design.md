# b11 Dataset Design (sections 15-19)

## Immutability
Existing datasets (b6, b8, b10) are untouched. Expectations are
never rewritten; the b11 set is a separate file
(`eval/b11-cases.json`, 294 cases at build time) produced by
`eval/b11_dataset.py`.

## Composition
- 260 carried-over b10 cases (expectations verbatim; original
  provenance preserved in `original_provenance`).
- 13 new author-identity cases: 6 GND confirmations + 7 attempted
  but unconfirmed authors.
- 21 new proxy cases for numeric comparison, missing conditions,
  claim-evidence, source independence and report integrity
  (all `agent_assigned`).

The brief's ~330-case figure is a target, not a quota: **294
cases** were produced. Quality and source-verifiability were
prioritised over count; no OCR/page ground truth was invented for
originals that were not obtained.

## Provenance (section 19 vocabulary)
`agent_assigned` / `bibliographic_source_supported` /
`authority_source_supported` / `original_page_checked` /
`human_reviewed` / `independent_human_verified` /
`conflicting_review` / `unresolved`.

Counts at build: agent_assigned 281, authority_source_supported
6, unresolved 7, human evaluation **0**.

Important correction carried from b10: the frozen b10 dataset
files still claim `bibliographic_source_supported` for 68 cases,
but the b10 final-review re-audit reduced genuinely
source-supported labels to 21 of 260 without annotating which.
b11 therefore does NOT inherit the claim: carried cases are
`agent_assigned` in b11 with the original claim preserved
verbatim. Official-source confirmation by the agent is not human
evaluation; `independent_human_verified` is used only when a
human actually reviewed the case (none at b11).

## Additional source confirmations (section 16, target +50)
Method: lobid GND exact preferredName + birth-year match against
the lexicon (existing key-free API, 14 queries). Confirmed (+6):
Marx 118578537, Descartes 118524844, Spencer 118616080, Adam
Smith 118615033, Hugo 118554654, Nishida Kitaro 118588230.
Attempted and NOT confirmed by this method (transliteration/name
forms or namesake crowding): Einstein, Hegel, Goethe, Nietzsche,
Herschel, Dostoevsky, Tolstoy - they remain `unresolved`. The
+50 target was **not reached** (6 achieved); no mass crawling was
performed and unconfirmed items stay unconfirmed.

## Grouped splits (section 18)
`eval/b11_grouped_splits.py`: connected components over shared
person/work/concept/document/source-family entities; split by
`sha256(seed|component_key) mod 3`, seed 20261128. Result:
dev 109 / fixed 95 / holdout 90 cases, 282 components,
cross-split entity overlap **0** (by construction and measured).
Dataset SHA-256 is recorded in `eval/b11-grouped-splits.json`.
