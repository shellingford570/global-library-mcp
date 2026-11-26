# Search lexicon (b6)

`src/global_library_mcp/data/search_lexicon.json` - the local,
version-controlled dictionary used for search expansion.

## Contents (1.0.0b6)

61 concepts, 22 authors, 15 works (98 entries), covering the
brief's initial domains: history of science and technology,
railway history, hydroelectric power, steam engines,
industrial revolution, philosophy, history of religion,
political thought, astronomy, biology, history of medicine,
economic history, literary history, newspaper history.

## Entry fields

- Concepts: concept_id, domain, labels per language
  (ja/en/de/fr), historical_variants per language, related
  (concept ids - suggestions, not synonyms),
  excluded_confusions (concept ids that must NOT be merged),
  source, verification_status.
- Authors: author_id, surname, given_names, birth/death
  years, name forms per language, known_works,
  authority_ids (viaf/gnd/ndl/isni/wikidata - currently
  unrecorded; see docs/authority-data-research.md), source,
  verification_status.
- Works: work_id, original_title, original_language,
  author_id, year_first, translated_titles per language,
  editions_note, source, verification_status.

## Sources and licence

Compiled for this project from standard public bibliographic
knowledge (title pages and publisher data). Names and titles
are bibliographic facts; no copyrighted dictionary data was
copied. Entries are marked `unverified` until checked against
an authority file; the loader rejects duplicate ids, dangling
references and label-less concepts so a bad edit fails tests
instead of silently degrading search.

## Maintenance

Add entries through the same JSON, keeping: one concept per
meaning (split near-synonyms and cross-link them as related +
excluded_confusions), historical forms only where attested,
and a source note for anything non-obvious. Grow by quality
of distinction, not by count.
