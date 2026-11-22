# Evidence verification

How this project decides that a page of OCR text may be cited, and the live
results for the reference documents. Verification date: **2026-11-22**.
Raw machine-readable results: `docs/verification/ndl-pages-live.json`
(regenerate with `python scripts/verify_ndl_pages.py --save <path>`).

## The rule

A page may ground an answer only when **all** of the following hold:

1. The page payload returned by the library matches the request: page id,
   book PID and digital frame agree (`verified_mapping` in the NDL adapter).
2. OCR text is actually present and passes the quality gate
   (length and replacement/control-character ratios; `evidence.py`).
3. For original-page verification, the IIIF manifest exists, contains a
   canvas for that digital frame, the canvas image URL equals the generated
   image URL, and the image itself answers an HTTP range request.

Anything failing a step is reported as **unverified with a reason**; it is
never silently dropped and never cited. Bibliographic records (title,
author, year) are discovery data, not evidence.

## Reference pages (NDL, live)

| Page | Document | OCR chars | Manifest canvases | Result |
|---|---|---|---|---|
| `994120_50` | 『発電水力の開発』 (1911) | 1,086 (from coordjson) | 97 | **verified** — identity, OCR, manifest, canvas 50, canvas-image match, image HTTP 206 |
| `1018770_21` | 『水力電気 上巻』 (1925) | 706 (from coordjson) | 200 | **verified** — all checks pass |
| `1886468_121` | 1942 material, PID 1886468 | 1,584 (from coordjson) | 202 | **verified** — all checks pass |

Notes:

- The NDL Page API returns OCR primarily as coordinate tokens (`coordjson`)
  for these pages; the adapter reconstructs the text and records
  `ocr_source: coordjson`.
- The printed page number is **not** exposed by the Page API and stays
  `unknown`; only the digital frame number is asserted.
- A 1942 document using the word 「發電所」 says nothing by itself about
  Meiji-era generation; era and context checks remain the reader's job, and
  the answer layer is instructed not to over-generalise across eras.

## End-to-end demo (live, 2026-11-22)

Question: 「発電水力の開発について教えて」 against NDL only.

- 9 verified evidence pages collected (e.g. `ndl:946285:946285_3`,
  『発電水力調査書』 frame 3), 0 unverified.
- With the deterministic mock provider (`LLM_PROVIDER=mock`), the research
  pipeline returned status `answered` with the citation resolved to the
  evidence record and its IIIF image URL. The mock's wording is templated;
  only the evidence and citation flow is real.
