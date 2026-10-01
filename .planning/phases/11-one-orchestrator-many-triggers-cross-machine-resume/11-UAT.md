---
status: complete
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
source: [11-VERIFICATION.md]
started: 2026-09-30T12:52:18Z
updated: 2026-10-01T05:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. A real GitHub Actions run of ci.yml's expanded quality job
expected: Push this branch (or open a PR from it) and let `.github/workflows/ci.yml`'s `quality` job run to completion on a real GitHub-hosted runner. The `Database tier (FakeWorker orchestration suite, QUAL-01)` step's `pytest_report_header` reports the `testcontainers` rung (confirming Docker is genuinely available on `ubuntu-latest`), the ~205-test `db` tier passes, and both the step's and the job's durations sit comfortably inside the `[ASSUMED]` `timeout-minutes: 20` / `30` budgets. Replace the `[ASSUMED]` comments with measured values.
result: issue
reported: |
  CI job failed before reaching the db-tier step. The "Unit and contract tiers" step
  (`uv run pytest -q -m "unit or contract"`) errored during test collection:
  pydantic_core.ValidationError: 2 validation errors for Settings — database_url and
  database_url_direct both "Field required". Three modules failed to import:
  tests/db/test_webhook_dispatches_resume.py, tests/db/test_webhook_resolves_answer.py,
  tests/unit/test_webhook_signature.py — all because src/dark_factory/webhook/app.py:416
  does `app = build_app()` at module import time, which eagerly constructs a real
  Settings() requiring DATABASE_URL/DATABASE_URL_DIRECT. CI has no such env var (by
  design — only the db-tier step provisions a database, via testcontainers inside that
  step's own pytest run). Job exited with code 2; the db-tier step and its
  testcontainers-rung/timing evidence were never reached.
severity: blocker

### 2. A live workflow_dispatch against a real GitHub repository
expected: Provision a real fine-grained PAT (`Actions: Read and write`, scoped to one repository), add the documented `resume.yml`, pause a real run on a GitHub issue, answer the clarifying comment, and watch the repository's Actions tab. Exactly one `workflow_dispatch` run of `resume.yml` starts, carrying the run id, and `dark-factory resume <run_id>` inside that job resumes the run to its next state.
result: issue
reported: |
  Ran the full live path against a real repo (app-new): created an issue, started a real run,
  it paused WAITING_HUMAN with a genuine BA clarifying question, replied on the GitHub issue,
  and the webhook receiver correctly recorded the answer and called workflow_dispatch — a real
  `resume` Actions run started on app-new carrying the exact run_id. That half is fully proven.

  But `dark-factory resume <run_id>` inside that job then failed: role_executions.error shows
  "[Errno 2] No such file or directory: 'claude'" (worker: claude-code). The reference
  resume.yml in README.md only `pip install`s the dark-factory package — it never installs the
  Claude Code CLI binary itself, which the claude-code worker shells out to. Any real deployer
  using the claude-code worker would hit this identical failure. Run ended status FAILED
  instead of advancing past BA.
severity: major

## Summary

total: 2
passed: 0
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-11-1
  truth: "The `Database tier (FakeWorker orchestration suite, QUAL-01)` step's `pytest_report_header` reports the `testcontainers` rung, the ~205-test `db` tier passes, and step/job durations sit inside their `[ASSUMED]` timeouts."
  status: failed
  reason: "User reported: CI job failed before the db-tier step ran — the 'Unit and contract tiers' step errored during collection with pydantic ValidationError (database_url/database_url_direct Field required), because webhook/app.py:416's module-level `app = build_app()` eagerly constructs real Settings() at import time, and CI's unit/contract step has no DATABASE_URL configured (by design)."
  severity: blocker
  test: 1
  artifacts: []
  missing: []

- gap_id: G-11-2
  truth: "`dark-factory resume <run_id>` inside the dispatched resume.yml job resumes the run to its next state."
  status: failed
  reason: "User reported (via live test against a real repo): workflow_dispatch fired correctly carrying the real run_id, but the job's `dark-factory resume` call failed with \"[Errno 2] No such file or directory: 'claude'\" — the reference resume.yml in README.md never installs the Claude Code CLI the claude-code worker needs, only the dark-factory Python package."
  severity: major
  test: 2
  artifacts: []
  missing: []
