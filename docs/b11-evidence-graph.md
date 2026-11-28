# b11 Evidence Graph (sections 31-39)

Implementation: `src/global_library_mcp/evidence_graph.py`.

- Node types: research_question, claim, evidence_candidate,
  document, page, person, work, edition, concept, source,
  comparison, timeline_event, report. Edge types and relation
  states follow sections 32-33 verbatim (`confirmed_reference`,
  `candidate`, `user_asserted`, `imported_unverified`,
  `restored_unverified`, `independently_reviewed`, `invalidated`,
  `unresolved`).
- Node IDs are stable (`document:<library>:<record>`,
  `claim:<artefact_id>:<claim_id>`, ...); every node/edge
  carries provenance; the graph is project-scoped and dangling
  or cross-project references are refused.
- **Trusted inputs only**: workspace documents/citations and
  `research_artefacts` rows. Note envelopes, arbitrary JSON,
  hand notes, unverified lexicon entries, user-set verified
  flags, imported claims and self-computed hashes never create
  `confirmed_reference` edges. Imported/restored artefacts
  appear only with their downgraded states.
- Revalidation: the graph is rebuilt from current store state
  on every read (section 39). Downgrading a citation/document
  or restoring a backup immediately downgrades dependent edges;
  historical observations stay in the store but are never
  rendered as currently valid.
- Capacity (section 38): 2,000 nodes / 5,000 edges caps with
  `omitted_nodes` / `omitted_edges` reported, offset/limit
  paging. Scale evaluation (`eval/b11_graph_scale.py`):
  100 docs -> 101 nodes in 0.004 s; 1,000 -> 1,001 nodes in
  0.042 s; 10,000 -> capped at 2,000 nodes (8,001 omitted) in
  0.498 s (build time only; fixture store writes excluded).

## Claim structuring (section 35)
`structure_claim` now also extracts event / condition /
modality / negation / attribution / uncertainty from surface
markers only, and records a per-field `extraction` state
(`extracted` / `not_extracted`). Fields absent from the text
stay not-extracted; nothing is completed from world knowledge.
Text preservation (the original statement) and extraction
success are reported separately.

## Per-claim evidence (section 36)
`summarize_claim_evidence` groups assessments into supporting
candidates / contradicting candidates / related / insufficient /
not_checked and counts independence-confirmed vs
independence-unknown support separately; unknown independence
is never phrased as multiple independent evidence.

## Source dependence (section 37)
`assess_source_dependence`: explicit reprint/derivation ->
`confirmed_dependent`; any weaker signal (same publisher+year,
shared citation chain, high text similarity) -> at most
`suspected_dependent`; recorded bases on both sides and no
signal -> `independence_confirmed`; otherwise
`independence_unknown`. Similarity alone confirms nothing.
