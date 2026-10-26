---
status: complete
phase: 09-independent-quality-gate-bounded-feedback-loops
source: [09-VERIFICATION.md, 09-06-SUMMARY.md]
started: 2026-09-23T12:15:00Z
updated: 2026-09-26T10:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. GATE-02/GATE-03: gate FAIL keeps the run out of COMPLETED
expected: Run reaches RunStatus.FAILED, not COMPLETED, with both configured commands recorded and the QA role-execution row's error naming quality_gate_fail.
result: pass

### 2. LOOP-03: iteration counter read/compared before the signal is chosen; exactly one counter incremented per attempt
expected: runs.qa_developer_iterations / runs.quality_gate_iterations increment by exactly 1 on a bounce and the two counters never cross-contaminate.
result: pass
source: `tests/db/test_qa_bounce.py`, `tests/db/test_iteration_cap_exhaustion.py` — both green in the combined run

### 3. LOOP-04 (adjacency): failing role with no earlier role yields ROLE_FAILED reason no_earlier_role_to_bounce_to
expected: A pipeline whose only role FAILs produces ROLE_FAILED immediately with the adjacency reason, never a call into transition() with ROLE_BOUNCED from the first node.
result: pass
source: manual one-role-pipeline check (thrown away after use, not a permanent test) — real drive() confirmed RunStatus.FAILED, zero ROLE_BOUNCED events, qa_developer_iterations stayed 0. The adjacency reason string itself lands on the ROLE_FAILED event's payload (confirmed by direct source read, runner.py:1319-1326), not RUN_FAILED's — the throwaway script's one failing assertion checked the wrong event, a script bug, not a product bug.

### 4. LOOP-04 (empty): a cap of 0 makes the first rejection terminal, no zero-value special case
expected: Run ends FAILED with zero ROLE_BOUNCED events and runs.qa_developer_iterations still 0.
result: pass
source: `tests/db/test_iteration_cap_exhaustion.py` — green in the combined run

### 5. LOOP-04 (idempotency): re-driving an exhausted run adds no further events/increments
expected: run_events row count and both counter columns are byte-identical before and after a second advance() call on a terminal run.
result: pass
source: `tests/db/test_iteration_cap_exhaustion.py` — green in the combined run

### 6. LOOP-01: a bounced Developer's next attempt receives verdict.json with QA's structured issues, end to end
expected: Developer attempt-1 RoleContext has no verdict.json entry; attempt-2 RoleContext has one whose produced_by names QA and whose content carries the FAIL issue's severity/criterion/description.
result: pass
source: "User ran `uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py` against real PostgreSQL 17: `2 passed in 129.17s (0:02:09)`. Root cause fixed by 09-06-PLAN.md (commit 8df8f06), structurally AST-guarded (tests/unit/test_role_context_rebuild_uses_the_worktree.py, 3 passed), now behaviorally confirmed end-to-end."
history: "Originally reported: tests/db/test_feedback_reaches_developer.py::test_qa_fail_delivers_structured_issues_to_developer_attempt_2 FAILED — dark_factory.artifacts.MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md, raised from context/builder.py:327 -> read_artifact_text. Reproduced twice (same failure both times the combined command was run). severity: major"

### 7. LOOP-02 (payload): a bounced Developer's next attempt receives quality_gate.json with the real per-command failure output, end to end
expected: Developer attempt-2 RoleContext has a quality_gate.json entry whose produced_by is the gate and whose parsed content carries a non-zero exit_code and the sentinel stderr text.
result: pass
source: "Same db-tier run as test 6 (2 tests in the module, both passed: `2 passed in 129.17s`). Same shared root cause, same 09-06-PLAN.md fix commit, now behaviorally confirmed end-to-end."
history: "Originally reported: tests/db/test_feedback_reaches_developer.py::test_gate_fail_delivers_real_command_output_to_developer_attempt_2 FAILED — same root: dark_factory.artifacts.MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md. Both failures in this module share the identical error, both raised from the same _resolve_input -> read_artifact_text call chain. severity: major"

