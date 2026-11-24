# Writing a library adapter

An adapter connects one institution's official APIs to the shared
evidence pipeline. The registry entry comes first; code second;
"verified" last, and only after a live run.

## 1. Research and register

Add the institution to `libraries.yaml` before writing code: official
API URL and spec, catalog/full-text/OCR/IIIF capabilities (use
`unknown` honestly), languages, auth, rate limits, rights/terms, and
`implementation_status: research-only`. Read the institution's terms:
use official APIs only, never scrape around access controls.

## 2. Implement the adapter

Create `src/global_library_mcp/adapters/<name>.py` with a subclass of
`LibraryAdapter` (`adapters/base.py`):

- `search(query, limit)` — required. Return `SearchResult` records
  with item-level rights; never infer redistribution permission.
- `get_document(record_id)` — metadata for one record.
- Page evidence (optional, in this order):
  - set `supports_in_document_search = True` only when the methods
    below really work;
  - `search_in_document(record_id, query)` → matches whose entries
    carry a stable page `id`;
  - `get_page_text(page_id)` → must return `contents`,
    `digital_frame`, `printed_page` (`"unknown"` when the source
    does not expose it — never guess), `ocr_source`, `image_url`,
    and `verified_mapping`, which may be true only when the returned
    payload's identity was cross-checked against the request;
  - `verify_original(page_id)` → per-check report in the shape the
    NDL/IA adapters return; every check recorded separately, failures
    as failed checks (with the exception type in the detail), never
    raised.
- Validate every identifier before building a URL from it, and raise
  `AdapterError(library_id, message)` for upstream problems so the
  service layer can report them per library.
- Refuse content the institution restricts (e.g. IA's
  `access-restricted-item`); item-level access conditions win over
  convenience.
- Register the adapter in `LibraryService.__init__`
  (`service.py`) under the same id as `libraries.yaml`.

## 3. Test

- Mocked unit tests first (respx), covering: search parsing, page
  identity mismatch → `verified_mapping` false, missing OCR,
  restricted items, and `verify_original` all-pass / one-check-fail.
- Then a small live check against the real API (keep request counts
  low): one search, one in-document search, one page, one original
  verification. Record the date and outcome in the registry's
  `verification` field and in `docs/api-research.md`.

## 4. Update the status docs

Update `docs/implementation-status.md` with the honest state:
implemented / live-verified / awaiting credentials / unsupported,
per capability — not per adapter as a whole.

## Reference implementations

- NDL (`adapters/ndl.py`): Book/Page APIs + IIIF Presentation checks.
- Internet Archive (`adapters/internet_archive.py`): djvu.xml page
  OCR aligned to BookReader leaves, metadata/access/djvu/range
  checks; note the djvu.txt separator pitfall documented there.
- Gallica (`adapters/gallica.py`): SRU search + texteBrut/IIIF page
  methods that are implemented but not live-verified (upstream 403)
  — the model for recording that distinction.
