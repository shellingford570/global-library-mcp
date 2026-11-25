# Library coverage roadmap (b5, section 14)

How to read this: "registry" counts institutions with a research
entry in libraries.yaml (25 after b5). It is NOT a count of
usable libraries. Usable today: 8 adapters (loc, ndl, gallica,
internet-archive, ddb, europeana, bsb, e-rara), of which page
OCR + original verification are live-verified for NDL, Internet
Archive, BSB/MDZ, and LoC (Chronicling America newspapers only).

## Priority candidates for the next phase

Ranked by the brief's criteria (page-level OCR availability,
original-image correspondence, official API stability, terms
clarity, auth friction, scholarly value, diversity, load,
implementation difficulty). All entries are research notes, not
live verifications.

1. **Gallica / BnF (already implemented)** - SRU + IIIF + ALTO
   stack is built and fixture-verified; only the upstream 403
   from this network blocks live page verification. Highest
   value per effort: re-verify from an allowed network.
2. **National Library of Finland (Finna)** - public API plus
   IIIF-served digitised books/newspapers; strong Nordic
   diversity gain. Needs terms + endpoint verification.
3. **Digital Public Library of America** - free API key,
   metadata aggregation with IIIF links to providers; page OCR
   depends on the providing institution, so it is a discovery
   layer more than a page source.
4. **KB / Delpher (Netherlands)** - IIIF-based newspaper/book
   platform; promising for page OCR; API terms to confirm.
5. **Biblioteca Nacional de España** - digital collections with
   IIIF presence; endpoint stability to confirm.
6. **Austrian National Library (ANNO/QuickSearch)** - strong
   newspaper corpus; interface terms to confirm.
7. **HathiTrust** - Data API exists but access is constrained
   (pairtree/bibliographic APIs public; full-text data is
   restricted); realistic scope is bibliographic + page images
   for public-domain volumes via the Data API terms.
8. **Trove (National Library of Australia)** - API key required
   (free for research use historically); newspapers are a major
   strength; key issuance is a separate approval step.
9. **Japan Search** - SPARQL/IIIF aggregation for Japanese
   cultural heritage; complements NDL rather than duplicating it.
10. **National Library of Korea / Taiwan NCL / NDLI / NLB
    Singapore / NLC China** - API or key requirements vary and
    several need registration; keep as research entries until a
    specific scholarly need prioritises one.

## Explicitly not planned

- Scraping providers that offer no official API.
- Bulk harvesting (OAI sets, IIIF collections) - discovery is
  query-driven and budgeted by design.
- Any provider whose terms prohibit the intended use.
