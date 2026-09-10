---
phase: 02-pause-resume-single-owner-execution
verified: 2026-09-10T00:00:00Z
status: human_needed
score: 5/5 must-haves verified (+ 4 invariants, 6 requirements)
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-01-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-01-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-02-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-02-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-03-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-03-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-04-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-04-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-05-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-05-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-06-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-06-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-07-PLAN.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-07-SUMMARY.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-REVIEW.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-REVIEW-FIX.md"
  - ".planning/phases/02-pause-resume-single-owner-execution/02-UAT.md"
  - "migrations/env.py"
  - "migrations/versions/0003_pause_resume_lease.py"
  - "src/dark_factory/cli.py"
  - "src/dark_factory/config/settings.py"
  - "src/dark_factory/domain/interaction.py"
  - "src/dark_factory/domain/status.py"
  - "src/dark_factory/events/catalog.py"
  - "src/dark_factory/orchestrator/answers.py"
  - "src/dark_factory/orchestrator/lease.py"
  - "src/dark_factory/orchestrator/lifecycle.py"
  - "src/dark_factory/orchestrator/runner.py"
  - "src/dark_factory/persistence/engine.py"
  - "src/dark_factory/persistence/models.py"
  - "src/dark_factory/persistence/mutations.py"
  - "src/dark_factory/persistence/repositories.py"
  - "src/dark_factory/workers/fake.py"
  - "tests/integration/test_phase2_acceptance.py"
covered_digest: "v1:sha256:6d7a1d83d8f719249cb9a70426ff25ebee122fa43cbcbc34d10b744d1d55c94a"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  gaps_closed:
    - "WR-01 — heartbeat now distinguishes a transient renewal exception (bounded retry via consecutive_errors) from an authoritative loss (renew_lease matched no row); fix present at lease.py:231-263, re-inspected, does not regress SC5."
    - "WR-02 — lease.py module docstring now states the guarantee is 'no concurrent durable mutation', not 'no concurrent execution' (lease.py:35-49)."
    - "WR-03 — LookupError and ValueError added to cli._ORCHESTRATION_ERRORS (cli.py:81-82); bare mutation-path errors now route to clean exit 2 per the D-05 contract."
    - "Prior human item 1 (fresh-eyes README pause/resume walkthrough vs real Neon) — completed, PASS in 02-UAT.md (commit a8beb21)."
    - "Prior human item 2 (production-scale lease timing 900s/300s vs real Neon PgBouncer) — completed, PASS in 02-UAT.md: pre-expiry claim declined, post-expiry claim succeeded, lock_expires_at advanced during a slow step."
    - "Prior human item 3 (accept the 900s/300s defaults / ~15-min dead-owner reclaim ceiling) — completed, PASS in 02-UAT.md: operator accepts."
    - "Prior human item 4 (accept PostgreSQL 18.6 vs postgres:17-alpine env deviation) — completed, PASS in 02-UAT.md: operator accepts the deviation carried since 01-01."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Re-run the DB/integration lease proof tiers against a real PostgreSQL — specifically tests/integration/test_heartbeat_slow_step.py, tests/integration/test_lease_expiry_reclaim.py, and tests/db/test_lease_lost_aborts_step.py — after the WR-01 heartbeat change (commit e9a231a)."
    expected: "All three pass. In particular: a transient renewal error does not immediately abort an in-flight step (the consecutive_errors retry keeps the step alive for up to one heartbeat interval), while a genuine lease loss (renew_lease matches no row) still sets lease_lost immediately and the owner still aborts before its commit; and the retry window does not let an owner outlive its own lock_expires_at such that a competitor false-steals. No PostgreSQL of any version was reachable in this verification environment, and the last recorded green DB run (02-07: 364 passed) predates commit e9a231a."
    why_human: "The WR-01 fix adds new heartbeat control flow (a consecutive_errors threshold governing transient-vs-authoritative loss and its interaction with lease_ttl_seconds reclaim timing). No executed test in this session exercises the transient-exception branch — the existing DB heartbeat proofs cover only the happy renewal path and the authoritative-loss path, both unchanged by the fix — and the code-fixer's own report (02-REVIEW-FIX.md) explicitly recommends a real-PostgreSQL run of these tiers 'before the phase proceeds'. Static analysis shows the change cannot cause a false steal or a hostage heartbeat, so SC5 as written holds; this check confirms the new branch's timing behaviour against a database rather than by inspection alone."
---

# Phase 2: Pause, Resume & Single-Owner Execution — Verification Report

