---
phase: 02-pause-resume-single-owner-execution
plan: 04
subsystem: testing
tags: [postgres, lease, single-owner, concurrency, race, expiry, reclaim, threading, subprocess, tdd]

# Dependency graph
requires:
  - phase: 02-03
    provides: "orchestrator/lease.py — claim_lease / renew_lease / release_lease + run_lease; apply_transition expected_owner_token fence; lease columns cleared on any stop-status transition; CLI 'owned by another process' notice + exit 0"
  - phase: 02-02
    provides: "tests/support/subprocess_runner.py (child_env / spawn / popen / run_id_from_stdout / wait_for) with lease + crash knobs; force_lease_expiry / use_lease_settings fixtures; slow FakeWorker + DARK_FACTORY_FAKE_SLEEP_MS"
  - phase: 02-01
    provides: "runs.owner_token / runs.lock_expires_at columns; human_interactions table; Alembic 0003"
  - phase: 01
    provides: "the one mutation path (apply_transition); resume-first advance/drive; DARK_FACTORY_CRASH_AFTER; the two-real-process test harness"
provides:
  - "tests/db/test_lease_claim_atomic.py — HITL-07 at the statement level: 16 threads / one session each call the real claim_lease against one run → exactly one token; a forced-expired run is reclaimed by exactly one new owner; a terminal run is claimable by nobody even while unowned; renew and release are token-fenced"
  - "tests/integration/test_single_owner_race.py — SC3: two real OS processes race the same run → exactly one advances, the loser prints the CLI owned-by-another-process notice and exits 0 with no writes and no duplicate ROLE_COMPLETED / role-execution row; plus a tight race from creation asserting the same invariants without pinning a winner"
  - "tests/integration/test_lease_expiry_reclaim.py — SC4: a killed owner's lease is not stolen before its DB-clock expiry (field-by-field snapshot equality after an early resume attempt) and is reclaimed after it — both by forcing the expiry and by genuinely waiting out a 2s injected TTL — continuing on the same attempt with no second run; plus a structural assertion that no reaper/scheduler/sweeper exists"
affects: ["02-05", "02-06", "02-07", "phase-11-cross-machine-resume"]

# Actuals (#2632)
actuals:
  tokens: 7000
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "one Session per thread for a concurrency proof: a shared Session is not thread-safe and proves nothing about two processes anyway; 16 threads rendezvous on a threading.Barrier to maximise claim overlap"
    - "process-level single-owner proof: two genuinely separate OS processes sharing only PostgreSQL, synchronised on an observable committed database condition (status == BA AND owner_token IS NOT NULL) via the wait_for polling helper — never a fixed sleep"
    - "invariant assertions over winner assertions: a tight race may see either child win, so the tests assert 'exactly one role-execution row / one ROLE_COMPLETED event / neither exited non-zero', never which process won"
    - "field-by-field snapshot equality for the permissive-failure direction: the not-stolen-before-expiry half snapshots status + owner_token + lock_expires_at + latest role-execution row + full event trail and asserts each unchanged after the early resume attempt"
    - "forced expiry (server-clock UPDATE) as the fast primary path + one genuine short-TTL real-wait reclaim as the honesty check that the database clock — not the forcing UPDATE — drives expiry"
    - "structural absence test: grep the source tree for reaper / sweeper / APScheduler / BackgroundScheduler / crontab / pg_cron / cron and assert none — lazy evaluation on the next claim is the entire expiry mechanism"

key-files:
  created:
    - "tests/db/test_lease_claim_atomic.py"
    - "tests/integration/test_single_owner_race.py"
    - "tests/integration/test_lease_expiry_reclaim.py"
  modified: []

key-decisions:
  - "No production code changed. Plan 02-04 is proof-only for the lease mechanism 02-03 shipped; every assertion runs against the real claim_lease / apply_transition / CLI."
  - "The slow-step window in test_single_owner_race.py is 15000ms (plan prose suggested ~4s). Against the operator's remote Neon endpoint a cold-starting losing child needs longer to spin up a fresh interpreter, open its connections and reach claim_lease while the lease is genuinely held; 15s is a generous upper bound on the loser's time-to-claim, not a timing assertion — the winner is synchronised on an observable DB condition. Committed in 3e46670."
  - "test_lease_expiry_reclaim.py uses no process-clock time-travel library (time_machine / freezegun) anywhere: lock_expires_at and every comparison against it are evaluated inside PostgreSQL, so time-travelling the test process would move nothing (02-RESEARCH Pitfall 4). Enforced by acceptance grep — count is 0."

