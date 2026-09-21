---
status: complete
phase: 07-claude-code-the-first-real-worker
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md]
started: 2026-09-20T23:45:00Z
updated: 2026-09-21T09:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. GitHub Actions CI actually runs and goes green (SC4 / QUAL-04)
expected: All four named steps (Lint, Types, Worker-name leak guard, Unit and contract tiers) go green on a real Actions run; a deliberate worker-name leak or a defanged guard step fails the build.
result: pass
verified: |
  Created private repo mariakravchenko/dark-factory, pushed branch, real Actions run
  (35577741173) went fully green on all 4 named steps. Then pushed a throwaway branch
  with a deliberate worker-name leak (uat/worker-leak-guard-check) and confirmed run
  35578371570 failed exactly at the "Worker-name leak guard (QUAL-04)" step, nothing
  else. Throwaway branch deleted (local + remote) after verification.

### 2. `db`/`integration` test tiers against real PostgreSQL/Neon
expected: Full suite (`uv run pytest -q`) green, including the tiers this sandbox cannot reach.
result: pass
verified: |
  User ran `uv run pytest -q` locally with a real backend available. Full suite:
  828 passed in 3382.99s (0:56:22), including the db and integration tiers.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