**Phase Goal:** A run can stop mid-role to ask a human a question, release its process safely, and later be resumed by exactly one process — even after the original process died.
**Verified:** 2026-09-10
**Status:** human_needed
**Re-verification:** Yes — after three code-review fix commits (e9a231a, 3617bb3, 19f4ccb) landed on `lease.py` / `cli.py`, and after 02-UAT.md (commit a8beb21) resolved all four human items from the prior report.

## Re-verification scope and constraints

The prior 02-VERIFICATION.md verdict (`human_needed`, 5/5) rested on static
inspection + the acceptance gate + `unit`/`contract` + `mypy`/`ruff` + executor-recorded
`db`/`integration` runs, and carried four outstanding human confirmations. Since
then:

1. **02-UAT.md (commit a8beb21) closed all four prior human items — 4 passed, 0
   issues.** The operator ran the README walkthrough verbatim against a real Neon
   endpoint, confirmed production-scale lease timing against a real Neon PgBouncer
   endpoint (pre-expiry claim declined, post-expiry claim succeeded,
   `lock_expires_at` advanced during a slow step), accepted the 900 s / 300 s
   defaults and the ~15-minute dead-owner reclaim ceiling, and accepted the
   PostgreSQL 18.6 vs `postgres:17-alpine` deviation carried since 01-01. These
   are recorded as `gaps_closed` and are **not** re-listed as open below.

2. **The three code-review Warnings (WR-01/02/03) are all fixed** and were
   re-inspected in the current tree:
   - **WR-01** (`lease.py:231-263`): `_heartbeat` now increments a
     `consecutive_errors` counter on a raised `renew_lease` exception, logs
     `lease.renew_error` with the attempt number, and `continue`s; it surrenders
     the lease on a transient error only once
     `consecutive_errors * interval >= ttl - interval`. A renewal that *executes
     and matches no row* still sets `lease_lost` and returns immediately —
     unchanged. `finally: hb_session.close()` still runs on every path including
     `continue`. The stop path (`while not stop.wait(interval)` + `stop.set()` in
     `__exit__`) is untouched, so the "heartbeat never outlives its owner"
     prohibition still holds.
   - **WR-02** (`lease.py:35-49`): new module-docstring paragraph "What the lease
     guarantees — and what it does not", stating the guarantee is *no concurrent
     durable mutation*, not *no concurrent execution*, and naming the two Phase-7
     mitigations. Docstring-only; zero behavioural change.
   - **WR-03** (`cli.py:81-82`): `LookupError` and `ValueError` added to
     `_ORCHESTRATION_ERRORS` with an explanatory comment. `apply_transition` and
     its helpers raise bare `LookupError` (missing `runs` row at lock time,
     missing `role_executions` row, no WAITING interaction in answer mode) and
     bare `ValueError` (`RoleExecutionWrite` / `HumanInteractionWrite` guards);
     these now route through `_report_orchestration_error` → exit 2 instead of an
     unhandled traceback → Typer exit 1. The earlier `except ValueError` for
     `UUID(run_id)` parsing in `resume` / `status` is a separate, earlier catch
     and is unaffected.

3. **Re-run here:** `uv run pytest -q -m unit` → **193 passed**, 171 deselected
   (0.42 s); `uv run mypy src/dark_factory` → clean (39 files); `uv run ruff
   check src/dark_factory` → clean. Matches 02-REVIEW-FIX.md's recorded gates.

4. **Still not runnable here:** the `db` / `integration` tiers (164 tests) — no
   PostgreSQL of any version is reachable (no Docker, no local `initdb`,
   `DARK_FACTORY_TEST_DATABASE_URL` unset). The last recorded green DB run
   (02-07: 364 passed, 0 skipped) **predates** commit e9a231a, so the WR-01
   heartbeat change has not been exercised against a database. This is the sole
   reason the phase remains `human_needed` — see Human Verification Required.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC1 | A role returning `NEEDS_INPUT` leaves the run `WAITING_HUMAN` with the question, the worker result, the worker session id and the current role persisted; the process exits 0 holding no open DB transaction. | ✓ VERIFIED | `runner._run_current_role` `Signal.ROLE_NEEDS_INPUT` arm (runner.py:389-431): one `apply_transition` carrying `re_status`/`re_result` (serialised NEEDS_INPUT), `worker_session_id`, retained `current_role`, `human_interaction=HumanInteractionWrite(mode="ask")`, `expected_owner_token=lease.token`; `lifecycle` retains the role; `apply_transition` clears both lease columns because `WAITING_HUMAN ∈ STOP_STATUSES` (mutations.py:281-283). `cli._drive_and_exit` exits 0 for `final ∈ _CLEAN_FINALS = (COMPLETED, WAITING_HUMAN)`. Proof file `tests/integration/test_pause_exit_zero.py` present + non-empty; acceptance gate maps SC1 to it; executor-recorded green; operator UAT item 1 exercised pause→`WAITING_HUMAN` exit 0 against real Neon. Unchanged by the three fix commits. |
