# Project JSON export / import (b7)

The portable project format moves one research project
between machines or environments. It is JSON:

```json
{
  "format": "global-library-mcp-project",
  "format_version": 1,
  "schema_version": 1,
  "application_version": "1.0.0b7",
  "exported_at": "2026-11-26T00:00:00Z",
  "project": { "...": "..." },
  "saved_documents": [],
  "saved_citations": [],
  "research_notes": [],
  "search_history": [],
  "saved_comparisons": [],
  "collections": [],
  "rights_observations": [],
  "export_omissions": [{"kind": "citation_excerpt", "count": 1, "reason": "..."}]
}
```

## Export

- One project per file. Other projects are never included.
- Excerpts that the rights policy does not permit for
  export are omitted; each omission is counted with a
  reason in `export_omissions`. The citation reference
  (source, page, offsets, hash) is still exported.
- Never exported: API keys, environment values, auth or
  session tokens, internal server details, absolute local
  file paths.

## Import — treated as untrusted input

- Limits: 25 MB file, 20,000 records, 100,000 characters
  per string, nesting depth 32.
- Secret-like keys (`api_key`, `token`, `password`,
  `secret`, `session`, `authorization`, `cookie`) are
  rejected. URLs must be http(s). Duplicate ids inside the
  file and dangling foreign keys are rejected.
- The whole import runs in **one transaction**; any error
  rolls everything back.
- Import always creates a **new project** with fresh
  internal ids (old ids are remapped, never reused), so an
  existing project is never overwritten.
- Imported citations keep their claimed verification state
  only as a historical claim (a `verification_observations`
  row with status `imported_claim`); their current status
  becomes `imported_unverified`. A `verified` flag in an
  import file never makes a citation verified in this
  environment.
- Import performs no network access: no URL in the file is
  fetched automatically.

## Final review corrections (v1.0.0b7 release)

- Import applies the storage policy and the 2,000-character
  cap to citation AND comparison excerpts; omissions are
  counted and reported.
- All verification fields are downgraded on import
  (status, page mapping, image status, `verified_at`);
  claimed values and rights/verification observation
  histories are preserved as history. Original timestamps
  are kept; migration time is separate.
- References are fully pre-validated with per-type ID maps:
  an unknown reference rejects the whole file (single
  transaction, nothing partially imported). Comparison
  excerpts are remapped to the new document IDs.
- Strict JSON: duplicate keys and non-finite numbers are
  rejected. Limits: 64 MB, 250,000 JSON objects, 60,000
  research records; oversized exports carry a warning
  pointing to SQLite backup migration. Imported excerpts
  are kept only when the file's stated rights pass the
  same storage policy, and are recorded as unverified
  claims (see `docs/b7-final-review.md` §2).
