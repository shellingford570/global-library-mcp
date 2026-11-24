# Phase 9-J: PR integration plan (no merge performed)

## Verified stack state (2026-11-24)

| PR | base ← head | State |
|---|---|---|
| #1 | master ← feat/v1-core | OPEN |
| #2 | feat/v1-core ← feat/global-library-evidence-v2 | OPEN |
| #3 | feat/global-library-evidence-v2 ← feat/global-library-research-v3 | OPEN |
| #4 | feat/global-library-research-v3 ← feat/global-library-reliability-v4 | OPEN |
| #5 | feat/global-library-reliability-v4 ← feat/global-library-semantic-v5 | OPEN |
| #6 | feat/global-library-semantic-v5 ← feat/global-library-retrieval-v6 | OPEN |
| #7 | feat/global-library-retrieval-v6 ← feat/global-library-evidence-safety-v7 | OPEN |
| #8 | feat/global-library-evidence-safety-v7 ← feat/global-library-research-engine-v8 | OPEN |
| #9 | feat/global-library-research-engine-v8 ← feat/global-library-ai-validation-v9 | (this phase) |

The stack is strictly linear: each branch's parent is the
previous branch, so the v9 head contains the entire history.

## Local integration check (performed)

A temporary local branch was created from `master`, the v9
head merged in (fast-forward, as expected for a linear
stack), and the full pytest suite run on the merged tree:
**all passed**. The temporary branch was deleted afterwards.
Nothing was pushed and no PR state changed.

## Recommended merge procedure (when approved)

1. **Use merge commits, not squash or rebase.** Squash/rebase
   rewrites the head commits, so every later PR in the stack
   would show the already-merged changes again as conflicts
   or duplicates. With merge commits, GitHub auto-retargets
   each next PR's base to `master` as its parent merges, and
   the diff shrinks to that phase only.
2. Merge strictly in order #1 → #9, waiting for GitHub
   Actions to go green on each PR *after* its base retargets
   (the retarget changes the diff base; CI re-runs).
3. After each merge, delete the merged head branch on GitHub
   (safe: its commits are in the next branch) — branch
   deletion is part of the merge step and needs the same
   approval as the merge itself.
4. After #9 lands: tag the release candidate from `master`
   (pyproject is at `1.0.0rc1`; the tag should match), run
   the Docker build + Playwright from CI on the tag, and
   only then consider the release verdicts in
   `docs/evaluation-phase9.md`.

## Release hygiene status

- README: current through Phase 8 (Phase 9 changes are
  internal + UI additions; a Phase 9 line is added with the
  evaluation doc).
- CHANGELOG: Phase 9 entry added with this phase.
- LICENSE: present. SECURITY.md: present.
- Install / Docker / MCP instructions: unchanged in Phase 9
  and covered by CI (Docker build + Playwright job).

## What this plan does NOT do

No PR was merged, no branch deleted, no force push used.
The merge itself remains the operator's decision.

## Phase 10-K update (2026-11-24)

Stack re-verified: master HEAD 8acc6bd; PRs #1-#9 all
OPEN / MERGEABLE / CI SUCCESS with the linear bases
unchanged; PR #10 (feat/global-library-research-beta-v10,
base feat/global-library-ai-validation-v9) extends the
stack to ten. New facts since the Phase 9 plan:

- **master has NO branch protection** (API check returned
  404). Nothing enforces CI-green or review before a merge;
  the operator is the only gate. Consider enabling
  protection before the release merge - operator's choice,
  not done here.
- **No auto-deploy exists**: the only workflow is
  test.yml. Merging cannot publish anything by itself.
- GitHub does NOT reliably retarget dependent PRs when a
  base branch's PR merges and the branch is kept. Procedure
  per merge, in order #1 -> #10: (1) merge with a merge
  commit; (2) immediately verify the next PR's base - it
  should become the previous base (or master at the end of
  the chain); (3) if it still points at the merged branch,
  retarget explicitly with `gh pr edit <n> --base <correct>`
  BEFORE merging it; (4) wait for CI on the retargeted PR;
  (5) only then merge. Never delete a branch in the chain
  until every PR above it has been retargeted and merged.
- Local integration check (Phase 10): a throwaway worktree
  merged master + the v10 head with no conflicts and the
  full pytest suite passed on the integrated tree. The
  worktree was deleted afterwards; nothing was pushed.
- Rollback: every stage is a merge commit, so any stage
  can be reverted with `git revert -m 1 <merge>` on master
  without rewriting history. Release tagging suggestion:
  tag the final merge `v1.0.0-research-beta` (pyproject is
  1.0.0rc1; bump to the beta version in the release PR).
- Dependency lock: requirements are pinned in pyproject
  with the [test] extras used by CI; the Docker build was
  verified in Phase 9 and is unchanged in Phase 10.
