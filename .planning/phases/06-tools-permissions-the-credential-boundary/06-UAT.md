---
status: testing
phase: 06-tools-permissions-the-credential-boundary
source: [06-VERIFICATION.md]
started: 2026-09-20T06:43:27Z
updated: 2026-09-20T06:43:27Z
---

## Current Test

number: 1
name: SC1 db-tier tracer proof — capability-denial event ordering and artifact-row invariant
expected: |
  `uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -q tests/db/test_capability_denied_fails_role.py`
  (with `.env` sourced or `DARK_FACTORY_TEST_DATABASE_URL` set, against a real PostgreSQL 17)
  2 passed — the denial run's `run_events` rows are ordered CAPABILITY_DENIED, ROLE_FAILED,
  RUN_FAILED; the CAPABILITY_DENIED payload key set is exactly {role, capability, reason};
  zero artifacts rows for the denied attempt; the grant-present companion reaches COMPLETED
  with its artifact row present.
awaiting: user response

## Tests

### 1. SC1 db-tier tracer proof — capability-denial event ordering and artifact-row invariant
expected: |
  `uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -q tests/db/test_capability_denied_fails_role.py`
  2 passed — run_events ordered CAPABILITY_DENIED, ROLE_FAILED, RUN_FAILED; payload keys
  exactly {role, capability, reason}; zero artifacts rows for the denied attempt; the
  grant-present companion test reaches COMPLETED with its artifact row present.
result: [pending]

### 2. SC2 cross-process env-dump proof
expected: |
  `uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -m integration -q tests/integration/test_worker_env_boundary.py`
  3 passed. (Blocked only by this repo's `integration`-marker autouse DB-provisioning
  fixture, not by any actual database need in the test itself — the identical
  credential-boundary claim is already independently confirmed at the unit tier.)
result: [pending]

### 3. SC4 db-tier sweep arms — secret-leak sweep against real persistence
expected: |
  `uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -q tests/integration/test_capability_denial_no_secret_leak.py`
  6 passed. (3 of 6 arms already independently re-run DB-free and pass; these 3 drive a
  real run through Postgres and assert persisted run_events/role_executions rows and the
  log sink.)
result: [pending]

### 4. Full suite regression
expected: |
  `set -a; . /Users/maryiakrauchanka/portfolio/dark-factory/.env; set +a; uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -q`
  Green except the 3 pre-existing phase-4-owned failures documented since 06-01-SUMMARY.md
  (tests/db/test_artifact_commit_per_role.py x2, tests/integration/test_pr_diff_excludes_artifacts.py x1)
  — unrelated to Phase 6's work. (Unit tier — 442 tests — already independently re-run and
  100% green with zero regressions.)
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
