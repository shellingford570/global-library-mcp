# Adding a library adapter (b5)

Checklist distilled from the NDL/IA/BSB/LoC/e-rara adapters.
Do not skip the verification steps: an adapter is "implemented"
only when its registry entry can state what was verified live.

1. **Research first.** Read the provider's official API docs.
   Record: endpoints, auth, terms (metadata vs OCR vs images
   may differ), rate limits, and whether a keyword search API
   actually exists. If it does not, build an ID-addressed
   adapter and say so - never simulate search.
2. **Registry entry** in `libraries.yaml`: capabilities per
   function with a status from the fixed vocabulary
   (research_only / implemented / fixture_verified /
   live_catalog_verified / live_page_verified /
   live_end_to_end_verified / unavailable /
   authentication_required / unsupported / bounded).
   The YAML loader refuses duplicate keys.
3. **Adapter class** under `src/global_library_mcp/adapters/`,
   subclassing `LibraryAdapter`: implement only what the
   official API supports; raise `AdapterError` with the reason
   for the rest. Register it in `adapters/__init__.py` and in
   `LibraryService.adapters`. New adapters are NOT added to
   `default_libraries` until live page verification and terms
   review are done (opt-in routing, b5 section 11).
4. **HTTP discipline.** Use the shared client (`make_client`)
   so the budget, Retry-After gate and byte caps apply. Never
   build a private client, never follow redirects cross-domain
   (use `get_within_domain`), never evade a 403.
5. **Page mapping.** Page ids must encode the provider's own
   identifiers. `verified_mapping` requires independent
   corroboration from the payload itself (manifest links,
   payload ids, titles), never positional guessing alone.
6. **Rights.** Surface the provider's per-item rights statement
   verbatim (manifest license, rights advisory, dc:rights).
   Unknown stays "unknown".
7. **Fixtures.** Mock-transport tests for document/page/verify,
   the mapping-negative case, and the unsupported operations.
8. **Live verification.** A few representative items (target:
   3+ items, 10+ pages for OCR claims), recorded in
   `docs/b5-live-verification.md`-style notes with request
   counts and failures included.
9. **Docs.** Update README library tables,
   `docs/implementation-status.md`, `docs/api-research.md` and
   the registry verification text - with dates.
