# Author / title resolution (b6, sections 12-13)

`resolution.py` links a bibliographic record to a lexicon
work or author as a CANDIDATE association with its basis
stated. It exists to group and explain, never to merge:
records keep their own record_id, pages, OCR, years,
translators and citations.

## Works (status vocabulary tightened in the b6 final review)

Author agreement is equality-based (full name forms, or the
"Surname, Given" catalogue form); substrings never count.
Every result carries `verification_status:
"lexicon_unverified"` — a lexicon match is never
authority verification.

- `candidate_exact_title_and_author`: exact title match and
  full-form author agreement. `work_id` is set (candidate).
- `candidate_title_only`: exact title but the author is
  unchecked or surname-level only; OR the lexicon title is
  merely contained in a longer record title (commentaries,
  studies, reviews). `work_id` is NOT set;
  `candidate_work_id` names the possibility.
- `refused_author_mismatch`: the title matches but the author
  disagrees (e.g. "Critique of Pure Reason" credited to
  Hegel, or to Erasmus Darwin for the Origin). Never linked.
- `ambiguous`: the title matches several works, or the
  surname is shared by several lexicon authors.
- `insufficient_metadata`: no usable title/author to judge.
- `no_match`: nothing claimed.

Work-level grouping separates: same digital item, same
edition candidate, same work in another
edition/translation, related work, unknown. Since the final
review, `same_edition_candidate` requires a known agreeing
year AND language AND at least one agreeing edition-level
field (publisher, place, edition statement, translator,
ISBN) with no conflicting field; conflicts give
`same_work_different_edition_or_translation`, and
insufficient metadata stays `same_work_candidate`. Records
are never merged.

## Authors

- `candidate_exact`: a full name form matches exactly.
- `candidate_surname_only`: the surname matches exactly one
  lexicon author (weak; displayed as candidate).
- `refused_ambiguous_surname`: the surname is shared
  (Darwin x2, Weber x2, Müller x4). Nobody is identified.
- String similarity alone never identifies an author; where
  a record itself carries an authority identifier, that
  identifier outranks this local matching (no current adapter
  supplies one; see docs/authority-data-research.md).

## Editions

A shared work_id never licenses merging page numbers, OCR,
publication years, translators or citation positions across
records. The 1859 and 1872 Origin of Species are one work and
two editions, and the system presents them as such.
