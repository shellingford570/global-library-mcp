# Workspace user guide (English summary)

Full guide: [workspace-user-guide.md](workspace-user-guide.md)
(Japanese). This page summarises the same content.

## Starting

```sh
global-library-mcp web --port 8000 --workspace
```

Workspace mode binds to loopback only; a non-loopback bind
is refused at startup. Without `--workspace`, the server is
the stateless search-only mode, unchanged from b6.

## Where data lives

One SQLite file in the OS user data directory — Linux:
`~/.local/share/global-library-mcp/workspace.db`; macOS:
`~/Library/Application Support/global-library-mcp/`;
Windows: `%LOCALAPPDATA%\global-library-mcp\`. Override
with `--workspace-path` or `GLM_WORKSPACE_PATH`. The file
is not encrypted. (Only the Linux path was exercised in
development; the macOS/Windows paths follow the platform
conventions but were not run on those OSes.)

## Workflow

1. Create a project in the workspace section.
2. Search as usual; each result card gains a
   "save to project" button.
3. In the page view, select a passage and save it as a
   citation. The excerpt must match the fetched OCR
   verbatim; verification status comes from the server,
   never from the browser.
4. Add notes, tags and collections; save comparisons from
   the documents tab (2–4 documents).
5. Tick "record search history" if you want searches kept
   under the selected project; history entries can be
   re-run.
6. Re-verify citations from the citations tab when you
   want a fresh check against the source.

## Export, import, backup

The export tab produces BibTeX, RIS, CSL JSON, plain text,
a Markdown project report and the portable JSON project
format; JSON import always creates a new project. Backup
downloads a consistent database copy (SQLite online backup
API); restore validates the candidate before replacing the
live database and keeps a pre-restore backup.

## Rights and limits

OCR full text and image bytes are never stored. Excerpts
are stored/exported only where the item's rights category
permits (public domain / permissive CC by default);
otherwise the citation keeps its reference and hash
without the text. The system does not guarantee that a
quotation is legally permissible. MCP tools cannot access
the workspace.
