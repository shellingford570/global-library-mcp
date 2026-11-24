# Phase 10-I: library terms of use - beta practice summary

Full research with sources and verification status follows
below (researched 2026-11-24; [verified-official] /
[verified-secondary] / [not found] markers preserved).
Headline practice for the Research Beta:

- **Default posture everywhere: short excerpts + a link to
  the original.** Nothing is presented as freely
  redistributable unless the library's own terms say so.
- **NDL**: three rule sets apply (full research below).
  Digital Collections content is governed per item by its
  publication scope （公開範囲）: only
  「インターネット公開（保護期間満了）」 items are freely
  reusable; adjudicated/licensed/transmission-limited
  items need the rights holder's permission, and IIIF
  fetchability is not a licence. The NDL Lab corpus the
  adapter uses is protection-expired material carrying the
  Public Domain Mark, free except for commercial +
  continuous use. NDL Search API metadata terms are per
  provider, with commercial use requiring an application.
  The beta shows per-item rights verbatim and links to the
  original beyond short excerpts.
- **Internet Archive**: open items' OCR is openly served;
  lending/borrow-restricted items are NEVER fetched for
  full text (the adapter refuses them; only BookReader
  preview-level access would be sanctioned, and the beta
  does not use it). Metadata carries archive.org
  attribution.
- **Gallica/BnF**: metadata is under the Licence Ouverte
  (commercial use allowed with attribution). Content reuse
  is non-commercial-free with the exact credit
  "Source gallica.bnf.fr / Bibliothèque nationale de
  France"; commercial reuse needs a paid BnF licence, and
  third-party/partner items are excluded even from that.
  The upstream 403 seen from this network must not be
  circumvented.
- **LoC / Europeana / DDB** (aggregator or adapter
  coverage): metadata is openly licensed (CC0 / public
  domain) per their terms; item-level rights statements
  still govern the content itself and are shown verbatim.
- **HathiTrust and all research-only registry entries**:
  no adapter, no fetching; listed as "under research".

# Phase 10-I: Library Terms of Use Research

Researched: 2026-11-24 (JST). Purpose: Phase 10-I of Global Library MCP —
establish, per integrated library, what the Research Beta may do with
bibliographic metadata, OCR full text, and original images, before any
public release.

Method: official terms/help/API pages located with web search and read
via search-result excerpts and page fetches. Each claim below is marked:

