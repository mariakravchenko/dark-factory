---
status: investigating
trigger: "UAT Phase 05: test_an_in_scope_edit_completes_with_no_revert FAILED with FileNotFoundError on <work_dir>/src/app.py after run reached COMPLETED; other 5 write-scope scenarios pass"
created: 2026-09-15T19:00:00Z
updated: 2026-09-15T19:00:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED -- the worktree is intentionally deleted on COMPLETED (D-04). The test asserts on-disk content after COMPLETED, which the design guarantees will be gone.
test: read runner.py:988-995 cleanup call site + worktree.py::remove_worktree + scope.py; compared the 6 scenarios' post-conditions
expecting: only the scenario asserting on-disk content after COMPLETED fails; FAILED scenarios keep the worktree
next_action: report ROOT CAUSE FOUND (goal: find_root_cause_only -- no fix)

bug_class: Bohrbug (deterministic; design/test-expectation mismatch, config category)

reasoning_checkpoint:
  hypothesis: "_cleanup_run_worktree runs remove_worktree on RunStatus.COMPLETED, deleting <work_dir> entirely; the assertion reads a path inside that deleted directory."
  confirming_evidence:
    - "runner.py:988-995 gates _cleanup_run_worktree on `new_status is RunStatus.COMPLETED`"
    - "worktree.py::remove_worktree runs `git worktree remove <target>` -- removes the whole directory"
    - "05-03-SUMMARY/05-VERIFICATION document this as decision D-04, wired at runner.py:989"
    - "test 6 explicitly asserts `work_dir.exists()` for a FAILED run and cites D-04 -- the same file knows the rule"
    - "scope.py::enforce_write_scope returns None with nothing reverted when there are no violations; DEVELOPMENT write_scope is ['src/**'] (conftest.py:389) so src/app.py is in scope and untouched"
  falsification_test: "If the file were missing for some other reason, the FAILED scenarios (2,3,4,6) that assert on work_dir contents would also be flaky. They all pass."
  fix_rationale: "N/A -- diagnose only"
  blind_spots: "Did not execute against a live PG17 to confirm the file lands on the working branch via wip_commit_if_dirty; inferred from code."
  candidate_causes:
    - "code: enforce_write_scope wrongly reverting an in-scope path -- RULED OUT (no violations => early return)"
    - "config: DEVELOPMENT write_scope not covering src/** -- RULED OUT (conftest.py:389 = ['src/**'])"
    - "environment/design: COMPLETED-transition worktree cleanup (D-04) deletes work_dir -- CONFIRMED"
    - "data: test asserts against a stale/other path -- RULED OUT (work_dir comes from worktree_path(), same fn runner uses)"
  and_gate: "no -- the single cause (D-04 cleanup) fully explains the observation and the 5 passing scenarios"

## Symptoms

expected: All 6 SC4 write-scope-enforcement integration scenarios pass; in-scope edit survives at <work_dir>/src/app.py with content "print('in scope')\n"
actual: 5/6 pass. test_an_in_scope_edit_completes_with_no_revert raises FileNotFoundError: .../dark-factory-runs/<run_id>/src/app.py
errors: "FileNotFoundError: [Errno 2] No such file or directory: '.../dark-factory-runs/<run_id>/src/app.py'"
reproduction: set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v (real PG17)
started: Phase 05 UAT 2026-09-15, first real-DB run of this phase

## Eliminated

- hypothesis: enforce_write_scope reverted the legitimate in-scope src/app.py
  evidence: scope.py:267-270 returns None with nothing reverted when violations is empty; DEVELOPMENT write_scope is ["src/**"] (conftest.py:389) and fnmatchcase("src/app.py", "src/**") is True. Also the run reached COMPLETED, which is only possible when no WriteScopeViolation was raised.
  timestamp: 2026-09-15

- hypothesis: the _WriteFileWorker wrote to a different path than the assertion reads
  evidence: both use the same `work_dir` object returned by _start() via worktree_path(root, run_id) -- the same pure function ensure_worktree/runner use.
  timestamp: 2026-09-15

- hypothesis: the worktree cleanup runs too early (before the role's write)
  evidence: runner.py:987-995 -- cleanup runs after apply_transition returns the terminal status, strictly after _run_current_role invoked the worker.
  timestamp: 2026-09-15

## Evidence

- timestamp: 2026-09-15
  checked: src/dark_factory/orchestrator/runner.py:988-995
  found: `if new_status is RunStatus.COMPLETED: _cleanup_run_worktree(run_id, work_dir, resolved_root, role=..., attempt=...)`
  implication: reaching COMPLETED is precisely the trigger for destroying work_dir

- timestamp: 2026-09-15
  checked: src/dark_factory/orchestrator/runner.py:565-615 (_cleanup_run_worktree)
  found: calls wip_commit_if_dirty(work_dir, ...) then remove_worktree(repo_root, run_id) non-forced. Docstring: "After this function returns, only the durable record remains -- the worktree filesystem copy is gone."
  implication: the in-scope edit is committed to the working branch (not lost), then the whole directory is removed. This is the documented D-04 contract.

- timestamp: 2026-09-15
  checked: src/dark_factory/git/worktree.py:143-156 (remove_worktree)
  found: `git worktree remove <target>` -- removes the entire worktree directory tree
  implication: work_dir/src/app.py cannot exist afterward; read_text raises FileNotFoundError with exactly the reported path shape

- timestamp: 2026-09-15
  checked: post-conditions of all 6 scenarios in tests/integration/test_write_scope_enforcement.py
  found: tests 2/3/4/6 all end in RunStatus.FAILED (no cleanup -> worktree survives -> their on-disk assertions hold). Test 5 ends COMPLETED but asserts only DB role statuses, never touching the filesystem. Test 1 is the ONLY scenario that both reaches COMPLETED and asserts on-disk content.
  implication: fully explains the 5-pass / 1-fail split with a single cause; no second contributing condition needed

- timestamp: 2026-09-15
  checked: test_write_scope_enforcement.py:542-543
  found: test 6 asserts `work_dir.exists()` with the comment "the failed run keeps its worktree on disk for inspection (D-04)"
  implication: the same test file already encodes the correct rule for FAILED but test 1 contradicts it for COMPLETED -- the defect is in test 1's expectation, not in enforcement

- timestamp: 2026-09-15
  checked: .planning/phases/05-isolated-workspace-git-lifecycle/05-03-SUMMARY.md:122, 05-VERIFICATION.md:79
  found: "fires only for RunStatus.COMPLETED, after the terminal transition has committed... FAILED and WAITING_HUMAN never trigger cleanup" / "confirmed at runner.py:989"
  implication: intended, reviewed, verified behaviour -- not a regression

## Resolution

root_cause: The run driver deliberately destroys the run's worktree when a run reaches RunStatus.COMPLETED (decision D-04). `_cleanup_run_worktree` (src/dark_factory/orchestrator/runner.py:565-615, called at :988-995) runs `wip_commit_if_dirty` -- which commits the in-scope `src/app.py` onto the working branch -- and then `remove_worktree`, which `git worktree remove`s the entire `<repo_parent>/dark-factory-runs/<run_id>/` directory. `test_an_in_scope_edit_completes_with_no_revert` asserts the file's content on the *worktree filesystem* after COMPLETED, a location the design guarantees no longer exists. There is no data loss: the content is durable on the working branch. The defect is the test's post-condition, which asserts against the wrong medium.
fix: (diagnose-only mode -- no fix applied)
verification: (n/a)
files_changed: []
