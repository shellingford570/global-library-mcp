# b11 candidates — Research Validation & Knowledge Synthesis

Design preparation only (updated for the b10 final review,
2026-11-28). Nothing here is approved or started; b11
implementation requires tana's separate approval.

## Priority 1 — Independent research-quality evaluation

- Human-assigned ground-truth labels (the b10 recount leaves
  21 source-supported / 239 agent-assigned / **0 human-verified**
  of 260 cases).
- Per-case source verification for bibliographic and authority
  labels (individual URLs / record ids / authority ids, checked
  fields, verification date).
- Relevance judgements for search results; page–OCR mapping
  verification on real records.
- Claim–evidence correspondence evaluation with the trusted
  reference format introduced in the b10 final review.
- Inter-annotator agreement reporting; a review UI or CSV flow
  (the b10 review sheet is the starting point).
- Entity-grouped splits (person / work / concept / source) as
  the primary reporting unit, since the case-hash split leaks
  entities across splits (8 authors, 6 works span splits).

## Priority 2 — Local NLI (design only; second model NOT approved)

- Candidate class: small multilingual NLI models with ONNX
  quantised builds (e.g. mDeBERTa-v3-base-xnli class models and
  distilled multilingual variants) — **no candidate is selected
  and none may be downloaded without separate approval** naming
  the model, licence, size and cost.
- For any future candidate, record before acquisition: model
  card, licence, parameter/quantised size, CPU inference cost,
  ONNX availability, Japanese/German/French coverage.
- Known limits to design around: historical orthography, OCR
  noise, negation/condition/numeric/era sensitivity; an
  embedding model measures similarity, NOT entailment — the
  b10 MiniLM must not be repurposed as an NLI judge.
- Shadow evaluation method: NLI scores recorded beside the
  frozen rule-based verification, never replacing it; promotion
  criteria and disagreement analysis defined in advance.
- Self-verification limit: the same model family must not be
  the sole judge of its own retrieval.

## Priority 3 — Evidence Graph

- Nodes: research question, claim, document, edition, page,
  verbatim citation, authority candidate, support candidate,
  contradiction candidate, independence state, source-dependency
  edges.
- Built on the b10 final-review foundations: trusted evidence
  references, edition candidates, source-family accounting
  (independence unknown unless confirmed with a basis).

## Priority 4 — Research knowledge synthesis

- Per-claim evidence lists across documents; difference lists;
  unresolved-item lists; chronological research views;
  multilingual document comparison; citation-bearing research
  reports. Synthesis never upgrades candidates into verified
  claims.

## Priority 5 — Real-use experience

- Research workspace polish; Zotero real-application
  compatibility (requires a real-machine environment, separate
  approval); research progress management; relationship
  visualisation within the b10 graph caps; export quality.

## Separate track — ChatGPT Controlled Pilot

Unchanged blockers: Plus connection route unconfirmed, DNS
pinning unimplemented, no production IdP, egress restrictions
unverified, per-user consent operations incomplete,
multi-process budget accounting incomplete, production audit
operations unverified. Re-confirm contract terms and connection
routes from current official OpenAI documentation at the time
the pilot is considered. No tunnel, key, contract change or
connection is approved here.
