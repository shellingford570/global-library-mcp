# b11 Final Review — fixes, measurements, and remaining constraints

This document records the b11 final-review round on PR #22:
every external-review finding was reproduced first
(`~/workspace/glm-scratch/b11-final-repro.py`, kept outside the
repo), then fixed on the branch in topic commits, with
regression tests in `tests/test_b11_final_review.py` and
`tests/test_b11_policy_compare.py`. Measurements name their
target code, conditions, evidence type and denominator.
Unmeasured items are stated as unmeasured.

## Part 1 — P0 trust boundaries (sections 3-11)

- **Evidence references (3-6).** `register_admitted_evidence`
  no longer defaults identity/admission states: states are
  derived from the actual `Evidence` object or recorded as
  `unrecorded`/`reference_only`, and such references are refused
  by the assessment path. Snapshots carry operation/session/
  project/citation bindings, excerpt offsets/hash, OCR source,
  rights, issue time and policy version. Registry caps: 4096
  global / 512 per session / 256 per operation, TTL 3600 s,
  thread-safe expiry purge and explicit revocation.
  `evidence_ref_status` reports current / expired /
  unknown_or_revoked / invalidated / revalidation_required
  against the live store (citation deletion, project mismatch,
  excerpt-hash change and rights-category change all
  invalidate). Caller-supplied years/place in
  `build_trusted_candidate` are kept only as `user_asserted`;
  assessment derives years from the registered text.
  The 10 required tamper negatives (other library / record /
  page, tampered years / place / rights_state, cross-project
  citation, missing text, non-string text, deleted citation)
  are all rejected — tests in `test_b11_final_review.py`.
- **Independence (7).** Confirmation now requires an explicit
  `independence_review` record (non-trivial basis ≥ 12 chars,
  non-empty source). Bare basis strings count as
  `user_asserted_independence` only. The six-state model is
  applied uniformly in `compare_facts`,
  `summarize_claim_evidence` and `assess_source_dependence`;
  `independently_confirmed_source_count` stays 0 without a
  reviewed record.
- **Artefact schemas (8-10).** `validate_payload` is a complete
  recursive per-kind schema: closed key sets at every level,
  required fields, status vocabulary (strings only), finite
  numbers, per-field string caps, list/depth/node caps, empty
  payload refused. `reference_problems` validates references
  recursively (citation ↔ document ↔ page consistency,
  saved_document_id ↔ (library, record) consistency, project
  membership) at save time and again at read time
  (`reference_integrity` on listed artefacts). Text-bearing
  keys are refused at any depth, so server artefacts reference
  citations by id instead of copying upstream text.
- **Rights observation order (11).** Schema v6 adds a monotonic
  sequence (`rights_seq_counter`, backfilled in rowid order on
  migration). Latest-observation selection orders by sequence;
  same-timestamp conflicts between server and non-server
  observations fail closed to the restrictive category.
  Negative tests: PD→In Copyright within one second resolves
  to In Copyright; the reverse order with an explicit later
  server observation resolves to Public Domain; an imported
  same-timestamp conflict fails closed.

## Part 2 — Evidence Graph (sections 12-19)

`evidence_graph.py` was rewritten over the real persisted
fields (`saved_document_id` joins). Question and claim nodes
appear for every claim artefact, including claims with zero
assessments (`evidence_state: no_evidence_registered`).
Assessment edges use the closed section-13 mapping; unknown
statuses map to `unresolved_reference`, never to support.
Provenance (`server_generated`) is an attribute, never a
confirmation: support edges stay `candidate`, and author/work
relations are `author_candidate`/`work_candidate`. Holding
relations (`held_by`) are separated from source-family
relations. Page/citation nodes come from saved citations with
their current verification and rights state (reference remains
available while excerpt display is forbidden). Generation is
index-based with deterministic edge ids, stable sorted paging,
explicit stub nodes for off-page endpoints, exact omitted
counts, and a 32-level depth cap on traversal. Edition nodes
are not generated (publication year alone is insufficient) and
concept nodes only from real comparison dictionary overlap —
both stated here as defined-but-limited.

## Part 3 — Reports (sections 20-27)

- Imported/restored artefacts are historical assertions:
  excluded from `claim_states`, shown in
  `historical_claim_states` with `counted_as_current_evidence:
  false` (20).
