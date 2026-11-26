# Authority data research (b6, section 14)

Question: can public authority files supply author name
variants, identity, life dates, original/translated titles and
identifiers for the local search lexicon - and under what
terms? Researched 2026-11-26. VIAF and NDL terms were
re-checked against the providers' own pages today; the other
providers' terms are their long-standing published terms and
must be re-checked before any integration. **b6 integrates
none of them**: the local lexicon stays the source of truth,
per the brief. This document is the evaluation for a future
phase.

## NDL Authorities (Web NDL Authorities, id.ndl.go.jp)
- Content: personal/family/corporate name authorities
  (~1.12M name records), place names, uniform titles, NDLSH
  subject headings, genre/form terms; works authorities are
  offered as bulk files.
- Access: SPARQL endpoint, bulk download files, individual
  download; no registration.
- Terms (provider page, checked 2026-11-26): bibliographic
  and authority data created by the NDL may be used free of
  charge, commercially or not, without application;
  attribution of the source is requested; edited data must be
  marked as edited and must not be presented as NDL-created.
- Fit: best source for Japanese name forms, Japanese uniform
  titles and work authorities. Recommended first candidate.

## VIAF (OCLC)
- Content: clustered name authorities from national
  libraries worldwide; name variants in many languages, life
  dates, links to source authority IDs (GND, LCNAF, BnF, NDL).
- Access: public API and bulk downloads.
- Terms (OCLC pages, checked 2026-11-26): the VIAF dataset is
  available under the Open Data Commons Attribution License
  (ODC-By); attribution in the prescribed form (or use of the
  canonical VIAF URIs) is required.
- Fit: the broadest cross-language name-variant source, and
  its clusters carry the other files' identifiers. Usable
  with attribution handling.

## GND (Deutsche Nationalbibliothek, via lobid.org)
- Content: German authority file - persons, corporate
  bodies, works, subjects; strong for German-language
  scholarship.
- Access: lobid JSON API and SRU; dumps.
- Terms: DNB publishes GND data under CC0 (public domain
  dedication) via lobid; re-check at integration time.
- Fit: best source for German name forms and work titles.
  Recommended alongside NDL.

## Library of Congress Authorities (id.loc.gov)
- Content: LCNAF names, subjects, titles.
- Access: linked-data service with JSON/RDF downloads, SRU.
- Terms: US federal government work, distributed without
  restriction by the Library of Congress; re-check at
  integration time.
- Fit: English name forms and uniform titles.

## ISNI
- Content: cross-domain person/organisation identifiers
  bridging library and rights databases.
- Access: public search; API services exist (some require
  registration/agreement).
- Terms: database rights held by ISNI; API use terms must be
  reviewed before any integration - do not assume bulk reuse
  is permitted.
- Fit: useful as an identifier crosswalk only, after terms
  review.

## BnF authorities (data.bnf.fr)
- Content: French national authority records with ARK
  identifiers; strong French name/title forms.
- Access: data.bnf.fr linked data, SPARQL, dumps.
- Terms: BnF open data is published under the French Licence
  Ouverte (open licence, attribution); re-check at
  integration time.
- Fit: best source for French forms.

## Wikidata
- Content: multilingual labels/aliases for people and works,
  life dates, identifier crosswalks (VIAF/GND/ISNI/LCNAF).
- Access: API and SPARQL endpoint; dumps.
- Terms: CC0.
- Fit: convenient crosswalk and alias source, but community-
  edited: values can be wrong or vandalised, so Wikidata must
  never be the sole basis for an identity link; corroborate
  against a library authority file.

## Conclusions for this project
1. Local lexicon first (b6 ships this). Authority files are a
   future enrichment path, in the order: NDL Authorities
   (Japanese works/names, no key, free terms), GND/lobid
   (German, CC0), VIAF (cross-language clusters, ODC-By
   attribution), then BnF and LCNAF; ISNI only after a terms
   review; Wikidata only as a corroborated crosswalk.
2. Any future lookup must be per-record and cached, inside
   the existing HTTP budget - no bulk synchronisation.
3. Authority data can be wrong or can disagree between
   files. An authority identifier is a strong signal, never
   an unconditional guarantee of identity; the refusal rules
   in resolution.py stay in force.
