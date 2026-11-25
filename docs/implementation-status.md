# Implementation status

Last updated: 2026-11-24 (branch `feat/global-library-research-engine-v8`, Phase 8).
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
| Candidate pool + bibliographic ranking (Phase 6) | implemented, verified | All query variants run; series dedupe; ranking by title families, metadata match, query multiplicity (`rank_candidates`) |
| Staged document fetching (Phase 6) | implemented, verified | Wave 1 screens up to max_documents+6 candidates x2 pages, wave 2 deepens partially relevant documents (incl. adjacent pages), wave 3 extends to deeper candidates |
| Page kinds + document-union promotion (Phase 6) | implemented, verified | `classify_page_kind` (front_matter/photo_plate/table/body); union promotion when one document's pages jointly cover all concept families under era + non-contradiction guards |
| Semantic / temporal screening (Phase 5, maintained Phase 6) | implemented, verified | Rule-based stance checker + temporal anchoring; onset detection per sentence; year-gated anchor inheritance; `GLM_SEMANTIC_EMBED_MODEL` attaches the embedding checker as a signal (model itself unverified in this environment) |
| English question analysis (Phase 6) | implemented, verified live | Content-word phrases, word-century/decade/era-name dates; IA and NDL both yield evidence for the reference questions |
| Evidence admission rule (Phase 7) | implemented, verified | `admission_decision` governs direct/promotion/union paths: era answers need anchored assertions; mentions never ground era answers; structured promotion record on every admitted page |
| Numeric binding (Phase 7) | implemented, verified | Kanji/Arabic quantity values; a numeric claim needs the value bound to the asked target; table-only values unverified (`numeric.py`) |
| Page kinds v2 + usage policy (Phase 7) | implemented, verified | index/colophon/admin_list/title_page/damaged added; bibliographic questions may use title/colophon, structure questions front matter |
| Search cache (Phase 7) | implemented, verified | Per-instance bibliographic cache + substring-variant dedupe (`cache_stats`) |
| Original verification | implemented (NDL IIIF, IA), verified | NDL: manifest/canvas/image checks. IA: metadata/access/djvu/page-range/OCR/image checks. Gallica IIIF verification implemented, not live-verified |
| Evidence-grounded answers | implemented, verified with mock provider | Real LLM is optional and disabled by default; citations whitelist-validated twice (provider and service layer) |
| Insufficient-evidence handling | implemented, verified | Status `insufficient_evidence`; no answer is produced from bibliographic data alone |
| Web UI (search + answers + evidence) | implemented, verified | Citation chips jump to evidence cards; inline IIIF verification; JA/EN toggle; claim support badges; IIIF image previews; query-language hint; document comparison view |
| Claim-level grounding screening | implemented, verified with mock provider | Per-claim support status (lexical screening + date-token checks + material numeric check); not a semantic proof |
| Evidence states + stage log (Phase 8-B) | implemented, verified | Per-page states (discovered / accessible / source_verified / relevant_candidate / supporting_passage / assessed_evidence / rejected_for_answer) with plain-language rejection reasons; per-stage outcome log on every collect |
| Passage extraction (Phase 8-C) | implemented, verified | Verbatim, char-located passages with context, era anchors, stance cues; `verify_quote` re-checks quotations against the fetched OCR (`passages.py`) |
| Research-materials mode (Phase 8-D) | implemented, verified | Same pipeline as answer mode (no duplicate calls); candidates presented as candidates with not-admitted reasons; MCP tool + `/api/materials` + Web UI mode |
| NLI checker interface (Phase 8-E) | implemented, model unverified here | Hypothesis-based (`nli.py`); verdict is an auxiliary signal, never an approval; load attempted once with a hard timeout - transformers/weights unavailable in this environment, recorded `not_checked` |
| Gold passage dataset (Phase 8-F) | implemented | `eval/gold-passages.json`: pipeline-admitted supporting passages + frozen Phase 7 must-reject fixtures, dev/eval split, agent-verified (no human-expert claim) |
| Real-LLM evaluation readiness (Phase 8-G) | implemented, not run | `llm_budget.BudgetPlan` guard (key, opt-in, priced model, estimate <= cap, --approve) + `eval/real_llm_run.py`; blocks with reasons and makes no call otherwise |
| Structured claims + partial answers (Phase 8-H) | implemented, verified with mock provider | claim_id / passage links / temporal scope / numeric values / support status / limitations; unverifiable claims are removed and the verified remainder is published as `answered_partial` |
| Request budget + circuit breaker (Phase 8-I) | implemented | `GLM_REQUEST_BUDGET` caps fetch waves; budget-limited insufficiency is worded as 'not confirmed within the budget'; per-library circuit breaker; FIFO-bounded search cache |
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

## b5 addendum (2026-11-25) — Global Coverage candidate

- BSB/MDZ: adapter implemented and live end-to-end verified
  (IIIF manifest, per-page hOCR, original image, proven page
  mapping, per-item manifest rights). ID-addressed: MDZ
  publishes no keyword search API. In-document search is
  bounded (20 pages) with explicit coverage.
- LoC: Chronicling America newspaper page OCR implemented and
  live verified (issue JSON segments + text-services full
  text + IIIF image info). General LoC remains bibliographic.
- e-rara: OAI-PMH metadata-by-ID adapter implemented and live
  verified; search and page OCR unsupported (no official
  interfaces confirmed). The OAI endpoint intermittently
  returns 503 (observed 2026-11-25, recovered minutes later).
- Shared IIIF module (Presentation v2/v3, ALTO, hOCR) in
  `iiif.py`; transport refuses unsupported content-encodings,
  treats truncated compressed streams as errors, and follows
  adapter redirects only within the same registrable domain.
- Registry: 25 entries; duplicate YAML keys are now refused by
  the loader; implemented libraries carry per-capability
  statuses. Adapters: 8. Page-OCR live-verified institutions:
  NDL, Internet Archive, BSB/MDZ, LoC (newspapers only).
- Details: docs/b5-global-coverage.md,
  docs/b5-live-verification.md, docs/library-coverage-roadmap.md.
