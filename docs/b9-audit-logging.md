# b9 — External audit logging

Module: `src/global_library_mcp/external/audit.py`.
Enable with `GLM_EXTERNAL_AUDIT_LOG=<path>` (JSONL). Events
are also kept in memory for tests/diagnostics.

## Recorded

Event id, timestamp (UTC), **pseudonymised** user id
(`u_` + first 16 hex of SHA-256 — the raw id never reaches the
log), tool name, library id, status, auth outcome, upstream
HTTP attempts, response bytes, rights category, denial count,
duration, cancellation flag, limit-hit kind, error class
(exception type or stable denial code only).

## Never recorded

Search terms, OCR text, excerpts, research notes, saved-item
lists, API keys, access/refresh tokens, cookies,
Authorization headers, raw upstream responses, exception
messages. The log therefore shows THAT a user searched the
NDL, not WHAT they researched; library-level granularity is
the most it reveals about research topics.

## Retention and rotation

Rotation at 5 MiB to a single `.1` file (older data is
overwritten). Deletion is by removing the log files — no
other copies are kept by this component. Deployments choose
their own retention period; the shipped default keeps at most
~10 MiB. Audit records are written for allowed, denied,
timed-out and cancelled calls alike, including kill-switch
and revocation events (as denied calls).
