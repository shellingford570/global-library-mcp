# b11 Research Artefact Security (sections 5-7)

- Storage: dedicated `research_artefacts` table (schema v5,
  migration with pre-migration backup, transaction, and
  future-schema refusal - the store's existing machinery).
- Payloads: recursive allowlist validation per kind - closed
  field sets at every nesting level, closed status vocabulary,
  string caps (200 chars for excerpt-like fields, 2000
  otherwise), finite numbers only, depth <= 6, list items
  <= 100, nodes <= 2000, payload <= 64 KiB. Text-bearing keys
  (`ocr_text`, `full_text`, ...) are rejected anywhere in the
  payload: originals are referenced via saved citations, never
  copied into artefacts - so a rights change on a citation
  cannot be bypassed by an artefact copy.
- References: `record_refs` must resolve to documents of the
  SAME project and `citation_refs` to its citations, at save
  time and again at import time (with ID remapping).
- Negative tests (tests/test_b11_stage0.py): hand-written v2
  envelope, forged envelope with a CORRECT self-computed
  SHA-256, payload tampering + hash recomputation, cross
  project copy, JSON-import forgery, backup-restore forgery -
  none affect progress counts, the graph, reports or any
  verified tally (all measure 0 promotions).
