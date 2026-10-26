---
phase: 02-pause-resume-single-owner-execution
plan: 05
subsystem: testing
tags: [postgres, lease, heartbeat, single-owner, hitl-08, sc5, pg_stat_activity, idle-in-transaction, threading, subprocess, tdd]

# Dependency graph
requires:
  - phase: 02-03
    provides: "orchestrator/lease.py — run_lease context manager + daemon heartbeat (renew on own session, sets lease_lost on a renewal that matches no row), __exit__ always stops/joins/releases; apply_transition expected_owner_token → LeaseLost fence; _run_current_role checks lease.lease_lost before any write"
  - phase: 02-02
    provides: "Settings.lease_ttl_seconds / lease_heartbeat_seconds + use_lease_settings fixture; engine connect_args application_name='dark-factory'; slow FakeWorker + DARK_FACTORY_FAKE_SLEEP_MS; tests/support/subprocess_runner.py (child_env / popen / spawn / wait_for / run_id_from_stdout)"
  - phase: 02-04
    provides: "the two-real-process race + killed-owner-reclaim proof patterns (invariant assertions over winner assertions; wait_for on a committed DB condition; real_session_factory + cleanup_runs idiom)"
  - phase: 01
    provides: "apply_transition one mutation path; resume-first advance/_advance_once/drive; the two-real-process harness"
provides:
  - "tests/integration/test_heartbeat_slow_step.py — SC5: a step >3x the lease TTL completes untouched while lock_expires_at strictly advances repeatedly (periodic renewal, not a single push); every competing resume during the step exits 0 with the owned-by-another-process notice and writes nothing; reaching COMPLETED clears both lease columns; a run_lease body that raises releases immediately; structural assertion that the lease path has no liveness probe"
  - "tests/integration/test_no_txn_across_worker.py — HITL-08: while a slow FakeWorker is mid-call, no dark-factory backend has a transaction open longer than 3s (pg_stat_activity xact_start age filter); plus a positive unit assertion that a session handed to create_run / apply_transition is out of its transaction once the helper returns"
  - "tests/db/test_lease_lost_aborts_step.py — the lease-loss abort proof: a stolen lease mid-step persists nothing, enforced independently by the in-memory flag AND the commit-time owner-token fence (removing either fails exactly one test); LeaseLost is a distinct type from ConcurrentTransition; the discarded step is re-runnable on the same attempt"
affects: ["02-07", "phase-11-cross-machine-resume"]

# Actuals (#2632)
actuals:
  tokens: 10500
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SC5 heartbeat proof: sample lock_expires_at from a separate connection every ~0.25s while a real subprocess runs a slow step; assert the series is non-decreasing with ≥3 strict increases — periodic renewal, not a claim-time push. Sampling stops the instant status leaves BA (the stop-status transition clears the lease columns)."
    - "HITL-08 proof by xact_start age, not by raw idle-in-transaction count: against a ~1.5s-round-trip endpoint a well-formed sub-second heartbeat transaction is briefly visible as 'idle in transaction' during its commit round-trip; the T-02-27 threat is a transaction *held open across the worker call*, so the assertion is `xact_start < now() - interval '3 seconds'` == 0 on every sample. The plan anticipates the transient ('may be non-zero only transiently')."
    - "two independently-sufficient guards proven by construction: one test sets the in-memory lease_lost flag with the owner token still matching the row (flag alone aborts, before apply_transition is called); one clears the flag and overwrites the owner token (the commit-time fence alone aborts, inside apply_transition). A refactor removing either guard fails exactly one test."
    - "driving one interruptible step in-process: claim a real lease (or open run_lease for a real heartbeat), build a LeaseHandle, call the private _advance_once(run_id, ..., lease=handle) with a sleep_ms FakeWorker; overwrite runs.owner_token from another session (a faithful competing claim also sets lock_expires_at) to simulate mid-step theft."
    - "injected-lease-value scaling: Open Decision 2's heartbeat≈TTL/3 ratio is what the plan says transfers; the illustrative 2s/1s absolute values leave no margin for the remote endpoint's ~1.5s renewal round-trip, so 6s/2s is used — same ratio, and `interval + renewal_latency` (~2.5s) sits inside the TTL. Production 300s/900s is unaffected (a ~1.5s renewal inside a 300s interval)."

