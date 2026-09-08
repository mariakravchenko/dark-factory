---
status: testing
phase: 01-walking-skeleton-one-durable-run
source: [01-09-SUMMARY.md, 01-VERIFICATION.md]
started: 2026-09-08T00:00:00Z
updated: 2026-09-08T00:00:00Z
---

## Current Test

number: 1
name: Real-Neon full-stack run (pooled + direct endpoint split)
expected: |
  `alembic upgrade head` applies cleanly through the DIRECT endpoint (creates
  `runs`, `role_executions`, `run_events`). `dark-factory run text:"add a health
  endpoint"` prints the run id on line 1, then `CREATED -> BA`, `BA -> COMPLETED`,
  then the summary block, and exits 0. `dark-factory status <run-id>` (and
  `--json`) reports `COMPLETED` / `current_role: BA` / `latest_attempt: 1` read
  through the POOLED endpoint. No PgBouncer / prepared-statement error appears
  against the pooled host — the `NullPool` + `prepare_threshold=None` +
  `pool_pre_ping` settings in `engine.py` are what this exercises for real.
awaiting: user response

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
result: [pending]
why_human: |
  External managed service (Neon) with PgBouncer transaction pooling. Plan 01-09
  declared this as a `user_setup` / end-of-phase human-check and it was NOT
  performed during execution. All automated db/integration tests ran against a
  throwaway PostgreSQL 18.6 instance with a single URL, never against Neon PG 17
  with the pooled-vs-direct endpoint split. The pooled-endpoint behaviour the
  `engine.py` / `migrations/env.py` settings target has no automated coverage.

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
