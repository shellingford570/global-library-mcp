# b11 NLI Shadow Evaluation (sections 27-30)

## Design
- `src/global_library_mcp/nli_backend.py` defines
  `LocalNLIBackend`, `UnavailableNLIBackend` (production
  default) and `SyntheticNLIBackend` (tests/proxy only).
- `shadow_assess()` records `nli_relation`, `nli_scores`,
  `nli_model_id`, `nli_model_revision` and `nli_status`
  (`unavailable` / `synthetic_test` / `shadow_evaluated`)
  ALONGSIDE `rule_based_status`. The rule-based status is
  returned unchanged on every path.
- Contradiction from NLI is recorded as
  `contradiction_candidate`, never as a confirmed contradiction.
- NLI never promotes a candidate the rule gate rejected, never
  confirms support, and its scores are never displayed as a
  probability of correctness (section 52 applies to NLI too).
- The pre-existing Phase 8/9 plumbing (`nli.py` `NliChecker`,
  `GLM_SHADOW_NLI=1` hook in `collect_evidence`) remains as-is;
  it degrades to `not_checked` because no model is present.

## Proxy evaluation (section 29)
`eval/b11_nli_cases.json`: 14 agent-labelled proxy cases
(direct support, numeric conflict, negation, era mismatch, unit
mismatch, partial support, unrelated; en/ja/de/fr/fi; one
OCR-noise case with historical glyphs). Labels describe the
intended NLI task; they are not human annotations.

Result with the SYNTHETIC backend (`eval/b11_nli_eval.py`):
agreement 0.857 (12/14). Known synthetic misses are recorded in
`eval/b11-nli-proxy-result.json` (unit mismatch kw vs MW scored
as entailment by token overlap). **This measures the harness and
the stand-in, not any real model.** Real-model shadow quality
is unmeasured until a model is approved and downloaded.

## Interpretation of the synthetic result (final review section 35)

The 0.857 (12/14) figure measures ONLY that the interface, the
status separation (`synthetic_test` vs `shadow_evaluated` vs
`unavailable`), the shadow plumbing and the evaluation harness
behave as designed. It is **not** a measurement of any real
model's NLI quality: the synthetic backend is a lexical-overlap
stub (`synthetic-lexical-overlap-v1`). Synthetic output is
stored and displayed only under the `synthetic_test` status and
is never written into research reports as an NLI judgement
(`synthesis.py` does not consume NLI output at all). Real-model
quality remains **unmeasured** until a separately approved
model acquisition happens.
