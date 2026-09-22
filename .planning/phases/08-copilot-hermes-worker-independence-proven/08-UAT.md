---
status: complete
phase: 08-copilot-hermes-worker-independence-proven
source: [08-VERIFICATION.md]
started: 2026-09-22T05:10:00Z
updated: 2026-09-22T06:15:00Z
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
result: issue
reported: "4 passed, 2 failed. Both failures are in test_artifact_scope_enforcement.py: test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails and test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails. Both assert proc.returncode == 0 on the `dark-factory run` CLI subprocess, and got 1 instead -- the run itself correctly reached terminal state FAILED (QA->FAILED / ARCHITECTURE->FAILED) after the artifact-scope violation was detected and reverted, but the CLI process now exits non-zero when the run's terminal state is FAILED."
severity: major

## Summary

total: 2
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-08-2
  truth: "CR-01 artifact-scope-enforcement negative-path tests (Hermes-tamper, Copilot-tamper) pass end to end against a real PostgreSQL 17"
  status: failed
  reason: "User reported: 4 passed, 2 failed. Both failures in test_artifact_scope_enforcement.py assert proc.returncode == 0 on the `dark-factory run` CLI subprocess, and got 1 -- the run correctly reached terminal state FAILED after the artifact-scope violation was detected and reverted, but the CLI now exits non-zero on a FAILED terminal run state."
  severity: major
  test: 2
  artifacts: []
  missing: []