key-files:
  created:
    - "tests/integration/test_heartbeat_slow_step.py"
    - "tests/integration/test_no_txn_across_worker.py"
    - "tests/db/test_lease_lost_aborts_step.py"
  modified: []

key-decisions:
  - "No production code changed. Plan 02-05 is proof-only for the heartbeat / no-transaction-across-the-worker / lease-lost-abort mechanism that 02-03 shipped — every assertion runs against the real run_lease heartbeat, real claim_lease / renew_lease / release_lease, real apply_transition owner-token fence, and real _run_current_role flag check. No `test(02-05)` RED phase preceded a `feat(02-05)` fix because no proof turned up a genuine defect (as 02-04 was also proof-only)."
  - "Injected lease values are 6s TTL / 2s heartbeat, not the plan's illustrative 2s / 1s. One heartbeat renewal round-trip against the operator's remote Neon endpoint measures ~1.4-1.6s (open session + one UPDATE...RETURNING + commit + close), so a 1s interval + ~1.5s renewal leaves the 2s TTL with no margin and a competitor polling every 0.5s claims in the gap — the owner then loses its own lease mid-step. 6s/2s keeps Open Decision 2's TTL/3 ratio (the part the plan says transfers) while giving `interval + latency` room inside the TTL. Mirrors 02-04's accepted 4s→15s slow-step scaling; same endpoint, same class of reason."
  - "HITL-08 is asserted on transaction *age* (xact_start older than 3s), not on a zero raw idle-in-transaction count. The heartbeat's own `with session.begin(): UPDATE` commit round-trip is transiently visible as 'idle in transaction' on this high-latency endpoint; that is a sub-second beat, not a held lock. The threat (T-02-27 / T-02-31) is a transaction that spans the multi-second worker call — such a transaction shows an xact_start many seconds in the past; a beat never does."
  - "test_a_lease_taken_while_the_worker_call_is_in_flight... keeps the 2s/1s short settings (via use_lease_settings) because it exercises the loss-*detection* direction, which the thief guarantees regardless of renewal timing; only the survival direction needs the widened margin."

patterns-established:
  - "SC5 slow-step heartbeat proof: periodic lock_expires_at advance sampled from a separate connection, competitors failing to claim on every attempt, BA-phase-only sampling"
  - "HITL-08 proof from pg_stat_activity by xact_start age (held-open), tolerant of transient sub-second beats on a high-latency endpoint"
  - "belt-and-braces abort proven by removing-one-guard-fails-exactly-one-test construction"
  - "release-on-exception proven with the default 900s TTL so a successful fresh claim can only mean the release ran"

