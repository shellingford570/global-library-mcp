# Internet Archive取得効率の調査 / IA Fetch-Efficiency Research

Question (b4, Section 9): can the Internet Archive adapter avoid
downloading a whole `djvu.xml` (observed up to ~46 MB per item)
for in-document search and single-page text?

Researched 2026-11-25 against official/primary sources. Only
officially provided mechanisms were considered.

## What exists

1. **Item files (current method).** `djvu.xml` / `djvu.txt` from
   the item's file listing. Complete and provenance-friendly (the
   file name is recorded and the page mapping is verified against
   the metadata), but all-or-nothing per item.
2. **BookReader page images.** Per-page JPGs
   (`/download/{id}/page/n{leaf}.jpg`) — already used for original
   page display. Images only, no text.
3. **Archive Labs experimental Book APIs**
   (`api.archivelab.org`, documented in the Internet Archive
   Developer Portal's "Experimental Book APIs"):
   - `GET /books/:itemid/searchinside?q=` — in-book search with
     page numbers, surrounding text and region coordinates.
   - `GET /books/:itemid/pages/:page/ocr` — **per-page OCR** with
     region coordinates.
   - `/books/:itemid/pages`, `/pages/:page` (image),
     `/ia_manifest`, `/iiif_manifest`.
4. **Cross-item full-text search** (the index behind
   archive.org's text search): returns page-level snippets across
   items. Useful for discovery, but snippets are not a
   provenance-checked page text source.

## Verification attempt (2026-11-25)

All three Archive Labs endpoints (book, per-page OCR,
search-inside) were probed for a known public item
(`in.ernet.dli.2015.202535`) from this environment: every request
failed at the connection level (no response). Whether the service
is down or unreachable from this network could not be determined.

## Findings and decision

- The Archive Labs APIs are labelled **experimental** by the IA
  Developer Portal itself, carry no stability commitment, and
  could not be verified at all from here. Building the evidence
  path on them now would trade a known-good provenance chain for
  an unverifiable one.
- Their page numbering semantics (reader page index vs. djvu
  leaf) would still need a mapping verification layer before any
  page could be called "verified" — the same problem the current
  adapter solves from metadata.
- HTTP Range requests against `djvu.xml` cannot reliably extract
  a specific page: XML is a single sequential document, a byte
  range has no page alignment, and a partial document cannot be
  parsed as XML. Not adopted.
- Restriction safety: any search-inside style endpoint must only
  ever be queried **after** the metadata restriction check the
  adapter already performs; nothing in this research changes the
  rule that lending-restricted items are refused.

**Decision: keep the current fetch method** (full djvu download
under the streaming caps, with per-item dedupe locks, TTL'd
caches, and safe abort + original-link fallback on oversize).
Revisit the Archive Labs per-page OCR endpoint if it becomes
reachable and its experimental status changes; the adapter's
provenance fields already record which file a page came from, so
a future per-page source can be added without changing the
evidence model.
