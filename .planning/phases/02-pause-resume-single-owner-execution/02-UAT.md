---
status: testing
phase: 02-pause-resume-single-owner-execution
source: [02-VERIFICATION.md]
started: 2026-09-10T00:00:00Z
updated: 2026-09-10T00:00:00Z
---

## Current Test

number: 1
name: Fresh-eyes README pause/resume walkthrough against a real Neon endpoint
expected: |
  A reader who has never seen the repo can start a scripted pause, read the recorded
  question via `dark-factory status`, and resume with `resume <id> --answer "..."` from a
  second shell, following only the README section — with no step they had to guess at, and
  the exit-code table making it unmistakable that a clean pause (exit 0) and a declined
  ownership race (exit 0) are successes, not faults.
awaiting: user response

## Tests

### 1. Fresh-eyes README pause/resume walkthrough against a real Neon endpoint
expected: A stranger follows only the README pause/resume section, literally, and pauses then resumes a run from two shells with no guessed step; the exit-code table makes clean-pause (exit 0) and declined-ownership-race (exit 0) unmistakably successes.
result: [pending]

### 2. Production-scale lease timing (900s TTL / 300s heartbeat) against a real Neon PgBouncer endpoint
expected: Pause a run, kill the owner, confirm a second process does NOT claim before `lock_expires_at`, then claims after; run a deliberately slow step and confirm `lock_expires_at` advances while it runs. Behaviour matches the short-injected-TTL (6s/2s, same TTL/3 ratio) integration proofs, at production scale.
result: [pending]

### 3. Confirm the Open Decision 2 production defaults (900s TTL / 300s heartbeat) are acceptable
expected: A genuinely dead owner's run is unclaimable for up to ~15 minutes and this phase provides no force-steal escape hatch. Operator either accepts the ceiling, or changes it (a one-line `Settings` default edit).
result: [pending]

### 4. Accept (or re-run against PostgreSQL 17) the db/integration proof tiers, which executed against PostgreSQL 18.6
expected: Operator confirms the PostgreSQL 18.6 vs the `postgres:17-alpine` pin in CLAUDE.md is an approved environmental deviation (carried since 01-01), or provisions a PG 17 endpoint for a confirmation run. No PostgreSQL was reachable in the verification environment, so the db/integration tiers were not re-executed by the verifier — the verdict rests on the executor-recorded green runs (02-07: 364 passed, 0 skipped), static source inspection, and the acceptance gate.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