patterns-established:
  - "16-thread barrier-synchronised concurrent claim as the statement-level mutual-exclusion proof"
  - "two-real-process race synchronised on a committed DB condition through wait_for, asserting invariants not winners"
  - "killed-owner reclaim proven twice — forced server-clock expiry (fast) and a real elapsed short TTL (honest)"
  - "structural no-reaper assertion: expiry is lazy on the next claim, nothing else"

requirements-completed: [HITL-07]

coverage:
  - id: D1
    description: "HITL-07 at the statement level — N concurrent claims against one run yield exactly one token; an expired lease is reclaimable by exactly one new owner; a terminal run is claimable by nobody; renew/release are token-fenced"
    requirement: "HITL-07"
    verification:
      - kind: db
        ref: "tests/db/test_lease_claim_atomic.py (5 tests: sixteen_concurrent_claims..., forced_expired..._exactly_one_new_owner, terminal_run..._nobody, renewal_moves..._only_owning_token, release_clears..._only_owning_token)"
        status: pass
    human_judgment: false
  - id: D2
    description: "SC3 — two real OS processes race the same run: exactly one executes the step, the other exits 0 with no status change, no writes, no duplicate ROLE_COMPLETED and no duplicate role-execution row; holds for a deterministic loser and for a tight race from creation"
    requirement: "HITL-07"
    verification:
      - kind: integration
        ref: "tests/integration/test_single_owner_race.py::test_two_processes_race_one_advances_the_other_exits_zero_without_writing"
        status: pass
      - kind: integration
        ref: "tests/integration/test_single_owner_race.py::test_a_tight_race_from_creation_still_yields_one_execution"
        status: pass
    human_judgment: false
  - id: D3
    description: "SC4 — a killed owner's lease is not stolen before its DB-clock expiry (snapshot unchanged field-by-field after an early resume) and is reclaimed after it, on the same attempt with no second run; proven by both a forced server-clock expiry and a genuine short-TTL elapsed wait; no reaper/scheduler/sweeper exists"
    verification:
      - kind: integration
        ref: "tests/integration/test_lease_expiry_reclaim.py::test_a_killed_owner_is_not_stolen_before_expiry_then_reclaimed_after_forcing"
        status: pass
      - kind: integration
        ref: "tests/integration/test_lease_expiry_reclaim.py::test_the_reclaim_also_works_after_a_genuinely_elapsed_short_ttl_no_forcing"
        status: pass
      - kind: integration
        ref: "tests/integration/test_lease_expiry_reclaim.py::test_expiry_is_lazy_there_is_no_reaper_scheduler_or_sweeper"
        status: pass
    human_judgment: false

# Metrics
duration: close-out (prior task commits pre-existed from a rate-limit interruption)
completed: 2026-09-10
status: complete
plan_head_before: bf81032515ab32ada1fde2ae99fe323725469799
---

# Phase 2 Plan 4: Single-Owner Race & Killed-Owner Expiry Reclaim Summary

**HITL-07, SC3 and SC4 proven adversarially — 16 concurrent claims yield exactly one token, two real processes racing one run yield exactly one execution and one clean exit-0 loser, and a killed owner's lease is untouchable until its Postgres-clock expiry then reclaimed on the same attempt.**

## Performance

- **Duration:** Close-out session (both task commits `3e46670` and `dc18ef4` pre-existed — a prior executor was interrupted by a rate limit after committing both proofs but before writing this SUMMARY or updating tracking).
- **Task commits dated:** 2026-09-09
- **Close-out completed:** 2026-09-10
- **Tasks:** 2 of 2
- **Files created:** 3 (all test files; no production change)

## Accomplishments