requirements-completed: [HITL-07, HITL-08]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "SC5 — a role step that runs more than three times the lease TTL is not falsely stolen: the owner's heartbeat pushes lock_expires_at forward repeatedly (≥3 strict increases) while the owner token never changes, and a competing process polling resume fails to claim on every attempt, exiting 0 with the owned-by-another-process notice and writing nothing"
    requirement: "HITL-07"
    verification:
      - kind: integration
        ref: "tests/integration/test_heartbeat_slow_step.py::test_a_slow_step_keeps_its_lease_and_the_expiry_advances_repeatedly"
        status: pass
    human_judgment: false
  - id: D2
    description: "The lease context releases on every exit path including an exception: a run_lease whose body raises leaves both lease columns null immediately and a fresh claim wins at once (proven with the default 900s TTL, so success can only mean release ran, not that a short TTL lapsed) — the hostage-taking failure mode (T-02-29)"
    requirement: "HITL-07"
    verification:
      - kind: integration
        ref: "tests/integration/test_heartbeat_slow_step.py::test_a_lease_context_whose_body_raises_releases_the_lease_immediately"
        status: pass
    human_judgment: false
  - id: D3
    description: "The lease path contains no liveness probe of any kind — no pg_stat_activity, os.getpid, os.getppid, psutil or SIGKILL — liveness is a freshly pushed expiry and nothing else"
    requirement: "HITL-07"
    verification:
      - kind: integration
        ref: "tests/integration/test_heartbeat_slow_step.py::test_the_lease_path_never_probes_another_process_for_liveness"
        status: pass
      - kind: other
        ref: "grep -v '^#' src/dark_factory/orchestrator/lease.py | grep -c 'pg_stat_activity\\|os.getpid\\|psutil' == 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "HITL-08 — no database transaction is held open across the worker call: while a deliberately slow FakeWorker is mid-call, no dark-factory backend has a transaction whose xact_start is older than 3s, sampled repeatedly (≥5 samples) during the call; proven from the server's own activity view, not by inspection"
    requirement: "HITL-08"
    verification:
      - kind: integration
        ref: "tests/integration/test_no_txn_across_worker.py::test_zero_backends_of_this_application_are_idle_in_transaction_during_the_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "HITL-08 positive companion — a session handed to create_run / apply_transition is not inside a transaction once the helper returns (each opens exactly one with session.begin() and makes no explicit commit)"
    requirement: "HITL-08"
    verification:
      - kind: integration
        ref: "tests/integration/test_no_txn_across_worker.py::test_a_session_handed_to_a_mutation_helper_is_not_in_a_transaction_afterwards"
        status: pass
    human_judgment: false
  - id: D6
    description: "A transition applied with a non-matching expected_owner_token raises LeaseLost and commits nothing (status / latest role-execution row field-by-field / event count all unchanged), even when the expected status is exactly what the caller expected (Pitfall 2); LeaseLost is a distinct type from ConcurrentTransition"
    requirement: "HITL-07"
    verification:
      - kind: db
        ref: "tests/db/test_lease_lost_aborts_step.py (test_a_transition_with_a_non_matching_owner_token..., test_lease_lost_is_a_distinct_error_type..., test_the_fence_holds_when_the_expected_status_is_exactly_right)"
        status: pass
    human_judgment: false
  - id: D7
    description: "A lease stolen while the worker call is in flight aborts the step through the runner with nothing persisted; the abort is enforced independently by the in-memory flag (flag set, token still matches → aborts before apply_transition) and by the commit-time token fence (flag clear, token overwritten → aborts inside apply_transition) — removing either guard fails exactly one test"
    requirement: "HITL-07"
    verification:
      - kind: db
        ref: "tests/db/test_lease_lost_aborts_step.py (test_a_lease_taken_while_the_worker_call_is_in_flight..., test_the_in_memory_flag_alone_aborts..., test_the_token_fence_alone_aborts...)"
        status: pass
    human_judgment: false
  - id: D8
    description: "After a lease-loss abort the discarded step is re-runnable on the same attempt: a fresh claim runs the step again, leaving exactly one role-execution row for the role and exactly one ROLE_COMPLETED event — indistinguishable from the step never having started"
    requirement: "HITL-07"
    verification:
      - kind: db
        ref: "tests/db/test_lease_lost_aborts_step.py::test_after_an_abort_the_discarded_step_re_runs_on_the_same_attempt"
        status: pass
    human_judgment: false
  - id: D9
    description: "Confirm the Open Decision 2 production defaults (900s TTL / 300s heartbeat) are acceptable now that the mechanism is proven at short values — a genuinely dead owner's run is unclaimable for up to 15 minutes with no earlier-steal escape hatch in this phase"
    verification: []
    human_judgment: true
    rationale: "A product/operations judgment about an acceptable reclaim-delay ceiling, not something a test can settle. The mechanism is proven; the numbers are an inheritance the developer should confirm or change (a one-line default edit)."

# Metrics
duration: ~3h (dominated by ~13min db + ~12min integration full-tier runs against the shared remote Neon endpoint, plus 3x heartbeat stability runs)
completed: 2026-09-10
status: complete
plan_head_before: 7ca08ec10c8eb7dbc8cedf47e752d4090b189bb8
---

# Phase 2 Plan 05: Heartbeat, No-Transaction-Across-the-Worker, and Lease-Lost Abort Summary

**SC5 and HITL-08 proven against the shipped mechanism: a step more than three times the lease TTL keeps its lease while the owner's heartbeat advances `lock_expires_at` repeatedly and a competitor fails to claim on every attempt; no `dark-factory` transaction is ever held open across the worker call (server activity view, by `xact_start` age); and a lease stolen mid-step aborts with nothing persisted, fenced independently by the in-memory flag and by the commit-time owner-token check.**

## Performance

- **Duration:** ~3h wall (most of it full-tier verification against the shared remote Neon endpoint: db 12m37s, integration 11m33s, plus three back-to-back heartbeat stability runs at ~100s each).
- **Completed:** 2026-09-10
- **Tasks:** 2 of 2
- **Files created:** 3 (all test files; no production change)

## Accomplishments