- **[verified-official]** — text read from the provider's own official page
  (or an official government listing describing that provider's API).
- **[verified-secondary]** — official text reproduced/quoted by a third
  party, or an official page that could not be fetched directly in this
  session (fetch failure noted). Treat as reliable but re-check before
  relying on it in a legal notice.
- **[not found]** — no official statement located. Recorded as
  "unknown - must not be assumed redistributable", per the Phase 10 brief.

Registry coverage (from `libraries.yaml`, read 2026-11-24): implemented
adapters exist only for **ndl**, **internet-archive**, **gallica**,
**loc**, plus the aggregators **europeana** and **ddb**
(`adapters/aggregators.py`). All other registry entries (japan-search,
ndli, kr-nlk, tw-ncl, sg-nlb, bsb, bl, ape, hathitrust, qdl, nli-il,
nlsa, trove, digitalnz, open-library, lac, bn-br, worldcat) are
research-only records with no adapter; they are covered briefly in §7.

---

## 1. National Diet Library (NDL), Japan

Three distinct services with three distinct rule sets. Do not conflate
them: (a) NDL Digital Collections (dl.ndl.go.jp) content, (b) NDL Search
API metadata (ndlsearch.ndl.go.jp), (c) NDL Lab "Next Digital Library"
API (lab.ndl.go.jp), which is the API the project's NDL adapter actually
uses for Book/Page search and OCR.

### 1.1 Digital Collections content (images and OCR of digitised items)

Source: NDL, "国立国会図書館ウェブサイトからのコンテンツの転載"
https://www.ndl.go.jp/use/reproduction **[verified-official]**

- Reuse is governed **per image / per item by its 公開範囲 (release
  category)**, shown in the item's "共有" (share) area. Categories:
  - `インターネット公開（保護期間満了）` (copyright term expired):
    freely usable, no application to NDL required.
  - `インターネット公開（裁定）` and `インターネット公開（許諾）`:
    in principle the **rights holder's permission is required**;
    the user must confirm this themselves. No application to NDL.
  - `国立国会図書館内/図書館・個人送信限定` and `国立国会図書館内限定`:
    not openly published; in principle rights-holder permission required.
- Content whose copyright belongs to NDL itself: reusable with
  **attribution only**, no application (subject to exceptions listed in
  the NDL website terms of use).
- Third-party copyright content: user's own responsibility; permission
  from the rights holder is in principle required unless the term has
  expired or a statutory limitation applies.
- Attribution: NDL asks that reuse indicate the material was reproduced
  from the NDL website (a request/協力お願い, plus the website terms).
- Per-volume and per-image categories can differ from the title-level
  category — the category of the specific image must be checked.

Implication: dl.ndl.go.jp IIIF delivery is a delivery mechanism, not a
licence. The IIIF manifest/image for a （裁定）/（許諾）/送信限定 item
must not be treated as redistributable merely because it is technically
fetchable. The project's adapter works against the NDL Lab corpus
(§1.3), which is restricted to 保護期間満了 items, but any direct
dl.ndl.go.jp IIIF use must carry the item's 公開範囲 through to the UI.

### 1.2 NDL Search API (SRU / OpenSearch / OpenURL / OAI-PMH harvest)

Source: NDL Search help, "17. APIのご利用について"
https://ndlsearch.ndl.go.jp/help/api (English:
https://ndlsearch.ndl.go.jp/en/help/api) **[verified-official]**

- **Bibliographic metadata**: terms are **per data provider** (NDL Search
  aggregates ~110 databases). Each provider row in the API provider list
  states its own metadata conditions for commercial / non-commercial use.
  - Metadata created by NDL itself: stated by NDL (official training
    material, https://www.ndl.go.jp/jp/dlib/standards/opendataset/index.html
    and NDL open-data presentations) to be freely usable free of charge
    regardless of commercial purpose, "CC BY相当" (equivalent to CC BY);
    one official guide states no attribution is required for NDL-created
    bibliographic data used per-record, while the API terms (below)
    require crediting the API itself. To be safe: credit NDL Search API
    and the data provider. **[verified-official]**
  - Metadata from other institutions: follow each institution's terms.
- **Commercial use**: an **application (利用申請) is required** for
  commercial use, except for metadata whose provider has pre-licensed
  use regardless of purpose. "Commercial" includes earning any revenue
  from the data (e.g. advertising-supported sites), even at a loss.
  Non-commercial, non-revenue use needs no application.
- **Continuous use**: NDL asks continuous users to notify via the
  application form regardless of whether an application is required.
- **Attribution (mandatory)**: sites/apps using the API **must state
  that they use the NDL Search API**; where a provider's conditions
  require it, the provider/database credit must also be shown (e.g. for
  CC BY metadata: credit + licence link).
- **Rate limits**: no numeric limit is published. NDL states it
  **limits concurrent requests**, and may **block** sources that
  continuously send large volumes. **[verified-official]** — numeric
  cap: **[not found]**.
- **Caching**: no explicit caching allowance or retention limit found
  in the API terms. **[not found]** — treat cached metadata as governed
  by the per-provider metadata licence; do not assume bulk redistribution
  rights beyond that licence.
- OCR full text / images: the NDL Search API is a metadata API; it does
  not license OCR text or page images. See §1.1 and §1.3.

### 1.3 NDL Lab "Next Digital Library" API (Book / Page / Illustration)

Sources: NDL Lab service page https://lab.ndl.go.jp/service/tsugidigi/
and API page https://lab.ndl.go.jp/service/tsugidigi/apiinfo/
(English: https://lab.ndl.go.jp/service/tsugidigi/tsugidigi_en/)
**[verified-official]**

- Corpus: only Digital Collections items whose copyright term has
  expired (~350,000 books/classics), i.e. the
  `インターネット公開（保護期間満了）` class.
- **The material data (OCR text data and image data) carry the Public
  Domain Mark (PDM).** Conditions/requests for secondary use:
  - If you edit/process the data, state that you did so; do not present
    edited data as if created by the author or by NDL.
  - Keep the indication that the data is freely reusable; do not remove
    CC0 / public-domain marks or notices.
  - Respect rights other than copyright (moral rights, portrait,
    privacy, trademark, etc.).
  - Historical materials may contain discriminatory period language;
    NDL asks for appropriate use.
- **API use**: free without application, **except commercial and
  continuous use** (営利目的かつ継続的な利用を除き、申請不要). For other
  uses, NDL directs users to contact them. Screenshots and search
  results may be freely reproduced without application.
- **Rate limits**: no numeric limit published on the API page.
  **[not found]** — numeric cap unknown; the NDL Search API's
  concurrency/blocking warning (§1.2) is the closest official guidance
  for NDL services generally.
- **Caching**: no explicit statement found. **[not found]**. The
  underlying data is PDM, so caching the OCR text/images of this corpus
  is consistent with the stated reuse terms, but no explicit cache
  permission was verified — record as "PDM data; caching not expressly
  addressed".
- Experimental service caveat: the Next Digital Library is an
  experimental (実験的) service from NDL's R&D office; OCR text is
  machine-generated and may change without notice.

### 1.4 NDL IIIF (dl.ndl.go.jp/api/iiif)

- No separate IIIF-specific licence was found. **[not found]** Image
  reuse follows the item's 公開範囲 (§1.1). For the NDL Lab corpus
  (§1.3) the images are PDM.

---

## 2. Internet Archive (archive.org)

Sources: Terms of Use, 31 Dec 2014, https://archive.org/about/terms.php
(canonical page could not be fetched directly in this session — it
renders via JavaScript; the 2014 text was verified through multiple
verbatim reproductions of the official text) **[verified-secondary]**;
"Bots, LLMs, and Automated Access", https://archive.org/developers/bots.html
**[verified-official]**; "Borrowing From The Lending Library",
https://help.archive.org/help/borrowing-from-the-lending-library/
**[verified-official]**.

- **Overall grant**: access to the Collections is free and "granted for
  scholarship and research purposes only". Users certify their use of
  any part of the Collections "will be limited to noninfringing or fair
  use under copyright law".
- **Bibliographic metadata**: per the developer portal, the Archive
  asserts no new copyright over the material in its database
  **[verified-secondary]**. Item metadata may carry a per-item licence
  in the `licenseurl` field. Metadata API reads need no key.
- **OCR full text (djvu.txt / djvu.xml) and images**: rights are
  **per item / per upload**. An item with a declared Creative Commons or
  other licence may be used under that licence; public-domain items are
  open. An item with **no explicit rights statement is uncertain** —
  default to cite-and-link, do not redistribute. There is no
  Archive-wide licence covering OCR text or scans.
- **Commercial use**: the Terms grant access for scholarship/research;
  commercial reuse is only as permitted by the individual item's
  licence. Do not build commercial redistribution on the Collections
  without per-item checks. **[verified-secondary]**
- **Attribution**: the Archive *requests* (standard academic practice)
  that publications resulting from research list the Archive as a
  resource in the bibliography. Not stated as a hard licence condition
  for API use, but adopt it as project policy.
- **Rate limits / automation rules** (bots guide) **[verified-official]**:
  - **Every automated request must carry a descriptive User-Agent**
    identifying the tool and version (and, for AI agents, the model).
  - No numeric rate limit is published. Add delays for bulk work,
    limit concurrency (the guide's example: 4 concurrent downloads with
    a 1-second delay), and **honour HTTP 429 and `Retry-After`**.
  - Use checksums to avoid re-downloading unchanged files; retry with
    exponential backoff.
- **Caching**: the bots guide advises automated tools to cache what
  they fetch **[verified-official, as paraphrased in secondary
  summaries of the page]**. No retention limit is published.
  **[not found]** for a formal caching licence — caching for
  operational purposes is consistent with the guide; redistribution of
  cached content still follows per-item rights.
- **Lending / restricted items (critical)** **[verified-official]**:
  - Books in the lending library are borrowable by **one patron at a
    time**, via a free archive.org account: renewable **1-hour** loans
    (BookReader only) or **14-day** loans (BookReader or
    DRM-encrypted file via LCP/Adobe Digital Editions); max 10 books
    at a time; waitlists when copies are out.
  - Items flagged `access-restricted-item` / carrying lending metadata
    are **not openly downloadable**: full text and page images are
    gated behind an individual loan. A third-party service must not
    fetch, cache, or relay their OCR or images — link to the item page
    so the user can borrow it themselves. (This matches the project's
    existing adapter behaviour of refusing restricted items.)
  - Note the legal context: US courts ruled against the Archive's
    lending programme in *Hachette v. Internet Archive* (2023, affirmed
    on appeal), which reinforces that lending copies must not be
    treated as open content.

---

## 3. Gallica / BnF (France)

Sources: "Conditions d'utilisation des contenus de Gallica" (BnF text,
reproduced verbatim in Gallica-generated PDFs and quoted in an
Assemblée nationale Q&A; canonical page
http://gallica.bnf.fr/html/und/conditions-dutilisation-des-contenus-de-gallica)
**[verified-secondary]**; data.gouv.fr official API listings for
API Gallica Recherche / IIIF / Document, e.g.
https://www.data.gouv.fr/dataservices/api-gallica-iiif
**[verified-official]**.

- **Content model**: most Gallica content is digital reproductions of
  **public-domain works** from BnF collections; reuse is framed by the
  French law of 17 July 1978 on reuse of public information.
- **Non-commercial reuse**: free, provided the source attribution is
  kept exactly: **« Source gallica.bnf.fr / Bibliothèque nationale de
  France »** (or « Source gallica.bnf.fr / BnF »). Academic/scientific
  publication counts as non-commercial.
- **Commercial reuse**: **paid and requires a licence** from BnF.
  "Commercial" includes resale of content as products/services and any
  reuse directly generating revenue (paid publications except academic,
  exhibitions, audiovisual productions, paid services/products,
  promotional material). High-definition files are obtained via
  utilisation.commerciale@bnf.fr.
- **Exceptions (per-item)**:
  - Reproductions of works still under a third party's copyright: no
    reuse without the rights holder's prior authorisation (private
    copying excepted).
  - Partner-institution documents (marked "Source gallica.bnf.fr /
    Bibliothèque municipale de …" etc.): that institution's own reuse
    conditions apply — check with the partner.
  - Gallica as a database is protected by the EU sui generis database
    right (BnF as producer, CPI L341-1 ff.) — wholesale extraction of
    the database is a separate issue from per-item reuse.
- **Bibliographic metadata**: descriptive metadata for Gallica digital
  documents is under the French State **Licence Ouverte (Open
  Licence)** — reusable including commercially, with attribution of
  source and date **[verified-official, data.gouv.fr listings]**.
- **APIs (SRU search, IIIF image, Document API)**: managed by BnF;
  access is **open without restriction, except in case of abusive use**
  ("Son accès est ouvert sans restriction, sauf en cas d'usage
  abusif"). No numeric rate limit published. **[not found]** for
  numbers. Note: BnF has recently been adding security measures that
  temporarily restrict Gallica API access (reported 2026); the project
  already receives upstream HTTP 403 from this network — do not attempt
  to circumvent; treat Gallica as not live-verified (as recorded in
  `libraries.yaml`).
- **OCR text**: Gallica OCR (texteBrut / ALTO) is part of the document
  content, so the content rules above apply: non-commercial reuse with
  the exact source mention; commercial reuse needs a licence.
  **[verified-secondary]** No OCR-specific separate licence found.
- **IIIF images**: same content rules; IIIF is a delivery protocol, not
  a licence. Public-domain status of the underlying work does not by
  itself waive BnF's reuse conditions on the reproductions for
  commercial use.

---

## 4. Library of Congress (loc.gov, United States) — adapter implemented

Sources: loc.gov API documentation and legal pages as quoted in search
excerpts (direct fetch of the API limits page returned HTTP 403 to this
session's fetcher and was not retried) **[verified-secondary]**;
per-collection Rights and Restrictions pages on loc.gov
**[verified-official]**.

- **Rights model**: item/collection-level. LoC states it does not own
  copyright in most collection material; many collections are public
  domain / "free to use and reuse" (e.g. FSA/OWI photographs, selected
  book collections), each with a per-collection **Rights and
  Restrictions Information** page and a per-item **Rights Advisory**.
  Items may instead be rights-restricted or not yet rights-evaluated —
  in those cases only thumbnails are served off-site. **Never infer
  redistribution rights from the absence of a restriction notice**:
  check the item's rights advisory.
- **Attribution**: credit line requested ("Library of Congress, Prints
  & Photographs Division, …" style per collection). Adopt per-item
  credit lines as provided.
- **API**: loc.gov JSON/YAML API is public, **no API key or
  authentication**. Rate guidance from LoC's "Working Within Limits"
  page and legal page: strongly encouraged self-limiting; JSON/YAML API
  ~**20 requests/minute** (exceeding can trigger a 1-hour block);
  image services and media ~150/minute; LoC's legal page recommends
  software submit **no more than 10 requests/minute in total** across
  machines and reserves the right to block IPs that ignore robots.txt
  or harm service delivery; expect possible 429s/CAPTCHAs even below
  the limits. robots.txt sets `Crawl-Delay: 5` for general crawlers
  and disallows some search endpoints — use the format/collection
  endpoints, not `/search/`.
- **OCR / full text**: Text Services provide OCR for covered
  collections; reuse follows the item's rights advisory. Chronicling
  America newspaper content is largely public domain (pre-1923 /
  US-government and partner-provided), per collection pages.
- **Caching**: no explicit caching terms found. **[not found]**.

---

## 5. Europeana (EU aggregator) — adapter implemented (API key required)

Source: Europeana API FAQ, Europeana Knowledge Base
https://europeana.atlassian.net/wiki/spaces/EF/pages/2360508417
**[verified-official]**; Europeana Licensing Framework summaries
**[verified-official/secondary]**.

- **Metadata**: **all metadata from Europeana's APIs is CC0** — reuse
  without restriction, including commercially.
- **Content objects** (the media linked via `edm:isShownBy` /
  `edm:object`, including previews): **per-item rights statement** in
  the `edm:rights` field (Creative Commons licences or
  RightsStatements.org statements). Always check `edm:rights` before
  using an object. The Search API's `reusability=open` filter returns
  only Public Domain Mark / CC0 / CC BY / CC BY-SA items.
- **API terms**: API use is governed by points 8–18 of Europeana's
  Terms of Use (per the FAQ). A free API key (`wskey`) is required.
- **Rate limits**: a daily call limit has historically applied
  (10,000 calls/day was documented for the API); the current numeric
  limit was **not verified** in this session. **[not found — re-check
  in the API console before launch]**.
- **Caching**: not expressly addressed in the sources read.
  **[not found]**. CC0 metadata may be cached/redistributed; object
  caching follows each item's `edm:rights`.
- OCR: Europeana aggregates mostly metadata and previews; full-text
  OCR availability and rights are provider/item-specific.

---

## 6. Deutsche Digitale Bibliothek (DDB, Germany) — adapter implemented

Source: DDB, "Using search results"
https://www.deutsche-digitale-bibliothek.de/content/suchergebnisse-verwenden?lang=en
**[verified-official]**.

- **Metadata**: **CC0** — "can be used freely, including for your own
  databases, portals and other contexts", downloadable via the DDB
  API. (Some records containing protected descriptive text may be
  withheld from the API.)
- **Digital objects**: per-object rights notice shown directly under
  each object, ranging from free (Public Domain Mark 1.0, CC0 1.0) to
  CC licences with conditions, to restricted. Follow the linked
  per-object licence/statement; there is no DDB-wide object licence.
- **API rate limits / caching**: not stated in the pages read.
  **[not found]**.

---

## 7. Other registry entries (no adapter implemented)

From `libraries.yaml` (statuses as recorded there, 2026-11-19/22) —
brief notes only; none of these may be integrated or redistributed
from without a fresh terms check:

- **japan-search** (jpsearch.go.jp): SPARQL/IIIF aggregator; rights are
  provider/item-specific. Unknown.
- **ndli** (India): site terms recorded as restricting commercial use,
  mining and harvesting. No API.
- **kr-nlk** (Korea): API needs membership, key and approval; terms
  unknown.
- **tw-ncl** (Taiwan), **lac** (Canada), **bn-br** (Brazil),
  **ape** (Archives Portal Europe): terms unknown.
- **sg-nlb** (Singapore): dataset metadata under Singapore's Open Data
  Licence; individual items may be all-rights-reserved.
- **bsb / MDZ** (Bavaria): item-specific; many works public domain,
  verify per item. Research-only note in the registry.
- **bl** (British Library): metadata services; Z39.50 noted as
  restricted/non-commercial. Item terms vary.
- **hathitrust**: bibliographic API; full-view availability depends on
  per-item `rightsCode` and region. Restricted data needs an access key.
- **qdl** (Qatar Digital Library): IIIF present; per-item usage terms,
  not uniform.
- **nli-il** (Israel): APIs need a key; per-item copyright conditions.
- **nlsa** (South Africa): CONTENTdm; record-specific rights.
- **trove** (Australia): API key required; metadata conditions include
  attribution and a **30-day cache limit** (as recorded in the registry
  from the v3 guide); objects have separate rights.
- **digitalnz**: per-record `rights_url` and `is_commercial_use` flags;
  source partner controls the object; ~10,000 calls/day/key recorded.
- **open-library** (Internet Archive project): data/source-item
  specific; API etiquette 1 req/s (3 req/s identified). Lending rules
  of §2 apply to its borrowable editions.
- **worldcat** (OCLC): member authentication; OCLC/member terms.

---

## 8. Practical summary for the Research Beta

Default posture (Phase 10 brief): prefer **short excerpts + link to the
original**; never present search results as proof of an answer; never
assume redistribution rights that were not verified.

| Library | Short excerpts + link to original | Cache OCR | Redistribute images | Commercial use |
|---|---|---|---|---|
| NDL Lab – Next Digital Library API (PDM corpus) | allowed | allowed (PDM data; caching not expressly addressed) | allowed (PDM; keep PD marks, note edits) | restricted — free API use excludes commercial+continuous use; application/contact required |
| NDL Digital Collections via dl.ndl.go.jp IIIF (general) | allowed for 保護期間満了 items; restricted otherwise | restricted — per-item 公開範囲 governs; only 保護期間満了 is free | restricted — per-item 公開範囲; （裁定）/（許諾）/送信限定 need rights-holder permission | restricted — per-item; NDL-owned content needs attribution, third-party content needs permission |
| NDL Search API (metadata) | allowed | restricted — per-provider metadata licence; no explicit cache terms found | n/a (metadata API; thumbnails need application for commercial use) | restricted — application required unless provider pre-licensed; must credit NDL Search API + provider |
| Internet Archive | allowed (scholarship/research; per-item licence governs quoting) | restricted — operational caching consistent with bots guide; redistribution per item licence; **never for lending-restricted items** | restricted — per item (`licenseurl` / rights); unknown if unstated | restricted — Terms grant scholarship/research use; commercial only per item licence |
| Gallica / BnF | allowed (non-commercial, with exact « Source gallica.bnf.fr / BnF » credit) | restricted — non-commercial only with source credit; partner/third-party items excluded | restricted — non-commercial with credit; commercial needs a paid BnF licence | restricted — paid licence required; metadata (Licence Ouverte) is the exception: allowed with attribution |
| Library of Congress | allowed (check item Rights Advisory) | unknown - must not be assumed redistributable (no cache terms found; item rights govern) | restricted — per item/collection; many collections explicitly free to reuse | restricted — per item rights; no blanket commercial grant found |
| Europeana | allowed (metadata CC0; objects per `edm:rights`) | allowed for metadata (CC0); restricted for objects (per `edm:rights`) | restricted — per item `edm:rights`; use `reusability=open` to filter | allowed for metadata (CC0); restricted for objects per rights statement |
| DDB | allowed (metadata CC0; objects per notice under each object) | allowed for metadata (CC0); restricted for objects | restricted — per-object licence (PDM/CC0 objects are free) | allowed for metadata (CC0); restricted for objects per licence |

### Cross-cutting rules for the Beta

1. Carry the rights signal end-to-end: NDL 公開範囲, IA
   `access-restricted-item`/`licenseurl`, Gallica source-mention type,
   LoC Rights Advisory, Europeana/DDB per-object licence. If the signal
   is absent, treat the item as **unknown - must not be assumed
   redistributable**: show metadata + short excerpt + link only.
2. Lending-only material (IA) is link-only. Never fetch its OCR/images.
3. Respect published automation rules even where no number exists:
   descriptive User-Agent and 429/Retry-After handling (IA), no
   concurrent-request abuse and possible blocking (NDL), ~10–20
   req/min self-limit (LoC). Do not circumvent 403s or challenges
   (Gallica currently 403s this network; BnF API access rules are
   being redefined — re-check before enabling the adapter).
4. Attribution is mandatory in at least: NDL Search API (API +
   provider credit), Gallica (exact source wording), Europeana/DDB
   object licences where the licence requires it (CC BY etc.), and is
   requested by NDL (website content), IA (bibliography) and LoC
   (credit lines). Implement attribution display for all sources.
5. Commercial launch changes the answer for NDL (Search API
   application; Lab API exclusion) and Gallica (paid licence). A
   non-commercial research beta and a commercial product are different
   compliance postures — decide and document which one ships.

### Open verification items before public release

- NDL: numeric rate limits (none published — consider notifying NDL
  Search of continuous use via their form, as they request).
- Europeana: current daily API call limit (not verified this session).
- Gallica: current canonical conditions page and the new API access
  arrangements after BnF's security changes; confirm whether the
  project may use the APIs at all from its hosting network.
- IA: re-read the canonical Terms page in a JS-capable browser (this
  session verified the 2014 text via verbatim reproductions only).
- LoC: re-read "Working Within Limits" directly (fetch returned 403
  in this session); figures above are from official-page quotations.
