# Implementation status

Last updated: 2026-11-22 (branch `feat/global-library-reliability-v4`, Phase 4).
Labels: **implemented** = code exists; **verified** = exercised against the real
service or a full local test; **not implemented** = absent by design or pending.

## Core pipeline

| Capability | Status | Notes |
|---|---|---|
| Cross-library catalog search | implemented, verified | LoC, NDL, Internet Archive, DDB live-verified 2026-11-22; Gallica blocked by upstream 403 from the verification network; Europeana needs an API key |
| Library registry (`libraries.yaml`) | implemented | Per-library capabilities, auth, rights, verification state |
| In-document (page) search | implemented (NDL, Internet Archive) | NDL via Page API; IA via local search over the item's public djvu OCR |
| Page OCR retrieval | implemented (NDL, IA), verified | NDL Book/Page APIs; IA djvu.xml by leaf (djvu.txt fallback). Gallica page text implemented via texteBrut but NOT live-verified (upstream 403) |
| Evidence model + OCR quality gate | implemented, verified | `Evidence` records; quality is a screening heuristic, not a correctness proof |
| Verified evidence collection | implemented, verified | `LibraryService.collect_evidence`, MCP tool `get_verified_evidence`, Web `/api/evidence` |
| Original verification | implemented (NDL IIIF, IA), verified | NDL: manifest/canvas/image checks. IA: metadata/access/djvu/page-range/OCR/image checks. Gallica IIIF verification implemented, not live-verified |
| Evidence-grounded answers | implemented, verified with mock provider | Real LLM is optional and disabled by default; citations whitelist-validated twice (provider and service layer) |
| Insufficient-evidence handling | implemented, verified | Status `insufficient_evidence`; no answer is produced from bibliographic data alone |
| Web UI (search + answers + evidence) | implemented, verified | Citation chips jump to evidence cards; inline IIIF verification; JA/EN toggle; claim support badges; IIIF image previews; query-language hint; document comparison view |
| Claim-level grounding screening | implemented, verified with mock provider | Per-claim support status (lexical screening + date-token checks + material numeric check); not a semantic proof |
| Question understanding | implemented (Phase 4) | Rule-based analysis: core concepts vs generic terms, era (incl. era-year conversion), region, intent, structured requirements; no LLM required |
| Relevance gate | implemented (Phase 4), live-evaluated | Per-page relevance screening (relevant / partially_relevant / irrelevant / uncertain) with reasons, separate from the OCR quality gate; only `relevant` pages ground answers, the rest are shown as related reference material |
| Answer withholding | implemented (Phase 4) | Answers are withheld when a screened claim is unsupported/conflicting (`answer_withheld`), and refusals name the missing core concepts with related documents attached |
| Answer-quality evaluation | implemented, Phase 4 runs done | 70-question dataset + fixture suite + runner in `eval/`; before/after results and failure analysis in `docs/evaluation.md` |
| Document comparison | implemented, verified | `compare_documents` (MCP + Web): aspect rows over verified pages, shared/unique terms, gaps, era notes |
| Web API rate limiting | implemented | Per-IP sliding window, 120 req/min default (`GLM_RATE_LIMIT_PER_MINUTE`), 429 on excess |
| MCP server | implemented | Tools listed in README.md |

## Adapters

| Library | Search | In-document | OCR pages | IIIF verify | Live status (2026-11-22) |
|---|---|---|---|---|---|
| NDL (JP) | yes | yes | yes | yes | verified end-to-end |
| Library of Congress (US) | yes | no | no | no | search verified |
| Internet Archive | yes | yes | yes (djvu.xml) | yes (non-IIIF checks) | page evidence live-verified 2026-11-22 (Phase 3) |
| DDB (DE) | yes | no | no | no | search verified |
| Gallica / BnF (FR) | yes | no (no official API) | yes (texteBrut) | yes (IIIF) | implemented but upstream 403 from verification network; NOT live-verified |
| Europeana (EU) | yes | no | no | no | awaiting `EUROPEANA_API_KEY` |
| All other registry entries | no | no | no | no | research only (see `libraries.yaml`) |

## Not implemented

- Page-level evidence for non-NDL libraries (Gallica ALTO / IIIF Content Search is the
  most promising next step; Internet Archive full-text endpoints are another).
- Printed-page-number resolution for NDL pages (the Page API does not expose it; the
  field stays `unknown` rather than guessed).
- Cross-document comparison beyond two documents' token contrast (LLM-assisted synthesis with per-claim citations) — the deterministic `compare_documents` exists; interpretive synthesis does not.
- Vector search / embeddings (deliberately out of scope for this design).
- Any production deployment.
