# b10 Final Review — fixes, measurements, and remaining limits

This document records the external final review of the b10
candidate (PR #21, candidate head `dc8d794`), the reproduction of
each finding BEFORE fixing, the fixes, and the re-measurements.
Measurements name their commit context, dataset, denominator and
evidence kind. Nothing here upgrades a proxy evaluation into a
human evaluation: independent human-verified labels remain **0**.

## 1. Reproductions (pre-fix, HEAD dc8d794)

Reproduction script: `~/workspace/glm-scratch/b10-final-repro.py`
(local record; results reproduced in this document).

| # | Finding (brief section) | Reproduced |
|---|---|---|
| 1 | Semantic scores never passed to the ranker on the service path (§4) | Yes — `semantic_scores` absent from service.py |
| 2 | No model integrity verification; backend rebuilt per call (§6) | Yes — no hashing; `get_local_backend()` constructed a new backend each call (and `/api/features` called it twice per request) |
| 3 | Local lexicon alone could reach `authority_verified` (§7) | Yes — Kant (local only) → `authority_verified` |
| 4 | Same-GND-id conflicting years lost in merge (§8) | Yes — two fetched GND records (1724 vs 1700) merged → `authority_verified`, no conflict |
| 5 | `identify_edition` presented a year match as an edition (§11) | Yes — no candidate marker |
| 6 | 100 kW vs 100 MW → `consistent_candidate` (§15) | Yes |
| 7 | Different documents counted as independent sources (§16) | Yes — `independent_source_count == 2` for two arbitrary documents |
| 8 | Different-place facts → `contradiction_candidate` (§15) | Yes |
| 9 | Caller-forged `admitted: True` assessed as evidence (§13) | Yes — reached `supported_candidate` |
| 10 | Artefacts: any note JSON with a b10 kind trusted (§17) | Yes (code inspection + post-fix test) |
| 11 | Series dedupe by normalised title+author deleted editions (§11) | Yes — code path `seen_series` |
| 12 | Adaptive stop decided before bibliographic filters (§12) | Yes — stop at source offset 68718 < filter at 70370 |
| 13 | Session capacity checked non-atomically (§26) | Yes — per-token/user caps only checked when the SDK returned a session id |
| 14 | ResearchRanker crashed on real SearchResult objects | **Found during this review** — `SearchResult` is a slots dataclass; `_research_score` assignment raised AttributeError (the Stage-3 eval used SimpleNamespace items, so this never fired). Fixed by a side table. |
| 15 | Adaptive-stop guard UnboundLocalError | **Found during this review** by the stop A/B probe — `_strict` unbound when no filter present. Fixed + regression test. |

## 2. CI separation (section 3)

- `docker-playwright` is now a **mandatory fixture job**: Docker
  build, non-root image user asserted, container started with
  `GLM_UPSTREAM_FIXTURE_DIR` mounted read-only, Playwright 17
  journeys asserted `passed == 17 && skipped == 0`, plus
  `tests/e2e_smoke_fixture.sh` (health, HTML, fixture search
  IA+NDL, document detail, NDL page OCR + verified mapping, IIIF
  manifest/canvas/image verification via `/api/verify`, compare,
  cancel, partial results on upstream error). Real server,
  LibraryService, adapters, BudgetedTransport; only upstream
  HTTP is fixed.
- New NDL fixtures were added (search, page `974405_2`, IIIF
  manifest, IIIF image) in the providers' real response shapes.
- `docker-live-smoke` is a new **informational** job running the
  rewritten `tests/e2e_smoke.sh`, which reports each stage and
  the HTTP status and preserves failures in the uploaded result
  file. The NDL page API 500 is recorded as an upstream failure,
  never rewritten into a normal response.
- `workspace-live` remains informational, as before.

## 3. Semantic search on the real service path (sections 4–6)

- `LibraryService.collect_evidence` / `research_materials` accept
  `ranking_mode` ∈ {legacy, lexical, semantic, hybrid} (also via
  MCP `research_materials`, Web `ranking_mode` parameter, and the
  Web UI selector). Default remains **legacy**.
- Every search response carries a `ranking` block:
  requested/effective mode, `semantic_backend_available`,
  `semantic_applied`, `fallback_reason`, `model_id`,
  `model_revision`, `candidate_pool_size`; per-result
  `ranking_reasons` are attached when a ranker ran.
  `semantic_applied` is true only when scores were actually
  computed and fused for that call.
- Model integrity: `semantic_local.MODEL_MANIFEST` pins the model
  id, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, the
  SHA-256 of the ONNX graph
  (`98a01d88…dc334f`) and of `tokenizer.json` (`2c3387be…076b8`),
  and size caps. `verify_model_dir()` refuses missing, symlinked,
  oversized or hash-mismatching files before any load.
- The backend is a process-wide singleton (measured cached
  access 0.021 ms vs first load 1,057 ms including hash
  verification); providers are CPU-only; output shape and
  NaN/Infinity are validated; inference runs through
  `encode_async` (executor) on the service path; batch ≤ 64,
  text ≤ 2,000 chars.
- Fallback: semantic/hybrid requested without a usable model →
  effective mode lexical with an explicit `fallback_reason`
  (never a silent claim of semantic search).

### Evaluations (measured 2026-11-28, this machine, CPU)

- **A. Whole-corpus ranking** (b6 simulation corpus, fixed split,
  35 scored cases; proxy labels): LEX Recall@10 0.7286, SEM
  1.0000, HYB (RRF) 0.8905 — re-measured at the final-review head
  (`eval/results-b10-final-semantic-fixed.json`). This is a
  small-corpus proxy measurement, **not** end-to-end search
  recall.
- **B. Candidate-pool re-ranking** (lexical top-20 pool per case,
  same corpus/cases): pool-order Recall@10 0.7286, semantic
  in-pool 0.8071, hybrid in-pool 0.8071
  (`eval/results-b10-final.json`). Re-ranking cannot resurrect
  records retrieval never found.
- **C. Real HTTP path**: local web server + fixture upstreams +
  real MiniLM — `GET /api/search?...&ranking_mode=semantic`
  returned `semantic_applied: true` with the pinned model
  id/revision; `/api/features` reports availability and the
  unavailable reason when no model is configured.
- **D. Evidence impact** (stub service probe): legacy and
  semantic modes produced identical admission outcomes
  (0 admitted / 1 unverified on the probe) — the frozen gates,
  not the ranker, decide admission.

## 4. Authority (sections 7–10)

- `authority_verified` now requires ALL of: an official-source
  record **actually fetched** (observation with `fetched=True`
  and an id strictly matching its scheme), exact name/variant
  match, ≥1 independent auxiliary signal (life-year or associated
  work match), person-type agreement, no unresolved ±1-year
  ambiguity and no conflict. Identifiers merely written in the
  local lexicon are **unverified** and can never verify.
- Observations are preserved per source before merging; years
  are never overwritten. The same authority id with disagreeing
  years → `conflicting_authorities`; a ±1-year disagreement is
  kept **ambiguous** (a calendar explanation requires an explicit
  documented basis, which is absent in the general case).
- GND queries: the name is stripped of Lucene syntax characters
  and sent as a single quoted phrase value; a test proves user
  input cannot inject fields/operators.
- Live authority clients remain **developer-experimental**
  (`LIVE_SOURCES_EXPERIMENTAL`): their synchronous, unbudgeted
  HTTP path is not wired into production search.
- Evaluation v2 (`eval/b10_authority_eval2.py`,
  `eval/results-b10-final-authority.json`): input conditions
  separated, no answer-key leakage. Over 20 identify cases
  (dev+fixed+holdout): name-only top-candidate correct 20/20,
  verified **0/20 in every mode** (local-only; denominator
  stated); official-fixture probes: fetched official + stated
  years → verified; same-id conflict → conflicting; local-only →
  candidate.

## 5. Editions, dedupe, adaptive stop (sections 11–12)

- Dedupe is now exact `(library_id, record_id)` only. Different
  editions/volumes/translations with distinct record ids are all
  kept (test: Kant 1781 + 1787 both survive). Work grouping
  remains presentation-only.
- `identify_edition` returns `status: edition_candidate`,
  `basis: publication_year_only` — a year never proves an
  edition.
- `adaptive_stop_allowed()`: the stop is refused when a
  bibliographic filter is present, when the user pinned the
  library set, or when the query intent is edition comparison /
  translation comparison / primary-source hunting (cue-based),
  and the strict signal is re-checked against the filtered pool.
  `GLM_ADAPTIVE_STOP=0` disables it. A/B probe (stub service):
  stop event fires only when allowed; materials identical (4)
  in the probe either way. The Stage-3 service measurement
  (attempts 22.9 → 22.1) remains the service-level figure; no
  larger claim is made.

## 6. Claims, contradictions, independence (sections 13–16)

- `assess_claim_evidence` assesses ONLY candidates built by
  `build_trusted_candidate()` — carrying `admission_source =
  glm_evidence_pipeline` and a complete `evidence_ref`
  (library/record/page/citation ids, excerpt offsets + SHA-256,
  admission and identity states). A bare `admitted: True`, a
  missing page id or a forged source is `not_checked` with the
  reason. Rows carry claim_id, the full reference, used and
  unconfirmed signals; `supported_candidate` requires every
  present claim element (subject, time, place, quantity+unit)
  to match; conditional passages are contextual only.
- `compare_facts`: identity (subject/predicate/object) mismatch
  → `insufficient_context`; place/scope/definition mismatch →
  `differing_scope`; SI unit conversion (kW/MW/GW, km/m, t/kg)
  with converted values recorded — 100 kW vs 100 MW is a
  contradiction **candidate**, never consistent; both-negated
  pairs are not mutual contradictions; `contradiction_confirmed`
  does not exist.
- Independence accounting: `evidence_item_count`,
  `distinct_document_count`, `distinct_library_record_count`,
  `source_family_candidate_count`,
  `known_dependent_source_count`, `independence_unknown_count`,
  `independently_confirmed_source_count`. Distinct documents are
  never independent sources; the legacy
  `independent_source_count` key is now `None` by design.
- Re-measured claims evaluation (frozen b10 dataset, trusted-ref
  inputs): structure fields actually evaluated (era + place)
  dev 8/8, fixed 7/7, holdout 5/5 — reported as **era/place
  extraction only** (section 23: predicate/object extraction is
  NOT evaluated and not claimed); snippet mapping dev 2/7,
  fixed 4/8, holdout 2/5 (down from 4/7, 5/8, 2/5 — the stricter
  supported gate under-promotes; thresholds were NOT loosened);
  contradiction dev 8/10, fixed 6/6, holdout 4/4;
  **false support promotions 0 on all splits**.
- New agent-authored challenge set (10 probes in
  `eval/b10_final_eval.py`): 10/10. Proxy labels; human-verified 0.

## 7. Workspace artefacts (sections 17–19)

- Strict per-kind schemas (types, unknown-field rejection),
  payload ≤ 64 KiB, lists ≤ 100, depth ≤ 6. Text-bearing fields
  (`ocr_text`, `full_text`, `page_text`, image payloads) are
  rejected — artefacts reference saved citations/documents by
  id; excerpts ≤ 200 chars. Referenced documents/citations must
  belong to the project.
- Envelopes are v2 with provenance + integrity hash. Only intact
  server-generated artefacts count in progress tallies; v1 /
  hand-written lookalikes are `user_asserted`, imports are
  `imported_unverified`, and neither can change verified-adjacent
  counts (tested with a forged `authority_verified` note).
- Relationship graph: ≤ 200 nodes / ≤ 500 edges, groups > 8
  aggregated through a group node, omitted counts reported,
  cross-project edges never emitted.
- No DB schema change; existing workspace data untouched
  (schema version and integrity asserted in tests).

## 8. External MCP sessions (sections 26–27)

- Capacity is **reserved atomically before** the SDK runs an
  initialize request (global / per-token / per-user, reservations
  included in the counts); reservations convert to bindings on
  session creation and are released on failure. `last_seen` is
  updated only after ownership verification. Concurrent test:
  10 simultaneous initializations against a per-user cap of 3 →
  exactly 3 created, 7 × 429, no residue.
- What remains true and is stated plainly: the middleware cannot
  reach inside the SDK to free its internal session objects when
  a binding expires; the binding layer refuses foreign/expired
  use, but SDK-internal resource accounting was not directly
  measurable from here. Stateless HTTP was considered and not
  adopted: it would change MCP client compatibility for a
  problem the reservation now bounds; the binding caps remain
  the enforced limit. Production connection blockers unchanged
  (DNS pinning, production IdP, Plus route).
- External separation re-verified by the existing suites: the
  external profile has no access to the local model, authority
  clients, artefacts or workspace; original-text and image
  transmission stay disabled; consent/budget/response caps are
  covered by the b9 integration suite and the 164-case security
  evaluation (both re-run for this release).

## 9. Causality: what actually improved the b6 numbers (section 20)

Same corpora (b6 fixed F / challenge F), simulation evidence:

| Config | Composition | fixed R@10 | challenge R@10 | avg attempts |
|---|---|---|---|---|
| A | b9 code + old evaluator + old lexicon | 0.8819 | 0.8611 | 40.2 |
| B | b9 code + **fixed evaluator** + old lexicon | 0.9005 | 0.9444 | 32.5 |
| C | B + new lexicon | 0.9005 | 0.9444 | 32.6 |
| D | b10 code + fixed evaluator + new lexicon (= this release) | **0.9167** | **1.0000** | 33.4 |

Decomposition (fixed / challenge): the evaluator routing fix
accounts for +0.0186 / +0.0833; the lexicon additions account
for **0.0000 / 0.0000 on these sets** (measured, not assumed);
the remaining b10 production-code changes account for
+0.0162 / +0.0556. Evaluator-fix gains are NOT product gains and
are reported separately, as required.
E (D + adaptive stop) is a service-level policy, not expressible
in the simulation harness; F (ResearchRanker) and G/H (semantic
/ hybrid) are reported by the ranking and whole-corpus
evaluations above; ResearchRanker remains **opt-in, not the
default**.

Full metrics at D (fixed evaluator): b6 fixed R@5 0.9167,
R@10 0.9167, R@20 0.9167, P@5 0.3944, MRR 0.8519, nDCG@10
0.8266, cross-language 0.6111; b6 challenge R@5/10/20 1.0000,
P@5 0.2444, MRR 0.8611, nDCG@10 0.9000; b8 fixed/standard
R@10 0.7667, cross-language discovery 0.7500. All §24 targets
met under the fixed evaluator. Author/work/edition candidate
precision is measured by the authority evaluation (§4 above);
negative-case false-candidate rates are in the b6 aggregates
(fixed 0.75 of negative cases surface some candidate — reported
in the eval JSON, unchanged in kind from b9).

Service fixture evaluation (Quick regression, §24): see
`eval/results-b10-final-service.json` — Quick F08
(マックス・ウェーバーの宗教社会学) retrieves only
`ndl:weber-shukyo` in quick mode because the German/English
variants that find `ddb:protestantische-ethik` /
`ia:protestant-ethic-en` are standard/deep-only — a pre-existing
mode-coverage property, disclosed in Stage 3 and unchanged.

## 10. Dataset independence and labels (sections 21–23)

- Grouped analysis: 8 authors and 6 works span multiple splits
  of the frozen 260-case dataset (split is by case-id hash), so
  split scores are not entity-independent; the holdout is a
  regression set from now on. Dataset SHA-256 values are in
  `eval/results-b10-final.json`.
- Label recount (§22): of 68 cases claimed
  `bibliographic_source_supported`, only **21** are backed by an
  individually verified identifier (GND ids live-verified
  2026-11-28 for the case's author); the recount is
  source_supported 21 / agent_assigned 239 /
  independent_human_verified **0**.
- Unmeasured/deferred, explicitly: predicate and object
  extraction (not evaluated), role-based traps in the authority
  dataset (translator/editor/about-vs-by — partially covered by
  the new challenge probes, not by the frozen dataset), NLI
  (not implemented; b11 design only).

## 11. Live verification (section 25)

- Kant, live, 2026-11-28 (final-review head): two standard-mode
  runs. DDB was queried and returned results; the German
  original-work record **"Immanuel Kant's Kritik der reinen
  Vernunft", ed. Benno Erdmann, DDB record
  `IFETABGFTVCC7E7FQOYD7XFZY73GAXD4`** is rank 1 at DDB for the
  German query (direct check), and a second DDB record
  `KA4K7RVTIMAUOUIOJ63NSNO6UBOWFWDL` is titled "Kritik der
  reinen Vernunft, zweite Auflage" (Hartknoch, Riga) — an
  edition **candidate** only; no year is recorded by DDB here,
  so no 1787 identification is claimed. In the two multilingual
  pipeline runs the DDB records did **not** reach the materials
  top-10 (IA noise ranked above them) — a worse outcome than
  the single Stage-6 run (#1 French translation IA, #10 DDB).
  Both are single-run live observations under upstream noise;
  neither is a settled ranking. The found record's OCR or any
  historical claim was NOT verified by this check.
- NDL page API (`lab.ndl.go.jp/dl/api/page/...`) still returned
  HTTP 500 on 2026-11-28 — recorded in the informational live
  job; the same path passes over fixed fixtures.

## 12. Performance (section 30, this machine, CPU)

- Model first load (incl. SHA-256 verification): 1,057 ms;
  cached singleton access: 0.021 ms; encode 30 texts: 45 ms;
  whole-corpus encode ≈ 9.6 ms/text.
- ResearchRanker re-rank: 10 items 1.45 ms, 30 items 3.17 ms,
  50 items 5.99 ms (lexical configuration).
- Model-free startup and the remaining service timings are in
  `eval/results-b10-perf.json` / `docs/b10-performance-evaluation.md`.
  Max RSS and concurrent-search measurements were not taken in
  this round — stated as unmeasured, not estimated.

## 13. Not achieved / still blocked

- DNS pinning unimplemented; no production IdP; ChatGPT Plus
  route unconfirmed; real-library text transfer disabled by
  construction. ChatGPT not connected; no tunnel created.
- NLI not implemented (second model not approved).
- Zotero: format-level 13/13 on synthetic records; real-app
  import unverified (no Zotero in this environment).
- Live authority APIs: experimental only (unbudgeted sync path).
- SDK-internal session resource release: not directly
  measurable (see §8).
- Human evaluation: 0 cases. All research-intelligence metrics
  are proxy evaluations over agent-assigned labels (21 cases
  source-supported after the recount).