- Citation integrity is re-checked at generation (library /
  record / saved document / page / excerpt hash / current
  verification state); failures downgrade the state to
  `unresolved` or `revalidation_required` (21).
- Every claim is displayed with statement, id, question link,
  support/oppose/context counts, independence, trust and last
  evaluation time; evidence-less claims show
  「根拠未登録」 (22).
- Markdown rendering uses the b7 `_md` escaper for all stored
  strings; injection negatives (fake headings, links, images,
  raw HTML, javascript: URLs) are pinned by tests (23).
- Claim → document traceability (title/author/year/citation
  key/URL/page) is present in both JSON and Markdown (24).
- `snapshot_id` hashes the full normalized inputs (project
  metadata, documents, citations, artefact payloads + trust,
  latest rights observation ids, policies, settings) and the
  report is generated under the store lock (25). Reports state
  they are current regenerations; saved report records freeze
  their save-time state (26).
- Numeric closeness (±10%) is labelled a comparison heuristic
  in `numeric_synthesis` output and in the report (27).

## Part 4 — Research API and UI (sections 28-32)

- New endpoints: GET questions/claims; claim linking
  (question / documents / citations); `assess` evaluates a
  claim against its saved citations through the frozen
  admission path (registry token issued from the citation's
  own excerpt and current verification states; unverified
  citations stay `evidence_reference_only`). No caller
  `admitted` flag exists — unknown fields are refused (422).
- Revalidation is split: `refresh` (state rebuild),
  `revalidate_references` (existence/consistency),
  `reverify_citation` (real original refetch via the existing
  `_reverify`), `revalidate_claim`. The legacy `revalidate`
  route answers as the refresh alias and says so. UI buttons
  use the same wording.
- Input validation: text fields must be strings (no `str()`
  coercion), length/byte caps, unknown-field refusal, NaN /
  Infinity JSON refused (400), structured 400/413/422 errors.
- New mandatory Playwright journey `tests/e2e/research.spec.js`
  (project → search → save → original page → citation →
  question → claim → citation link → assessment → graph →
  report preview → MD/JSON download → reload re-display),
  wired into the workspace CI job with a no-skip assertion.
  Local result: research 1/1, workspace 6/6 (fresh server).
  In one combined local run on this 1.5-CPU VM, two workspace
  journeys hit project-creation timing races under parallel
  load; both pass standalone. This is a local harness timing
  observation, not a product assertion failure.

## Part 5 — Models and evaluation (sections 33-39)

- **MiniLM gate (33).** The per-event-loop `asyncio.Semaphore`
  was replaced by a process-wide gate (threading semaphore +
  lock-guarded waiter count): the cap of 2 (queue 8, 5 s
  deadline) holds across loops, threads and Web+MCP combined;
  a reservation is released only when the inference thread
  finishes, including after caller cancellation (tested).
- **NLI (34/35).** No model was downloaded. The acquisition
  application is now concrete (per-file bytes and SHA-256 from
  the Hugging Face API, total 359,318,185 bytes for the
  quantized-ONNX set, no external data files, label mapping
  0/1/2 = entailment/neutral/contradiction, MIT) in
  `docs/b11-nli-model-selection.md`. The synthetic backend's
  0.857 (12/14) verifies interface/status/shadow plumbing
  only; synthetic output is never stored or displayed as a
  real NLI judgement, and reports do not consume NLI output.
- **Split coverage (36).** Measured by
  `eval/b11_split_coverage.py` over the 294-case set:
  persons 13/294 (4.42%), works 0/294, concepts 0/294,
  documents 0/294, source families 13/294 (4.42%);
  281 cases are ungroupable. Cross-split entity overlap 0
  applies ONLY to identifier-assigned cases; duplicate risk
  for the rest is UNCONFIRMED, not zero.
- **Blind review (37).** CSV/HTML contain no predicted or gold
  labels (the HTML's judgement words are the reviewer's input
  options). Import now rejects out-of-vocabulary judgements
  and conflicting duplicates, requires reviewer identity, and
  excludes blanks. Human evaluation remains **0**; agreement
  is **unmeasured**. The +6 lobid GND confirmations are
  source confirmations, not human evaluation.
