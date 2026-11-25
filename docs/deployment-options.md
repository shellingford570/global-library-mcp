# Deployment options for the Research Beta (comparison, 2026-11-24)

No deployment has been performed. This document compares the
candidate routes from the integration brief; choosing and
provisioning one requires separate approval, and no paid
service may be contracted without it.

| Criterion | Local MCP (per user) | Docker self-host | Managed web service | Cloud limited beta |
|---|---|---|---|---|
| Monthly cost | 0 (user's machine) | VPS cost only (small instance suffices) | platform fee + usage | cloud usage; free tiers may cover a small beta |
| Free tier | n/a (local) | none | often a free/hobby tier with sleep limits | free tiers exist but vary; verify current terms |
| CPU / memory | user's | 1–2 vCPU / 1–2 GB is enough for the beta workload | plan-dependent | plan-dependent |
| HTTPS | not needed (stdio) | operator must configure (reverse proxy) | provided | provided |
| Concurrency cap | per-process only | gateway/reverse proxy must set it | plan-dependent | gateway configuration required |
| Rate limiting | per-client limiter in the app (120/min default) | same + proxy limits | same + platform limits | same + platform limits |
| Upstream API load | bounded by the per-question budget (Standard 25 units) | same | same | same |
| Monitoring | none built in | operator's responsibility | platform dashboards | cloud monitoring |
| Logs | local only; no query logging beyond the process | operator-managed | platform-managed | cloud-managed; mind query privacy |
| Recovery | restart the process | container restart policy | platform | cloud tooling |
| Scaling | single user | vertical only | platform scaling | cloud scaling |
| Security posture | strongest (nothing leaves the machine; no LLM key in beta) | operator keeps TLS + updates | shared responsibility | shared responsibility |

Recommendation from the integration brief: start with local
MCP use and a small, invited beta; widen only after the terms
checks in docs/phase10-library-terms.md are closed and the
gateway items in docs/phase10-security-audit.md (TLS, global
concurrency cap) are in place. The beta deployment must not
set LLM_ENABLED or any LLM API key.