| SC2 | `dark-factory resume <run-id> --answer "..."` from a brand-new process continues the same role execution and attempt — never creates a new run and needs nothing from the original process. | ✓ VERIFIED | `cli.resume` → `submit_answer` (answers.py: one `apply_transition`, `expected_status=WAITING_HUMAN`, same role-execution row `id=latest.id` marked `RESUMING`, interaction `mode="answer"`) → `_drive_and_exit` → `_run_current_role` reads `latest.status == _ROLE_RESUMING` (runner.py:338) and calls `worker.resume(context, previous, state.pending_answer)`. No `create_run`/`start_run` on this path. Proof file `tests/integration/test_resume_with_answer.py` present; acceptance gate maps SC2 to it; executor-recorded green; operator UAT item 1 resumed from a second shell to `COMPLETED` exit 0. Unchanged by the fix commits. |
| SC3 | Two processes racing `advance` on the same run: one executes, the other exits cleanly without changing status and without duplicating work. | ✓ VERIFIED | `run_lease` claims via one conditional `UPDATE runs ... WHERE (owner_token IS NULL OR lock_expires_at < now()) AND status NOT IN terminal ... RETURNING id` (lease.py:119-145); loser gets `None` → `LeaseNotAcquired` → `cli._report_lease_not_acquired` prints to stderr and **exits 0** having written nothing; winner's every `apply_transition` is fenced by `expected_owner_token`. Proof files `tests/integration/test_single_owner_race.py` + `tests/db/test_lease_claim_atomic.py` present; acceptance gate maps SC3; executor-recorded green (4× flake-smoke clean). Claim path untouched by the fix commits. |
| SC4 | A process killed while owning a run loses its lease by database-clock expiry, and the next process claims the run and continues from the last committed step. | ✓ VERIFIED | Killed owner leaves `owner_token` + a future `lock_expires_at`; `claim_lease` predicate rejects the second process before `func.now()` passes `lock_expires_at` (`LeaseNotAcquired` → exit 0, no steal); after the DB clock passes it the claim succeeds and `_advance_once` reconstructs wholly from Neon (`load_run_state`) on the same attempt. Expiry is lazy — no reaper (structural grep). Proof file `tests/integration/test_lease_expiry_reclaim.py` present; acceptance gate maps SC4; executor-recorded green; operator UAT item 2 confirmed pre-expiry decline + post-expiry reclaim at production scale against real Neon. See Human Verification — this file should be re-run post-WR-01. |
| SC5 | A role step that runs longer than the lease TTL is not falsely stolen — the owner heartbeats the lease while the step is in flight. | ✓ VERIFIED | `run_lease` starts a daemon heartbeat that calls `renew_lease` every `interval` on its **own** session, pushing `lock_expires_at = func.now() + ttl`; a competing `claim_lease` keeps matching zero rows. `__exit__` always `stop.set()` → `join` → best-effort `release_lease` on every exit path. WR-01 changed only the *failure* handling (transient exception → bounded retry; authoritative "matched no row" → immediate `lease_lost` as before); it does not touch the successful-renewal path and cannot extend the lease or cause a false steal. Proof files `tests/integration/test_heartbeat_slow_step.py` + `tests/db/test_lease_lost_aborts_step.py` present; acceptance gate maps SC5; executor-recorded green (3× flake-smoke) — **but recorded before commit e9a231a**; operator UAT item 2 observed `lock_expires_at` advancing during a slow step against real Neon. See Human Verification. |

**Score:** 5/5 success criteria verified (static inspection of the post-fix tree + acceptance gate + executor-recorded runs + independent code review + operator UAT against real Neon). The `db`/`integration` proofs for SC4/SC5 were not re-executed here after the WR-01 change — see Human Verification Required.

### Phase Invariants

