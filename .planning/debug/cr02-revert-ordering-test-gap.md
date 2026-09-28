---
status: investigating
trigger: "UAT test-coverage gap: no regression test for CR-02 escaping-path + revert-ordering interaction (Phase 05 UAT test 2)"
created: 2026-09-15T00:00:00Z
updated: 2026-09-15T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED (AND-gate, two contributing causes) - (1) structural: scope-module coverage was partitioned "pure functions -> unit / everything else -> full-pipeline integration", leaving no git-backed unit home for revert coverage; (2) process+misclassification: CR-02 landed in a sandbox with no Postgres and its test was deferred to WR-02, which was skipped on the incorrect premise that the test needs a DB.
test: read scope.py, 05-REVIEW-FIX.md CR-02/WR-02, both write-scope test files, unit-tier git test patterns
expecting: confirmed - revert_paths has no DB dependency; unit tier already runs real git via make_git_repo
next_action: report ROOT CAUSE FOUND (goal: find_root_cause_only - do not write the test)

reasoning_checkpoint:
  hypothesis: "The CR-02 regression test is absent because revert_paths coverage only ever existed transitively through the DB-bound integration pipeline, and the fixer inherited that false DB dependency when deciding to skip WR-02."
  confirming_evidence:
    - "scope.py module docstring line 4: 'No database access anywhere in this module'; revert_paths(worktree, paths) takes an explicit Path and only calls run_git"
    - "Only test import of dark_factory.git.scope in all of tests/ is `is_out_of_scope, validate_write_scope_patterns` (test_write_scope.py:22). Zero direct imports of revert_paths/enforce_write_scope/_resolve_in_worktree."
    - "test_write_scope.py:4 self-scopes to 'Pure functions only -- no git, no filesystem, no database (unit tier)'"
    - "test_write_scope_enforcement.py is pytest.mark.integration and every test takes real_session_factory/engine, reaching revert_paths only via drive()"
    - "05-REVIEW-FIX.md:146-147 skips the test because 'it would need to run against that same database to be validated'"
    - "tests/unit/test_git_lifecycle.py, test_git_diff.py, test_git_worktree.py are all pytest.mark.unit and run REAL git against tmp_path via tests.support.git_repo.make_git_repo"
  falsification_test: "If revert_paths or _resolve_in_worktree took a Session/engine, or if no unit-tier test ran real git, the DB-dependency premise would be correct and the cause would be purely environmental."
  fix_rationale: "N/A - diagnosis only (goal: find_root_cause_only)."
  blind_spots: "Have not executed the integration suite (no Postgres here); have not confirmed CR-02's fix is behaviorally correct, only that it is untested."
  candidate_causes:
    - "code/test-architecture: no git-backed unit-tier home for scope revert coverage"
    - "environment: sandbox had no reachable Postgres 17 when CR-02 landed"
    - "process: code-review-time fix with test explicitly deferred to a separate (then-skipped) finding"
  and_gate: "yes - DB-unreachability alone does NOT explain the gap, because the test never needed a DB. It required BOTH the mis-drawn unit/integration partition (no obvious DB-free home) AND the fixer's inherited belief that revert coverage implies the integration tier."

## Symptoms

expected: A regression test exists covering CR-02: violation set where an escaping path (symlink out of worktree) sorts alphabetically BEFORE ordinary in-worktree violations; revert_paths still reverts every non-escaping violation (tracked restored from HEAD, new files removed from disk+index) and exactly one WriteScopeViolation is raised naming the escaping path(s).
actual: UAT grep for "symlink" and "_resolve_in_worktree|revert_paths" in tests/ found only tests/unit/test_artifact_paths.py:56 test_t_04_01_symlink_escaping_root_raises (unrelated single-symlink detection). Zero hits for the scenario.
errors: none - coverage gap, not a crash
reproduction: N/A - grep-confirmed absence. Referenced as test 2 in .planning/phases/05-isolated-workspace-git-lifecycle/05-UAT.md
started: CR-02 landed as a Critical code-review fix in 05-REVIEW-FIX.md; WR-02 (the test) explicitly skipped. Re-confirmed Phase 05 UAT 2026-09-15.

## Eliminated

## Evidence

- timestamp: 2026-09-15T00:00:00Z
  checked: file inventory of tests/
  found: tests/unit/test_write_scope.py EXISTS and was NOT surfaced by the UAT greps (grep terms were "symlink" and "_resolve_in_worktree|revert_paths")
  implication: UAT grep may have been incomplete; must check whether test_write_scope.py covers the ordering scenario before concluding total absence

- timestamp: 2026-09-15T00:00:00Z
  checked: src/dark_factory/git/scope.py (full)
  found: CR-02 fix is at revert_paths lines 214-247 (per-path try/except WriteScopeViolation collecting `escapes`, single raise after the loop). Escaping check is _resolve_in_worktree line 142. The alphabetical ordering comes from enforce_write_scope line 268 `sorted(...)`. Module docstring line 4 - "No database access anywhere in this module".
  implication: revert_paths is git-only and unit-testable with a plain tmp_path repo; no DB required.

- timestamp: 2026-09-15T00:00:00Z
  checked: tests/unit/test_write_scope.py + tests/integration/test_write_scope_enforcement.py
  found: unit file is scoped "Pure functions only -- no git, no filesystem, no database" and imports ONLY is_out_of_scope/validate_write_scope_patterns. Integration file is pytest.mark.integration, all 6 tests take real_session_factory/engine and reach revert_paths only transitively via drive().
  implication: all revert-path behavior coverage is DB-gated by accident of test partitioning, not by need.

- timestamp: 2026-09-15T00:00:00Z
  checked: grep for `from dark_factory.git.scope import` across tests/
  found: exactly one hit (test_write_scope.py:22). Zero direct tests of revert_paths/enforce_write_scope/_resolve_in_worktree anywhere.
  implication: UAT's "zero hits" conclusion is correct despite its grep missing test_write_scope.py entirely.

- timestamp: 2026-09-15T00:00:00Z
  checked: tests/unit/test_git_lifecycle.py, test_git_diff.py, test_git_worktree.py
  found: all three are pytest.mark.unit and drive REAL git against tmp_path repos via tests.support.git_repo.make_git_repo
  implication: a DB-free unit-tier home for this test was already available and idiomatic when CR-02 landed - the WR-02 skip rationale was factually wrong.

- timestamp: 2026-09-15T00:00:00Z
  checked: .planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW-FIX.md lines 57-85, 119-147
  found: CR-02 marked "fixed, requires human verification"; fixer ran the same grep and deferred coverage to WR-02. WR-02 skipped as "environment/infrastructure limitation" because "it would need to run against that same database to be validated" (lines 146-147).
  implication: the misclassification is documented verbatim and is the proximate reason no test was written.

## Resolution

root_cause: "Test-architecture partition: the write-scope module's coverage was split 'pure functions -> unit tier / everything else -> full-pipeline DB integration tier', so revert_paths/_resolve_in_worktree behavior was only ever reachable through drive() behind the `engine` fixture; AND process misclassification: CR-02 was a code-review-time fix in a sandbox with no reachable Postgres 17, whose regression test was deferred to WR-02 and then skipped as an environment limitation on the explicitly-stated but incorrect premise that the test requires a database - when scope.py is documented as having no DB access and the unit tier already exercises real git via make_git_repo."
fix: "N/A - diagnose-only mode."
verification: "N/A - diagnose-only mode."
files_changed: []
