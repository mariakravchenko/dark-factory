---
status: diagnosed
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
test: (complete) source reading, git archaeology, differential sibling comparison, direct execution of the exit decision
expecting: (met) all six evidence lines converge on the test-defect explanation
next_action: (none — diagnose-only mode) return ROOT CAUSE FOUND; do NOT fix
goal: find_root_cause_only (diagnose only, do NOT fix)

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
fix: "NOT APPLIED — diagnose-only mode (goal: find_root_cause_only). Feeds /gsd-plan-phase --gaps for G-08-2."
verification: "N/A — no fix applied."
files_changed: []
