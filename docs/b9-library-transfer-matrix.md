# b9 — Per-library external transfer matrix

Checked: 2026-11-27. One row per implemented adapter. Values
are allowed / restricted / unknown per the grounding rule in
`src/global_library_mcp/external/transfer_matrix.py`: a cell
is `allowed` only where the library's official API/terms
permit that use; unaddressed uses are `unknown` and are
treated as not permitted beyond minimal reference data.
OCR full text and original-image binaries are prohibited for
every library by policy. Item-level rights always apply on
top of this matrix; the matrix can only restrict further.

| Library | Metadata | Reference URL | OCR excerpt | OCR full text | Image URL | Image binary | Third-party AI | Attribution | Commercial | Item check required |
|---|---|---|---|---|---|---|---|---|---|---|
| ndl | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | National Diet Library Digital Collections | restricted by NDL terms; item rights govern | yes |
| internet-archive | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Internet Archive | item rights govern; lending items restricted | yes |
| loc | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Library of Congress | item rights govern (Rights & Restrictions) | yes |
| bsb | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Bayerische Staatsbibliothek / MDZ | provider/item-specific (registry terms_rights) | yes |
| ddb | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Deutsche Digitale Bibliothek | API terms: commercial use, credit and bulk-access conditions apply | yes |
| gallica | restricted | allowed | restricted | prohibited | restricted | prohibited | unknown | BnF / Gallica | BnF terms restrict commercial use, mining and harvesting | yes |
| europeana | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Europeana and the providing institution | item rights statement governs (Europeana Rights Framework) | yes |
| e-rara | unknown | allowed | restricted | prohibited | restricted | prohibited | unknown | e-rara / ETH-Bibliothek | unknown - not confirmed from official terms | yes |
| finna | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Finna / the providing organisation | metadata CC0; item rights are the provider's, not CC0 | yes |
| finland-nl-digi | unknown | allowed | restricted | prohibited | restricted | prohibited | unknown | National Library of Finland | unknown - digi service terms not confirmed for transfer | yes |
| dpla | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | DPLA and the providing institution | metadata CC0; item rights via RightsStatements.org govern | yes |
| kb-delpher | restricted | allowed | restricted | prohibited | restricted | prohibited | unknown | KB, national library of the Netherlands / Delpher | KB terms restrict reuse; item rights govern | yes |
| japan-search | allowed | allowed | restricted | prohibited | restricted | prohibited | unknown | Japan Search / the providing organisation | per-item accessInfo licence and restrictions govern | yes |

## Sources

- ndl: https://dl.ndl.go.jp/ (NDL Digital Collections terms of use)
- internet-archive: https://archive.org/about/terms.php
- loc: https://www.loc.gov/legal/
- bsb: https://www.digitale-sammlungen.de/en/ (MDZ terms)
- ddb: https://www.deutsche-digitale-bibliothek.de/content/api (API terms)
- gallica: https://gallica.bnf.fr/ (BnF reuse conditions)
- europeana: https://www.europeana.eu/en/rights (Rights Framework)
- e-rara: https://www.e-rara.ch/ (terms not confirmed for API transfer)
- finna: https://www.finna.fi/Content/api (Finna API; metadata CC0)
- finland-nl-digi: https://digi.kansalliskirjasto.fi/ (terms not confirmed)
- dpla: https://dp.la/info/developers/codex/policies (DPLA API policies)
- kb-delpher: https://www.delpher.nl/ (KB terms of use)
- japan-search: https://jpsearch.go.jp/ (Japan Search terms; per-item accessInfo)

## Reading the matrix

- `metadata = allowed` means the minimal bibliographic fields
  may be sent when the item itself is not access-restricted.
- No library's terms, as checked, explicitly contemplate
  sending OCR excerpts to a third-party AI service, so
  `ocr_excerpt` is nowhere `allowed` and `third_party_ai` is
  `unknown` throughout: with the shipped matrix the excerpt
  tool can never fire on a real library. The allow path is
  verified only against synthetic fixtures (brief section 15)
  and would need a library whose terms are confirmed for that
  use, plus a separate deployment approval.
- Finna and DPLA metadata are CC0 at the aggregator level;
  item rights remain the provider's and are checked per item.
