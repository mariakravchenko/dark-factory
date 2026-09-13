---
status: testing
phase: 04-the-four-role-pipeline-artifact-handoffs
source: [04-VERIFICATION.md]
started: 2026-09-13T12:00:00Z
updated: 2026-09-13T12:00:00Z
---

## Current Test

number: 1
name: Fresh-eyes readability of a real run's artifact tree
expected: |
  A person who has never seen this codebase can follow the handoff from
  acceptance_criteria.json through design.md to verdict.json and see which
  criterion ids (AC-1, etc.) line up across the files.
awaiting: user response

## Tests

### 1. Fresh-eyes readability of a real run's artifact tree
expected: Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (requirements.md, acceptance_criteria.json, design.md, constraints.json, implementation_summary.json, test_report.json, verdict.json). A person who has never seen this codebase should be able to follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids line up across the files.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
