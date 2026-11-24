# Implementation status

Last updated: 2026-11-22 (branch `feat/global-library-evidence-v2`).
Labels: **implemented** = code exists; **verified** = exercised against the real
service or a full local test; **not implemented** = absent by design or pending.

## Core pipeline

| Capability | Status | Notes |
|---|---|---|
| Cross-library catalog search | implemented, verified | LoC, NDL, Internet Archive, DDB live-verified 2026-11-22; Gallica blocked by upstream 403 from the verification network; Europeana needs an API key |
| Library registry (`libraries.yaml`) | implemented | Per-library capabilities, auth, rights, verification state |
| In-document (page) search | implemented (NDL) | Other adapters do not expose page search yet |
| Page OCR retrieval | implemented (NDL), verified | Book/Page APIs of the NDL Next Digital Library |
| Evidence model + OCR quality gate | implemented, verified | `Evidence` records; quality is a screening heuristic, not a correctness proof |
| Verified evidence collection | implemented, verified | `LibraryService.collect_evidence`, MCP tool `get_verified_evidence`, Web `/api/evidence` |
| IIIF original verification | implemented (NDL), verified | Manifest, canvas, canvas-image match, image reachability as separate checks; MCP tool `verify_original_page`, Web `/api/verify` |
| Evidence-grounded answers | implemented, verified with mock provider | Real LLM is optional and disabled by default; citations whitelist-validated twice (provider and service layer) |
| Insufficient-evidence handling | implemented, verified | Status `insufficient_evidence`; no answer is produced from bibliographic data alone |
| Web UI (search + answers + evidence) | implemented, verified | Citation chips jump to evidence cards; inline IIIF verification; JA/EN toggle |
| MCP server | implemented | Tools listed in README.md |

## Adapters

| Library | Search | In-document | OCR pages | IIIF verify | Live status (2026-11-22) |
|---|---|---|---|---|---|
| NDL (JP) | yes | yes | yes | yes | verified end-to-end |
| Library of Congress (US) | yes | no | no | no | search verified |
| Internet Archive | yes | no | no | no | search verified |
| DDB (DE) | yes | no | no | no | search verified |
| Gallica / BnF (FR) | yes | no | no | no | upstream 403 from verification network; not live-verified |
| Europeana (EU) | yes | no | no | no | awaiting `EUROPEANA_API_KEY` |
| All other registry entries | no | no | no | no | research only (see `libraries.yaml`) |

## Not implemented

- Page-level evidence for non-NDL libraries (Gallica ALTO / IIIF Content Search is the
  most promising next step; Internet Archive full-text endpoints are another).
- Printed-page-number resolution for NDL pages (the Page API does not expose it; the
  field stays `unknown` rather than guessed).
- Cross-document comparison tool (`compare_documents` candidate).
- Vector search / embeddings (deliberately out of scope for this design).
- Any production deployment.
