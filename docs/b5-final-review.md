# b5 final review - findings, reproductions, fixes (2026-11-26)

An external review of PR #16 (at e3dd449) found defects in the
first b5 candidate. Each finding was reproduced against the
code before being fixed; the regression tests live in
tests/test_b5_final_review.py (63 tests) and the Playwright
additions in tests/e2e/search.spec.js.

## P0 findings and fixes

### S2/S3 - BSB page mapping was weaker than reported
Reproduced: verified_mapping required only canvas/service
suffix matches and a substring search for the hOCR title in
the first 600 characters; the manifest OCR link was recorded
but not required; verify_original never looked at OCR at all
and accepted any HTTP 200/206 as an image.
Fix: all checks are structural URL parses - the manifest @id
must carry the object id as a path segment; the canvas @id
must carry it and end with the exact segments canvas/{n}; the
image service id's final segment must be exactly
{object_id}_{n:05d}; the manifest seeAlso OCR link must parse
to exactly /ocr/{object_id}/{n} on the MDZ host; the hOCR
<title> element is parsed (new iiif.hocr_title) and must equal
{object_id}_{n:05d}. Constructing the URL is no longer counted
as a signal. verify_original reuses the get_page_text result
(they cannot disagree) and fetches a small IIIF rendition,
requiring an image signature/Content-Type - an HTML error page
with HTTP 200 fails. Negative tests: other object's canvas,
other object's service, wrong manifest, missing OCR link, OCR
link for another page, title mismatch, HTML image, and the
page-unverified/verify-verified contradiction case.

### S4 - SSRF surface on upstream-supplied URLs
Reproduced: BSB fetched the manifest's image_url directly;
LoC accepted any host ending in "loc.gov" for the full-text
URL; get_within_domain checked only the registrable domain.
Fix: http.validate_fetch_url + fetch_validated - https only,
no embedded credentials, port absent-or-443, IP literals must
be public (loopback/private/link-local/reserved/multicast and
ambiguous integer/hex forms refused), localhost refused, and
exact host allowlists per adapter (BSB: api.digitale-
sammlungen.de; LoC text/image: tile.loc.gov + www.loc.gov).
get_within_domain now validates the initial URL and EVERY
redirect hop (an https->http downgrade fails the scheme
check), keeps the same-registrable-domain rule, and strips
Authorization/Cookie when the host changes. Every hop remains
a budgeted request. DNS: check_dns_public refuses when any
resolved address is non-public; it runs when GLM_DNS_CHECK=1.
Stated scope: a DNS pre-check cannot fully prevent rebinding
(TOCTOU; httpx has no address pinning), and behind an
HTTP(S) proxy resolution happens at the proxy - the always-on
controls are the structural checks, allowlists and redirect
confinement. NDL/IA/Gallica/DDB/Europeana were audited: they
fetch only URLs constructed from validated ids on fixed hosts
(IA/Gallica via get_within_domain), so no payload-derived URL
is fetched there.