- **SC5** (`tests/integration/test_heartbeat_slow_step.py`, 3 tests): a real `dark-factory run` process runs a ~20 s worker step under an injected 6 s TTL / 2 s heartbeat. From a separate connection the run row is sampled every ~0.25 s while it is in `BA`: `lock_expires_at` is non-decreasing and strictly increases at least three times (a standalone measurement over ~20 s wall saw **5 strict advances**, the expiry moving forward ~17 s — one renewal per ~2.5 s cycle of `2 s wait + ~0.5 s renew round-trip`), and `owner_token` is identical in every sample. Up to 6 competing `resume` subprocesses are launched during the first 10 s of the step; every one exits 0, prints `is owned by another process` on stderr with no traceback, prints no transition line, and changes nothing — afterwards there is exactly one `BA` role-execution row at attempt 1 and exactly one `ROLE_COMPLETED` event. Reaching `COMPLETED` leaves both lease columns `NULL` (cleared by the stop-status transition, not left to expire), so a process started afterward returns immediately. A separate in-process test drives `run_lease` around a body that raises and asserts both lease columns are `NULL` straight away and a fresh `claim_lease` wins — with the **default 900 s TTL**, so the claim can only succeed because `__exit__` released. A structural test asserts `lease.py` contains no `pg_stat_activity` / `os.getpid` / `os.getppid` / `psutil` / `SIGKILL`.
- **HITL-08** (`tests/integration/test_no_txn_across_worker.py`, 2 tests): while a slow `FakeWorker` is mid-call in a real process, the test repeatedly queries `pg_stat_activity` for `dark-factory` backends whose transaction has been open longer than 3 s and asserts the count is **0 on every sample** (≥ 5 samples). The test's own connection is unlabelled, so it never counts itself. A raw `idle in transaction` count is also collected for the failure narrative — transient blips there are a heartbeat commit round-trip on the high-latency endpoint, not a held lock. A companion unit-level assertion in the same file: after `create_run` returns and after `apply_transition` returns, `session.in_transaction()` is `False`.
- **Lease-lost abort** (`tests/db/test_lease_lost_aborts_step.py`, 7 tests): `apply_transition` with a non-matching `expected_owner_token` raises `LeaseLost` and writes nothing — asserted field-by-field on the latest role-execution row and on the event count, and asserted to hold even when `expected_status` is exactly right (Pitfall 2). `LeaseLost` is not a subclass of `ConcurrentTransition` and vice versa, and each failure mode raises its own type. Through the runner: a real `run_lease` + daemon heartbeat under the short lease, a 4 s worker call, the owner token overwritten from another session mid-call → the heartbeat's next renewal matches no row, sets the flag, and `_advance_once` raises `LeaseLost` before any write. Two variants isolate the guards: **flag set / token still matches** aborts before `apply_transition` is ever called; **flag clear / token overwritten** aborts inside `apply_transition`. After an abort, a fresh claim re-runs the step on attempt 1 with exactly one role-execution row and one `ROLE_COMPLETED` event.

## Task Commits

1. **Task 1 — SC5 heartbeat slow-step + HITL-08 no-txn proofs** — `7673d20` (`test(02-05)`)
2. **Task 2 — lease-lost mid-step abort proof** — `b5c1eb7` (`test(02-05)`)

**Plan metadata:** _(this commit)_ — SUMMARY.md, STATE.md, ROADMAP.md, REQUIREMENTS.md.

`plan_head_before = 7ca08ec10c8eb7dbc8cedf47e752d4090b189bb8`; `git rev-list --count 7ca08ec..HEAD` = **2** task commits.

## RED / GREEN / REFACTOR notes

Both tasks carry `tdd="true"` and both plan files list `src/` modules (`lease.py`, `runner.py`) in `files_modified` — but only *conditionally*, "if a proof turns up a real gap". No gap was found:

- **RED:** each proof was written against the mechanism 02-03 shipped and run. None failed for a real-defect reason. The one iteration needed on Task 1 was the injected-lease-value margin (2 s/1 s → 6 s/2 s) and the HITL-08 assertion shape (raw count → `xact_start` age) — both are test-methodology corrections for the remote endpoint's latency, not production fixes. Task 2's `test_a_lease_taken_while_the_worker_call_is_in_flight...` first failed because the initial design re-claimed through `advance()` after the thief had already overwritten `owner_token` *and left `lock_expires_at` NULL*, which the claim predicate reads as "owned forever"; corrected by claiming through `run_lease` first (so the claim precedes the theft) and by making the simulated theft also set a fresh expiry.
- **GREEN:** no `feat(02-05)` commit — there is no production change to make. `test_heartbeat_slow_step.py` + `test_no_txn_across_worker.py` pass; `test_lease_lost_aborts_step.py` passes with 7 collected tests.
- **REFACTOR:** none.

