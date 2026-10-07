---
status: resolved
trigger: "4 passed, 2 failed. Both failures are in test_artifact_scope_enforcement.py: test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails and test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails. Both assert proc.returncode == 0 on the `dark-factory run` CLI subprocess, and got 1 instead — the run itself correctly reached terminal state FAILED (QA->FAILED / ARCHITECTURE->FAILED) after the artifact-scope violation was detected and reverted, but the CLI process now exits non-zero when the run's terminal state is FAILED."
created: 2026-09-22T00:00:00Z
updated: 2026-09-22T00:00:00Z
---

## Current Focus

hypothesis: |
  CONFIRMED — this is (a), a stale/incorrect TEST expectation, not a CLI regression. The
  `assert proc.returncode == 0` in the shared harness `_drive_shipped_config`
  (test_artifact_scope_enforcement.py:128) was lifted verbatim from a POSITIVE-path caller
  (test_real_pipeline_zero_config.py:237) and applied to two NEGATIVE-path tests whose runs
  are expected — and asserted by those same tests — to reach terminal FAILED. Per phase-01
  decision D-05, FAILED -> exit 1 is the correct, documented, guarded CLI contract.
bug_class: Bohrbug (deterministic — reproduces on every run against a real Postgres 17)
test: (complete) executed the three artifact-scope tests, the four D-05 exit-code guards, and the two sibling integration modules against a real external PostgreSQL 17; then a revert-check on the hermes-tamper caller
expecting: (met) 6/6 of the original UAT command pass, D-05 guards unregressed, and the bug returns on revert
next_action: (none — RESOLVED) User confirmed fixed 2026-10-07. Archived; knowledge-base entry appended. The CI-gate residual risk was split into its own session, integration-tier-excluded-from-ci-credential-free-tests-could-run.md, rather than widened into this fix.
goal: find_and_fix (resumed; prior session was diagnose-only)

fix_already_present: |
  The recommended fix was ALREADY APPLIED AND COMMITTED in 7b752fe
  "fix(08-06): give _drive_shipped_config a per-caller expected exit code and D-05
  cross-check" (1 file changed, test-only — src/dark_factory/cli.py untouched).
  It implements exactly the diagnosed direction, and goes further than the minimum:
  `expected_exit` is keyword-only with NO default (so a future caller cannot silently
  inherit a wrong expectation), and the harness cross-checks the caller's expected exit
  against the persisted terminal status via `_D05_SUCCESS_STATUSES`, so a disagreement
  between the D-05 mapping and the observed run status now fails loudly.
  This resumed session's remaining job is VERIFICATION, not implementation.

