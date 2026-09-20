---
status: testing
phase: 07-claude-code-the-first-real-worker
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md]
started: 2026-09-20T23:45:00Z
updated: 2026-09-20T23:45:00Z
---

## Current Test

number: 1
name: GitHub Actions CI actually runs and goes green (SC4 / QUAL-04)
expected: |
  All four named steps (Lint, Types, Worker-name leak guard, Unit and contract tiers) go
  green on a real Actions run; a deliberate worker-name leak or a defanged guard step fails
  the build.
awaiting: user response

## Tests

### 1. GitHub Actions CI actually runs and goes green (SC4 / QUAL-04)
expected: All four named steps (Lint, Types, Worker-name leak guard, Unit and contract tiers) go green on a real Actions run; a deliberate worker-name leak or a defanged guard step fails the build.
result: [pending]

### 2. `db`/`integration` test tiers against real PostgreSQL/Neon
expected: Full suite (`uv run pytest -q`) green, including the tiers this sandbox cannot reach.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