This mirrors 02-04, which was also a proof-only plan against the 02-03 lease with `test(02-04)` commits and no production change.

## Files Created/Modified

- `tests/integration/test_heartbeat_slow_step.py` (created, 347 lines) — SC5: periodic-renewal proof, competitor-never-claims, lease-cleared-on-stop, release-on-exception, no-liveness-probe structural assertion.
- `tests/integration/test_no_txn_across_worker.py` (created, 217 lines) — HITL-08: `pg_stat_activity` `xact_start`-age proof + `session.in_transaction()` companion.
- `tests/db/test_lease_lost_aborts_step.py` (created, 553 lines) — lease-loss abort: direct fence, distinct-type, mid-step abort through the runner, both-guards-independently-sufficient, re-runnability.

## The exact activity-view query used

```sql
SELECT count(*) FROM pg_stat_activity
WHERE application_name = 'dark-factory'
AND state LIKE 'idle in transaction%'
AND xact_start < now() - (:linger * interval '1 second')   -- :linger = 3
```

Asserted `= 0` on every sample taken while the worker call is in flight. A raw variant without the `xact_start` clause is also sampled and reported in the failure message only.

## Observed heartbeat behaviour

- Injected: `LEASE_TTL_SECONDS=6`, `LEASE_HEARTBEAT_SECONDS=2`; worker step ~20 s (`DARK_FACTORY_FAKE_SLEEP_MS=20000`).
- One heartbeat renewal round-trip (open `Session` + one `UPDATE runs ... RETURNING` + commit + close) against the remote endpoint: **~1.4–1.6 s** (measured in isolation).
- Standalone 20 s sampling of `lock_expires_at`: **5 strict advances**, expiry moved forward **~17.1 s** — i.e. one successful renewal per ~2.5 s (`2 s interval + ~0.5 s renew`), never letting the 6 s TTL lapse.
- In the full test the sampler is interleaved with a live subprocess and `_run_row` reads are ~1.4 s each; strict advances are fewer per unit wall time but comfortably `≥ 3` on all three stability runs.

## Hardening applied to lease.py / runner.py

**None.** Both proofs pass against the code as shipped by 02-03:

- `run_lease.__exit__` already stops the heartbeat, joins it, and best-effort releases on *every* exit path (proven by `test_a_lease_context_whose_body_raises_releases_the_lease_immediately`).
- the heartbeat already renews on its own session in a sub-second `with session.begin()` transaction and never holds one open (proven by the `xact_start`-age assertion returning 0 throughout the step).
- `_run_current_role` already checks `lease.lease_lost.is_set()` *before* building any write and raises `LeaseLost` (proven by the flag-alone test).
- `apply_transition` already fences the commit on `expected_owner_token` against the already-locked `runs` row (proven by the fence-alone test and the direct-fence tests).

## Decisions Made

See `key-decisions` in the frontmatter. The load-bearing ones: (1) **injected lease values are 6 s / 2 s, not 2 s / 1 s** — Open Decision 2's `heartbeat ≈ TTL/3` ratio is preserved (it is the part the plan says transfers), but the absolute values are scaled so one ~1.5 s renewal round-trip plus the interval sits inside the TTL against the remote endpoint; at 2 s / 1 s a competitor polling every 0.5 s claims in the ~0.5 s gap between renewals and the owner loses its own lease mid-step. (2) **HITL-08 is asserted on transaction age, not raw idle-in-transaction count** — a well-formed sub-second heartbeat transaction is briefly visible as `idle in transaction` during its commit round-trip on a ~1.5 s-RTT endpoint; the threat is a transaction *held open across the worker call*, which shows an `xact_start` many seconds old.

## Deviations from Plan

### 1. [Rule 1 - test methodology, not a code fix] Injected lease values 2 s / 1 s → 6 s / 2 s