- **HITL-07 at the statement level** (`tests/db/test_lease_claim_atomic.py`, 5 tests): sixteen threads each with their own `Session`, barrier-synchronised, calling the real `claim_lease` against one unowned run → exactly one token, and the run's stored `owner_token` equals it. A `force_lease_expiry`-aged run: exactly one token again, and a *different* token from round one. A run driven to a terminal status: zero tokens, both lease columns still `NULL`. Renewal and release move/clear the lease only for the owning token; a never-issued token leaves the row byte-identical.
- **SC3** (`tests/integration/test_single_owner_race.py`, 2 tests): two real OS processes sharing only PostgreSQL. Deterministic-loser scenario — the winner runs a 15s slow step, the test polls the DB via `wait_for` until `status == BA AND owner_token IS NOT NULL`, then spawns the loser which prints `is owned by another process` on stderr (no traceback) and exits 0; afterwards exactly one `BA` role-execution row at attempt 1, exactly one `ROLE_COMPLETED` event, run count unchanged. Tight-race scenario — both children spawned back-to-back against a fresh run, assertions on the invariants only (never on which won).
- **SC4** (`tests/integration/test_lease_expiry_reclaim.py`, 3 tests): a process killed the instant `CREATED → BA` commits (via `DARK_FACTORY_CRASH_AFTER`) leaves `owner_token` non-null and `lock_expires_at` in the server future. A second process resuming *before* that expiry gets nothing, exits 0, and leaves status / owner token / latest role-execution row / full event trail unchanged — asserted field by field. After `force_lease_expiry`, a third process reclaims the run, continues from the last committed step on the *same* attempt, reaches `COMPLETED` (lease cleared), and the audit trail has exactly one `ROLE_STARTED`. Honesty test: the same reclaim after a genuine 2s injected TTL and a real elapsed wait, no forcing update. Structural test: the source tree contains no reaper / sweeper / scheduler / cron construct.

## Task Commits

Each task was committed atomically by the prior executor:

1. **Task 1: SC3 — exactly one owner, at the statement level and across two real processes** — `3e46670` (test)
2. **Task 2: SC4 — a killed owner's lease is not stolen before its expiry, and is reclaimed after it** — `dc18ef4` (test)

**Plan metadata:** `docs(02-04): complete single-owner race + expiry-reclaim plan`

## Files Created/Modified

- `tests/db/test_lease_claim_atomic.py` (created, 271 lines) — HITL-07 statement-level mutual-exclusion proof: 16-thread concurrent claim, forced-expiry single-reclaim, terminal-run un-claimable, renew/release token fencing.
- `tests/integration/test_single_owner_race.py` (created, 208 lines) — SC3: deterministic-loser two-process race + tight race from creation.
- `tests/integration/test_lease_expiry_reclaim.py` (created, 273 lines) — SC4: not-stolen-before-expiry (field-by-field snapshot), reclaimed-after (forced + honest real-wait), structural no-reaper assertion.

## Confirmation the two prior commits satisfy their acceptance criteria

Both commits were reviewed (`git show 3e46670`, `git show dc18ef4`) against Task 1 and Task 2 `<acceptance_criteria>` and `<done>`, and the disk files match the commits exactly (no working-tree drift):

| Acceptance criterion | Where satisfied | Status |
|---|---|---|
| ≥16 threads, each its own session, exactly one token | `test_lease_claim_atomic.py` `_THREADS = 16`, `_claim_from_n_threads` (one `factory()` per thread) | met |
| concurrent claim on a terminal run → zero tokens, both lease columns null | `test_a_terminal_run_is_claimable_by_nobody_even_while_unowned` | met |
| renewal with a non-owning token → false, changes nothing | `test_renewal_moves_the_lease_only_for_the_owning_token` (asserts row tuple equality) | met |
| first child via non-blocking spawn, wait on an observable DB condition before starting the second | `popen(...)` + `wait_for(_role_held(engine, run_id))` where `_role_held` = `status == "BA" and owner_token is not None` | met |
| both children exit 0 | asserted in both race scenarios | met |
| exactly one `ROLE_COMPLETED` event after the race | `_role_completed_events(...)` length 1 in both scenarios | met |
| loser stderr carries the CLI owned-by-another-process wording, no traceback | `assert "is owned by another process" in loser.stderr`; `"Traceback" not in ...` both sides | met |
| no bare fixed-duration sleep as a synchronisation primitive in the race file | confirmed — `grep 'sleep' tests/integration/test_single_owner_race.py` → none | met |
| killed owner leaves non-null owner token + `lock_expires_at` later than a separately selected server timestamp | `test_a_killed_owner_is_not_stolen_before_expiry_...` (`select(func.now())` comparison) | met |
| second process before expiry exits 0, leaves status / owner token / latest role-execution row / event count unchanged | same test — field-by-field snapshot equality | met |
| third process after forced expiry exits 0, drives to terminal on the same attempt | same test — `execs[0].attempt == snap_re[2]`, status `COMPLETED` | met |
| total `runs` count unchanged across the whole test | `_count_runs(engine) == runs_at_start + 1` (one run created by the test itself) | met |
| a reclaim test after a genuinely short TTL and a real wait, no forcing update | `test_the_reclaim_also_works_after_a_genuinely_elapsed_short_ttl_no_forcing` (`time.sleep(_SHORT_TTL + 2)`, plain `resume`) | met |
| module docstring states why the process-clock time-travel library is not used | present — 02-RESEARCH Pitfall 4 paragraph | met |
| `grep -v '^#' ... \| grep -c 'time_machine\|freezegun'` → 0 | confirmed — count is 0 | met |