reasoning_checkpoint:
  hypothesis: "test_artifact_scope_enforcement.py's shared harness asserts a success exit code on runs it simultaneously asserts must reach FAILED; the CLI's FAILED->1 mapping is the correct D-05 contract."
  confirming_evidence:
    - "Direct execution: _drive_and_exit returns 0 for COMPLETED/WAITING_HUMAN and 1 for FAILED (observed, not inferred)."
    - "git show e65aa25:src/dark_factory/cli.py — the exit line was BYTE-IDENTICAL at the commit that created the failing test."
    - "tests/integration/test_exit_codes.py::test_exit_1_when_the_worker_script_supplies_a_failed_result asserts returncode == 1 on a persisted FAILED — a pre-existing guard directly contradicting the new test."
    - "01-RESEARCH.md D-05 records exit 1 = FAILED as a decision, flagged 'Reversibility: costly — the Phase 11 CI trigger encodes these three codes.'"
    - "Sibling negative test (test_role_reassignment_sc2.py:292) expects ARCHITECTURE FAILED and deliberately omits any returncode assertion."
    - "08-05-SUMMARY.md coverage D4/D5/D6: all three tests were 'collection-verified clean; not execution-verified' — they never ran before this UAT."
  falsification_test: "Find a commit where `dark-factory run` exited 0 on a FAILED terminal state, or a decision record superseding D-05. Neither exists: git log -L on the function shows only 3 commits, all phase 01-02, and the content is identical at the test's own commit."
  fix_rationale: "N/A — diagnose-only. Direction: remove/relocate the returncode assertion from the shared harness so negative cases assert exit 1 (or do not assert at all, per the SC2 idiom) while the positive control keeps asserting 0. Changing the CLI would break test_exit_codes.py and reverse a costly-to-reverse decision."
  blind_spots: "Could not execute the failing tests here (no Docker/initdb/DARK_FACTORY_TEST_DATABASE_URL — the same constraint that let the defect ship). The exit decision itself was executed directly, so the mechanism is observed; only the full end-to-end re-run is unverified locally."
  candidate_causes:
    - "code (test): copy-pasted positive-path assertion in a shared negative-path harness — CONFIRMED"
    - "code (production/CLI): regression in exit-code mapping — REFUTED (byte-identical at test-creation commit; guarded by test_exit_codes.py)"
    - "config: shipped .dark-factory config causing spurious failure — REFUTED (positive control uses the identical config and passes)"
    - "environment: no reachable Postgres in the authoring sandbox — CONTRIBUTING to the escape, not to the failure"
    - "process: 08-05-PLAN said 'drive the run in process'; executor used the CLI-subprocess idiom instead, inheriting the positive-path template's assertion — CONTRIBUTING"
  and_gate: |
    Mixed. For the TEST FAILURE: single cause, no AND — the one wrong assertion is necessary and
    sufficient, deterministic every run. For the ESCAPE (why it shipped): a genuine AND of
    (wrong assertion authored) AND (no reachable Postgres in the authoring sandbox, so the test
    was committed collection-verified only and never executed). Fixing only the assertion closes
    the failure; the escape needs the execution gate.

## Symptoms

expected: |
  `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py
  tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py`
  against a reachable PostgreSQL 17 — all tests pass, including the three
  artifact-scope-enforcement end-to-end scenarios (Hermes negative, Copilot negative,
  positive control).
actual: |
  4 passed, 2 failed. Failures: test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails
  and test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails.
  Both assert proc.returncode == 0 on the `dark-factory run` CLI subprocess; got 1.
  The run reached terminal state FAILED correctly (QA->FAILED / ARCHITECTURE->FAILED)
  after the artifact-scope violation was detected and reverted.
errors: |
  AssertionError: exit=1 (expected 0), from tests/integration/test_artifact_scope_enforcement.py:128
  inside helper _drive_shipped_config -> _run_cli_against_real_repo(...),
  asserted via `assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"`
reproduction: Test 2 in .planning/phases/08-copilot-hermes-worker-independence-proven/08-UAT.md, gap G-08-2
started: Discovered during /gsd-verify-work 08 UAT session, 2026-09-22

## Eliminated

## Evidence

- timestamp: 2026-09-22T00:00:00Z
  checked: .planning/debug/knowledge-base.md for matching patterns
  found: One entry (phase4-artifact-commit-bugs). Related domain (write_scope / artifact scope enforcement / run FAILED) but a DIFFERENT failure mode — that one was about runs unexpectedly reaching FAILED. Here the FAILED state is EXPECTED and correct; only the CLI process exit code is disputed.
  implication: No direct known-pattern hypothesis. Its lesson is still relevant as a caution: "stale test fixtures, not a production defect" was the answer last time in this same subsystem.