### 8. CR-01 (ROLE-05 on bounce): a real four-role drive() run where QA writes outside its declared write_scope on an attempt that would otherwise bounce ends FAILED
expected: Zero ROLE_BOUNCED events, runs.qa_developer_iterations still 0, the planted path reverted from disk, exactly one role_executions row per role, and a RUN_FAILED event naming write_scope.
result: pass
source: `tests/db/test_write_scope_enforced_on_bounce.py::test_a_bounce_is_write_scope_enforced_exactly_like_a_completion` — green in the combined run. This is CR-01's own behavioral proof, the last item this phase's gap closure needed.

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-09-6
  truth: "Developer attempt-1 RoleContext has no verdict.json entry; attempt-2 RoleContext has one whose produced_by names QA and whose content carries the FAIL issue's severity/criterion/description"
  status: resolved
  reason: "User reported: tests/db/test_feedback_reaches_developer.py::test_qa_fail_delivers_structured_issues_to_developer_attempt_2 FAILED with dark_factory.artifacts.MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md"
  severity: major
  test: 6
  root_cause: "Test-fixture defect, zero production impact. tests/db/test_feedback_reaches_developer.py's _CapturingWorker (lines 189-191) calls build_role_context(fresh_session, self._repo_root, ...) directly to rebuild the DEVELOPMENT attempt-2 context, but self._repo_root is set to repo_root=root (the config_root_factory tree, <tmp>/repo) at lines 275/373 -- NOT the git worktree runner.py itself always passes (work_dir, from ensure_worktree). worktree_path() makes the worktree a sibling of repo_root (<repo_root.parent>/dark-factory-runs/<run_id>/), so the two roots never coincide and read_artifact_text looks under the wrong tree entirely. design.md just happens to be the first required input DEVELOPMENT declares, so it's the first read to fail -- ARCHITECTURE's artifacts were committed correctly (confirmed: the DB lookups ahead of the failing read all succeeded). The only production call site of build_role_context (runner.py:866) always passes work_dir, so real advance()/resume() is unaffected. Confirmed by a real non-DB differential experiment (make_git_repo + ensure_worktree + write_role_artifacts): reading via repo_root reproduces the exact error shape, reading via work_dir succeeds."
  artifacts:
    - path: "tests/db/test_feedback_reaches_developer.py"
      issue: "_CapturingWorker constructed with repo_root=root instead of repo_root=work_dir at lines 275 and 373 (the two call sites that construct it for the rebuild-at-attempt-2 scenario)"
  missing:
    - "Construct _CapturingWorker with repo_root=work_dir (already in scope at lines 262/358) instead of repo_root=root at both call sites"
  debug_session: ".planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md"
  fix:
    plan: "09-06-PLAN.md"
    commit: "8df8f06 (feat), da0147f (test), 26c6074 (docs)"
    approach: "Route 2 from the debug session: _record_and_maybe_rebuild now calls ensure_worktree(base_branch=fresh_state.base_branch, working_branch=fresh_state.working_branch) itself and passes the returned work_dir to build_role_context, instead of the constructor handing it a pre-computed path. Both _CapturingWorker construction sites unchanged (repo_root=root is correct under this route). New DB-free AST guard: tests/unit/test_role_context_rebuild_uses_the_worktree.py (3 passed)."
    verified_structurally: true
    verified_behaviorally: true
    behavioral_evidence: "User ran `uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py` against real PostgreSQL 17: 2 passed in 129.17s (0:02:09), 0 failed, 0 skipped. Confirmed 2026-09-26."
- gap_id: G-09-7
  truth: "Developer attempt-2 RoleContext has a quality_gate.json entry whose produced_by is the gate and whose parsed content carries a non-zero exit_code and the sentinel stderr text"
  status: resolved
  reason: "User reported: tests/db/test_feedback_reaches_developer.py::test_gate_fail_delivers_real_command_output_to_developer_attempt_2 FAILED with the identical dark_factory.artifacts.MissingArtifactContentError: artifact file not found: .../artifacts/ARCHITECTURE/design.md"
  severity: major
  test: 7
  root_cause: "Identical root cause to G-09-6 -- same test module, same _CapturingWorker defect, same wrong-root bug (repo_root instead of work_dir), just triggered by the sibling test function (test_gate_fail_delivers_real_command_output_to_developer_attempt_2, lines 358-379) constructing the same worker class the same wrong way."
  artifacts:
    - path: "tests/db/test_feedback_reaches_developer.py"
      issue: "_CapturingWorker constructed with repo_root=root instead of repo_root=work_dir at line 373 (this test's own call site)"
  missing:
    - "Same fix as G-09-6, applied at this test's call site (line 373)"
  debug_session: ".planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md"
  fix:
    plan: "09-06-PLAN.md"
    commit: "8df8f06 (feat), da0147f (test), 26c6074 (docs)"
    approach: "Same fix as G-09-6 — shared call site, shared commit."
    verified_structurally: true
    verified_behaviorally: true
    behavioral_evidence: "Same db-tier run as G-09-6 (same command, same module, both scenarios green): 2 passed in 129.17s (0:02:09), 0 failed, 0 skipped. Confirmed 2026-09-26."
