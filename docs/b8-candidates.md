# b8 candidates — Global Coverage II (design/research only)

Status: **design and research only.** No b8 implementation
has started; starting it requires a separate approval.
Prepared as part of the v1.0.0b7 final-review round
(brief section 40).

Priority order decided for b8: **Finna first, DPLA second,
Gallica third** (re-verification only from a permitted
ordinary network; the upstream 403 is not a precondition
and must not be evaded). Then KB/Delpher, Japan Search,
the Spanish and Austrian national libraries, HathiTrust,
Trove, the National Library of Korea and the National
Library of Taiwan.

Evaluation axes for every candidate: bibliographic search;
page OCR; original images; identifier scheme; rights
information; API terms; authentication; cost; rate limits;
fit with multilingual search (b6); fit with the research
workspace (b7) — above all, whether the institution's
rights information can be connected **safely** to the
workspace storage policy (fail-closed classification,
per-item statements, no cross-item reuse).

## 1. Finna (first priority)

- **What it is:** the Finnish discovery platform
  (finna.fi), aggregating Finnish libraries, archives and
  museums — including National Library of Finland
  material. Finna the platform must be distinguished from
  each holding institution: records carry the source
  organisation, and rights/digital availability are
  per-record and per-institution.
- **API:** public REST search API (`api.finna.fi/v1/search`
  family, VuFind-derived), no key required for search;
  record-level metadata in MARC-derived fields; links out
  to digital objects, with IIIF used by several Finnish
  providers.
- **OCR/images:** varies by provider; the National
  Library's digitised collections (digi.nationallibrary.fi)
  expose OCR for newspapers/books. Whether page-level OCR
  is reachable through Finna records or only via the
  provider's own service is a b8 research item.
- **Rights:** Finna records carry rights/usage fields for
  many collections; quality is uneven across providers.
  Workspace fit: classify per record with the existing
  fail-closed policy; provider-level statements must not
  be treated as item-level grants (same rule as b7 §3/§4).
- **Multilingual fit:** Finnish/Swedish/English metadata;
  historical Finnish/Swedish orthography variants are a
  natural b6 expansion target.
- **Open questions for b8:** API terms for harvesting and
  local storage; rate limits; whether a stable record ID
  and page ID scheme can back verified citations.

## 2. DPLA (second priority)

- **What it is:** the Digital Public Library of America —
  a US aggregation platform (dp.la), not a holding
  library. The providing institution and the aggregation
  must be distinguished, and originals live at the
  provider.
- **API:** `api.dp.la/v2` items search; **an API key is
  required** (requested by email; obtaining one needs the
  user's approval — no key has been requested).
- **Rights:** DPLA normalises rights to
  RightsStatements.org URIs and Creative Commons URIs in
  the `rights` / `edm:rights` fields — the best-structured
  rights feed of any candidate, and a direct structural
  match for the b7 policy parser (no free-text guessing).
- **OCR/images:** DPLA itself is metadata + links;
  page OCR depends on the provider (e.g. HathiTrust,
  Internet Archive). A DPLA adapter would be
  bibliographic-first, with original handoff to the
  provider, like e-rara in b5.
- **Open questions:** current API availability/terms,
  key issuance process, rate limits, and how provider
  identifiers map to citable pages.

## 3. Gallica (third priority)

- **What it is:** the BnF digital library. SRU search,
  IIIF manifests, per-page OCR (alto/text) — the adapter
  exists since b5 but the upstream returns **403 from
  this network**, so it has never been live-verified.
- **Plan:** re-verify only if a permitted ordinary network
  path becomes available. No evasion, no special
  transport. b8 does not block on Gallica.
- **Rights:** BnF per-item rights statements; French
  public-domain material is extensive. Workspace fit is
  good *if* access is restored, because identifiers
  (ARK) are stable and page-level.

## 4. Other candidates (research notes)

| candidate | search | page OCR | images | identifiers | rights info | auth/cost | notes |
|---|---|---|---|---|---|---|---|
| KB / Delpher (NL) | Delpher API for newspapers/books | yes for Delpher items | IIIF at KB | stable KB IDs | per-item, Dutch statements | API terms to confirm | strong newspaper fit with LoC experience |
| Japan Search (NDL) | official API (jpsearch.go.jp) | links to providers | provider-dependent | jpsearch IDs aggregate provider IDs | per-provider | key/registration to confirm | aggregation layer over Japanese providers incl. NDL |
| Biblioteca Nacional de España | catalogue + Hemeroteca Digital | partial | yes | BNE IDs | per-item | terms to confirm | Spanish imprints complement BSB |
| Österreichische Nationalbibliothek | catalogue + ANNO newspapers | ANNO full text | yes | ANNO IDs | per-item | terms to confirm | Austrian newspapers, German Fraktur OCR |
| HathiTrust | catalogue + Data API | page OCR via Data API (restricted tiers) | Page images via Data API | HT IDs (pairtree) | bibliographic vs full-view distinction is explicit | Data API key; some data restricted | rights model is the most formalised; full-view limits are contractual |
| Trove (NLA) | Trove API v3 | newspaper OCR text via API | yes | Trove IDs | per-item | API key required | Australian newspapers; key needs user approval |
| National Library of Korea | catalogue search | partial digital collections | yes | NLK IDs | per-item, Korean statements | terms to confirm | Korean historical materials; CJK expansion fit |
| National Central Library, Taiwan | catalogue + digital collections | partial | yes | NCL IDs | per-item | terms to confirm | Traditional-character historical materials; fits b6 historical-form expansion |

## 5. Recommendation

Start b8 with **Finna** (no key needed, real API,
identifiers and provider structure researchable without
new credentials), prepare **DPLA** in parallel as a
documents-only study until the user approves requesting
an API key, and keep **Gallica** as a re-verification
opportunist. For every new institution, the b7 rule
applies unchanged: rights information connects to the
workspace storage policy only per item, structurally
parsed, fail-closed — an aggregator's platform-level
terms never substitute for an item-level statement.
