---
status: testing
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-10-01T11:35:00Z
updated: 2026-10-01T11:35:00Z
---

## Current Test

number: 1
name: A real GitHub Actions run of the fixed `ci.yml`'s `quality` job
expected: |
  The `Unit and contract tiers` step passes (no longer exits 2 at collection — the G-11-1
  failure the original UAT reported). The `Database tier (FakeWorker orchestration suite,
  QUAL-01)` step is actually reached, its `pytest_report_header` reports the `testcontainers`
  rung, the ~205-test `db` tier passes, and both step/job durations sit inside their
  `[ASSUMED]` `timeout-minutes` budgets (20/30). Replace the `[ASSUMED]` comments with the
  measured values once observed.
awaiting: user response

## Tests

### 1. A real GitHub Actions run of the fixed `ci.yml`'s `quality` job
expected: |
  Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job
  run to completion on a real GitHub-hosted runner. The `Unit and contract tiers` step passes
  (no longer exits 2 at collection), the `Database tier (FakeWorker orchestration suite,
  QUAL-01)` step is reached and its `pytest_report_header` reports the `testcontainers` rung,
  the ~205-test `db` tier passes, and both step/job durations sit inside their `[ASSUMED]`
  budgets (20/30 min). This is the exact scenario UAT test 1 originally ran and found broken
  (G-11-1): the branch carrying the fix commits has never been pushed, so no CI run has ever
  seen the corrected `webhook/app.py`.
result: [pending]

### 2. A live `workflow_dispatch` + `dark-factory resume` against a real repository, with the worker runtime installed
expected: |
  Copy the corrected reference `resume.yml` block from README into a real target repository,
  follow the new "### The worker runtime" subsection to install the binary the repository's
  configured roles need, pause a real run on a GitHub issue, answer the clarifying comment,
  and watch the Actions tab. `dark-factory resume <run_id>` inside that job advances the run
  past BA instead of recording a `FAILED` role execution with an errno-2 "no such file or
  directory" error, and `dark-factory status <run_id>` confirms the run reached its next
  state. This is the exact live path UAT test 2 originally ran and found broken (G-11-2): no
  second live attempt against a real repository has been recorded since the README fix
  landed.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
