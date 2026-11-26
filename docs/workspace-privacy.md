# Workspace privacy (b7)

Research data can reveal unpublished work, hypotheses and
interests. The b7 workspace is designed so that this data
stays on the user's machine:

- **Local only.** All workspace data lives in one SQLite
  file under the OS user data directory (override:
  `GLM_WORKSPACE_PATH`). There is no account, no cloud
  sync and no telemetry.
- **No automatic external sends.** Saving, notes, history
  and exports never trigger network calls. The only
  outbound requests are the library searches and page
  fetches the user explicitly runs, and citation
  re-verification, which the user must request explicitly
  per citation. Research notes and project contents are
  never sent to upstream library APIs or to any AI service.
- **Explicit saving.** Nothing is persisted without a user
  action: documents and citations are saved by button,
  search history only when the opt-in checkbox is ticked
  and a project is selected.
- **Logs.** Note text, citation excerpts, API keys and
  session/CSRF tokens are never written to logs. The CSRF
  token exists only in the served page and request headers;
  it is not stored in the database or in exports.
- **Exports exclude secrets.** The JSON project format
  rejects secret-like keys on import and never contains
  API keys, environment values, tokens or absolute local
  paths.
- **File permissions.** Database file 0600, data directory
  0700. The database is **not encrypted**; anyone with
  read access to the file can read the research data.
  Protect it like any private document, and use the
  built-in backup to keep copies in places you trust.
- **Deletion.** Projects can be deleted from the UI (two
  steps, with related-record counts shown first). Deleting
  a project does not delete backups or exported files you
  made earlier — remove those separately if needed.
- **Git safety.** Database files, WAL/SHM sidecars,
  backups and local exports are covered by `.gitignore`
  patterns so research data is not committed by accident.
