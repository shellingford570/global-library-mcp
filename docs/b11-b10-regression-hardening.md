# b11 Stage 0 — b10 residual trust-boundary hardening

Date: 2026-11-28. Base: master 333f314 (v1.0.0b10). All findings
were reproduced BEFORE fixing (reproduction script kept in the
working record; results below).

## Reproductions (before fix)

1. A hand-written note containing a v2 artefact envelope with a
   CORRECT self-computed SHA-256 and trust="server_generated"
   was counted as a server-generated artefact in research
   progress (claims_with_insufficient_evidence became 1).
2. A forged candidate dict with admission_source and a complete
   evidence_ref (hash of never-admitted text) passed _trusted_ref.
3. compare_facts counted caller-asserted independence_confirmed
   flags with no basis: independently_confirmed_source_count=2
   for two unbased flags.
4. compare_facts compared values with all identity conditions
   missing (no subject/predicate/object/place).
5. Quick-mode semantic fallback (code inspection + regression
   test): the sort key read the REQUESTED mode, so when a
   semantic request fell back to lexical, lexical scores were
   zeroed and the reported fallback never actually ranked.

## Fixes

- **Artefact authenticity (sections 5-7)**: artefacts moved to a
  dedicated `research_artefacts` table (schema v5; migration
  keeps the automatic pre-migration backup, runs in a
  transaction, future schemas are refused). The trust column is
  written only by server code paths. Plain notes are never
  artefacts; legacy note envelopes surface as
  trust="user_asserted" only. Project JSON import inserts
  artefacts as imported_unverified with citation/document
  references remapped (unresolvable references dropped and
  reported). Backup restore downgrades server artefacts to
  restored_unverified in apply_restore_trust_downgrade.
  Payload validation is now a recursive allowlist: closed
  nested key sets, closed status vocabulary, free-text fields
  (notes/note/reason/description/summary/excerpt/quote) capped
  at 200 chars so original text cannot be smuggled under
  another name, all strings capped, finite numbers only, node
  and depth caps.
- **Evidence references (section 8)**: trusted references are
  issued only by register_admitted_evidence(), called by the
  service for gate-admitted evidence; the registry keeps an
  immutable snapshot (ids, passage offsets, excerpt hash,
  identity states, rights state, admission time, TTL).
  build_trusted_candidate now requires a registry token and
  verifies the excerpt against the snapshot; assessment
  re-verifies token, fields, offsets and text hash, and refuses
  expired/revoked/mismatched references.
- **Independence (section 9)**: confirmed only with an explicit
  independence_basis AND no dependent_on claim; conflicting
  flags fall back to unknown and are counted in
  independence_flag_conflicts; each distinct document is
  counted in exactly one bucket; counts never go negative.
- **Comparison conditions (section 10)**: pairs missing
  subject/predicate/object/place/unit (with values present),
  or carrying NaN/Infinity, are insufficient_context.
  Affirm-vs-negate of the same value is a contradiction
  candidate; differing values under negation are not
  comparable; approximate values whose ranges overlap are
  insufficient_context. "No mismatch" is never reported as
  "agreement confirmed" without the identity conditions.
- **Semantic fallback (section 11)**: Quick and Standard paths
  now sort by the EFFECTIVE mode; invalid model output (NaN,
  dimension mismatch, score-count mismatch) triggers the
  lexical fallback with a recorded reason. cosine_scores
  validates dimensions and finiteness.
- **Model resources (section 12)**: encode_async is gated
  (max 2 concurrent inferences, max 8 queued waiters, 5 s
  acquire deadline, max 256 texts per call). The reservation
  is released only when the inference THREAD finishes, so a
  cancelled caller cannot leak or double-free a slot; timeout
  is never described as forced termination. process_rss_bytes()
  is available for memory reporting.
- **b10 artefact migration (section 13)**: existing v1/v2 note
  envelopes keep their content as researcher notes but are
  untrusted (user_asserted). No b10 tag or release is modified.
  NOTE for b10 users: b10 progress tallies that were produced
  from note-stored artefacts are recomputed under the stricter
  trust model in b11; hand-written envelopes no longer count.

## Stage 0 exit check (section 14)

Forged-promotion counts after the fix (tests/test_b11_stage0.py,
18 tests): artefacts 0, evidence references 0, rights smuggling
0, cross-project 0, import/restore forgery 0, independence
over-count 0, fallback display/execution mismatches 0. Model
resource caps verified by a concurrency test. Full regression
in the Stage 0 commit message.
