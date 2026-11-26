# Author / title resolution (b6, sections 12-13)

`resolution.py` links a bibliographic record to a lexicon
work or author as a CANDIDATE association with its basis
stated. It exists to group and explain, never to merge:
records keep their own record_id, pages, OCR, years,
translators and citations.

## Works

- `linked`: a lexicon work's original or translated title
  matches the record title (exact, or contained at >=8 chars)
  AND the record author agrees with the work's author (any
  name form, or the surname).
- `refused_author_mismatch`: the title matches but the author
  disagrees (e.g. "Critique of Pure Reason" credited to
  Hegel). Never linked.
- `ambiguous`: the title matches several works.
- `no_match`: nothing claimed.

Work-level grouping separates: same digital item, same
edition candidate (same work + year + language), same work
in another edition/translation, related work, unknown. Only
the first three are computed, from the link plus the record's
own year/language; the rest stay ungrouped.

## Authors

- `linked`: a full name form matches exactly.
- `linked_surname_only`: the surname matches exactly one
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
