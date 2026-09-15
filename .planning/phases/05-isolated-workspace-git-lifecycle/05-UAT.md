---
status: testing
phase: 05-isolated-workspace-git-lifecycle
source: [05-VERIFICATION.md]
started: 2026-09-15T16:30:06Z
updated: 2026-09-15T16:30:06Z
---

## Current Test

number: 1
name: Run the SC4 proof against a real database
expected: |
  `set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v`
  against a reachable PostgreSQL 17. All 6 scenarios pass (in-scope edit survives untouched;
  a tracked-edit violation is restored from HEAD; a new-file violation is removed from disk
  and the git index; an empty write_scope fails on any change at all; a later role is not
  penalized for an earlier role's legitimate in-scope edit; a role that both writes a valid
  artifact and commits a violation in the same attempt still fails while the artifact content
  survives on the branch).
awaiting: user response

## Tests

### 1. Run the SC4 proof against a real database
expected: |
  `set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v`
  against a reachable PostgreSQL 17. All 6 scenarios pass.
  Why human: no PostgreSQL 17 is reachable in this sandbox. This is the single Phase 5 proof
  file that has never been executed against a real database at any point in this phase's
  history — not when originally authored (05-04-SUMMARY.md), and not after the two Critical
  code-review fixes (CR-01, CR-02) that touch exactly this code path landed
  (05-REVIEW-FIX.md WR-02, explicitly skipped for the same reason).
result: [pending]

### 2. Add and run a CR-02 regression test
expected: |
  Construct a violation set containing one path that resolves outside the worktree (e.g. a
  worker-created symlink pointing outside the checkout) sorted alphabetically before one or
  more ordinary in-worktree violations, and call enforce_write_scope/revert_paths against it.
  Every non-escaping violation is still reverted (tracked edits restored from HEAD; new files
  removed from disk and the index), and exactly one WriteScopeViolation is raised afterward,
  naming the escaping path(s).
  Why human: grep across tests/ for "symlink"/"_resolve_in_worktree"/"revert_paths" returns
  zero hits for this exact scenario at any test tier. CR-02's fix currently rests entirely on
  code review and manual reasoning, with no executed regression coverage anywhere in the suite.
result: [pending]

### 3. Re-run the full suite and confirm no regression from CR-01's pathspec narrowing
expected: |
  `set -a; . ./.env; set +a; uv run pytest -q` against a reachable PostgreSQL 17, after items
  1-2 above pass. 624+ passed, 0 failed, 0 skipped. Also confirm `git worktree list --porcelain`
  names exactly one worktree and `git branch --list 'dark-factory/*'` is empty afterward
  (currently ~24 leftover from a pre-existing, unrelated accumulation — see deferred-items.md).
  Why human: CR-01 narrowed ARTIFACT_EXCLUDE_PATHSPEC, the constant shared by SC2's PR-diff
  exclusion and SC4's write-scope change-scan. The fix's correctness for SC2 was cross-checked
  by hand against test_pr_diff_excludes_artifacts.py's existing assertion text rather than by
  re-running that test against a live database.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
