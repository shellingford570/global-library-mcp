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

## Final review corrections (v1.0.0b7 release)

- Backup creation is an explicit POST returning a backup
  ID; GET download serves only an existing backup and never
  creates one. At most 10 backups are kept; files are 0600.
- Restore requires explicit confirmation and deep candidate
  validation (schema, columns, foreign keys, vocabularies —
  not `integrity_check` alone), quiesces the API during the
  swap, takes a pre-restore backup, and rolls back
  automatically on failure.
- Trust boundary: a checksum computed from an uploaded file
  does not prove authenticity. An uploaded database is
  never auto-certified as one of your own backups, and
  verification states inside a restored database are
  historical records, still subject to current-rights
  gating. See `docs/b7-final-review.md` §2.

## 最終レビュー追記（2026-11-26）

- 復元開始は原子的な所有権確保（`acquire_restore()`）で
  排他化され、同時復元は 409 で拒否される。
- 信頼状態の降格は DB 置換後のロールバック範囲**内**で
  実行される。降格・初期化・整合性検査のいずれが失敗
  しても、回復用バックアップから元DBへ自動復帰する。
- 復元された DB 内の過去の権利観測・検証結果は真正性を
  証明できないため、全件 `restored_claim` に降格される
  （元の source は履歴として保持）。
- **バックアップファイル自体は保存済み研究データを含む
  機密性の高いファイル**であり、権利フィルター済み
  エクスポートとは異なる。共有・保管は利用者の責任で
  慎重に行うこと。
