---
status: resolved
trigger: "UAT Phase 05: test_an_in_scope_edit_completes_with_no_revert FAILED with FileNotFoundError on <work_dir>/src/app.py after run reached COMPLETED; other 5 write-scope scenarios pass"
created: 2026-09-15T19:00:00Z
updated: 2026-10-07T10:00:43Z
symptoms_prefilled: true
goal: find_and_fix
---

## Current Focus

hypothesis: CONFIRMED -- the worktree is intentionally deleted on COMPLETED (D-04). The test asserts on-disk content after COMPLETED, which the design guarantees will be gone.
test: fix-acceptance guardrail run in full against real PG17 -- all 5 signals pass (guardrail_verdict: accepted). See Resolution.verification.
expecting: n/a -- verification complete
next_action: none -- session closed. The user confirmed fixed on 2026-10-07 ("Confirmed fixed + track mypy gap"), accepting that the production D-04 worktree-cleanup behaviour stays as-is. Archived to .planning/debug/resolved/, knowledge-base entry appended. The unrelated mypy --strict errors in tests/support/fake_artifacts.py:276/278/286 (noted under verification.adjacent_tests.lint_type) are tracked separately as debug session `fake-artifacts-mypy-strict-errors` and are deliberately NOT part of this session's scope or commit.

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

root_cause: The run driver deliberately destroys the run's worktree when a run reaches RunStatus.COMPLETED (decision D-04). `_cleanup_run_worktree` (src/dark_factory/orchestrator/runner.py:767-817, called at :1869) runs `wip_commit_if_dirty` -- which commits the in-scope `src/app.py` onto the working branch -- and then `remove_worktree`, which `git worktree remove`s the entire `<repo_parent>/dark-factory-runs/<run_id>/` directory. `test_an_in_scope_edit_completes_with_no_revert` asserts the file's content on the *worktree filesystem* after COMPLETED, a location the design guarantees no longer exists. There is no data loss: the content is durable on the working branch. The defect is the test's post-condition, which asserts against the wrong medium.

fix: |
  Test-only (production code deliberately untouched -- the cleanup behaviour is
  correct and intentional per D-04). In
  tests/integration/test_write_scope_enforcement.py::test_an_in_scope_edit_completes_with_no_revert:
    1. Replaced the filesystem read `(work_dir / "src" / "app.py").read_text("utf-8")`
       with a working-branch read: `read_committed(root, working_branch_name(run_id), "src/app.py")`
       -- the same `tests.support.git_repo` helper test 6 already uses for its
       branch-content assertion -- keeping the identical content equality.
    2. Added the companion assertion `assert not work_dir.exists()`, the mirror
       image of test 6's `assert work_dir.exists()` for a FAILED run. The scenario
       now *proves* D-04's cleanup contract instead of contradicting it.
    3. Added an in-test comment explaining why the read must not be "simplified"
       back to a filesystem read.
  Closes Phase 05 UAT gap G-05-1. Shipped as commit d494c33 (authored in an
  earlier session of this same debug investigation); this session verified it.

verification:
  target_test: { result: pass }
  mutation_check:
    result: pass
    tooling: "no mutation framework configured (Stryker is JS; no mutmut/cosmic-ray in pyproject.toml or uv.lock) -- ran one hand-seeded mutant instead of skipping"
    mutant: "runner.py:809 `wip_commit_if_dirty(...)` -> `pass` (removes the behaviour the new assertion guards: content reaching the working branch)"
    mutant_killed: true
    detail: "driving test FAILED with `fatal: path 'src/app.py' does not exist in 'dark-factory/run-<id>'` -- the new assertion bites on the root-cause behaviour (branch durability), not on a symptom. Production code restored immediately (git checkout; tree verified clean)."
  no_op_deletion:
    result: pass
    deletion_justified_by_rca: n/a
    detail: "net +17/-2 and strictly strengthening: one wrong-medium assertion replaced by a same-strength content assertion on the correct medium PLUS one new cleanup-contract assertion. No branch removed, no assertion weakened, no production behaviour short-circuited."
  adjacent_tests:
    result: pass
    suites_run:
      - "tests/integration/test_write_scope_enforcement.py (6 passed -- all 6 SC4 scenarios, real PG17)"
      - "tests/db/test_artifacts_show_reads_committed_content.py + tests/integration/test_artifact_scope_enforcement.py + tests/integration/test_worktree_lifecycle.py (10 passed)"
      - "tests/db/test_secret_redaction_e2e_full_pipeline.py (4 passed)"
    import_graph: "read_committed / dark_factory.git.committed consumers -- all 4 consuming test files run"
    lint_type: "ruff check + ruff format --check clean on the changed file; mypy --strict reports 3 PRE-EXISTING errors in tests/support/fake_artifacts.py:276/278/286 (reproduce in isolation at a clean HEAD, in a file this fix never touches -- unrelated, reported separately, deliberately not folded into this session)"
  revert_and_reconfirm:
    result: pass
    bug_returned_on_revert: true
    fixed_on_reapply: true
    detail: "Reverse-applied d494c33's hunk to the working tree only (`git show d494c33 -- <file> | git apply -R`, index untouched so a concurrent session's staged work was not disturbed). Driving test FAILED with exactly the reported shape: `FileNotFoundError: [Errno 2] No such file or directory: '.../dark-factory-runs/<run_id>/src/app.py'`. Restored via `git checkout --`; test passes again; full file 6/6 green. Diff is a single hunk in a single file -- minimal."
  environment: "real PostgreSQL 17 via DARK_FACTORY_TEST_DATABASE_URL (external rung), matching the UAT reproduction command"
  guardrail_verdict: accepted

files_changed:
  - "tests/integration/test_write_scope_enforcement.py (test-only; commit d494c33)"
