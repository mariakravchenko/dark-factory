---
status: diagnosed
phase: 05-isolated-workspace-git-lifecycle
source: [05-VERIFICATION.md]
started: 2026-09-15T16:30:06Z
updated: 2026-09-15T18:45:00Z
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
severity: minor
diagnosis: |
  Not a product bug. Root cause: by design (D-04), a COMPLETED run's worktree is committed
  to the working branch and then deleted. The test asserts file content on the (now-deleted)
  worktree filesystem instead of the working branch. See G-05-1 in Gaps section.

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
  severity: minor
  test: 1
  root_cause: "NOT a product bug — no data loss. By design (decision D-04), _cleanup_run_worktree (runner.py:565-615, called at :988-995 when new_status is RunStatus.COMPLETED) commits the in-scope file to the working branch via wip_commit_if_dirty, then deletes the entire worktree directory via remove_worktree. Every later reader reads the branch, never the worktree filesystem, once a run is COMPLETED. The failing test asserts (work_dir / \"src\" / \"app.py\").read_text() — a location the design guarantees is gone after COMPLETED. Test 6 in the same file already encodes the correct pattern (reads content off the branch, and separately asserts work_dir.exists() for the FAILED case where the worktree is kept for inspection). The defect is the test's post-condition, not the write-scope enforcement or the run driver."
  artifacts:
    - path: "tests/integration/test_write_scope_enforcement.py"
      issue: "test_an_in_scope_edit_completes_with_no_revert (line ~302) asserts file content on the worktree filesystem after COMPLETED, which D-04 deliberately deletes"
  missing:
    - "Rewrite the assertion to read the in-scope file's content off the working branch (e.g. via the same run_artifact_text helper test 6 already uses, or `git show <working_branch>:src/app.py`) instead of the worktree filesystem"
    - "Add a companion assertion that work_dir no longer exists after COMPLETED, turning the scenario into a positive proof of D-04 rather than a contradiction of it"
  debug_session: .planning/debug/in-scope-edit-missing-after-completed.md

- gap_id: G-05-2
  truth: "A CR-02 regression test exists and passes: a violation set containing an escaping symlink path sorted alphabetically before in-worktree violations, run through enforce_write_scope/revert_paths, still reverts every non-escaping violation and raises exactly one WriteScopeViolation naming the escaping path(s)."
  status: failed
  reason: "Confirmed via grep: no test exercises this scenario at any test tier. CR-02's fix rests entirely on code review and manual reasoning, with zero executed regression coverage. User directed: fix."
  severity: major
  test: 2
  root_cause: "Two conditions combined: (1) test-architecture partition — tests/unit/test_write_scope.py self-scopes to pure functions only (no git/filesystem/DB) and imports only is_out_of_scope/validate_write_scope_patterns, so scope-revert behavior (revert_paths, enforce_write_scope, _resolve_in_worktree) is reachable only transitively through drive() in the integration-tier test_write_scope_enforcement.py, which requires a real DB; (2) CR-02 landed in a sandbox with no reachable Postgres, and its test was deferred to WR-02 under the mistaken premise that it needed the same database — but scope.py explicitly states 'No database access anywhere in this module', and revert_paths(worktree, paths) takes a plain Path and only calls run_git. A DB-free unit-tier home for this test already existed as a pattern (test_git_lifecycle.py, test_git_diff.py, test_git_worktree.py all drive real git against tmp_path at unit tier) but was never used for scope.py."
  artifacts:
    - path: "src/dark_factory/git/scope.py"
      issue: "_resolve_in_worktree (line ~142, escaping-path check), revert_paths (lines ~214-247, the CR-02 fix — per-path try/except collecting escapes, single raise after the loop), and enforce_write_scope's sorted(...) (line ~268, source of the alphabetical ordering that makes this scenario reachable) have zero direct test coverage"
  missing:
    - "New unit-tier test file tests/unit/test_write_scope_revert.py (sibling to test_git_*.py; keep test_write_scope.py's pure-function-only charter intact)"
    - "Use make_git_repo(tmp_path / \"repo\") + git_commit_all to build a real tmp_path git repo — no DB, no drive(), pytest.mark.unit"
    - "Construct violations: a tracked file (e.g. src/app.py), an untracked new file, and a symlink whose name sorts alphabetically before both (e.g. aa-escape -> outside tmp_path)"
    - "Call revert_paths directly with the sorted violation list; assert the in-worktree violations are reverted and exactly one WriteScopeViolation is raised naming the escaping path"
    - "Add boundary-neighbor cases: escape-only, escape-last, multiple escapes"
  debug_session: .planning/debug/cr02-revert-ordering-test-gap.md
