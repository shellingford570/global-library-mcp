# PR audit and integration plan

Audit date: 2026-11-22. Auditor: development agent (no merges performed).

## Current structure (verified against GitHub)

```
master
  └─ feat/v1-core                 PR #1  OPEN, MERGEABLE, checks pass
       └─ feat/global-library-evidence-v2
                                   PR #2  OPEN, MERGEABLE, checks pass
            └─ feat/global-library-research-v3   (Phase 3 work, PR to be opened)
```

- PR #1: `feat/v1-core` -> `master`, "feat: v1.0 release candidate verification".
- PR #2: `feat/global-library-evidence-v2` -> `feat/v1-core`, "feat: evidence-first OCR answers with IIIF verification (v2)".
- Ancestry is strictly linear: `master` is an ancestor of `feat/v1-core`, which
  is an ancestor of `feat/global-library-evidence-v2` (verified with
  `git merge-base --is-ancestor`). Each branch is a pure superset of its base,
  so merging in order cannot drop features.
- Diff sizes at audit time: PR #1 touches the full v1 tree; PR #2 adds 5 phase
  commits (evidence pipeline, IIIF verification, answer/citation validation,
  Web UI, registry/docs).
- GitHub Actions: the latest completed runs for both PRs pass (`test` and
  `docker-playwright`). One run for the newest branch push was still pending
  at audit time and is re-checked before the Phase 3 PR is opened.

## Security review of the stacked changes

- No credentials in source (scanned in v2 Phase F); API keys are env-only.
- LLM base URL is validated against local/private targets; upstream errors are
  sanitised before reaching clients; the web layer sets CSP/nosniff/frame
  protections. Details: `docs/code-review.md`.
- No new third-party dependencies were added by PR #2 (httpx, mcp, PyYAML,
  pytest/respx, Playwright were already present).

## Recommended integration order (requires the maintainer's approval)

1. Merge PR #1 (`feat/v1-core` -> `master`) and delete `feat/v1-core`.
   GitHub automatically retargets PR #2's base to `master`.
2. Re-check PR #2: confirm the diff is unchanged (it should be identical,
   because the branch was a strict descendant) and that Actions pass.
3. Merge PR #2 into `master` and delete `feat/global-library-evidence-v2`.
   The Phase 3 PR (base: `feat/global-library-evidence-v2`) is then
   automatically retargeted to `master` as well.
4. Review and merge the Phase 3 PR last.

Alternative: retarget PR #2 to `master` manually before merging #1. Not
recommended — while `feat/v1-core` is unmerged, PR #2's diff would then
include all of PR #1's changes and become hard to review.

**No merge is performed by the development agent.** Each step above is
executed only on the maintainer's explicit instruction.
