# Code review notes

Review of the pre-existing code at base commit `1ff32ff` and of the changes on
`feat/global-library-evidence-v2`. Date: 2026-11-22.

## What was already solid

- Adapters validate identifiers before building URLs (NDL PID/page-id checks)
  and never follow redirects blindly in the web layer.
- Error messages are sanitised (`sanitize_error` redacts credential-like query
  parameters) before reaching API responses.
- The LLM provider is opt-in (`LLM_ENABLED`), validates its base URL against
  local/private targets, and treats record text as untrusted data.
- The NDL page mapping check (`verified_mapping`) already cross-checked page
  id, book and frame — the evidence pipeline builds directly on it.
- Web responses carry CSP, `nosniff`, frame denial and `no-store`.

## Issues found and addressed on this branch

1. **Answers were grounded in bibliographic summaries.** `LibraryService.answer`
   passed search-result descriptions to the LLM, so an "answer" could cite a
   book whose text was never read. Replaced by the evidence pipeline: only
   verified OCR pages reach the provider (Phase B/D).
2. **Citations were positional indices.** An index can silently point at the
   wrong record when result ordering changes. Citations are now stable
   `citation_key`s (`library:record:page`), whitelist-validated in both the
   provider and the service layer; a single bad key withholds the answer.
3. **A natural-language question rarely matches catalog fields.** Evidence
   collection now falls back to extracted content terms for the catalog
   search (the raw question is still tried first).
4. **Generating an IIIF URL was treated as image availability.** Verification
   now checks manifest, canvas, canvas-image equality and a real range
   request separately (Phase C).

## Environment note (not a code bug)

The base test suite appeared to fail 10/15 in this sandbox: the sandbox's
`no_proxy` value contains bracketed IPv6 entries (`[::1]`) that make
httpx 0.28 raise `InvalidURL` when building proxy patterns. With the proxy
variables unset (or `no_proxy` reduced to `localhost,127.0.0.1` for live
calls) all tests pass, and CI (no such proxy) is unaffected.

## Security checklist for this branch

- No API keys or credentials in source (scanned); keys come from the
  environment only. `.env`, `.venv`, `node_modules` are git-ignored.
- No new outbound endpoints: the web server only calls the same official
  library APIs as the adapters, plus the operator-configured LLM endpoint.
- LLM payload is capped (8 evidence items, 1,500 OCR characters each).
- Document text is data, never instructions: provider prompts state this,
  and the mock provider demonstrates the citation contract without an LLM.
- IIIF verification performs one small range request (1 KiB) per page
  instead of downloading originals.
