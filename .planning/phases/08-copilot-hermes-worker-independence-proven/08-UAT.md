---
status: resolved
phase: 08-copilot-hermes-worker-independence-proven
source: [08-VERIFICATION.md]
started: 2026-09-22T05:10:00Z
updated: 2026-10-26T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Live CLI suites pass against real binaries
expected: |
  All three live suites (`test_copilot_live.py`, `test_hermes_live.py`,
  `test_claude_code_live.py`) transition from SKIPPED to PASSED with a real binary and
  credential present, no code change required.
result: pass
note: |
  copilot and claude-code CLIs installed/authenticated; both live suites PASSED (2 passed,
  1 skipped) against a real DARK_FACTORY_TEST_DATABASE_URL Postgres 17. Hermes deliberately
  out of scope for this project per user decision (2026-09-22) -- test_hermes_live.py remains
  SKIPPED by design, not a defect. Accepted as pass.

### 2. Role-reassignment (SC2/WORK-09) and CR-01 artifact-scope end-to-end proofs pass against a real PostgreSQL 17
expected: |
  With a reachable PostgreSQL 17 (Docker, local `initdb`, or `DARK_FACTORY_TEST_DATABASE_URL`),
  `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py`
  — all 8 tests pass: the SC2 paired-run equality proof and its negative case, the
  shipped-config zero-config pipeline reaching COMPLETED across three real runtimes, and the
  three artifact-scope-enforcement end-to-end scenarios (Hermes negative, Copilot negative,
  positive control).
result: pass
reported: "Resolved via debug session cli-exit-code-on-failed-run (G-08-2): tests/integration/test_artifact_scope_enforcement.py's shared harness _drive_shipped_config now takes an expected_exit parameter (1 for the two tamper/negative callers, 0 for the positive control) instead of a hardcoded == 0 assertion, plus a cross-check tying the expectation to the persisted role_executions.error content. Verified: all 8 tests in test_role_reassignment_sc2.py / test_real_pipeline_zero_config.py / test_artifact_scope_enforcement.py pass against real PostgreSQL 17 (DARK_FACTORY_TEST_DATABASE_URL). Confirmed by user 2026-10-26."
severity: major

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-08-2
  truth: "CR-01 artifact-scope-enforcement negative-path tests (Hermes-tamper, Copilot-tamper) pass end to end against a real PostgreSQL 17"
  status: resolved
  resolution: "Test-only fix (production CLI exit-code mapping, D-05, was always correct and unchanged since phase 02). _drive_shipped_config now parameterizes expected_exit per caller instead of hardcoding 0. Verified against real PostgreSQL 17: 6/6 passed (was 4 passed, 2 failed), plus a revert-check reproducing the original AssertionError when expected_exit is reverted to 0. Confirmed by user 2026-10-26."
  reason: "User reported: 4 passed, 2 failed. Both failures in test_artifact_scope_enforcement.py assert proc.returncode == 0 on the `dark-factory run` CLI subprocess, and got 1 -- the run correctly reached terminal state FAILED after the artifact-scope violation was detected and reverted, but the CLI now exits non-zero on a FAILED terminal run state."
  severity: major
  test: 2
  root_cause: "tests/integration/test_artifact_scope_enforcement.py:128, in the shared harness _drive_shipped_config, asserts proc.returncode == 0 unconditionally on the `dark-factory run` CLI subprocess -- copied verbatim from a positive-path test (test_real_pipeline_zero_config.py:237) into a harness that also serves two negative-path tests whose runs are expected (and explicitly asserted by those same tests) to reach terminal FAILED. Per phase-01 decision D-05 (01-RESEARCH.md:18), FAILED -> exit 1 is the correct, documented, costly-to-reverse CLI contract (the Phase 11 CI trigger encodes these exit codes). The CLI (src/dark_factory/cli.py:147-157) is correct and unchanged since Phase 02 -- this is not a regression. tests/integration/test_exit_codes.py already asserts the opposite (FAILED -> exit 1) as its own D-05 contract guard, confirming the two tests cannot both be right. Shipped without ever executing (08-05-SUMMARY.md recorded D4/D5/D6 as collection-verified only, no DB available in that sandbox) -- this UAT session was their first real run."
  artifacts:
    - path: "tests/integration/test_artifact_scope_enforcement.py"
      issue: "_drive_shipped_config (line 128) asserts proc.returncode == 0 unconditionally, wrong for the two negative-path (tamper) callers which expect the run to reach FAILED and the CLI to exit 1 per D-05"
  missing:
    - "Give _drive_shipped_config an expected_exit parameter (1 for the two tamper/negative cases, 0 for the positive control) instead of a hardcoded == 0 assertion"
    - "Assert proc.returncode == expected_exit for each of the three callers in test_artifact_scope_enforcement.py"
  debug_session: ".planning/debug/cli-exit-code-on-failed-run.md"