No gaps were found in the two prior commits. No `test(02-04)` / `fix(02-04)` remediation commit was needed.

## Verification results

All commands run against `/Users/maryiakrauchanka/portfolio/dark-factory` with `.env` sourced for the DB-backed tiers (via a wrapper script so no secret value entered the session).

| Check | Result |
|---|---|
| 1. `pytest -m db -q` (whole DB tier) | **82 passed**, 238 deselected, exit 0 (603.86s against the shared remote Neon endpoint) |
| 2. `pytest -m integration -q` (whole integration tier) | **41 passed**, 279 deselected, exit 0 (599.23s) |
| 3. `ruff check .` | **All checks passed**, exit 0 |
| 4. Race-proof flakiness smoke — `test_single_owner_race.py` + `test_lease_expiry_reclaim.py` 3× back-to-back | Run 1: **5 passed** in 149.28s · Run 2: **5 passed** in 150.63s · Run 3: **5 passed** in 154.59s · a 4th confirmation run: **5 passed** in 150.58s. **Zero flakiness across 4 consecutive runs; no non-determinism, no winner-pinning failure, no timeout.** |

### Observed per-file / per-test timings (against remote Neon)

| File | Test | call time |
|---|---|---|
| `test_single_owner_race.py` | `test_two_processes_race_one_advances_the_other_exits_zero_without_writing` | 36.94s (+3.34s setup) |
| `test_single_owner_race.py` | `test_a_tight_race_from_creation_still_yields_one_execution` | 24.56s |
| `test_lease_expiry_reclaim.py` | `test_a_killed_owner_is_not_stolen_before_expiry_then_reclaimed_after_forcing` | 48.59s |
| `test_lease_expiry_reclaim.py` | `test_the_reclaim_also_works_after_a_genuinely_elapsed_short_ttl_no_forcing` | 37.03s |
| `test_lease_expiry_reclaim.py` | `test_expiry_is_lazy_there_is_no_reaper_scheduler_or_sweeper` | 0.03s |

Both files together run in a stable **~150s** (4 measurements: 149.28 / 150.63 / 154.59 / 150.58).

### Synchronisation condition the race test waits on

`test_single_owner_race.py` never sleeps to synchronise. Before spawning the losing child it calls
`wait_for(_role_held(engine, run_id), timeout=20)`, where `_role_held` polls a fresh `Session` for
the committed condition **`run.status.value == "BA" and run.owner_token is not None`** — i.e. "the
first child has genuinely entered the role and is holding the lease inside the worker call". The 15s
slow step is only a generous upper bound on the loser's cold-start time-to-claim, not a timing
assertion.

## Decisions Made

