# Citation export formats (b7)

All exporters are deterministic template code. Unknown
fields are omitted, never invented; candidate work/author
ids are never exported as authority data. Excerpts pass the
rights gate again at export time; omissions are counted
with reasons in the JSON export and listed in Markdown
reports.

## BibTeX

Classic **BibTeX** (not BibLaTeX), UTF-8. Types: `@book`
(default for titled records), `@article` (articles and
newspapers), `@manual`, `@misc`. Fields: title, author
(`and`-joined), year (only when a 4-digit year is present
in the recorded date), publisher, address, edition,
translator, volume, isbn, doi, url, urldate, language.
Citation keys are derived from the record itself
(author-slug + year + first title word) so re-exporting the
same document yields the same key; collisions inside one
export set get deterministic a/b suffixes. Values are
escaped in a single pass (backslashes become
`\textbackslash{}`, braces/&/%/#/_ are escaped), and
newlines are flattened, so stored metadata cannot smuggle
TeX commands into an export.

Verification: the output was parsed by the independent
`bibtexparser` 2.1.0 (3 entries incl. a Japanese record and
a newspaper-as-@article, 0 failed blocks).

## RIS

Standard tag set (TY/TI/AU/PY/PB/CY/ET/VL/SP/EP/DO/SN/UR/
LA/N1/ER). Types: BOOK/JOUR/NEWS/MANUAL/GEN. Every value is
forced onto one physical line — CR/LF are stripped — so
stored metadata cannot inject extra records or tags
(unit-tested). UTF-8 throughout.

## CSL JSON

Follows the CSL input schema: id (the same stable key),
type (book / article-journal / article-newspaper /
document), title, author/translator as `{family, given}`
only when the split is safe ("Surname, Given" or two-token
names); CJK and multi-token names use `{literal}`. `issued`
carries date-parts only when a year is known; `accessed`
comes from the recorded retrieval date. Publisher,
publisher-place, edition, volume, page, DOI, ISBN, URL,
language are included when present.

## Plain text

A simple author 『title』 year publisher [key] URL line.
This is NOT APA/Chicago/MLA; no strict style conformance is
claimed for any style in b7.

## Zotero compatibility (brief section 45)

Implemented for format compatibility with Zotero's
BibTeX/RIS/CSL-JSON import paths, based on the public
format specifications. **A real Zotero import was not
performed** in b7 (no Zotero account connection, no writes
to any Zotero library — both are outside the approved
scope). The BibTeX parse check above used bibtexparser, an
independent parser, not Zotero itself. Treat "Zotero
compatible" as "standards-conformant export, parser-checked"
until an isolated local Zotero import test is run.

## Final review corrections (v1.0.0b7 release)

- Citation keys are stored per document at save time and
  never change when other documents are added or removed;
  they survive JSON migration.
- Unknown material types stay generic (BibTeX `@misc`,
  RIS `GEN`, CSL `document`) instead of being forced to
  book; newspapers use BibTeX misc / RIS NEWS / CSL
  article-newspaper. Full dates are kept, pre-1500 years
  are kept, and BCE/unparseable dates are never fabricated
  into years. Organisation authors remain CSL literal.
- BibTeX is parse-checked with an independent parser
  (bibtexparser); RIS and CSL JSON are validated
  structurally in tests. Zotero real-application import
  has NOT been performed.
- Markdown reports escape all stored text (headings,
  links, images, fences, HTML) and re-gate excerpts
  against current rights at export time.
