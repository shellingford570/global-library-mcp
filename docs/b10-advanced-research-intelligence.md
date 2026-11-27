# Global Library MCP v1.0.0b10 — Advanced Research Intelligence

Development record, 2026-11-27/28. Branch
`feat/advanced-research-intelligence-b10` from master
`66f2867` (v1.0.0b9). Submitted as a pull request for review;
merge, tagging and release are separate decisions.

## What b10 set out to do

Deepen research capability rather than widen coverage: fix the
b9 external-profile residual risks, recover and improve
multilingual retrieval, add authority resolution for authors /
works / editions, compare lexical and local semantic search
honestly, structure research questions and claims, map claims
to admitted evidence as candidates, detect contradiction
candidates across sources, and carry the results into the
Research Workspace and UI — all without loosening any frozen
evidence condition, without paid APIs, and with the external
profile's scope unchanged.

## Stage map

| Stage | Record |
|---|---|
| 0 — b9 residual risks | `docs/b10-b9-regression-hardening.md` |
| 1 — evaluation foundation | `docs/b10-multilingual-routing.md` |
| 2 — authority | `docs/b10-authority-resolution.md`, `docs/authority-data-research.md` (b10 update) |
| 3 — search sophistication | `docs/b10-ranking.md`, `docs/b10-semantic-search.md`, `docs/b10-model-card.md` |
| 4 — research intelligence | `docs/b10-claim-evidence.md`, `docs/b10-contradiction-detection.md` |
| 5 — research experience | `docs/b10-workspace-integration.md` |
| 6 — evaluation & submission | `docs/b10-evaluation.md`, `docs/b10-performance-evaluation.md`, `docs/b10-live-verification.md` |

## Headline outcomes

- b9 residual risks reproduced then fixed (consent expiry
  re-checks at send/return, per-data-class consent, send-level
  library binding, budget-ledger separation, per-user session
  caps, typed external projections, per-library reference-host
  allowlists, document identity states, consent-file hardening,
  unified startup validation, audit labelling). External
  connection remains DISABLED in practice: DNS pinning is
  still unimplemented, no production IdP exists, and the
  ChatGPT Plus route is still unconfirmed.
- The b6 fixed-set regression was traced to a simulation
  routing defect (language detected from variant text) plus a
  lexicon gap — not to ranking. Fixed: **fixed F Recall@10
  0.9167, challenge 1.0000**, all section-43 multilingual
  targets met.
- AuthorityResolver with live-verified GND identifiers (ten
  focus authors), zero false verifications on the frozen
  260-case b10 dataset (68 bibliographic-source-supported /
  192 agent-assigned labels; no human-verified labels).
- Local semantic search (one Apache-2.0 model, 127 MB, pinned
  revision, offline) is the strongest cross-language discovery
  signal measured (whole-corpus Recall@10 1.0000 vs lexical
  0.7286 on the fixed corpus); it is opt-in and never feeds
  evidence admission.
- ResearchRanker was NOT adopted as the default ranker — the
  hybrid comparison was mixed — and ships opt-in with ranking
  reasons. Reported as a non-adoption.
- Structured claims map to admitted evidence as candidates
  with zero false support promotions; contradiction detection
  produces candidates only, never confirmed contradictions;
  document counts and independent-source counts are kept
  separate everywhere.
- Regression: pytest 628 (0 skipped), Playwright 17 + 6,
  security evaluation 164/164, MCP profiles unchanged
  (full 15 / research 14 / external 5), paid API calls 0.

## Not done / not claimed

- ChatGPT connection of any kind; Secure MCP Tunnel; DNS
  pinning; production IdP (all unchanged blockers).
- NLI model (a second model needs separate approval).
- Zotero real-application import (no Zotero in this
  environment; format-level checks only).
- Independent human evaluation of any dataset.
- VIAF live use (bot-blocked from this network; client
  implemented and fixture-tested, off by default).
- b11 work of any kind.