See `key-decisions` in the frontmatter. In short: no production code changed; the slow-step window
is 15s (not the plan's ~4s) to accommodate remote-Neon child cold-start; no process-clock
time-travel library is used against a database-clock property.

## Deviations from Plan

Plan execution itself introduced **no code deviations** — both task commits pre-existed and were
confirmed correct. Two items are recorded for completeness:

### 1. [Rule 1 - environmental, pre-existing in commit `3e46670`] Slow-step window widened 4s → 15s

- **Found during:** review of the prior executor's `3e46670`.
- **Issue:** the plan prose suggested a fake-sleep of "the order of four seconds" so the losing
  child reliably reaches its claim while the lease is held. Against the operator's *remote* Neon
  endpoint a freshly-spawned `uv run` child needs longer than 4s to start a new interpreter, open
  its connections and reach `claim_lease`.
- **Resolution:** the prior executor set `_SLOW_STEP_MS = 15000`. This is sound — the winner is
  synchronised on an observable DB condition (`wait_for`), not on the sleep; the sleep is only an
  upper bound on the loser's startup. Left as-is.
- **Verification:** 4 consecutive green runs of the file, deterministic loser every time.

### 2. [Documented timing miss — test left intact] `test_lease_expiry_reclaim.py` exceeds the "under 60 seconds" acceptance sub-criterion

- **Found during:** verification step 4 (`--durations`).
- **Issue:** Task 2 `<acceptance_criteria>` states the file should pass "in under 60 seconds". Its
  slowest single test is 48.59s and the file's total call time is ~86s, against the shared *remote*
  Neon endpoint. The overage is entirely network round-trip latency plus repeated subprocess
  cold-starts (`run` + up to three `resume` children per test) — not a design flaw. The injected
  TTLs are exactly as specified (`_LONG_TTL = 3600`, `_SHORT_TTL = 2`) and the only real wait is
  `_SHORT_TTL + 2 = 4s`.
- **Decision:** NOT fixed. The only ways under 60s on this endpoint would be to drop the real-process
  coverage or the honesty real-wait test — both would gut the proof. The criterion's intent ("stays
  fast, no real minutes") is met: ~86s not ~10min, no multi-minute sleeps. A local Postgres 17
  (`initdb` / Docker rung) would bring this well under 60s; the operator runs against remote Neon by
  choice.
- **Impact:** none on correctness. Flagged here and carried for `/gsd-verify-work`.

---

**Total deviations:** 0 code changes in this close-out. 1 pre-existing environmental adjustment in
`3e46670` (confirmed sound), 1 documented acceptance-criterion timing miss (test intentionally left
intact). No scope creep.

## Issues Encountered

- **DB + integration tiers are slow against the shared remote Neon endpoint** — 603s and 599s
  respectively. This matches the 02-03 SUMMARY's note ("full suite ~16.5 min against the shared Neon
  endpoint"). Not specific to this plan; all tiers exit 0.
- **An uncommitted `.planning/WINDOWS.md` change was on disk at close-out** — broken-windows ledger
  entry #3 (02-03's `test_fresh_process_resume.py` forced-expiry deviation), recorded
  2026-09-09T18:00 by the 02-03 executor but never committed (its metadata commit `bf81032` predates
  the ledger write). Included in this plan's metadata commit so it is not left dangling. Not
  introduced by 02-04.

## Known Stubs

None. All three files are real end-to-end proofs — real `claim_lease` / `renew_lease` /
`release_lease` against real rows, real `apply_transition`, real CLI subprocesses, real
`force_lease_expiry` server-clock UPDATE, and a real elapsed wait for the honesty check.

## Requirements status (shared-ID gate)

The plan's `requirements: [HITL-07]` remains **Pending** in `REQUIREMENTS.md`. HITL-07 is also
declared by 02-01, 02-02, 02-03, 02-05 and 02-07; 02-05 (SC5 heartbeat / no-transaction-across-the-
worker / lease-lost abort) and 02-07 (phase acceptance gate) have no `*-SUMMARY.md` yet, so the
shared-ID gate keeps HITL-07 Pending until the last declaring plan finishes. This plan ships and
proves the adversarial half of HITL-07 (statement-level 16-thread mutual exclusion + two-real-process
race); 02-07 marks the ID Complete.

## Next Phase Readiness

- **02-05** (heartbeat + no-txn + lease-lost abort): `force_lease_expiry`, `use_lease_settings`, the
  two-real-process harness and `DARK_FACTORY_FAKE_SLEEP_MS` are all now proven usable against the
  lease under adversarial conditions. The `run_lease` daemon heartbeat renews on its own session.
- **02-07** (phase acceptance gate): SC3 → `tests/integration/test_single_owner_race.py`,
  SC4 → `tests/integration/test_lease_expiry_reclaim.py`, HITL-07 (statement level) →
  `tests/db/test_lease_claim_atomic.py`. Marker strings recorded: `is owned by another process`
  (stderr), `BA → COMPLETED` (stdout transition line).

---
*Phase: 02-pause-resume-single-owner-execution*
*Completed: 2026-09-10*

## Self-Check: PASSED

- All created files present on disk: `tests/db/test_lease_claim_atomic.py`, `tests/integration/test_single_owner_race.py`, `tests/integration/test_lease_expiry_reclaim.py`, `.planning/phases/02-pause-resume-single-owner-execution/02-04-SUMMARY.md`.
- Both task commits present in history: `3e46670` (Task 1, `test(02-04): SC3 + HITL-07 mutual-exclusion proofs`), `dc18ef4` (Task 2, `test(02-04): SC4 lease not-stolen-before-expiry / reclaimed-after proofs`).
- Full `<verification>` re-run green: db tier 82 passed / integration tier 41 passed / `ruff check .` clean / 3× (in fact 4×) race-proof smoke all 5 passed with zero flakiness.