- **Found during:** Task 1, first run of `test_heartbeat_slow_step.py` — the owning process lost its *own* lease mid-step (`lease.lost` → `lease.lost_mid_step` → exit 2).
- **Issue:** one heartbeat renewal round-trip against the operator's remote Neon endpoint measures ~1.4–1.6 s. With a 1 s interval the renewal cycle is ~2.5 s while the TTL is 2 s, so the lease is briefly expired between every pair of renewals; six competitors polling `claim_lease` every 0.5 s reliably hit that gap and steal it.
- **Fix:** injected `LEASE_TTL_SECONDS=6`, `LEASE_HEARTBEAT_SECONDS=2` (same `TTL/3` ratio) and widened the step to ~20 s (> 3× TTL). Competitor launches spaced to 1.5 s and capped at 6 to keep row-lock contention off the heartbeat.
- **Impact:** none on what is proven — SC5's claim is about the ratio, which is unchanged; the production 300 s / 900 s defaults have a ~1.5 s renewal inside a 300 s interval and are untouched. Mirrors 02-04's accepted 4 s → 15 s slow-step scaling.
- **Verification:** `test_heartbeat_slow_step.py` + `test_no_txn_across_worker.py` run three times back-to-back, all green (5 passed each, ~100 s).

### 2. [Rule 1 - test methodology] HITL-08 asserted on `xact_start` age, not raw idle-in-transaction count

- **Found during:** Task 1, first green-ish run of `test_no_txn_across_worker.py` — raw `idle in transaction` count was `[0,0,0,1,0,1,...]`.
- **Issue:** the heartbeat's `with session.begin(): UPDATE` parks its backend `idle in transaction` for the ~0.5 s commit round-trip on this endpoint, so a raw count occasionally reads 1. That is a sub-second beat, not a held transaction.
- **Fix:** the assertion counts only `dark-factory` backends whose `xact_start` is older than 3 s — a transaction genuinely spanning the multi-second worker call; the plan explicitly anticipates the transient ("may be non-zero only transiently"). Raw count still collected for the failure narrative.
- **Impact:** none — the T-02-27 / T-02-31 threat is a *held* transaction, which is exactly what the age filter catches.

### 3. [Rule 1 - Bug in the test, corrected before commit] Simulated mid-step theft must also set a fresh expiry

- **Found during:** Task 2, `test_a_lease_taken_while_the_worker_call_is_in_flight...`.
- **Issue:** the first design re-claimed through `advance()` after a helper had overwritten only `owner_token`, leaving `lock_expires_at` NULL; `claim_lease`'s predicate (`owner_token IS NULL OR lock_expires_at < now()`) reads "owner set, no expiry" as owned-forever, so the second `advance()` raised `LeaseNotAcquired` at claim time instead of `LeaseLost` at commit time.
- **Fix:** the test now opens `run_lease` first (claim precedes the theft), and `_overwrite_owner_token` sets both `owner_token` and a fresh `now() + 900s` expiry — a faithful stand-in for a real competing `claim_lease`.
- **Impact:** none on scope; the test now exercises the intended path (heartbeat detects the loss, `_advance_once` aborts on the flag).

---

**Total deviations:** 3, all test-methodology corrections made before the task commits. **No production code changed.** No scope creep.

## Issues Encountered

- **The remote endpoint's per-round-trip latency (~1.4–1.6 s) is the dominant design constraint for this plan.** It is what forced the injected-lease-value scaling (deviation 1) and the `xact_start`-age assertion (deviation 2). A local Postgres 17 would let the plan's literal 2 s / 1 s values pass; the operator runs against remote Neon by choice (the same environmental deviation carried since `01-01-SUMMARY.md`).
- **Full-tier runs are slow** — db 12m37s (89 passed), integration 11m33s (46 passed). Consistent with 02-03/02-04. All green.

## Verification Results

