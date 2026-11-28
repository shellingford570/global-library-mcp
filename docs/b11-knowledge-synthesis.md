# b11 Knowledge Synthesis (sections 40-45)

Implementation: `src/global_library_mcp/synthesis.py`.
Template-based only; no LLM (paid or otherwise) is involved.

- Claim states (section 41): synthesis relabels assessments
  into supported_candidate / partially_supported /
  conflicting_candidate / contextual_only /
  insufficient_evidence / not_checked / unresolved. The
  synthesis layer has NO code path that produces a confirmed
  or verified state; unknown input statuses become
  `unresolved`.
- Timeline (section 42): date kinds stay distinct (event_date,
  estimated_era, publication_date, reprint_date,
  translation_publication_date, acquisition_date,
  verification_date); undated/invalid entries are counted, not
  placed; output states `causality: not_asserted`.
- Numeric synthesis (section 43): original value/unit always
  preserved; normalisation only within a unit family, with the
  conversion written out; target/region/era/definition/scope
  and the approximate flag travel with each fact. Averages,
  sums and rates across facts are never computed.
- Multilingual comparison (section 44): concept alignment and
  claim alignment are separate counts; sharing a concept never
  counts as sharing a claim.
- Further-research candidates (section 45): generated gaps are
  labelled `existence: unconfirmed`; additional searches run
  only on explicit user action or within the existing budget.
