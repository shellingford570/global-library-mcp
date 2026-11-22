# Contributing

Thanks for helping build an open, evidence-first library gateway.

## Ground rules

- **Evidence before claims.** A feature is "verified" only after a live run
  against the real service or a full local test. Mark everything else
  honestly (`unknown`, `unsupported`, `awaiting credentials`).
- **Never fabricate bibliographic data.** Titles, authors, years, page
  numbers and rights statements come from the source or stay `unknown`.
- **Respect each library's terms.** Use official APIs only; no scraping
  workarounds, no access-limit evasion. Record the terms you relied on in
  `libraries.yaml`.
- **No secrets in the repo.** API keys come from environment variables.
- **Small, phased changes.** Land one phase at a time with tests, and push
  early — never let the newest code exist only on one machine.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest                      # unit tests (mocked HTTP)
npm install
npx playwright install chromium
npx playwright test         # E2E (spins up the web UI on :8000)
global-library-mcp web --port 8000
```

Live checks against real library APIs are welcome but keep request counts
small and record the date and outcome in `libraries.yaml` and
`docs/api-research.md`.

## Adding a library adapter

1. Research the official API and record it in `libraries.yaml`
   (capabilities, auth, limits, rights, last-checked date).
2. Implement the adapter under `src/global_library_mcp/adapters/`,
   validate all identifiers before building URLs, and sanitise errors.
3. Add mocked unit tests first; then a small live check; then update
   `docs/implementation-status.md` with the honest status.
