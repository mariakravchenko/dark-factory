---
status: complete
phase: 01-walking-skeleton-one-durable-run
source: [01-09-SUMMARY.md, 01-VERIFICATION.md]
started: 2026-09-08T00:00:00Z
updated: 2026-09-09T09:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Real-Neon full-stack run (deferred end-of-phase check, Plan 01-09 `user_setup`)
expected: |
  With a real Neon project on PostgreSQL 17: set `DATABASE_URL` to the POOLED
  connection string (host contains `-pooler`) and `DATABASE_URL_DIRECT` to the
  DIRECT string (host without `-pooler`). From a clean checkout:
  `cp .env.example .env` and fill both URLs -> `uv sync --all-extras --dev` ->
  `uv run alembic upgrade head` -> `uv run dark-factory run text:"add a health endpoint"`
  -> `uv run dark-factory status <run-id>` and `uv run dark-factory status <run-id> --json`.
  Observe: `alembic upgrade head` applies cleanly through the direct endpoint;
  `run` prints the run id on line 1, then `CREATED -> BA`, `BA -> COMPLETED`, then
  the summary block, exit 0; `status` reports `COMPLETED` / `current_role: BA` /
  `latest_attempt: 1` through the pooled endpoint; no prepared-statement / PgBouncer
  error against the pooled host.
result: pass
verified_by: operator against a real Neon PostgreSQL project on 2026-09-09
observed: |
  `uv run alembic upgrade head` applied `0001_walking_skeleton` then
  `0002_role_exec_uniqueness` through the direct endpoint with no error.
  `uv run dark-factory run text:"add a health endpoint"` (run twice) each printed
  a UUID on line 1, then `CREATED -> BA`, `BA -> COMPLETED`, then the summary
  block (terminal state COMPLETED, last role BA, attempt 1).
  `uv run dark-factory status 51450902-ad80-4885-8b54-0d8914095555` ->
  status COMPLETED / current_role BA / current_step 0 / latest_attempt 1 /
  timestamps present / base_branch, working_branch = `-`.
  `--json` -> the same fields as one JSON object (source_ref null, branches null).
  No PgBouncer / prepared-statement error appeared against the pooled host.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
