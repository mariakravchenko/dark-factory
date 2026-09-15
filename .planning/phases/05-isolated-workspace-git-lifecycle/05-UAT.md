---
status: partial
phase: 05-isolated-workspace-git-lifecycle
source: [05-VERIFICATION.md]
started: 2026-09-15T16:30:06Z
updated: 2026-09-15T18:28:12Z
---

## Current Test

[testing complete]

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
result: issue
reported: |
  test_an_in_scope_edit_completes_with_no_revert FAILED with FileNotFoundError: the run
  reached RunStatus.COMPLETED but work_dir/src/app.py does not exist afterward — the
  in-scope edit did not survive. Other 5 scenarios passed (tracked-edit revert, new-file
  revert, empty write_scope, later-role non-penalization, valid-artifact-survives-with-
  violation). 1 failed, 5 passed in 130.88s.
severity: blocker

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
result: issue
reported: |
  Confirmed via grep: no test exercises this scenario (escaping symlink violation sorted
  alphabetically before in-worktree violations, against enforce_write_scope/revert_paths).
  Missing regression coverage for CR-02. User directed: fix — route into gap-closure so the
  test is authored and run as part of the fix cycle.
severity: major

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
result: blocked
blocked_by: prior-phase
reason: "Depends on tests 1-2 passing first; both have open gaps (G-05-1 blocker fix, CR-02 regression test) that must land before a clean full-suite run is meaningful."

## Summary

total: 3
passed: 0
issues: 2
pending: 0
skipped: 0
blocked: 1

## Gaps

- gap_id: G-05-1
  truth: "All 6 SC4 scenarios pass: in-scope edit survives untouched; a tracked-edit violation is restored from HEAD; a new-file violation is removed from disk and the git index; an empty write_scope fails on any change at all; a later role is not penalized for an earlier role's legitimate in-scope edit; a role that both writes a valid artifact and commits a violation in the same attempt still fails while the artifact content survives on the branch."
  status: failed
  reason: "User reported: test_an_in_scope_edit_completes_with_no_revert FAILED with FileNotFoundError: the run reached RunStatus.COMPLETED but work_dir/src/app.py does not exist afterward — the in-scope edit did not survive. Other 5 scenarios passed. 1 failed, 5 passed in 130.88s."
  severity: blocker
  test: 1
  artifacts: []
  missing: []

- gap_id: G-05-2
  truth: "A CR-02 regression test exists and passes: a violation set containing an escaping symlink path sorted alphabetically before in-worktree violations, run through enforce_write_scope/revert_paths, still reverts every non-escaping violation and raises exactly one WriteScopeViolation naming the escaping path(s)."
  status: failed
  reason: "Confirmed via grep: no test exercises this scenario at any test tier. CR-02's fix rests entirely on code review and manual reasoning, with zero executed regression coverage. User directed: fix."
  severity: major
  test: 2
  artifacts: []
  missing: []
