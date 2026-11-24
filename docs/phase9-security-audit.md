# Phase 9-I: security audit (pre-real-LLM)

Scope: the code paths that will touch a real LLM, plus the
standing surfaces. Each item names the control and where it
lives. Audited 2026-11-24 on
`feat/global-library-ai-validation-v9`.

| Area | Finding / control |
|---|---|
| API key handling | Keys come from environment only (`LLM_API_KEY` / `OPENAI_API_KEY`); never logged, never written to results files, never in fixtures. Phase 9-A tests assert the key string appears nowhere in provider results or error reasons. Repo-wide secret scan over tracked files (key patterns, private-key headers): **no hits**. |
| Endpoint validation | `OpenAICompatibleProvider` requires HTTPS for non-local base URLs and rejects private/local IP targets (`base_url_error`); the approved plan prints the base URL and the executed run inherits the approved environment. Residual: DNS rebinding between validation and connect is not pinned — noted, accepted for an evaluation-only path behind operator approval. |
| SSRF / redirects | Outbound library traffic goes to fixed library endpoints (NDL, Internet Archive) with configured base URLs; user input never becomes a host. httpx default redirect handling applies; no user-controlled URL fetching exists in the answer path. |
| Prompt injection | Library OCR is untrusted data: the system prompt instructs the model to treat record text as data, never instructions; citations are whitelist-validated against supplied evidence; claims are screened against the OCR and unverified claims are dropped before publication; the answer text is composed from verified claims (Phase 9-A.2). A fixture with an instruction-bearing OCR passage is covered by tests (payload + behaviour). |
| Response shape validation | Provider JSON is parsed defensively: non-dict / missing answer / bad citations → sanitised unavailability; transport errors (timeout, 429, 500, garbage) → fixed reason strings with status class only. |
| Cost-cap bypass | Three layers: BudgetPlan (pre-run), the run_evaluation approval gate (no hand-off env → exit 2, no call), UsageLedger (per-call worst-case refusal during the run). There is no `--approve` flag on the runner for an agent to flip. |
| Rate limits | Library traffic: per-question request budget + circuit breaker (Phase 8-I); LLM traffic: call cap = question count, one call per question, no retries implemented against the LLM endpoint (a failed call is recorded, not retried — retry policy is part of the ledger design: max_retries is a planning parameter, and the provider performs no automatic retry today). |
| Cache bounds | Search cache FIFO-bounded at 256 entries (Phase 8-I). |
| Personal data | Evaluation datasets contain only synthetic questions and public-domain historical excerpts; the LLM payload contains question text + OCR excerpts only. No user data is sent anywhere. |
| Copyright | Materials mode shows each record's rights status verbatim from the library; unknown rights are never presented as freely redistributable; excerpts are short passages with source links. Gold datasets carry a license note (public-domain historical OCR, short excerpts for evaluation). |
| Dependencies | SBOM generation exists from Phase 3 (`docs/` + CI). No new runtime dependency was added in Phase 9. A live vulnerability scan (pip-audit) was not run in this environment; recommended in CI before a release tag. |

## Residual risks (accepted, recorded)

1. DNS-level endpoint redirection is not pinned (evaluation
   path only, operator-approved runs).
2. The claim screening is lexical; a fluent LLM fabrication
   that happens to share vocabulary with the OCR can pass —
   this is precisely what the Phase 9-E experiment is designed
   to measure before any production use.
3. NLI/embedding backends are not loadable here; semantic
   defence in depth beyond the rule checker is unproven.
