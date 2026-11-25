# b5 live verification record (2026-11-25)

Environment: this project's sandbox VM, official public APIs only,
identified User-Agent, small request counts, shared HTTP budget.
Fixture-test success is recorded separately in the test suite and
is never counted here.

## BSB / MDZ (NEW - live end-to-end verified)

Adapter calls: get_document, get_page_text (@5), verify_original
(@5) for three objects; bounded search_in_document on one.

| object | pages | page 5 OCR chars | mapping | verify | rights (manifest) |
|---|---|---|---|---|---|
| bsb10120542 (Spindler, 1854) | 172 | 1,286 | verified (5/5 checks) | verified | NoC-NC/1.0 |
| bsb00046575 (Augustinus, Clm 1435) | 333 | 1,464 | verified (5/5 checks) | verified | Public Domain Mark 1.0 |
| bsb00012345 (Acta, incunable) | 29 | 42 | verified (5/5 checks) | verified | Public Domain Mark 1.0 |

Mapping proof: canvas @id suffix, image-service id suffix,
manifest seeAlso OCR link, the documented /ocr/{id}/{page}
pattern, and the hOCR payload's own title all agree.
Bounded in-document search on bsb10120542 ("Invaliden"):
20/172 pages searched, coverage reported as incomplete - the
term was not in the first 20 pages; this is reported as a
bounded search, not as absence from the work.
Totals: 29 HTTP requests, ~4.2 MB decoded (~3.75 MB on the wire).

## Library of Congress - Chronicling America (NEW page capability)

Issue sn83030214 (New-York tribune), 1907-01-01, ed-1:
get_document reports 14 pages; get_page_text for seq-2 returned
53,368 OCR characters with verified_mapping = true (single
segment for the seq, segment URL matches sp=2, segment id and
IIIF image info present); verify_original = verified.
Totals: 5 HTTP requests, ~174 KB, ~10 s end to end.
Scope: Chronicling America newspapers only. This does NOT make
"LoC" a page-OCR library in general.

## e-rara (NEW - metadata by ID, live verified)

GetRecord for 30815284 returned the real record (1885 map
drawing, Zentralbibliothek Zürich set, DOI landing page,
rights "PDM 1.0"). The OAI endpoint answered 503 twice during
the session and recovered minutes later; the adapter retries a
503 once and otherwise surfaces it as a retryable error.
OAI-PMH is not a search interface; page OCR is unsupported.

## Existing libraries

NDL and Internet Archive behaviour is covered by the standard
regression topics (see docs/b5-global-coverage.md for the run
recorded with this candidate) and by the unchanged fixture
suite (248 pytest). No admission/relevance rule was changed.

## Regression topics (b5 candidate, Standard, live, 2026-11-25)

The five standing topics through `research_materials` (defaults:
NDL/LoC/Gallica/IA; the new adapters are opt-in and were not in
this run). Partial failures for loc/gallica are the known ones
(slow LoC responses, Gallica upstream 403).

| topic | total | materials | admitted | HTTP |
|---|---|---|---|---|
| 進化論 (Darwin) | 50.3s | 15 | 2 | 34 |
| 明治の水力発電 | 32.0s | 10 | 0 | 23 |
| 日本の鉄道史 | 59.6s | 14 | 0 | 39 |
| 哲学史 | 18.2s | 13 | 3 | 18 |
| 科学史 | 30.1s | 11 | 4 | 14 |

NDL/IA behaviour is intact (materials, excerpts, admissions all
present). Totals vary run to run with upstream latency (the b3
post-fix run measured 32.1/27.7/15.3/7.3/25.1s on the same
topics); no performance improvement is claimed from this single
run, and no admission rule was loosened.
