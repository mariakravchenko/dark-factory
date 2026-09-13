---
status: complete
phase: 04-the-four-role-pipeline-artifact-handoffs
source: [04-VERIFICATION.md]
started: 2026-09-13T17:10:00Z
updated: 2026-09-13T17:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Fresh-eyes readability of a real run's artifact tree
expected: Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (requirements.md, acceptance_criteria.json, design.md, constraints.json, implementation_summary.json, test_report.json, verdict.json). A person who has never seen this codebase can follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids line up across the files. G-04-1's specific defect (ids missing from design.md/implementation_summary.json) is now fixed and machine-asserted; what remains is judging whether the layout and the "Criterion AC-1 met" carrier-line phrasing genuinely read well to a first-time viewer.
result: pass

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
</content>
