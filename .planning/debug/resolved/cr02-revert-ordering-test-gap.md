---
status: resolved
trigger: "UAT test-coverage gap: no regression test for CR-02 escaping-path + revert-ordering interaction (Phase 05 UAT test 2)"
created: 2026-09-15T00:00:00Z
updated: 2026-10-07T00:00:00Z
resolved: 2026-10-07T00:00:00Z
follow_up_sessions:
  - claude-cli-test-spawns-real-binary-with-key-present
---

## Current Focus

hypothesis: RESOLVED. Root cause confirmed earlier (AND-gate, two causes). On resume the prescribed fix was found ALREADY LANDED by plan 05-06 (commits 0017004 + 1c8296e) - so this session's work was the fix-acceptance guardrail rather than authoring the test.
test: ran the 7-test suite (green, no DB); then the decisive revert-check - restored the pre-CR-02 shape of revert_paths and re-ran
expecting: CONFIRMED on both counts - 7 passed in 1.90s with no DB; 3 of 7 FAIL under pre-CR-02 code, including the CR-02 regression proper, with exactly the predicted failure mode
next_action: none - human confirmed "Confirmed fixed" on 2026-10-07; G-05-2 closed, session archived

guardrail_verdict: accepted
human_verification: "CONFIRMED 2026-10-07. Operator accepted the fix-acceptance guardrail (all 5 signals PASS, revert-check decisive) and agreed G-05-2 is closed. No code change was pending."

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

- timestamp: 2026-10-07T00:00:00Z
  checked: whether the prescribed fix still needed writing (ls tests/unit/, git log for the path)
  found: tests/unit/test_write_scope_revert.py ALREADY EXISTS (11994 bytes, mtime Sep 16 09:48 - one day AFTER this debug file was created), committed in 0017004 "test(05-06): CR-02 regression suite - escape ordering and boundary neighbours" and 1c8296e "test(05-06): prove escape-first ordering end to end via enforce_write_scope"
  implication: plan 05-06 consumed this debug session's diagnosis and closed G-05-2 after the session paused. The resume directive's instruction to CREATE the file was stale. Correct action shifts from authoring to validating.

- timestamp: 2026-10-07T00:00:00Z
  checked: full read of tests/unit/test_write_scope_revert.py (268 lines) against the Resolution's prescribed scenario
  found: matches the prescription exactly - make_git_repo(tmp_path/'repo') + git_commit_all, pytest.mark.unit, no DB fixture, no drive(). Violation set is a tracked file (src/app.py, committed then tampered AND staged), an untracked-but-staged new file (src/new.py), and a symlink named 'aa-escape' pointing at tmp_path/outside/secret.txt which sorts alphabetically BEFORE both src/ paths. All four prescribed boundary neighbours present: escape-first, escape-last, escape-only, multiple-escapes - plus escape-never-acted-upon and single-raise-naming.
  implication: not a stub and not a narrower substitute; the prescribed coverage is genuinely present.

- timestamp: 2026-10-07T00:00:00Z
  checked: `uv run pytest -m unit -q tests/unit/test_write_scope_revert.py`
  found: 7 passed in 2.74s (re-confirmed 1.90s on a second run), zero skips, no database, no .env sourcing needed
  implication: confirms the central diagnostic claim empirically - this coverage never required Postgres, so the WR-02 skip rationale was factually wrong.

- timestamp: 2026-10-07T00:00:00Z
  checked: DECISIVE revert-check (fix-acceptance Signal 4) - restored the pre-CR-02 shape of revert_paths (bare propagating `_resolve_in_worktree(worktree, path)`, no `escapes` list, no trailing collected raise) and re-ran the suite
  found: 3 of 7 FAILED - test_escape_sorted_first_still_reverts_every_later_violation, test_multiple_escapes_are_all_named_in_the_single_raised_exception, test_enforce_write_scope_produces_the_escape_first_ordering_itself. Failure mode is exactly the one the docstring predicts: `assert "print('tampered by a violation')\n" == "print('original')\n"` - src/app.py was never reverted because the first escape aborted the loop. The 4 that still passed (escape-last, escape-only, never-acted-upon, single-raise-naming) are precisely the cases whose outcome is CR-02-independent.
  implication: the suite is NOT vacuous - it genuinely fails against a pre-CR-02 implementation and discriminates exactly the behavior CR-02 changed. scope.py then restored byte-identically (empty `git diff`), suite green again.

- timestamp: 2026-10-07T00:00:00Z
  checked: regression + static gates; acceptance-gate registration on disk
  found: full unit tier 819 passed / 1 skipped / 1 failed; the single failure is tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder, unrelated (asserts the Claude credential gate returns FAILED, but this machine has a working authenticated `claude` CLI so it returned COMPLETED). ruff check, ruff format --check, mypy all clean on the test file and scope.py. tests/integration/test_phase5_acceptance.py lines 86/124/144 register the file under SC4, ROLE-05 and _VALIDATION_PROOF_FILES; 05-VALIDATION.md:64 names it.
  implication: fix accepted. The one failure is a pre-existing environment-dependent test (my source diff for this session is zero), logged below as a separate finding - not a regression from this work.

