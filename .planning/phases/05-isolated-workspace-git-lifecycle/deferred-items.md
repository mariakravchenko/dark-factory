# Deferred items — Phase 05

Out-of-scope discoveries logged during execution, not fixed (SCOPE BOUNDARY).

## 05-04

- **This repository's own checkout carries pre-existing leftover git state**:
  `git worktree list --porcelain` reports 25 worktrees (24 more than the
  expected 1) and `git branch --list 'dark-factory/*'` lists ~24
  `dark-factory/run-<uuid>` branches, all rooted under
  `.claude/worktrees/dark-factory-runs/<uuid>/` (a GSD parallel-executor's own
  nested checkout of this repo, not the sibling-of-repo-root location
  `dark_factory.git.worktree.worktree_path` computes). Their commit history
  (e.g. `docs(01): create phase plan`) indicates these date back to an earlier
  phase's DB-reachable human-verification round, not to this plan's own
  execution — this plan's sandbox has no reachable PostgreSQL 17 (see
  05-04-SUMMARY.md's Test Execution Handoff) and created no worktrees or
  branches of its own in this session.

  Task 3's `<verify>` block includes an assertion that this checkout carries
  exactly one worktree and zero `dark-factory/*` branches after a full-suite
  run — this could not be checked to a PASS in-sandbox, both because the
  pre-existing accumulation predates this plan and because the full db/
  integration suite (whose teardown fixtures are what's supposed to keep this
  clean) cannot run here. Not fixed: destructively removing 24 worktrees and
  branches via `git worktree remove --force` / `git branch -D` is exactly the
  class of operation this project's own destructive-git-operation guardrails
  exist to prevent an agent from doing unilaterally, and cleaning it up is not
  caused by, nor required to complete, this plan's own deliverables (the
  matcher, the enforcement wiring, and the acceptance gate). Flagged for the
  human's next full-suite verification round: run `git worktree prune` and
  review the 24 `dark-factory/run-*` branches for deletion once confirmed
  safe to discard.