| Check | Result |
|---|---|
| 1. `pytest -m db -q` (whole DB tier) | **89 passed**, 243 deselected, exit 0 (757 s) |
| 2. `pytest -m integration -q` (whole integration tier) | **46 passed**, 286 deselected, exit 0 (693 s) |
| 3. `mypy src/dark_factory` (`--strict`) | Success: no issues found in 39 source files |
| 4. `ruff check .` | All checks passed |
| 5. `test_heartbeat_slow_step.py` + `test_no_txn_across_worker.py` ×3 back-to-back | Run 1: 5 passed (101.65 s) · Run 2: 5 passed (99.55 s) · Run 3: 5 passed (101.49 s) — zero flakiness |
| `test_lease_lost_aborts_step.py` (Task 2 `<verify>`, ≥ 6 tests) | **7 passed** (152 s) |
| `test_transition_atomic.py` + `test_state_event_pairing.py` (Task 2 regression `<verify>`) | passed unchanged (in the 12-passed combined run) |
| `mypy src/dark_factory/orchestrator` (Task 1 `<verify>`) | Success |
| `grep -v '^#' src/dark_factory/orchestrator/lease.py \| grep -c 'pg_stat_activity\|os.getpid\|psutil'` | **0** |
| `grep -v '^#' src/dark_factory/orchestrator/lease.py \| grep -c 'datetime\.now\|datetime\.utcnow'` | **0** |
| `grep -v '^#' src/dark_factory/orchestrator/lease.py \| grep -c 'pg_advisory\|SKIP LOCKED\|skip_locked'` | **0** |

## `<human-check>` — production TTL / heartbeat defaults

**Deferred to `/gsd-verify-work`** (coverage D9, `human_judgment: true`). The mechanism is now proven at short values; the question the developer must answer is whether the shipped defaults — **900 s lease TTL, 300 s heartbeat** — are acceptable as production values, given that a genuinely dead owner's run is unclaimable for up to ~15 minutes and this phase provides no way to force an earlier steal. The fix, if the ceiling is too high, is a one-line default change in `Settings` plus a note — not a redesign. The automated substitute proof used 6 s / 2 s (same ratio); the ratio, not the absolute value, is what transfers.

## Known Stubs

None. Every path is a real end-to-end proof: real `run_lease` daemon heartbeat renewing on its own session, real `claim_lease` / `renew_lease` / `release_lease`, real `apply_transition` owner-token fence, real `_run_current_role` flag check, real two-process races, and the real PostgreSQL `pg_stat_activity` view.

## Requirements status (shared-ID gate)

The plan's `requirements: [HITL-07, HITL-08]` both remain **Pending** in `REQUIREMENTS.md`. Both IDs are also declared by 02-07 (the phase acceptance gate), which has no `*-SUMMARY.md` yet, so the shared-ID gate keeps them Pending until 02-07 finishes. This plan ships and proves the heartbeat half of HITL-07 (SC5) and the transaction-boundary half of HITL-08 (activity-view proof); 02-07 marks both IDs Complete.

## Next Phase Readiness

- **02-06** (generic mechanism + redaction sweep): order-independent per the plan's `coupling_justified`; unaffected — no `src/` change here.
- **02-07** (phase acceptance gate): SC5 → `tests/integration/test_heartbeat_slow_step.py::test_a_slow_step_keeps_its_lease_and_the_expiry_advances_repeatedly`; HITL-08 → `tests/integration/test_no_txn_across_worker.py::test_zero_backends_of_this_application_are_idle_in_transaction_during_the_call`; lease-loss abort → `tests/db/test_lease_lost_aborts_step.py`. Marker strings unchanged: `is owned by another process` (stderr), `BA → COMPLETED` (stdout).
- **Phase 11** (cross-machine resume): the DB-clock-only expiry and the no-process-identity-check invariants are now enforced structurally (`test_the_lease_path_never_probes_another_process_for_liveness`) as well as by the 02-03/02-04 greps.

---
*Phase: 02-pause-resume-single-owner-execution*
*Completed: 2026-09-10*

## Self-Check: PASSED

- All created files present on disk: `tests/integration/test_heartbeat_slow_step.py`, `tests/integration/test_no_txn_across_worker.py`, `tests/db/test_lease_lost_aborts_step.py`, `.planning/phases/02-pause-resume-single-owner-execution/02-05-SUMMARY.md`.
- Both task commits present in history: `7673d20` (`test(02-05)` — SC5 heartbeat + HITL-08 no-txn), `b5c1eb7` (`test(02-05)` — lease-lost mid-step abort).
- Full `<verification>` re-run green: db tier 89 passed / integration tier 46 passed / `mypy --strict` clean / `ruff check .` clean / heartbeat+no-txn ×3 back-to-back all 5 passed with zero flakiness. All three `lease.py` invariant greps return 0.
- `git rev-list --count 7ca08ec..HEAD` = 2, matching `actuals.commits: 2`.
