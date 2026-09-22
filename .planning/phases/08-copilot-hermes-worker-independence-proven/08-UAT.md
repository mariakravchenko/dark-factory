---
status: testing
phase: 08-copilot-hermes-worker-independence-proven
source: [08-VERIFICATION.md]
started: 2026-09-22T05:10:00Z
updated: 2026-09-22T05:10:00Z
---

## Current Test

number: 1
name: Live CLI suites pass against real `copilot`/`hermes`/`claude` binaries
expected: |
  Install a real `copilot` binary with a valid `COPILOT_GITHUB_TOKEN` and a real `hermes`
  binary with a valid `ANTHROPIC_API_KEY` in a clean container, then run:
  `uv run pytest -q -rs tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py tests/integration/test_claude_code_live.py`
  All three suites transition from SKIPPED to PASSED with no code change, exercising
  `CopilotWorker`/`HermesWorker`/`ClaudeCodeWorker` against the genuine binaries
  (ROADMAP SC1's literal clean-container claim, D-02's deferred live spike).
awaiting: user response

## Tests

### 1. Live CLI suites pass against real binaries
expected: |
  All three live suites (`test_copilot_live.py`, `test_hermes_live.py`,
  `test_claude_code_live.py`) transition from SKIPPED to PASSED with a real binary and
  credential present, no code change required.
result: [pending]

### 2. Role-reassignment (SC2/WORK-09) and CR-01 artifact-scope end-to-end proofs pass against a real PostgreSQL 17
expected: |
  With a reachable PostgreSQL 17 (Docker, local `initdb`, or `DARK_FACTORY_TEST_DATABASE_URL`),
  `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py`
  — all 8 tests pass: the SC2 paired-run equality proof and its negative case, the
  shipped-config zero-config pipeline reaching COMPLETED across three real runtimes, and the
  three artifact-scope-enforcement end-to-end scenarios (Hermes negative, Copilot negative,
  positive control).
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