- timestamp: 2026-09-22T00:10:00Z
  checked: src/dark_factory/cli.py:15-18 (module docstring), :126 (_CLEAN_FINALS), :147-157 (_drive_and_exit)
  found: |
    Docstring: "Exit codes (D-05): 0 for COMPLETED, 1 for a persisted FAILED, 2 for a
    bad invocation where nothing was persisted". Code: `_CLEAN_FINALS = (RunStatus.COMPLETED,
    RunStatus.WAITING_HUMAN)` and `raise typer.Exit(code=0 if final in _CLEAN_FINALS else 1)`.
  implication: FAILED -> exit 1 is the explicit, documented, intentional contract — not incidental.

- timestamp: 2026-09-22T00:12:00Z
  checked: .planning/phases/01-walking-skeleton-one-durable-run/01-RESEARCH.md:18 (D-05 decision text)
  found: |
    "D-05: Exit codes for `run` / `resume`: `0` when the run reaches `COMPLETED`; `1` when the
    run reaches `FAILED` (a real, persisted terminal delivery failure); `2` for bad invocation...
    Reversibility: costly — the Phase 11 CI trigger encodes these three codes."
  implication: |
    D-05 is a recorded phase-01 architecture decision, explicitly flagged as COSTLY to reverse
    because Phase 11's CI trigger depends on the three codes. An artifact-scope violation that
    fails the run IS "a real, persisted terminal delivery failure" — exit 1 is contract-correct.

- timestamp: 2026-09-22T00:14:00Z
  checked: git log -L 147,158:src/dark_factory/cli.py (history of the exit-code function)
  found: |
    Only three commits ever touched it: cd63c62 feat(01-06) [phase 01, introduced],
    e51126f fix(01) [phase 01, WR-07 exit-2 branch], 360f594 feat(02-03) [phase 02].
    UNTOUCHED since phase 02.
  implication: |
    REFUTES the "genuine CLI regression" hypothesis. The exit-code logic has not changed in six
    phases. The failing test was authored in phase 08 (e65aa25, 29ec3c2), long after the CLI
    behavior was fixed. The CLI did not "now" start exiting non-zero — it always did.

- timestamp: 2026-09-22T00:16:00Z
  checked: tests/integration/test_exit_codes.py (dedicated D-05 guard, phase 01)
  found: |
    Line 1 docstring: "The D-05 exit-code contract, exercised across a real process boundary."
    :49 test_exit_0_on_the_happy_path -> asserts returncode == 0
    :59 test_exit_1_when_the_worker_script_supplies_a_failed_result -> asserts returncode == 1
    :74 test_exit_2_on_an_unrecognised_prefix... -> asserts returncode == 2
    :81 test_orchestration_error_exits_2... -> asserts returncode == 2
  implication: |
    DIRECT CONTRADICTION. A pre-existing, passing integration test asserts returncode == 1 for a
    persisted FAILED run. If `dark-factory run` were "fixed" to exit 0 on FAILED,
    test_exit_codes.py::test_exit_1_when_the_worker_script_supplies_a_failed_result would break.
    Two tests in the repo cannot both be right; the phase-01 one encodes the recorded decision.

- timestamp: 2026-09-22T00:18:00Z
  checked: |
    Differential: the sibling NEGATIVE test tests/integration/test_role_reassignment_sc2.py:292-295
    (expects ARCHITECTURE FAILED, run != COMPLETED) vs the failing negative tests.
  found: |
    The SC2 negative test calls `_run_cli_against_real_repo(...)` and goes STRAIGHT to
    `run_id = UUID(proc.stdout.splitlines()[0].strip())` with NO returncode assertion at all.
    The SC2 POSITIVE test (:158-159) DOES assert `proc.returncode == 0`.
  implication: |
    The correctly-written negative test deliberately omits the returncode assertion precisely
    because a negative case does not exit 0. This is the working-case/failing-case difference:
    presence of `assert proc.returncode == 0` in a negative-path harness.

- timestamp: 2026-09-22T00:20:00Z
  checked: |
    Origin of the assertion — tests/integration/test_real_pipeline_zero_config.py:233-237
    (the idiom test_artifact_scope_enforcement.py's docstring says it reuses).
  found: |
    `proc = _run_cli_against_real_repo(...)` then `assert proc.returncode == 0,
    f"exit={proc.returncode}\n{proc.stdout}"` — inside
    test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script, a POSITIVE-path test
    whose run reaches COMPLETED. There, returncode == 0 is correct.
  implication: |
    The assertion was lifted verbatim from a positive-path caller into
    _drive_shipped_config (test_artifact_scope_enforcement.py:127-128), which is a SHARED harness
    used by BOTH negative cases AND the positive control. Correct for the control, wrong for the
    two negative cases.

- timestamp: 2026-09-22T00:22:00Z
  checked: Pass/fail split predicted by the hypothesis vs the reported split
  found: |
    The 3 tests in test_artifact_scope_enforcement.py all route through _drive_shipped_config.
    Only the positive control (test_the_identical_shipped_config_with_no_tampering_completes...)
    reaches COMPLETED -> exit 0 -> its returncode assertion holds -> PASSES.
    Both negative cases reach FAILED -> exit 1 -> assertion fails -> FAIL.
    Reported: "4 passed, 2 failed", both failures the two negative cases.
  implication: |
    The hypothesis predicts the exact observed split, including WHICH tests pass. A CLI
    regression would not spare the positive control selectively in this pattern.

- timestamp: 2026-09-22T00:24:00Z
  checked: Internal consistency of the two failing tests
  found: |
    Both failing tests assert `result["status"] != "COMPLETED"` and
    `result["status_by_role"]["QA"|"ARCHITECTURE"] == "FAILED"` — i.e. the test author
    explicitly expected a FAILED terminal state — while the shared harness simultaneously
    asserts the CLI exited 0.
  implication: |
    The test file is self-contradictory: it demands a FAILED run AND a success exit code.
    That is a copy-paste defect signature, not a deliberate contract claim.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    On resume — whether the prescribed fix still needed applying. Read
    tests/integration/test_artifact_scope_enforcement.py in full; `git log` +
    `git log -S'expected_exit'` on that path; `git show --stat 7b752fe`.
  found: |
    The fix ALREADY LANDED in 7b752fe "fix(08-06): give _drive_shipped_config a per-caller
    expected exit code and D-05 cross-check" — 1 file changed, 41 insertions, TEST-ONLY.
    `_drive_shipped_config` now takes keyword-only `expected_exit: int` with NO default
    (:112), asserts `proc.returncode == expected_exit` (:145), and the three callers pass
    expected_exit=1 (hermes-tamper :216), 1 (copilot-tamper :281), 0 (positive control :344).
    It also added a cross-check (:176-181) asserting
    `(status_value in _D05_SUCCESS_STATUSES) == (expected_exit == 0)`.
  implication: |
    No implementation work remained — the diagnosed direction was implemented exactly, and
    went beyond the minimum (no-default keyword-only param prevents silent inheritance by a
    future caller; the DB cross-check fails loudly if the D-05 mapping and the persisted
    status ever diverge). This session's job collapsed to the fix-acceptance guardrail.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    src/dark_factory/cli.py:165,196 and `git log -L` on the exit decision — whether any
    production exit-code change crept in alongside.
  found: |
    `_CLEAN_FINALS = (RunStatus.COMPLETED, RunStatus.WAITING_HUMAN)` (:165) and
    `raise typer.Exit(code=0 if final in _CLEAN_FINALS else 1)` (:196), unchanged; the
    decision line's last touching commit is still 360f594 (phase 02).
  implication: |
    The D-05 contract was never altered. The fix is test-only, exactly as the diagnosis
    required. Nothing reversed the costly-to-reverse decision.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    The prior session's blind spot — no reachable Postgres. Re-probed the environment:
    DARK_FACTORY_TEST_DATABASE_URL is now set (external rung; Neon PG 17). Docker absent,
    no local initdb, so tests/conftest.py `_select_rung()` resolves to "external".
  found: Postgres reachable; the integration tier is executable in this session for the first time.
  implication: |
    The one blind spot that let the defect ship (and that the prior session could not close)
    is closed for this verification. The original reproduction command can now actually run.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Guardrail Signal — original reproduction + D-05 regression guard.
    `uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py
    tests/integration/test_exit_codes.py` then the other two files from the UAT command.
  found: |
    7 passed in 199.33s (3 artifact-scope + 4 D-05 exit-code guards).
    3 passed in 191.18s (test_role_reassignment_sc2.py, test_real_pipeline_zero_config.py).
    Original UAT command's 6 tests: 6 passed, 0 failed. Was "4 passed, 2 failed".
  implication: |
    Both originally-failing negative tests now pass, the positive control still passes, and
    all four test_exit_codes.py D-05 guards still pass — so the fix did not shift the CLI
    contract to make the new tests green. The two adjacent integration files are unregressed.

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    Guardrail Signal — revert-check (is the fix load-bearing, or vacuous?). Temporarily
    mutated the hermes-tamper caller back to `expected_exit=0` (the pre-fix state) and ran
    that single test.
  found: |
    1 failed in 54.21s — `AssertionError: exit=1 expected=0` at
    test_artifact_scope_enforcement.py:145. Byte-for-byte the original symptom
    ("AssertionError: exit=1 (expected 0)", then at :128).
  implication: |
    The bug returns on revert and the fix removes it — the regression test is NOT vacuous.
    Strongest available acceptance signal. Mutation fully restored afterwards
    (`git diff --quiet` on the test file confirms it is identical to the committed state).

- timestamp: 2026-10-07T00:00:00Z
  checked: |
    The ESCAPE half of the AND-gate — whether a gate now executes the integration tier.
    .github/workflows/ci.yml:55-61 and tests/conftest.py:142.
  found: |
    conftest raises `pytest.UsageError` (not skip) when no Postgres is reachable — so an
    unrun integration test cannot silently pass. BUT ci.yml:55-59 still deliberately
    EXCLUDES the `integration` tier, with the documented reason "some of its tests drive
    real agent CLIs whose credentials (e.g. ANTHROPIC_API_KEY) this hosted runner does not
    have" and an explicit "Do not 'fix' this omission ... without first provisioning those
    credentials." Notably these three tests need no real credentials — they install fake
    CLIs (write_fake_hermes/copilot/claude) and monkeypatch fake tokens.
  implication: |
    The failure is closed; the ESCAPE gate is still open — no CI gate executes these tests.
    The in-code guards from 7b752fe (no-default keyword-only `expected_exit` + the D-05
    cross-check) are the recurrence guard that is actually in place. Splitting the
    fake-CLI-only integration tests into a CI-runnable selector is a real follow-up but a
    phase-level decision, deliberately NOT taken here (out of a debug fix's scope).

## Resolution

root_cause: |
  TEST DEFECT (option (a) — stale/incorrect test expectation). ZERO production defect.

  `tests/integration/test_artifact_scope_enforcement.py:128`, inside the shared harness
  `_drive_shipped_config`, asserts `proc.returncode == 0` on the `dark-factory run`
  subprocess. That assertion was copied verbatim from `test_real_pipeline_zero_config.py:237`,
  a POSITIVE-path test whose run reaches COMPLETED (where exit 0 is correct), into a harness
  that also serves two NEGATIVE-path tests whose runs are expected — and explicitly asserted
  by those same tests (`result["status"] != "COMPLETED"`, `status_by_role[...] == "FAILED"`)
  — to reach terminal FAILED.

  Per phase-01 decision D-05 (01-RESEARCH.md:18), `dark-factory run` exits 0 for COMPLETED,
  1 for a persisted FAILED, 2 for a bad invocation where nothing was persisted. An
  artifact-scope violation that fails the role and the run is precisely "a real, persisted
  terminal delivery failure", so exit 1 is contract-correct. The CLI is behaving as designed
  and as guarded.

  The two failing tests are therefore self-contradictory: they demand a FAILED run AND a
  success exit code. The positive control passes only because its run genuinely reaches
  COMPLETED, which is why the split is exactly "4 passed, 2 failed".

  Contributing cause of the ESCAPE (AND-gate): 08-05-SUMMARY.md coverage entries D4/D5/D6
  record all three tests as "collection-verified clean; not execution-verified" because the
  authoring sandbox had no reachable PostgreSQL 17. The tests were committed having never
  been run; this UAT session is their first execution.
fix: |
  ALREADY APPLIED by commit 7b752fe "fix(08-06): give _drive_shipped_config a per-caller
  expected exit code and D-05 cross-check" — test-only, 1 file, 41 insertions. This resumed
  session wrote NO new code; it verified that fix. Nothing was changed in
  src/dark_factory/cli.py, as the diagnosis required.

  What 7b752fe does, in tests/integration/test_artifact_scope_enforcement.py:
    1. `_drive_shipped_config` gains keyword-only `expected_exit: int` with NO default
       (:112), so a future caller cannot silently inherit another caller's expectation.
    2. The hardcoded `assert proc.returncode == 0` becomes
       `assert proc.returncode == expected_exit` (:145).
    3. The three call sites state their own expectation: expected_exit=1 for the two
       tamper/negative callers (:216, :281) and expected_exit=0 for the untampered
       positive control (:344).
    4. Added guard (:176-181): the harness cross-checks the caller's `expected_exit`
       against the terminal status it reads back from Postgres —
       `(status_value in _D05_SUCCESS_STATUSES) == (expected_exit == 0)` — so the test
       fails loudly if the CLI's D-05 mapping and the observed run status ever disagree,
       rather than silently encoding a stale expectation again.

oracle_type: |
  specified — the assertion is checked against a recorded, published contract (D-05 in
  01-RESEARCH.md:18, restated in src/dark_factory/cli.py's module docstring), not against
  observed behavior. `_D05_SUCCESS_STATUSES` is the contract transcribed into the test, and
  the cross-check at :176 ties it to the persisted status rather than to the exit code alone.
  Not implicit: an exit code alone would also be produced by an unrelated terminal failure,
  which is exactly the masking the later 10-07/G-10-1 error-blob assertions closed.

verification: |
  guardrail_verdict: accepted

  signal_original_repro: PASS — the exact UAT command's 6 tests now pass (was 4 passed,
    2 failed). 3 artifact-scope tests pass: both tamper cases exit 1 and satisfy
    expected_exit=1; the positive control exits 0.
  signal_contract_regression: PASS — all 4 tests/integration/test_exit_codes.py D-05 guards
    still pass (7 passed in 199.33s with the artifact-scope file). Proves the fix did not
    reverse the costly D-05 decision to turn the new tests green.
  signal_adjacent_regression: PASS — tests/integration/test_role_reassignment_sc2.py and
    tests/integration/test_real_pipeline_zero_config.py: 3 passed in 191.18s. These are the
    sibling/origin modules the harness borrows from, the likeliest regression surface.
  signal_revert_check: PASS (strongest) — reverting only the hermes-tamper caller to
    expected_exit=0 reproduces the original symptom exactly: `AssertionError: exit=1
    expected=0` at :145, 1 failed in 54.21s. The fix is load-bearing, the test is not
    vacuous. Mutation reverted; `git diff --quiet` confirms the test file is byte-identical
    to its committed state.
  signal_production_diff_empty: PASS — src/dark_factory/cli.py untouched; `_CLEAN_FINALS`
    and the `typer.Exit(code=0 if final in _CLEAN_FINALS else 1)` decision last changed in
    phase-02 commit 360f594. Zero production change, matching the zero-production-defect
    diagnosis.
  signal_deletion_only: N/A — the diff adds a parameter and a cross-check; it does not
    weaken or delete an assertion. The one assertion it replaced became strictly stronger
    (per-caller expectation plus a DB cross-check vs. a single hardcoded constant).

  blind_spot_closed: The prior session could not execute these tests (no reachable
    Postgres). This session ran them against a real external PostgreSQL 17, so the
    mechanism is now observed end to end, not inferred.
  residual_risk: The `integration` tier is still excluded from CI (ci.yml:55-59, real
    agent-CLI credentials), so no automated gate re-runs this proof. The in-code recurrence
    guards from 7b752fe are what prevent the class from returning.

files_changed: []  # this session: none. The fix itself shipped in 7b752fe (test-only).
