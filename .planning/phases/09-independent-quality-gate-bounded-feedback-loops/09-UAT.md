---
status: testing
phase: 09-independent-quality-gate-bounded-feedback-loops
source: [09-VERIFICATION.md]
started: 2026-09-23T12:15:00Z
updated: 2026-09-23T12:15:00Z
---

## Current Test

number: 1
name: GATE-02/GATE-03 — a gate whose commands produced a non-zero exit_code never reaches RunStatus.COMPLETED on that attempt, regardless of the worker's own success-claiming WorkerResult.summary
expected: |
  Run reaches RunStatus.FAILED, not COMPLETED, with both configured commands recorded and the QA role-execution row's error naming quality_gate_fail.
  Run: `uv run pytest -m db -q tests/db/test_quality_gate_gates_the_run.py::test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary`
awaiting: user response

## Tests

### 1. GATE-02/GATE-03: gate FAIL keeps the run out of COMPLETED
expected: Run reaches RunStatus.FAILED, not COMPLETED, with both configured commands recorded and the QA role-execution row's error naming quality_gate_fail.
result: [pending]

### 2. LOOP-03: iteration counter read/compared before the signal is chosen; exactly one counter incremented per attempt
expected: runs.qa_developer_iterations / runs.quality_gate_iterations increment by exactly 1 on a bounce and the two counters never cross-contaminate.
result: [pending]

### 3. LOOP-04 (adjacency): failing role with no earlier role yields ROLE_FAILED reason no_earlier_role_to_bounce_to
expected: A pipeline whose only role FAILs produces ROLE_FAILED immediately with the adjacency reason, never a call into transition() with ROLE_BOUNCED from the first node.
result: [pending]

### 4. LOOP-04 (empty): a cap of 0 makes the first rejection terminal, no zero-value special case
expected: Run ends FAILED with zero ROLE_BOUNCED events and runs.qa_developer_iterations still 0.
result: [pending]

### 5. LOOP-04 (idempotency): re-driving an exhausted run adds no further events/increments
expected: run_events row count and both counter columns are byte-identical before and after a second advance() call on a terminal run.
result: [pending]

### 6. LOOP-01: a bounced Developer's next attempt receives verdict.json with QA's structured issues, end to end
expected: Developer attempt-1 RoleContext has no verdict.json entry; attempt-2 RoleContext has one whose produced_by names QA and whose content carries the FAIL issue's severity/criterion/description.
result: [pending]

### 7. LOOP-02 (payload): a bounced Developer's next attempt receives quality_gate.json with the real per-command failure output, end to end
expected: Developer attempt-2 RoleContext has a quality_gate.json entry whose produced_by is the gate and whose parsed content carries a non-zero exit_code and the sentinel stderr text.
result: [pending]

### 8. CR-01 (ROLE-05 on bounce): a real four-role drive() run where QA writes outside its declared write_scope on an attempt that would otherwise bounce ends FAILED
expected: Zero ROLE_BOUNCED events, runs.qa_developer_iterations still 0, the planted path reverted from disk, exactly one role_executions row per role, and a RUN_FAILED event naming write_scope.
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
