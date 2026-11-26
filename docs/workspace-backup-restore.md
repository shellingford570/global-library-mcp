# Workspace backup and restore (b7)

The database contains your research. It is **not encrypted**
at rest (SQLite file, 0600 permissions, in a 0700
directory). Treat backups with the same care.

## Backup

Use the workspace UI (エクスポート tab → バックアップ作成 /
ダウンロード) or the API (`POST /api/workspace/backup`).
Backups are made with SQLite's online backup API, which is
safe under WAL — never copy `workspace.db` alone while the
server is running and call that a backup (the WAL may hold
uncommitted pages). Each backup records its creation time,
schema version, size and SHA-256, and passes
`PRAGMA integrity_check` at creation.

## Restore

UI: エクスポート tab → バックアップから復元. The server
verifies the candidate (readable SQLite, integrity ok,
schema not newer than this build) **before** touching the
live database, then backs up the current database to
`backups/pre-restore-<timestamp>.db`, stops writes,
replaces the file atomically and reopens it. A corrupt or
future-schema candidate is rejected and the live database
is left untouched.

## Notes

- Backups are local files only; nothing is uploaded
  anywhere by the application.
- Deleting a project does not delete copies inside backups
  or exported files you already made.
- Restoring an older-schema backup migrates it forward on
  open; restoring is one-way (keep the pre-restore backup
  if you may need to go back).
