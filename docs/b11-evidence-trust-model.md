# b11 Evidence Trust Model (sections 5-9)

Three trust questions are kept separate:

1. **Artefact trust** - who produced this stored object?
   Server-generated artefacts live in the `research_artefacts`
   table (schema v5) with server-managed IDs and a trust column
   only the server sets (`server_generated` /
   `imported_unverified` / `restored_unverified`). Anything a
   user can write (notes, imported JSON) is at most a claim
   about an artefact, surfaced as `user_asserted`.
2. **Evidence-reference trust** - did the frozen admission
   pipeline actually admit this passage? References are opaque
   registry tokens (`evr_...`) issued at admission time with an
   immutable snapshot (ids, offsets, excerpt hash, identity
   states, rights state, TTL). Verification is a field-by-field
   comparison against the snapshot; caller-constructed
   references - even with correct hashes of real text - fail.
3. **Claim trust** - what may be concluded? Assessments stay
   candidate-level (`supported_candidate`,
   `contradiction_candidate`, `insufficient_evidence`); the
   synthesis layer cannot mint confirmed facts, independence
   requires a recorded basis, and rights state is re-read from
   current store state whenever artefacts, graphs or reports
   are produced.

Downgrade paths are one-way: import -> imported_unverified,
restore -> restored_unverified, and nothing in the codebase
promotes either back.
