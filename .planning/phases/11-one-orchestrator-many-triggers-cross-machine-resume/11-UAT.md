---
status: testing
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-09-30T12:52:18Z
updated: 2026-09-30T12:52:18Z
---

## Current Test

number: 1
name: A real GitHub Actions run of ci.yml's expanded quality job
expected: |
  Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run
  to completion on a real GitHub-hosted runner. The `Database tier (FakeWorker orchestration
  suite, QUAL-01)` step's `pytest_report_header` reports the `testcontainers` rung (confirming
  Docker is genuinely available on `ubuntu-latest`), the ~205-test `db` tier passes, and both the
  step's and the job's durations sit comfortably inside the `[ASSUMED]` `timeout-minutes: 20` / `30`
  budgets. Replace the `[ASSUMED]` comments in `ci.yml` with measured values.
awaiting: user response

## Tests

### 1. A real GitHub Actions run of ci.yml's expanded quality job
expected: Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner. The `Database tier (FakeWorker orchestration suite, QUAL-01)` step's `pytest_report_header` reports the `testcontainers` rung (confirming Docker is genuinely available on `ubuntu-latest`), the ~205-test `db` tier passes, and both the step's and the job's durations sit comfortably inside the `[ASSUMED]` `timeout-minutes: 20` / `30` budgets. Replace the `[ASSUMED]` comments with measured values.
result: [pending]

### 2. A live workflow_dispatch against a real GitHub repository
expected: Provision a real fine-grained PAT (`Actions: Read and write`, scoped to one repository), add the documented `resume.yml`, pause a real run on a GitHub issue, answer the clarifying comment, and watch the repository's Actions tab. Exactly one `workflow_dispatch` run of `resume.yml` starts, carrying the run id, and `dark-factory resume <run_id>` inside that job resumes the run to its next state.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
