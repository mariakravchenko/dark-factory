---
status: testing
phase: 02-pause-resume-single-owner-execution
source: [02-VERIFICATION.md]
started: 2026-09-10T00:00:00Z
updated: 2026-09-10T14:10:00Z
---

## Current Test

number: 5
name: Re-run the DB/integration lease proof tiers against a real PostgreSQL, post-WR-01
expected: |
  Run tests/integration/test_heartbeat_slow_step.py, tests/integration/test_lease_expiry_reclaim.py,
  and tests/db/test_lease_lost_aborts_step.py (ideally the full db/integration tiers) against a real
  PostgreSQL, after the WR-01 heartbeat change (commit e9a231a). All pass: a transient renewal error
  does not immediately abort an in-flight step (the consecutive_errors retry keeps it alive for up to
  one heartbeat interval), a genuine lease loss still sets lease_lost immediately and the owner still
  aborts before its commit, and the retry window does not let an owner outlive its own lock_expires_at
  (no false steal — SC5; no shift in killed-owner reclaim timing — SC4).
awaiting: user response

## Tests

### 1. Fresh-eyes README pause/resume walkthrough against a real Neon endpoint
expected: A stranger follows only the README pause/resume section, literally, and pauses then resumes a run from two shells with no guessed step; the exit-code table makes clean-pause (exit 0) and declined-ownership-race (exit 0) unmistakably successes.
result: pass
note: "Operator ran README steps 1-3 verbatim against a real Neon endpoint. Pause produced `BA → WAITING_HUMAN` exit 0; `status` showed `WAITING_HUMAN` / `current_role: BA`; `resume --answer` produced the `run.resumed` stderr info line and `BA → COMPLETED` exit 0 — output matched the README examples step for step, run-id substitution obvious."

### 2. Production-scale lease timing (900s TTL / 300s heartbeat) against a real Neon PgBouncer endpoint
expected: Pause a run, kill the owner, confirm a second process does NOT claim before `lock_expires_at`, then claims after; run a deliberately slow step and confirm `lock_expires_at` advances while it runs. Behaviour matches the short-injected-TTL (6s/2s, same TTL/3 ratio) integration proofs, at production scale.
result: pass
note: "Operator confirmed production-scale lease timing against a real Neon PgBouncer endpoint: pre-expiry claim declined, post-expiry claim succeeded, and lock_expires_at advanced during a slow step — matching the short-injected-TTL integration proofs."

### 3. Confirm the Open Decision 2 production defaults (900s TTL / 300s heartbeat) are acceptable
expected: A genuinely dead owner's run is unclaimable for up to ~15 minutes and this phase provides no force-steal escape hatch. Operator either accepts the ceiling, or changes it (a one-line `Settings` default edit).
result: pass
note: "Operator accepts the ~15-minute unclaimable ceiling for a dead owner and the absence of a force-steal escape hatch in this phase; the 900s/300s defaults stand."

### 4. Accept (or re-run against PostgreSQL 17) the db/integration proof tiers, which executed against PostgreSQL 18.6
expected: Operator confirms the PostgreSQL 18.6 vs the `postgres:17-alpine` pin in CLAUDE.md is an approved environmental deviation (carried since 01-01), or provisions a PG 17 endpoint for a confirmation run. No PostgreSQL was reachable in the verification environment, so the db/integration tiers were not re-executed by the verifier — the verdict rests on the executor-recorded green runs (02-07: 364 passed, 0 skipped), static source inspection, and the acceptance gate.
result: pass
note: "Operator accepts the PostgreSQL 18.6 vs postgres:17-alpine pin as an approved environmental deviation carried since 01-01."

### 5. Re-run the DB/integration lease proof tiers against a real PostgreSQL, post-WR-01
expected: Run tests/integration/test_heartbeat_slow_step.py, tests/integration/test_lease_expiry_reclaim.py, and tests/db/test_lease_lost_aborts_step.py (ideally the full db/integration tiers) against a real PostgreSQL, after the WR-01 heartbeat change (commit e9a231a). All pass; the new consecutive_errors retry branch does not cause a false steal (SC5) or shift killed-owner reclaim timing (SC4), and a genuine lease loss still aborts the step before commit.
result: [pending]
reason_human_needed: "WR-01 (commit e9a231a) added new heartbeat control flow — a consecutive_errors threshold governing transient-vs-authoritative renewal loss — that landed after the last recorded green DB run (02-07: 364 passed). No runnable test in-session exercises the transient-exception branch, and no PostgreSQL was reachable in the verification environment. Static analysis shows the change cannot cause a false steal or hostage heartbeat; this confirms the timing behaviour against a database."

## Summary

total: 5
passed: 4
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
