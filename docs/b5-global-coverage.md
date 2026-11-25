# b5 - Global Coverage (development candidate 1.0.0b5)

Goal: more institutions where bibliographic search, page OCR,
original images, citations and rights arrive as one consistent
chain - not just more searchable catalogues.

## What changed

- **BSB/MDZ adapter (new, live end-to-end verified).** IIIF
  Presentation 2 manifests, per-page hOCR from the documented
  MDZ OCR API, original images via IIIF Image 2, per-item
  rights from the manifest license. Page mapping is proven by
  five agreeing signals (see docs/b5-live-verification.md).
  MDZ publishes no keyword search API, so the adapter is
  ID-addressed; BSB holdings are discovered through DDB.
  In-document search is bounded (20 pages) with explicit
  coverage, because MDZ has no full-text search API and its
  OCR downloads are rate-limited per 24h.
- **LoC Chronicling America (new page capability).** Newspaper
  page OCR via the loc.gov issue JSON (segment-proven mapping)
  and the text-services full text, with IIIF image info checks.
  Applies to Chronicling America only - general LoC remains
  bibliographic. A short page cache keeps verify from
  re-fetching the slow LoC payloads.
- **e-rara adapter (new, metadata by ID).** OAI-PMH GetRecord
  (oai_dc). OAI is harvesting, not search, and no documented
  per-page OCR/IIIF endpoint was confirmed, so page access is
  honestly unsupported. One bounded retry on transient 503.
- **Shared IIIF module** (`iiif.py`): Presentation v2/v3
  parsing, ALTO and hOCR text extraction for all adapters.
- **Transport hardening (section 12 fixtures).** Explicit
  `Accept-Encoding: gzip, deflate`; other encodings refused
  rather than passed through undecoded; truncated compressed
  streams raise instead of yielding partial text; concatenated
  gzip members decode fully; redirects in adapters now go
  through `get_within_domain` (each hop budgeted, cross-domain
  refused). Retry-After behaviour from b4 was re-verified by
  the existing fixture suite.
- **Registry.** The duplicated top-level `notes` key is removed
  and the YAML loader now refuses duplicate keys. Every
  implemented library carries a per-capability
  `capability_status` in the fixed vocabulary; BSB and e-rara
  entries were added (25 registry entries, 8 adapters).
- **Multilingual discovery (section 10).** German umlaut
  transliteration and French/German diacritic folding join the
  Japanese script variants as search-only query expansions.
  Originals are never altered for quotation; admission rules
  are untouched.
- **Routing (section 11).** New adapters are opt-in (not in
  `default_libraries`) until live page verification + terms
  review; explicit user selection is always honoured, and
  failures keep surfacing in `search_scope` with reasons.
- **Comparison (section 15).** `compare_aspect` now computes
  shared/unique terms for 3-4 documents (previously hard-coded
  to exactly two, silently empty otherwise); era-span notes
  generalised. Lexical difference is still not presented as
  semantic disagreement.
- **Web UI (section 16).** A registry-driven library directory
  with region/language filters and an OCR-capable-only filter,
  per-capability status chips, and opt-in checkboxes for the
  ID-addressed adapters. Quick/Standard/Deep and server-side
  cancel are unchanged.

## Not done / not claimed

- No ChatGPT connection, no tunnel, no external transmission.
- Gallica live page verification still blocked by upstream 403
  from this network; Europeana still needs an API key.
- IA full-text still downloads whole djvu files (unchanged).
- AI answering remains experimental; no paid API was used.
