# Quickstart — Global Library MCP 1.0.0b2 (Research Beta)

A research tool for searching libraries worldwide and checking
sources against page-level OCR and original page images. No paid
LLM API is required. AI answering is experimental and disabled by
default.

日本語版： [quickstart.md](quickstart.md)

## 1. Install

Requirements: Python 3.11+, Git.

```sh
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
python3 -m venv .venv
.venv/bin/pip install .
```

Windows (PowerShell):

```powershell
git clone https://github.com/shellingford570/global-library-mcp
cd global-library-mcp
git checkout v1.0.0b2
py -m venv .venv
.venv\Scripts\pip install .
```

Docker:

```sh
docker build -t global-library-mcp .
docker run --rm -p 127.0.0.1:8000:8000 global-library-mcp
```

## 2. Start the Web UI

```sh
.venv/bin/global-library-mcp web --port 8000
```

Open http://127.0.0.1:8000 in your browser (on Windows:
`.venv\Scripts\global-library-mcp web --port 8000`).

## 3. Your first search

Type a question in the search box (e.g. "materials about
hydroelectric power in the Meiji era"). Results are grouped:

- **Verified evidence**: pages whose identity is confirmed.
  "Verified" does not guarantee OCR accuracy: always visually
  compare the OCR with the original page image before quoting
- **Related materials**: relevant but unverified pages
- **Unverified**: pages whose correspondence to the original
  could not be confirmed. The material may still be useful, but
  check the original image before quoting

## 4. Reading OCR

Each page shows its OCR text. OCR contains recognition errors.
Always compare important quotations with the original page
image. "Verified" means the page mapping is consistent with the
metadata; it does not guarantee OCR accuracy.

## 5. Checking the original image

Each page has an "original" link to the library's page image
(IIIF for NDL, BookReader images for the Internet Archive).
Visually confirm that the page number and text match before
quoting.

## 6. Comparing documents

"Compare" lets you pick two materials and view page excerpts
from both on the same topic side by side.

## 7. Getting citation information

Every piece of evidence carries a citation key (e.g.
`ndl:992954:992954@12`). When citing in a paper or report,
include the citation key together with the original URL.

## 8. MCP connection

Any stdio MCP client (Claude Desktop, Claude Code, Cursor,
Google Antigravity, …) can use this as an MCP server. See
[mcp-clients.md](mcp-clients.md) for configuration examples.
The server command is `global-library-mcp mcp` (stdio).

## 9. Troubleshooting

- **One library errors (e.g. 403)**: that library may be
  unreachable from your network environment. Try another
  network, or use the other libraries' results. It is not
  necessarily a bug.
- **No results**: shorten the query, or try the other language
  (Japanese / English).
- **Multi-volume items show as unverified**: this is by design.
  Use the original link and check in the library's own viewer.

## 10. Supported libraries

- Supported (live-verified): National Diet Library (NDL),
  Internet Archive
- Research stage: Gallica/BnF, Europeana, Library of Congress,
  DDB and others. Research-stage entries are not supported
  libraries. Per-library terms: see
  [phase10-library-terms.md](phase10-library-terms.md).

## 11. Terms of use

Rights differ per holding library and per item. Check the
rights statement shown on each page and credit the source.
Lending-restricted items are never fetched. For a per-licence
use guide see [rights-guide.md](rights-guide.md) (note:
CC BY-NC-ND is not public domain).

## 12. Reporting bugs

Use GitHub Issues:
https://github.com/shellingford570/global-library-mcp/issues

Templates are grouped by category (search results / OCR quality
/ original-page mapping / library connection / MCP connection /
UI / security / new-library requests). **Do not post personal
information, API keys, or confidential materials.**

**Do not post security-vulnerability details in a public issue.**
Report them privately, following [SECURITY.md](../SECURITY.md).

## 13. Known limitations (1.0.0b3)

- Search speed depends on each library's API. A library that
  does not answer within 10 seconds is cut off and reported as a
  partial failure with the reason (e.g. Library of Congress).
  Gallica returns 403 from some networks; that is likewise
  reported, never evaded.
- Actual HTTP requests are capped per operation (Quick 30 /
  Standard 80 / Deep 200, with per-host caps). In the web UI's
  staged flow, the bibliographic search and the detailed
  investigation count as separate operations.
- Internet Archive full-text files are large; a response over
  the per-response cap (25 MB) is aborted and reported as a
  partial failure with a link to the original and the reason.
- A detailed investigation can be cancelled; "cancelled" is
  shown only after the server confirms the stop. The overall
  investigation limit is 300 seconds.
- AI answering remains experimental (disabled by default).
