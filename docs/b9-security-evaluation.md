# b9 — External MCP security evaluation

Fixed synthetic case set, executed by
`eval/b9_security_eval.py` against the real external server,
token validator, URL validation and rights policy with a fake
LibraryService. Results: `eval/results-b9-security.json`.
No live API, no real tokens, no real research data; security
probing is confined to this project's own fixtures (brief
section 35).

## Results

| Category | Cases | Passed |
|---|---|---|
| normal | 20 | 20 |
| rights | 30 | 30 |
| auth | 24 | 24 |
| injection | 20 | 20 |
| isolation | 20 | 20 |
| ssrf | 30 | 30 |
| limits | 20 | 20 |
| **Total** | **164** | **164** |

(Final-review edition: the candidate set had 171 cases; the
auth set shrank with the reduced 5-tool profile and the
continuation/excerpt cases were replaced by removal, offset
and send-guard cases. A separate REAL-PATH integration suite
(tests/test_b9_integration.py, 6 tests) measures the same
class of properties through the official SDK client, a real
HTTP server, real LibraryService and the real budgeted
transport - see docs/b9-final-review.md.)

Failed cases: none.

## Mandatory safety metrics (brief section 36)

| Metric | Value |
|---|---|
| Unauthenticated operations allowed | 0 |
| Invalid-token operations allowed | 0 |
| Insufficient-scope operations allowed | 0 |
| Forbidden-tool calls allowed | 0 (no such tools are registered) |
| Workspace leaks | 0 |
| Unknown-rights text transfers | 0 |
| Forbidden text transfers | 0 |
| Secret leaks | 0 |
| Cross-user contamination | 0 |
| Bad-URL fetches | 0 |
| Budget overruns | 0 |
| Oversize responses | 0 |
| Post-deadline upstream work | 0 |
| Post-revocation successes | 0 |

These zeros hold **within this synthetic case set**. They do
not prove the absence of unknown vulnerabilities (brief
section 36); the residual risks are recorded in
docs/b9-external-security.md and docs/b9-threat-model.md.