### S5/S6 - LoC Chronicling America mapping and image checks
Reproduced: sp was a substring check (sp=2 matched sp=20);
single-segment and image-info presence were recorded but not
required; verify_original treated a reachable info.json as a
reachable image.
Fix: sp is compared as a parsed query value; exactly one
segment is required; the item id must end with the issue path
(lccn/date/edition); the segment_id must contain the lccn and
the issue's compact date; the text-services URL must be on an
allowlisted host with its segment query parameter exactly
equal to the segment_id; the returned entry must be keyed by
that segment_id with non-empty text; the IIIF info URL's
service identifier must equal the segment_id transformed to
the service form. verify_original separates
image_service_reachable, image_service_identity_verified
(info.json @id equals the payload's service), image_reachable
(a real small image, signature-checked), page_mapping_verified
and ocr_available; verified requires mapping + identity +
real image.

### S7/S8 - BSB results did not reach the service pipeline
Reproduced: BSB returned {hits: [...]}, while the service
reads matches.list[].id - BSB hits were invisible to
research_materials, get_verified_evidence and
compare_documents. The service's per-host budget for
in-document search was 8, below BSB's 20-page window.
Fix: a common schema (service._canonical_in_document_result)
with matches.list entries carrying id/page_id/record_id/
match_id/snippet/score/digital_frame/printed_page/
mapping_status plus pages_searched/total_pages/complete/
partial_failures; BSB returns it natively (the old "hits" key
is kept as an alias). The service budget for in-document
search is now 30 requests / 25 per host. BSB search keeps
partial results on failure or budget exhaustion, reports the
searched range, and accepts start_page/end_page windows
(still capped at 20 pages per call). DDB->BSB: DDB search
results carry provider identifiers but no automated hand-off
to BSB object ids is implemented; the documented path is
manual (find the bsb object id, then open it by ID) - stated
as a limitation, not papered over.

## P1 findings and fixes

- S9 rate limits: BSB paces OCR/Image requests (0.34s, a
  conservative local choice - MDZ publishes no numeric cap and
  the value is never presented as one), caches manifests
  (1h) and page OCR (1h, so repeat reads do not re-hit the
  24h-limited APIs), and stops a scan on 429. LoC's 3s rate
  limit now covers the page JSON, text-services, info.json and
  image fetches (previously the verify fetches bypassed it);
  cache hits return before any waiting.
- S10 Retry-After: the transport gate now loops on the LATEST
  host deadline under ONE absolute send window (gate waits and
  the semaphore wait both count); a request is never sent
  before an extended deadline, and never sent at all once the
  window is spent. Regression test: a gate extended mid-wait
  from 0.5s to 1.6s delays the send past 1.5s.
- S11 compression: chunk-boundary tests for multi-member
  gzip found a REAL bug - when one chunk contained the ends of
  two members, the third member was silently dropped. The
  decoder now swaps decompressors in a loop. Also covered:
  truncated last member, trailing garbage, CRC corruption,
  raw and zlib deflate, >64KB outputs, cumulative byte caps
  across responses.
- S12 IIIF: v2 service as list, multiple images (the one with
  a service wins), multiple sequences, license as dict/list,
  otherContent no longer mistaken for OCR (kept separately);
  v3 external AnnotationPage references skipped, body lists
  and Choice bodies handled, only supplementing text bodies
  count as OCR (commenting does not). ALTO refuses entity
  declarations and caps element count; hOCR input is size
  bounded. Parsing a manifest is never itself a mapping proof.
- S13 e-rara: the OAI header identifier must equal the
  requested id; deleted records are refused; DOI extraction
  uses a strict pattern (doi.org prefixes normalised); the
  holding institution is "unknown" (setSpec is a collection
  code, dc:publisher is not the holder); every dc:rights value
  is preserved; the 503 retry honours Retry-After. The docs
  say a usable per-page API "could not be confirmed", not
  that none exists.
- S14 printed pages: BSB no longer derives printed_page from
  the canvas label; printed_page is "unknown" with the label
  preserved as canvas_label and printed_page_source stating
  the position.
- S15 rights: Rights gains a classification - CC0, Public
  Domain Mark and NoC-NC are distinct values
  (public-domain-mark / cc0 /
  rightsstatements-noc-nc-noncommercial); the UI already
  restricted links to https via safeHref, and the directory's
  official-site link now uses it too. Nothing in this phase
  transmits materials to external AI.
- S16 capability counts: registry 25 entries; adapters 8;
  keyword-searchable 6 (loc, ndl, gallica, internet-archive,
  ddb, europeana); ID-addressed bibliographic 2 (bsb, e-rara);
  page-OCR implemented 5 (ndl, internet-archive, gallica, bsb,
  loc-Chronicling-America); page-OCR live-verified 4 (ndl,
  internet-archive, bsb, loc newspapers); OCR+original live
  stage-C verified 4; end-to-end search-to-evidence live 2
  (ndl, internet-archive). get_page_image now serves BSB/LoC
  through the adapters and returns a reasoned "unsupported"
  elsewhere; the research profile still has exactly 14 tools.
  A registry/adapter consistency test guards the vocabulary
  and the ID-addressed honesty rules.
- S17 comparison: service-level tests now compare two BSB
  documents end to end and keep a failed document visible
  (verified_pages 0, status insufficient_evidence);
  compare_aspect additionally returns partial_terms (present
  in some but not all documents), surfaced in the service
  rows, so partial overlap is not read as consensus.
- S18 Web UI: an ID-lookup panel (document / page OCR /
  bounded in-document search via the new /api/in-document
  route) makes the ID-addressed flows operable; Playwright
  grew from 12 to 15 tests covering the directory filters,
  the BSB-not-searchable chip, the lookup document (rights
  classification shown), page mapping state and coverage.

## Live re-verification after the fixes (2026-11-26, S20)

Grading per S19: A metadata, B page OCR, C mapping + real
image, D full pipeline.

- BSB: A 3/3 items; B 7/7 pages across the 3 items (pages
  5,6,7 / 5,100 / 5,10) with ALL strict checks true; C 2/2
  verify_original runs verified with real JPEG renditions
  (~10-11 KB, signature ok); D: service-level in-document
  search ran live (20 pages, 17 HTTP requests with cache
  hits, coverage reported) and the compare path is covered
  by service-level fixtures. Rights classes came back
  exactly as classified (NoC-NC for bsb10120542, Public
  Domain Mark for the other two).
- LoC Chronicling America: B 2/2 pages on two different
  issues (1907-01-01 and 1907-01-02, seq-2; 53,368 and 39,843
  OCR chars) with all seven strict checks true; C 2/2
  verify_original verified (the second issue's image-service
  stage failed once on a transient upstream error and passed
  on a single retry - recorded, not hidden).
- e-rara: A 1/1 (record 30815284; header identifier match,
  strict DOI 10.3931/e-rara-140634, rights values preserved).
- Gallica: not re-verified (upstream 403 from this network;
  no circumvention attempted, per instructions).

No human visual collation of OCR against page images was
performed. "Verified" here means the payload-level identity
chain above - not OCR accuracy and not the truth of the
content.