| Invariant | Status | Evidence |
| --------- | ------ | -------- |
| No DB transaction held across a worker call | ✓ VERIFIED | `_advance_once` opens a read session, calls `load_run_state`, closes it in `finally`; `_run_current_role` runs `worker.execute`/`worker.resume` with no session open; the write session is opened only for the `apply_transition` commit. Heartbeat renews in a sub-second `with session.begin()` per beat on its own session (`renew_lease`, lease.py:148-163). WR-01 did not change the transaction shape of a beat. `test_no_txn_across_worker.py` present; executor-recorded green; 02-REVIEW.md confirms in code. |
| Claim-don't-check concurrency (conditional `UPDATE` lease + guarded status update) | ✓ VERIFIED | `claim_lease` is exactly one `sa.update(Run).where(id, status NOT IN terminal, owner_token IS NULL OR lock_expires_at < func.now()).values(...).returning(Run.id)`. `apply_transition` uses `session.get(Run, run_id, with_for_update=True)` + `expected_status` guard + `expected_owner_token` fence (mutations.py:259-268). `grep` of `lease.py` for `pg_advisory` / `SKIP LOCKED` / `skip_locked` → 0. |
| All expiry checks use the database clock, never a process clock | ✓ VERIFIED | Every expiry value in `lease.py` is `func.now() + timedelta(seconds=ttl)`; every comparison is `lock_expires_at < func.now()`. `grep` of `lease.py` for `datetime.now` / `datetime.utcnow` → 0. The only `threading.Event.wait` use is the heartbeat's inter-renewal delay (a duration, not a timestamp) — WR-01 kept it a delay. |
| Infrastructure credentials never reach `human_interactions.question`/`.answer` or any worker/event/log | ✓ VERIFIED (recorded) | `mutations._write_human_interaction` applies `redact(spec.question, ...)` / `redact(spec.answer, ...)` at the single mutation-path call site (mutations.py:375, 393); `HumanInteractionWrite` carries raw text by contract. `tests/unit/test_single_mutation_path.py` `_LIFECYCLE_CTORS` includes `HumanInteraction` (re-run here: passes). `tests/integration/test_redaction_interactions.py` sweeps every interaction column + event payload + `role_executions.result` + a real structlog sink (executor-recorded green). |

## Requirements Coverage

Union of `requirements:` across all 7 PLAN frontmatters = `{STATE-04, HITL-01,
HITL-02, HITL-03, HITL-07, HITL-08}` — **exactly** the six phase requirement ids
in ROADMAP.md. No orphans, no extras.

