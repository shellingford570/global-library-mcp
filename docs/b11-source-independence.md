# b11 Source Independence (sections 34/37)

Independence is a property that must be EARNED with a recorded
basis, never a default:

- `compare_facts` (Stage 0): `independence_confirmed` counts
  only with a non-empty `independence_basis` and no
  `dependent_on`; conflicting flags fall back to unknown and
  are counted in `independence_flag_conflicts`.
- `assess_source_dependence` (Stage 3): dependence states are
  confirmed_dependent / suspected_dependent /
  independence_unknown / independence_confirmed under the rules
  in docs/b11-evidence-graph.md.
- Claim-evidence summaries keep confirmed and unknown counts in
  separate keys; UI/report layers must not merge them.

When nothing can be confirmed, confirmed = 0 is the correct
answer, and b11's own fixture measurements indeed confirm 0
independent sources for the synthetic project scenarios.
