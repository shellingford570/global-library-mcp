# Phase 10-H: Research Beta security audit

Extends docs/phase9-security-audit.md (LLM-path focused) to
the public Research Beta surface. Audited 2026-11-24 on
feat/global-library-research-beta-v10.

| Area | Finding / control |
|---|---|
| LLM blockade on beta paths | TESTED: with beta defaults (LLM_ENABLED unset, no key), service.answer and research_materials complete with ZERO calls to api.openai.com / api.x.ai (trap-route test, tests/test_phase10_beta_security.py). The provider refuses before any network call when disabled or keyless, and again when the payload would exceed the input-token bound. |
| SSRF | Outbound traffic goes only to configured library endpoints (registry adapters with fixed base URLs) and, when explicitly enabled, the validated LLM base URL (HTTPS required for non-local hosts; private/loopback/link-local/reserved IP literals rejected). User input never becomes a host. |
| DNS rebinding | Residual, recorded since Phase 9: hostnames are validated as literals, DNS resolution is not pinned between validation and connect. For the beta this matters only for the operator-configured LLM endpoint, which is disabled by default. Library endpoints are fixed public hosts. |
| Redirects | httpx follows redirects for library GETs; redirect targets are the libraries' own CDNs in practice. No user-controlled URL is fetched. Recorded as a monitored residual, not a beta blocker. |
| Input validation | Web API: q required and length-capped ("q is too long" → 400); limit clamped 1..100 in the service; MCP tools validate types and raise on invalid page numbers; unknown library IDs are filtered, not errors. |
| Rate limiting | Web API per-client sliding window (GLM_RATE_LIMIT_PER_MINUTE, default 120/min → 429). Per-question upstream request budget defaults to Standard 25 and clamps at the Deep cap of 200 (Phase 10-A). No global concurrency semaphore exists in-process; a public deployment should also cap concurrency at the gateway - recorded as a deployment requirement. |
| Caches | Search cache FIFO 256. Page cache was UNBOUNDED - fixed in Phase 10-H (FIFO 256). No TTL: entries live until evicted; acceptable for public-domain page OCR, recorded. |
| XSS / OCR sanitisation | The web UI inserts record/OCR fields through esc() in every template and uses textContent for headings; links are built with esc() and rel="noreferrer noopener". OCR is data, never markup. |
| Error sanitisation | API errors pass through sanitize_error; provider failures return fixed reason strings (status class only); no stack traces, keys or request headers reach responses or results files (Phase 9-A tests assert this). |
| Secrets in logs | Keys are read from the environment only, never logged or persisted; repo secret scan (Phase 9) re-run for Phase 10 files: no hits. Evaluation records save no keys or personal data (Phase 10-E field list). |
| Dependencies | pip-audit 2.10.1 over 102 installed packages: vulnerabilities ONLY in pip itself (12, tooling) and pytest (2, dev-only). No runtime dependency vulnerabilities found. |
| Docker | Dockerfile runs as USER appuser (non-root); no new privileges added in Phase 10. |
| Paid-LLM access from beta | LLM features sit behind LLM_ENABLED + operator-held key + (for evaluations) the approval hand-off; the beta default posture is disabled, and the blockade test above proves the public paths cannot trigger a call. |

## Deployment requirements before public exposure

1. Terminate TLS and set a global concurrency cap at the
   gateway (the in-process limiter is per-client only).
2. Keep LLM_ENABLED unset in the beta deployment; AI
   experiments run in a separate environment.
3. Re-run pip-audit and the secret scan at release time.