- **Old vs new policy (38).** `tests/test_b11_policy_compare.py`
  reports agreement with the frozen b10 probe expectations
  and with the b11 policy separately (the three identity-less
  probes: old 0/3, new 3/3), and pins positive cases with full
  identity fields that DO compare (contradiction / consistent
  / differing scope). Frozen b10 files were not modified.
- **Quality metrics (39).** `eval/b11_quality_metrics.py`
  (agent-labelled built-in fixtures): year extraction 1.0
  (4/4), place 1.0 (4/4), subject 0.0 (0/4 — the structurer's
  subject differs from the fixture intent; disclosed, not
  tuned), original-statement preservation 1.0 (4/4),
  evidence-reference resolution: genuine 1/1, forged 0/1,
  false support 0/1, false contradiction 0/1, independence
  misrecognition 0 confirmed (2 asserted), report citation
  resolution 0.5 on the fixture (1 resolved / 1 missing by
  construction). Predicate/object/quantity/unit/negation/
  condition extraction rates are **unmeasured** (no labelled
  cases).

## Part 6 — Migration, scale, scenarios (sections 41-44)

- Restore validation now covers `research_artefacts` (trust /
  kind vocabularies, payload JSON shape and size) with
  version-conditional required tables (v5/v6); a backup's
  `server_generated` is never believed (restore downgrade
  unchanged). JSON import remaps nested references; graph and
  report rebuild after import with imported claims historical.
- Scale (`eval/b11_perf_final.py`, this VM): 100 docs —
  graph 18 ms, report 77 ms; 1,000 docs / 3,000 citations —
  graph 209 ms, report 0.90 s; 10,000 docs / 30,000 citations
  / 1,000 artefacts — graph generation 71,002 nodes / 81,000
  edges, build+page median 3.0 s, progress 7.1 s, report
  20.8 s, artefact save 1.6 s, peak RSS 375.6 MB. Processed
  totals are reported separately from paged counts.
  Reference-integrity indexing was changed from
  O(artefacts × project) to one index per listing to reach
  these numbers; 10k-scale report/progress remain slow and
  are a b12 design candidate, not hidden.
- Scenarios A-J: A research journey (Playwright, real HTTP);
  B evidence-less claim displayed without support (report
  test); C cross-document reference combination refused
  (section 9 test); D import non-promotion (stage 6 + report
  test); E citation deletion invalidates references (section
  5 test); F rights change incl. same-second PD→In Copyright
  (section 11 tests); G report shows evidence-less claims with
  resolvable references (report tests); H refresh vs refetch
  distinction (API test + UI wording); I 10,000-document
  capacity (perf measurement above); J external MCP profile
  exposes only its 5 search tools — no research artefact,
  graph, original-text or report tool exists in that profile
  (profile tests + security evaluation below).

## Part 7 — Regression (sections 45-47)

- Admission gates frozen: no changes to evidence admission,
  temporal anchoring, numeric binding, page kind, relevance
  gate, citation/claim verification, insufficient_evidence or
  answer_withheld logic in this round.
- MCP profiles unchanged: full 15 / research 14 / external 5;
  external original-text sending disabled.
- External security evaluation: **164/164**
  (`eval/b9_security_eval.py`); real-path integration suite
  6/6. CI success is not claimed as proof of no
  vulnerabilities.
- Search quality re-measured under identical conditions:
  b6 fixed (config F) Recall@10 **0.9167**, challenge
  **1.0000**, b8 fixed Standard **0.7667**, cross-language
  **0.7500** — all identical to the b10/b11 baselines.
  Service eval over fixed HTTP fixtures (10 cases):
  Quick Recall@10 **0.4667** (avg HTTP 12.6), Standard
  **0.8667** (avg HTTP 22.1) — also identical; Quick remains
  unimproved and is disclosed as such.
- Full pytest: see the release record (target ≥ 704 + new
  final-review tests, 0 skipped in mandatory suites).

## Remaining constraints (not release blockers, not hidden)

Independent human evaluation 0; NLI model not acquired;
Zotero real-app verification not done; source-confirmed
labels +6 only; evaluation set 294 cases; Quick Recall@10
0.4667 unchanged; Kant German-original ranking unstable
across runs; NDL page API still returns upstream HTTP 500
(informational live smoke only); external-connection blockers
unchanged (DNS pinning unimplemented, no production IdP, Plus
route unconfirmed, real-library text transfer disabled by
construction); ChatGPT is NOT connected.