## Resolution

root_cause: "Test-architecture partition: the write-scope module's coverage was split 'pure functions -> unit tier / everything else -> full-pipeline DB integration tier', so revert_paths/_resolve_in_worktree behavior was only ever reachable through drive() behind the `engine` fixture; AND process misclassification: CR-02 was a code-review-time fix in a sandbox with no reachable Postgres 17, whose regression test was deferred to WR-02 and then skipped as an environment limitation on the explicitly-stated but incorrect premise that the test requires a database - when scope.py is documented as having no DB access and the unit tier already exercises real git via make_git_repo."

fix: "No new change was required in this session: the prescribed fix had already landed via plan 05-06 (commits 0017004, 1c8296e) after this session paused. The fix is tests/unit/test_write_scope_revert.py - a new DB-free unit-tier proof file, sibling to test_git_lifecycle.py/test_git_diff.py/test_git_worktree.py, holding the first direct import of revert_paths/enforce_write_scope anywhere in the suite. It establishes the git-backed unit-tier home whose absence was contributing cause (1), while leaving tests/unit/test_write_scope.py's 'pure functions only' charter untouched. Registered as an SC4/ROLE-05 acceptance proof so the drift guard stays honest."

oracle_type: "derived (contract) - assertions are derived from revert_paths' documented contract (every non-escaping violation reverted: tracked restored from HEAD and unstaged, created file gone from disk and index; exactly one WriteScopeViolation naming every escape), not implicit crash-detection."

verification:
  signal_1_reproduction: "PASS - the original symptom was an absence, re-confirmed absent at diagnosis time by grep; the named file now exists, imports revert_paths directly, and executes."
  signal_2_regression: "PASS - full unit tier 819 passed / 1 skipped. Sole failure (test_worker_registry_names.py) is pre-existing and environment-dependent; this session's source diff is zero."
  signal_3_static_gates: "PASS - ruff check, ruff format --check, mypy all clean."
  signal_4_revert_check: "PASS (decisive) - restoring the pre-CR-02 revert_paths shape turns 3 of 7 tests red, including the CR-02 regression proper, with the exact predicted failure mode. The suite is not vacuous. scope.py restored byte-identically afterwards (empty git diff)."
  signal_5_diff_shape: "PASS - additive test-only change; no production code deleted or weakened, no assertion loosened anywhere."
  guardrail_verdict: "accepted"

files_changed: []
files_changed_note: "Zero files changed by this session. The fix's own files were committed earlier by plan 05-06: tests/unit/test_write_scope_revert.py (new), tests/integration/test_phase5_acceptance.py (modified - SC4/ROLE-05/_VALIDATION_PROOF_FILES tuples). scope.py was temporarily mutated for the Signal 4 revert-check and restored byte-identically."

prevention:
  why_not_caught: "No gate existed for this class: nothing checks that a code-review fix marked 'requires human verification' ever acquires its deferred regression test. CR-02's test was deferred to WR-02 by design, and WR-02 was then closed as an 'environment/infrastructure limitation' - a disposition that no gate cross-examines against the module it concerns. Aggravating, not causal: the unit/integration partition offered no obvious DB-free home for scope coverage, so the false 'needs Postgres' premise looked plausible and went unchallenged for two phases."
  guard: "tests/unit/test_write_scope_revert.py, registered in tests/integration/test_phase5_acceptance.py (lines 86/124/144) under SC4, ROLE-05 and _VALIDATION_PROOF_FILES, and named in 05-VALIDATION.md:64 - so deleting or renaming the proof file fails the acceptance gate rather than silently reopening the gap. Proven non-vacuous by mutation (pre-CR-02 revert_paths turns 3 of 7 red)."
  recommended_not_implemented: "Treat 'test deferred to a later finding' as a tracked debt item that blocks phase verification until the test exists, and require any 'needs a database' skip rationale to cite the DB dependency in the module under test - scope.py's docstring says the opposite verbatim ('No database access anywhere in this module'), so this skip was falsifiable from the source alone."

separate_finding: "tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder asserts WorkerResultStatus.FAILED on the premise that no Claude credentials exist in the test environment; on a machine with an authenticated `claude` CLI it returns COMPLETED and the test fails. The test is coupled to the absence of a credential rather than to adapter-resolution behavior, which is what its name says it proves. Out of scope for this session. ALREADY TRACKED in its own debug session (slug: claude-cli-test-spawns-real-binary-with-key-present, opened from a concurrent session) - deliberately NOT duplicated here."