| Requirement | Source Plans | Status | Evidence |
| ----------- | ------------ | ------ | -------- |
| STATE-04 | 02-01, 02-02, 02-06, 02-07 | ✓ SATISFIED | `human_interactions` table (id, run_id, role_execution_id, question, answer, status, created_at, answered_at); `status` VARCHAR(16) + named CHECK `interaction_status` carrying exactly `WAITING`/`ANSWERED`/`CANCELLED`; partial unique index `uq_one_waiting_interaction_per_run`; both FKs. Migration `0003_pause_resume_lease` reversible. Proof `tests/db/test_human_interactions_schema.py` present. REQUIREMENTS.md line 76 `[x]` / line 232 Complete. |
| HITL-01 | 02-03, 02-06, 02-07 | ✓ SATISFIED | The only pause mechanism is a `NEEDS_INPUT` worker result; `_run_current_role` branches on `signal_from_result(result)` (runner.py:354, 389), never a role name. Proof `tests/db/test_pause_mechanism_generic.py` (two-node pipeline, both nodes pause through structurally identical code) present. REQUIREMENTS.md line 84 `[x]` / line 237 Complete. |
| HITL-02 | 02-02, 02-03, 02-06, 02-07 | ✓ SATISFIED | On `NEEDS_INPUT`: result + worker session id + `current_role` + interaction row + `QUESTION_CREATED`/`RUN_PAUSED` all in one `apply_transition` transaction; lease cleared atomically; process exits 0. Proofs `tests/integration/test_pause_exit_zero.py` + `tests/db/test_pause_path_atomic.py` present. REQUIREMENTS.md line 85 `[x]` / line 238 Complete. |
| HITL-03 | 02-02, 02-03, 02-07 | ✓ SATISFIED | `dark-factory resume <run-id> --answer "..."` from a brand-new process; decision driven entirely by persisted columns (`RESUMING` marker, `pending_answer`). Proof `tests/integration/test_resume_with_answer.py` present. WR-03 tightened the exit-code contract on this path (bare `LookupError`/`ValueError` → exit 2). REQUIREMENTS.md line 86 `[x]` / line 239 Complete. |
| HITL-07 | 02-01, 02-02, 02-03, 02-04, 02-05, 02-07 | ✓ SATISFIED | Single-owner via conditional `UPDATE` lease + `with_for_update` + `expected_owner_token` fence; no distributed-lock service. Proofs `tests/integration/test_single_owner_race.py` + `tests/db/test_lease_claim_atomic.py` + `tests/integration/test_lease_expiry_reclaim.py` + `tests/db/test_lease_lost_aborts_step.py` present. WR-02 records in the module docstring that the guarantee is "no concurrent durable mutation", not "no concurrent execution" (a stalled owner past TTL — benign for `FakeWorker`, Phase-7 mitigation named). REQUIREMENTS.md line 90 `[x]` / line 243 Complete. |
| HITL-08 | 02-01, 02-02, 02-03, 02-05, 02-07 | ✓ SATISFIED | No transaction spans the worker call; ownership is a column with DB-clock expiry renewed by a thread on its own session. Proofs `tests/integration/test_no_txn_across_worker.py` + `test_heartbeat_slow_step.py` present. REQUIREMENTS.md line 91 `[x]` / line 244 Complete. |

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/dark_factory/orchestrator/lease.py` | claim-don't-check lease + `run_lease` context manager + heartbeat | ✓ VERIFIED | 283 lines. `claim_lease` / `renew_lease` / `release_lease` (one guarded `UPDATE...RETURNING` each), `run_lease` contextmanager, `LeaseHandle`, `LeaseNotAcquired`. Imported by `runner.py` and `answers.py`. All three invariant greps → 0. WR-01 heartbeat retry + WR-02 docstring present and re-inspected. |
| `src/dark_factory/orchestrator/answers.py` | `submit_answer` — one guarded transition out of `WAITING_HUMAN` | ✓ VERIFIED | Precheck (`RunNotFoundError` / `NotWaitingForHuman` / `NoPendingInteraction`) then one `apply_transition` inside `run_lease`; constructs no ORM row. Imported by `cli.py`. |
| `src/dark_factory/orchestrator/lifecycle.py` | `ROLE_NEEDS_INPUT → WAITING_HUMAN` arm, role retained; `WAITING_HUMAN` illegal to leave | ✓ VERIFIED | Pure function; imports nothing from `dark_factory.persistence`. Unchanged by the fix commits. |
| `src/dark_factory/orchestrator/runner.py` | lease-wrapped `advance`/`drive`, stop-set early return, execute-vs-resume dispatch, needs-input branch, lease-loss abort | ✓ VERIFIED | `advance`/`drive` early-return on the whole `STOP_STATUSES` set without claiming (runner.py:219, 468); `_advance_once` assumes lease held; `_run_current_role` reads persisted `_ROLE_RESUMING` marker (line 338), checks `lease.lease_lost.is_set()` after the worker call (line 348) → `raise LeaseLost`, pauses on `Signal.ROLE_NEEDS_INPUT`. Every `apply_transition` passes `expected_owner_token=lease.token` (lines 299, 431). Unchanged by the fix commits. |
| `src/dark_factory/persistence/mutations.py` | `apply_transition` + `expected_owner_token` fence + `human_interaction` + lease clear on stop | ✓ VERIFIED | `LeaseLost`, `HumanInteractionWrite` exported. Fence raises against the already-`with_for_update`-locked `runs` row (lines 259-268). `_write_human_interaction` redacts `question`/`answer` at the single call site (lines 375, 393). Lease columns cleared when `next_status ∈ STOP_STATUSES` (lines 281-283). Unchanged by the fix commits. |
| `src/dark_factory/persistence/repositories.py` | `LatestExecution.result`, `RunState.pending_answer`, `pending_question` | ✓ VERIFIED | Bound-parameterised select for the `ANSWERED` interaction bound to the latest attempt; `run_events` never queried on this path. |
| `src/dark_factory/persistence/models.py` | `HumanInteraction` ORM, `_INTERACTION_STATUS`, `Run.owner_token` / `Run.lock_expires_at` | ✓ VERIFIED | 8-column table + partial unique index; two nullable lease columns, no server default. `_INTERACTION_STATUS` built `native_enum=False, create_constraint=True`. |
| `migrations/versions/0003_pause_resume_lease.py` | Alembic revision, reversible | ✓ VERIFIED | `down_revision = "0002_role_exec_uniqueness"`; `upgrade()` creates table + both indexes + two `runs` columns; `downgrade()` mirrors. `migrations/env.py` `_OWNED_TABLES` includes `human_interactions`. Executor-recorded `alembic check` clean + down/up round trip. |
| `src/dark_factory/config/settings.py` | `lease_ttl_seconds` (900) / `lease_heartbeat_seconds` (300) + coherence validator | ✓ VERIFIED | Plain ints; `@model_validator(mode="after")` rejects non-positive TTL and `heartbeat >= TTL` naming both fields; neither enters `known_secret_values()`. `tests/unit/test_settings.py` re-run here: passes (defaults 900/300 asserted; equal-to-TTL and greater-than-TTL both rejected naming `lease_heartbeat_seconds`). |
| `src/dark_factory/cli.py` | `resume --answer`; exit 0 for `COMPLETED`/`WAITING_HUMAN`; exit 0 + notice on lost race | ✓ VERIFIED | `_CLEAN_FINALS = (COMPLETED, WAITING_HUMAN)`; `LeaseNotAcquired` caught before `_ORCHESTRATION_ERRORS` in both `_drive_and_exit` and the `--answer` branch → exit 0 with stderr notice. **WR-03 fix present:** `_ORCHESTRATION_ERRORS` now includes `LookupError, ValueError` (lines 81-82) with an explanatory comment. |
| `tests/integration/test_phase2_acceptance.py` | acceptance gate: 5 SC + 6 req mapped to named proofs, fails-not-skips | ✓ VERIFIED | `grep -c 'pytest.skip'` → 0. All 12 mapped proof files confirmed present + non-empty on disk this session. Marked `integration` so it needs a DB to *run*, but its assertions are pure file-existence — statically confirmed here. |
| `.env.example` / `README.md` | lease knobs documented; pause/resume walkthrough; 3-way exit-code contract | ✓ VERIFIED | `.env.example` carries `LEASE_TTL_SECONDS=900` / `LEASE_HEARTBEAT_SECONDS=300` with unit + consequence comments. `README.md` pause/resume section + exit-code table with both new zero cases; operator UAT item 1 followed it verbatim against real Neon with no guessed step. |

## Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `runner.advance`/`drive` | `orchestrator/lease.run_lease` | `with run_lease(run_id, session_factory=...) as lease:` wraps the loop / single step (runner.py:222, 471) | ✓ WIRED |
| `runner._run_current_role` | `persistence/mutations.apply_transition` | pause branch passes `human_interaction=HumanInteractionWrite(mode="ask")` + `expected_owner_token=lease.token` into one call (runner.py:413-431) | ✓ WIRED |
| `orchestrator/answers.submit_answer` | `persistence/mutations.apply_transition` | exactly one guarded call inside `run_lease`, `human_interaction=HumanInteractionWrite(mode="answer")`, no direct ORM writes (answers.py:99-144) | ✓ WIRED |
| `runner._run_current_role` | persisted `role_executions.status` | execute-vs-resume read from `latest.status == _ROLE_RESUMING` (runner.py:338), never in-memory | ✓ WIRED |
| `cli.resume --answer` | `orchestrator/answers.submit_answer` | called before the drive loop (cli.py:198-205); command holds no lifecycle logic | ✓ WIRED |
| `mutations.apply_transition` | `runs.owner_token` (already-locked row) | `LeaseLost` if `expected_owner_token != run.owner_token` — free fence, no second select (mutations.py:266-268) | ✓ WIRED |
| `mutations.apply_transition` | `runs.owner_token`/`lock_expires_at` | cleared to NULL when `next_status ∈ STOP_STATUSES` — atomic with the state change (mutations.py:281-283) | ✓ WIRED |
| `cli._ORCHESTRATION_ERRORS` | `mutations.apply_transition` bare `LookupError`/`ValueError` | WR-03: both types now in the tuple → `_report_orchestration_error` → exit 2 instead of Typer default exit 1 | ✓ WIRED |

## Data-Flow Trace

| Value | Source | Status |
| ----- | ------ | ------ |
| `human_interactions.question` | worker `NEEDS_INPUT` result → `HumanInteractionWrite(mode="ask")` → `redact()` → INSERT in `_write_human_interaction` | ✓ FLOWING |
| `human_interactions.answer` | `--answer` argv → `submit_answer` → `HumanInteractionWrite(mode="answer")` → `redact()` → UPDATE of the run's single `WAITING` row located inside the txn with `.with_for_update()` | ✓ FLOWING |
| `RunState.pending_answer` | `SELECT answer FROM human_interactions WHERE role_execution_id = latest.id AND status = 'ANSWERED'` | ✓ FLOWING |
| resume dispatch decision | `role_executions.status == 'RESUMING'` (persisted) | ✓ FLOWING |
| `lock_expires_at` | `func.now() + timedelta(seconds=ttl)` — server clock, both write and compare, including every WR-01 retry iteration | ✓ FLOWING |

## Behavioural Spot-Checks

| Behaviour | Command | Result | Status |
| --------- | ------- | ------ | ------ |
| unit tier | `uv run pytest -q -m unit` | 193 passed, 171 deselected (0.42 s) | ✓ PASS |
| strict typing | `uv run mypy src/dark_factory` | Success: no issues in 39 source files | ✓ PASS |
| lint | `uv run ruff check src/dark_factory` | All checks passed | ✓ PASS |
| WR-01 present | read `lease.py:231-263` | `consecutive_errors` counter + `lease.renew_error` log + threshold `consecutive_errors * interval >= ttl - interval`; authoritative "matched no row" path unchanged | ✓ PASS |
| WR-02 present | read `lease.py:35-49` | "What the lease guarantees — and what it does not" paragraph present | ✓ PASS |
| WR-03 present | `grep -n 'LookupError\|ValueError' cli.py` | both in `_ORCHESTRATION_ERRORS` (lines 81-82) with comment | ✓ PASS |
| debt markers in changed src | `grep -nE 'TODO\|FIXME\|XXX\|HACK\|PLACEHOLDER\|not implemented' lease.py cli.py` | none | ✓ PASS |
| acceptance gate — no skip | `grep -c 'pytest.skip' tests/integration/test_phase2_acceptance.py` | 0 | ✓ PASS |
| all 12 mapped proof files present + non-empty | filesystem check | 12/12 | ✓ PASS |
| db / integration tiers (incl. post-WR-01 heartbeat/reclaim proofs) | — | not runnable (no PostgreSQL reachable) | ? SKIP → human_needed |

## Probe Execution

No project probes (`scripts/*/tests/probe-*.sh`) exist; this is not a
migration/tooling phase in the probe sense. The phase's own acceptance mechanism
is `tests/integration/test_phase2_acceptance.py` (assessed above).

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | — | — | None. No debt markers in the changed files, no stub returns, no hardcoded empty data feeding a rendered value, no disabled tests linked to a requirement. |

## Code-Review Findings (02-REVIEW.md → 02-REVIEW-FIX.md, re-assessed)

| ID | Finding | Fix commit | Re-verified in current tree | Undermines a SC / invariant? |
| -- | ------- | ---------- | -------------------------- | ---------------------------- |
| WR-01 | A single transient heartbeat-renewal error aborted an in-flight step with no retry. | e9a231a | ✓ `lease.py:231-263` — transient exception now retried within the TTL budget; authoritative "matched no row" still an immediate loss; `hb_session.close()` in `finally` on every path; stop path untouched. | No. Makes the owner's self-abort more tolerant of blips; does not touch the successful-renewal path, cannot extend the lease, cannot cause a false steal, cannot make the heartbeat outlive its owner. SC5 and the "no hostage heartbeat" prohibition still hold on inspection. **The new branch is not exercised by any executed test — see Human Verification.** |
| WR-02 | Worker call not bounded by lease validity; a stalled owner past TTL could run its worker concurrently with a second process (durable state still single-owner via the fence). | 3617bb3 | ✓ `lease.py:35-49` — docstring now states "no concurrent durable mutation, not no concurrent execution", names the Phase-7 mitigations. | Documentation only. The HITL-07 nuance is now recorded, not silently assumed. Benign for `FakeWorker`. Mitigation correctly deferred to Phase 7. |
| WR-03 | Bare `LookupError`/`ValueError` from `apply_transition` escaped as Typer exit 1 instead of the D-05 exit-2 "nothing persisted" code. | 19f4ccb | ✓ `cli.py:81-82` — both types added to `_ORCHESTRATION_ERRORS` with a comment; covered by the 193 passing unit tests. | No. Tightens the D-05 exit-code contract on the exact path SC1/SC2 exercise; the SC-relevant codes (clean pause = 0, declined race = 0) were already correct. |

## Prior Human Verification Items — all resolved by 02-UAT.md (commit a8beb21)

| # | Prior item | UAT result |
| - | ---------- | ---------- |
| 1 | Fresh-eyes README pause/resume walkthrough against a real Neon endpoint | **PASS** — operator ran README steps 1-3 verbatim against real Neon: pause → `BA → WAITING_HUMAN` exit 0; `status` showed `WAITING_HUMAN` / `current_role: BA`; `resume --answer` → `run.resumed` stderr line + `BA → COMPLETED` exit 0; output matched the README examples step for step. |
| 2 | Production-scale lease timing (900 s TTL / 300 s heartbeat) against a real Neon PgBouncer endpoint | **PASS** — pre-expiry claim declined, post-expiry claim succeeded, `lock_expires_at` advanced during a slow step — matching the short-injected-TTL integration proofs. |
| 3 | Confirm the 900 s / 300 s production defaults are acceptable (~15-min dead-owner reclaim ceiling, no force-steal) | **PASS** — operator accepts the ceiling and the absence of a force-steal escape hatch in this phase; the defaults stand. |
| 4 | Accept (or re-run against PostgreSQL 17) the db/integration proof tiers, which executed against PostgreSQL 18.6 | **PASS** — operator accepts the PostgreSQL 18.6 vs `postgres:17-alpine` pin as an approved environmental deviation carried since 01-01. |

## Human Verification Required

One item remains — **new since the prior report**, arising from the WR-01 heartbeat
change (commit e9a231a) landing after the last recorded green DB run:

### 1. Re-run the lease heartbeat / reclaim proof tiers against a real PostgreSQL, post-WR-01

**Test:** With a real PostgreSQL endpoint configured (`DARK_FACTORY_TEST_DATABASE_URL`
or Docker), run:
`uv run pytest -q tests/integration/test_heartbeat_slow_step.py tests/integration/test_lease_expiry_reclaim.py tests/db/test_lease_lost_aborts_step.py`
and ideally the full `db`/`integration` tiers.

**Expected:** All pass. Specifically confirm: (a) a genuine lease loss
(`renew_lease` matches no row) still sets `lease_lost` immediately and the owner
still aborts before its `apply_transition` commit; (b) the WR-01
`consecutive_errors` retry on a *transient* renewal exception does not push an
owner's effective ownership past its own last-good `lock_expires_at` such that a
competitor false-steals mid-step (SC5); (c) `test_lease_expiry_reclaim.py`'s
killed-owner reclaim timing (SC4) is unaffected by the retry budget.

**Why human:** The WR-01 fix adds new heartbeat control flow (a `consecutive_errors`
threshold governing transient-vs-authoritative loss and its interaction with
`lease_ttl_seconds` reclaim timing). No executed test in this session exercises
the transient-exception branch — the existing DB heartbeat proofs cover only the
happy renewal path and the authoritative-loss path, both unchanged by the fix —
and no PostgreSQL was reachable here. 02-REVIEW-FIX.md itself states these tiers
"must be run against a real PostgreSQL 17 to fully verify WR-01 and WR-03" and
recommends doing so "before the phase proceeds". Static analysis shows the change
cannot cause a false steal or a hostage heartbeat, so SC4/SC5 as written hold;
this check confirms the new branch against a database rather than by inspection
alone.

## Observations (non-blocking)

- **`02-VALIDATION.md` frontmatter remains stale** (`status: draft`,
  `nyquist_compliant: false`). The substance (the per-requirement test map) is
  fully delivered and drift-guarded by `tests/integration/test_phase2_acceptance.py`.
  Process-hygiene only.
- **`deferred-items.md`** records two out-of-scope discoveries correctly bounded to
  later phases (multi-node `role_executions` row reuse → Phase 3; `ruff format` on
  planning-doc code fences → resolved via `[tool.ruff] extend-exclude`).
- **IN-01…IN-06 from 02-REVIEW.md** are Info-level and out of fix scope; none
  falsifies a Phase 2 SC or invariant. IN-02 (`migrations/env.py` pooled-URL
  fallback) and IN-03 (inert `workflow` snapshot) are worth carrying into Phase 3.
- **ROADMAP marks Phase 2 `Mode: mvp`** but the phase goal is a plain
  goal-with-success-criteria statement, not an "As a … I want … so that …" user
  story. Consistent with the prior verification, this report verifies against the
  five explicit ROADMAP success criteria as observable truths rather than
  invoking MVP user-flow-coverage handling.

## Gaps Summary

No gaps block the phase goal. Every success criterion has a substantive,
correctly-asserting proof file mapped and existence-enforced by the acceptance
gate; every phase invariant holds under static inspection of the post-fix tree
and independent code review; all six requirement ids are covered and marked
Complete. The three 02-REVIEW.md Warnings are all fixed and re-inspected in the
current source, and the four prior human items are all resolved PASS in
02-UAT.md.

The phase is `human_needed` (not `passed`) for one reason only: the WR-01
heartbeat change (commit e9a231a) landed after the last recorded green
`db`/`integration` run, its new transient-error retry branch is not exercised by
any test that could run in this environment (no PostgreSQL reachable), and the
code-fixer explicitly recommended a real-PostgreSQL run of the lease proof tiers
before the phase proceeds. This is a low-risk confirmation — static analysis
shows the change cannot regress SC4 or SC5 — but it is a genuine unexercised
behavioural path on the lease-reclaim timing interaction, which is exactly what a
human checkpoint is for.

---

_Verified: 2026-09-10_
_Verifier: Claude (gsd-verifier)_
_Re-verification: after commits e9a231a / 3617bb3 / 19f4ccb and 02-UAT.md (a8beb21)_
