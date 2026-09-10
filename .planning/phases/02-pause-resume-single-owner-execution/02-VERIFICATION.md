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
covered_digest: "v1:sha256:eba7fae6099b5fe98b9423fc3a11c90e64bb4a9be0e09b8dce16a8de2dc6e1d9"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Fresh-eyes README pause/resume walkthrough against a real Neon endpoint"
    expected: "A reader who has never seen the repo can start a scripted pause, read the recorded question via `dark-factory status`, and resume with `resume <id> --answer \"...\"` from a second shell, following only the README section — with no step they had to guess at, and the exit-code table making it unmistakable that a clean pause (exit 0) and a declined ownership race (exit 0) are successes, not faults."
    why_human: "Legibility / operator-experience judgment; the commands were run and the mechanism is proven by the automated suite, but 'can a stranger follow this' is not something a test can settle (02-03 <human-check>, 02-07 <human-check>)."
  - test: "Production-scale lease timing against a real Neon PgBouncer transaction-pooled endpoint at the shipped 900 s TTL / 300 s heartbeat"
    expected: "Pause a run, kill the owner, confirm a second process does not claim before `lock_expires_at`, then claims after; run a deliberately slow step and confirm `lock_expires_at` advances while it runs. Behaviour matches the short-injected-TTL proofs at production scale."
    why_human: "A real-minutes end-to-end timing test is impractical in CI; the injected 6 s/2 s (TTL/3 ratio) integration proofs establish the mechanism, the production-scale timing is an operator smoke check (02-VALIDATION.md Manual-Only Verifications; 02-05 coverage D9)."
  - test: "Confirm the Open Decision 2 production defaults (900 s TTL / 300 s heartbeat) are acceptable"
    expected: "A genuinely dead owner's run is unclaimable for up to ~15 minutes and this phase provides no force-steal escape hatch. Either accept the ceiling, or change it (a one-line `Settings` default edit)."
    why_human: "A product/operations judgment about an acceptable reclaim-delay ceiling, not something a test can settle (02-05 <human-check>, coverage D9 human_judgment: true)."
  - test: "Accept (or re-run against PostgreSQL 17) the db/integration proof tiers, which executed against PostgreSQL 18.6"
    expected: "Operator confirms the PG 18.6 vs the `postgres:17-alpine` pin in CLAUDE.md is an approved environmental deviation (carried since 01-01) or provisions a PG 17 endpoint for a confirmation run."
    why_human: "Operator-approved environmental deviation; verifier cannot decide it. No PostgreSQL of any version was reachable in the verification environment, so the db/integration tiers were not re-executed here — this verdict rests on the executor-recorded green runs, static source inspection, and the acceptance gate."
---

# Phase 2: Pause, Resume & Single-Owner Execution — Verification Report

**Phase Goal:** A run can stop mid-role to ask a human a question, release its process safely, and later be resumed by exactly one process — even after the original process died.
**Verified:** 2026-09-10
**Status:** human_needed
**Re-verification:** No — initial verification

## Verification constraints

No PostgreSQL (any version) was reachable in the verification environment, so the
`db` and `integration` test tiers could not be re-executed. Per the task's
stated fallback, this verdict rests on:

1. **Static inspection of the delivered source** against each success criterion
   and each phase invariant (all 16 impl/migration files read in full).
2. **The acceptance-gate file** `tests/integration/test_phase2_acceptance.py`
   read in full — it maps all 5 success criteria and all 6 requirement ids to
   named proof files; every one of the 12 distinct proof files was confirmed
   present on disk, non-empty, and containing `def test_` functions whose
   bodies assert the criterion-specific properties (not stubs).
3. **The `unit`/`contract` tier, re-run here: 200 passed, 0 failed** (0.43 s).
4. **`mypy --strict src/dark_factory`: clean (39 files); `ruff check`: clean** —
   re-run here.
5. **Executor-recorded full-suite runs** across the phase: 02-03 (310 passing),
   02-04 (db 82 / integration 41), 02-05 (db 89 / integration 46), 02-06
   (349 passed), 02-07 (**364 passed, 0 skipped**, `alembic check` clean).
6. **02-REVIEW.md** (independent code review, 0 Critical) which traced the four
   phase invariants in code and found them holding.

The success criteria are behaviour-dependent (state transitions, cancellation /
cleanup / ordering invariants). Their proof files exist, are substantive, and
are recorded green by the executors and by an independent code review — but they
were not re-executed in this environment. That, plus the genuinely outstanding
human items below, is why the phase routes to `human_needed` rather than
`passed`.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC1 | A role returning `NEEDS_INPUT` leaves the run `WAITING_HUMAN` with the question, the worker result, the worker session id and the current role persisted; the process exits 0 holding no open DB transaction. | ✓ VERIFIED | `runner._run_current_role` `ROLE_NEEDS_INPUT` branch: `re_status="WAITING_HUMAN"`, `re_result=outcome` (serialised NEEDS_INPUT), `worker_session_id=result.worker_session_id`, events `QUESTION_CREATED`→`RUN_PAUSED`, `human_interaction=HumanInteractionWrite(mode="ask")`; `lifecycle.transition` `ROLE_NEEDS_INPUT` arm retains the role; `apply_transition` clears both lease columns because `WAITING_HUMAN ∈ STOP_STATUSES`; commit is one `with session.begin()`, session closed in `finally`. `cli._drive_and_exit` exits 0 for `final ∈ (COMPLETED, WAITING_HUMAN)`. Proof: `tests/integration/test_pause_exit_zero.py` asserts all five writes + lease NULL + exit 0 as one block (recorded pass). |
| SC2 | `dark-factory resume <run-id> --answer "..."` from a brand-new process continues the same role execution and attempt — never creates a new run and needs nothing from the original process. | ✓ VERIFIED | `cli.resume` → `submit_answer` (one `apply_transition`: `WAITING_HUMAN`→`RunStatus(current_role)`, same role-execution row `id=latest.id` marked `RESUMING`, interaction `ANSWERED`) → `drive` → `_run_current_role` reads the persisted `RESUMING` marker and calls `worker.resume(context, previous, answer)` with `previous` validated from the stored NEEDS_INPUT dict and `answer` from `RunState.pending_answer`. No `create_run` on this path. Proof: `tests/integration/test_resume_with_answer.py` asserts same `role_executions.id`, same `attempt`, run-count unchanged, fresh child env, `HUMAN_ANSWER_RECEIVED`→`RUN_RESUMED` (recorded pass; 3 tests incl. two negative cases). |
| SC3 | Two processes racing `advance` on the same run: one executes, the other exits cleanly without changing status and without duplicating work. | ✓ VERIFIED | `run_lease` claims via one conditional `UPDATE runs ... WHERE (owner_token IS NULL OR lock_expires_at < now()) ... RETURNING id`; the loser gets `None` → `LeaseNotAcquired` → `cli._report_lease_not_acquired` prints `is owned by another process` on stderr and **exits 0** having written nothing; the winner's every `apply_transition` is fenced by `expected_owner_token`. Proof: `tests/integration/test_single_owner_race.py` (deterministic-loser + tight race, invariant assertions: exactly one `ROLE_COMPLETED`, one BA row @ attempt 1, both exit 0, no traceback) + `tests/db/test_lease_claim_atomic.py` (16 barrier-synchronised threads → exactly one token). Recorded pass; 4× flake-smoke clean. |
| SC4 | A process killed while owning a run loses its lease by database-clock expiry, and the next process claims the run and continues from the last committed step. | ✓ VERIFIED | Killed owner (`os._exit` via `DARK_FACTORY_CRASH_AFTER`) leaves `owner_token` + future `lock_expires_at`; `claim_lease` predicate rejects the second process before expiry (`LeaseNotAcquired` → exit 0, no steal); after the server clock passes `lock_expires_at` the claim succeeds and `_advance_once` reconstructs wholly from Neon (`load_run_state`) and continues on the same `attempt`. Expiry is lazy — no reaper/scheduler/sweeper (structural grep test). Proof: `tests/integration/test_lease_expiry_reclaim.py` (3 tests: forced expiry + field-by-field snapshot equality for the not-stolen half + honest short-TTL real-wait reclaim + no-reaper). Recorded pass. |
| SC5 | A role step that runs longer than the lease TTL is not falsely stolen — the owner heartbeats the lease while the step is in flight. | ✓ VERIFIED | `run_lease` starts a daemon heartbeat thread that calls `renew_lease` every `heartbeat_seconds` on **its own** session, pushing `lock_expires_at = func.now() + ttl`; a competing `claim_lease` keeps matching zero rows. `__exit__` always stops/joins/best-effort-releases on every exit path (normal, exception, clean pause). Proof: `tests/integration/test_heartbeat_slow_step.py` (≥3 strict expiry advances over a step >3× TTL, owner token constant, every competitor loses & exits 0, release-on-exception with default 900 s TTL, structural no-liveness-probe grep) + `tests/db/test_lease_lost_aborts_step.py` (7 tests: token fence + in-memory flag each independently sufficient, `LeaseLost` distinct from `ConcurrentTransition`, re-runnable on same attempt). Recorded pass; 3× flake-smoke clean. |

**Score:** 5/5 success criteria verified (static + acceptance-gate + executor-recorded runs; not re-executed here — see constraints).

### Phase Invariants

| Invariant | Status | Evidence |
| --------- | ------ | -------- |
| No DB transaction held across a worker call | ✓ VERIFIED | `_advance_once` opens a read session, calls `load_run_state`, closes it in `finally`; `_run_current_role` runs `worker.execute`/`worker.resume` with **no** session open; the write session is opened only for the `apply_transition` commit. Heartbeat renews in a sub-second `with session.begin()` per beat. `test_no_txn_across_worker.py` asserts zero `dark-factory` backends with a transaction lingering `> 3 s` during a 12 s worker call, plus a positive `not session.in_transaction()` after `create_run` / `apply_transition`. 02-REVIEW.md confirms. |
| Claim-don't-check concurrency (conditional `UPDATE` lease + guarded status update) | ✓ VERIFIED | `claim_lease` is exactly one `sa.update(Run).where(id, status NOT IN terminal, owner_token IS NULL OR lock_expires_at < func.now()).values(...).returning(Run.id)`. `apply_transition` uses `with_for_update` row lock + `expected_status` guard + `expected_owner_token` fence. `grep` of `lease.py` for `pg_advisory` / `SKIP LOCKED` / `skip_locked` → 0. No distributed-lock service. |
| All expiry checks use the database clock, never a process clock | ✓ VERIFIED | Every expiry value in `lease.py` is `func.now() + timedelta(seconds=ttl)`; every comparison is `lock_expires_at < func.now()`. `grep` of `lease.py` for `datetime.now` / `datetime.utcnow` → 0. The only `time`/`Event.wait` use is the heartbeat's inter-renewal delay (not a timestamp). |
| Infrastructure credentials never reach `human_interactions.question`/`.answer` or any worker/event/log | ✓ VERIFIED (recorded) | `mutations._write_human_interaction` applies `redact(spec.question, ...)` / `redact(spec.answer, ...)` at the single mutation-path call site; `HumanInteractionWrite` carries raw text by contract. `tests/unit/test_single_mutation_path.py` `_LIFECYCLE_CTORS` includes `HumanInteraction` (re-run here: passes). `tests/integration/test_redaction_interactions.py` sweeps every interaction column + every event payload + `role_executions.result` + a real structlog sink, presence-then-absence (recorded pass). |

## Requirements Coverage

Union of `requirements:` across all 7 PLAN frontmatters = `{STATE-04, HITL-01,
HITL-02, HITL-03, HITL-07, HITL-08}` — exactly the six phase requirement ids in
ROADMAP.md. No orphans, no extras.

| Requirement | Source Plans | Status | Evidence |
| ----------- | ------------ | ------ | -------- |
| STATE-04 | 02-01, 02-02, 02-06, 02-07 | ✓ SATISFIED | `human_interactions` table (id, run_id, role_execution_id, question, answer, status, created_at, answered_at); `status` is `VARCHAR(16)` + named CHECK `interaction_status` carrying exactly `WAITING`/`ANSWERED`/`CANCELLED` (DB-enforced); partial unique index `uq_one_waiting_interaction_per_run`; both FKs. Migration `0003_pause_resume_lease` reversible. Proof: `tests/db/test_human_interactions_schema.py` (12 tests). REQUIREMENTS.md line 76 / 232 = Complete. |
| HITL-01 | 02-03, 02-06, 02-07 | ✓ SATISFIED | The only pause mechanism is a `NEEDS_INPUT` worker result; `_run_current_role` branches on `signal_from_result(result)`, never a role name. Proof: `tests/db/test_pause_mechanism_generic.py` injects a two-node pipeline (`BA` + an invented `ARCHITECTURE` node) and asserts both nodes pause through structurally identical code (projected-remainder equality). |
| HITL-02 | 02-02, 02-03, 02-06, 02-07 | ✓ SATISFIED | On `NEEDS_INPUT`: result + worker session id + `current_role` + interaction row + `QUESTION_CREATED`/`RUN_PAUSED` all in one `apply_transition` transaction; lease cleared atomically; process exits 0. Proof: `tests/integration/test_pause_exit_zero.py` + `tests/db/test_pause_path_atomic.py` (crash injected between every sub-write of pause **and** answer → all-or-nothing, run stays resumable, attempt unchanged). |
| HITL-03 | 02-02, 02-03, 02-07 | ✓ SATISFIED | `dark-factory resume <run-id> --answer "..."` from a brand-new process; decision driven entirely by persisted columns (`RESUMING` marker, `pending_answer`). Proof: `tests/integration/test_resume_with_answer.py`. |
| HITL-07 | 02-01, 02-02, 02-03, 02-04, 02-05, 02-07 | ✓ SATISFIED | Single-owner via conditional `UPDATE` lease + `with_for_update` + token fence; no distributed-lock service. Proof: `tests/integration/test_single_owner_race.py` + `tests/db/test_lease_claim_atomic.py` + `tests/integration/test_lease_expiry_reclaim.py` + `tests/db/test_lease_lost_aborts_step.py`. See WR-02 below for the documented stalled-owner limitation. |
| HITL-08 | 02-01, 02-02, 02-03, 02-05, 02-07 | ✓ SATISFIED | No transaction spans the worker call; ownership is a column with DB-clock expiry renewed by a thread on its own session. Proof: `tests/integration/test_no_txn_across_worker.py` (`pg_stat_activity` by `application_name`, `xact_start`-age filter) + `test_heartbeat_slow_step.py`. |

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/dark_factory/orchestrator/lease.py` | claim-don't-check lease + `run_lease` context manager + heartbeat | ✓ VERIFIED | 250 lines. `claim_lease` / `renew_lease` / `release_lease` (one guarded `UPDATE...RETURNING` each), `run_lease` contextmanager, `LeaseHandle`, `LeaseNotAcquired`. Imported by `runner.py` and `answers.py`. All three invariant greps → 0. |
| `src/dark_factory/orchestrator/answers.py` | `submit_answer` — one guarded transition out of `WAITING_HUMAN` | ✓ VERIFIED | 151 lines. Precheck (RunNotFound / NotWaitingForHuman / NoPendingInteraction) then one `apply_transition` inside `run_lease`; constructs no ORM row. Imported by `cli.py`. |
| `src/dark_factory/orchestrator/lifecycle.py` | `ROLE_NEEDS_INPUT → WAITING_HUMAN` arm, role retained; `WAITING_HUMAN` illegal to leave | ✓ VERIFIED | Pure function; imports nothing from `dark_factory.persistence`. New arm present; every `(WAITING_HUMAN, *)` raises `IllegalTransitionError`. |
| `src/dark_factory/orchestrator/runner.py` | lease-wrapped `advance`/`drive`, stop-set early return, execute-vs-resume dispatch, needs-input branch, lease-loss abort | ✓ VERIFIED | `advance`/`drive` early-return on the whole `STOP_STATUSES` set without claiming; `_advance_once` assumes lease held; `_run_current_role` reads persisted `RESUMING` marker, checks `lease.lease_lost` after the worker call, pauses on the signal. Every `apply_transition` passes `expected_owner_token=lease.token`. |
| `src/dark_factory/persistence/mutations.py` | `apply_transition` + `expected_owner_token` fence + `human_interaction` + lease clear on stop | ✓ VERIFIED | `LeaseLost`, `HumanInteractionWrite` exported. Fence raises against the already-locked `runs` row. `_write_human_interaction` redacts `question`/`answer` at the single call site. Lease columns cleared when `next_status ∈ STOP_STATUSES`. |
| `src/dark_factory/persistence/repositories.py` | `LatestExecution.result`, `RunState.pending_answer`, `pending_question` | ✓ VERIFIED | Third bound-parameterised select for the `ANSWERED` interaction bound to the latest attempt; `run_events` never queried. |
| `src/dark_factory/persistence/models.py` | `HumanInteraction` ORM, `_INTERACTION_STATUS`, `Run.owner_token` / `Run.lock_expires_at` | ✓ VERIFIED | 8-column table + partial unique index; two nullable lease columns, no server default. `_INTERACTION_STATUS` built `native_enum=False, create_constraint=True`. |
| `migrations/versions/0003_pause_resume_lease.py` | Alembic revision, reversible | ✓ VERIFIED | `down_revision = "0002_role_exec_uniqueness"`, id ≤ 32 chars; `upgrade()` creates table + both indexes + two `runs` columns; `downgrade()` mirrors. `migrations/env.py` `_OWNED_TABLES` gains `human_interactions`. Executor-recorded `alembic check` clean + down/up round trip. |
| `src/dark_factory/config/settings.py` | `lease_ttl_seconds` (900) / `lease_heartbeat_seconds` (300) + coherence validator | ✓ VERIFIED | Plain ints; `@model_validator(mode="after") _lease_intervals_are_coherent` rejects non-positive TTL and `heartbeat >= TTL` naming both fields; neither enters `known_secret_values()`. Unit tier re-run here: passes. |
| `src/dark_factory/cli.py` | `resume --answer`; exit 0 for `COMPLETED`/`WAITING_HUMAN`; exit 0 + notice on lost race | ✓ VERIFIED | `_CLEAN_FINALS = (COMPLETED, WAITING_HUMAN)`; `LeaseNotAcquired` caught before `_ORCHESTRATION_ERRORS` → exit 0 with stderr notice. See WR-03 below for the `LookupError`/`ValueError` gap. |
| `tests/integration/test_phase2_acceptance.py` | acceptance gate: 5 SC + 6 req mapped to named proofs, fails-not-skips | ✓ VERIFIED | 230 lines, 6 test fns, 0 `pytest.skip`. All 12 mapped proof files confirmed present, non-empty, containing `def test_`. Drift-guard against `02-VALIDATION.md`'s per-requirement map. Marked `integration` so it needs a DB to *run*, but its assertions are pure file-existence — statically confirmed here. |
| `.env.example` / `README.md` | lease knobs documented; pause/resume walkthrough; 5-outcome exit-code table | ✓ VERIFIED | `.env.example` carries `LEASE_TTL_SECONDS=900` / `LEASE_HEARTBEAT_SECONDS=300` with unit + consequence comments. `README.md` §"Pause a run for a human, then resume it (Phase 2)" + exit-code table with both new zero cases + "What Phase 2 deliberately does not do". |

## Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `runner.advance`/`drive` | `orchestrator/lease.run_lease` | `with run_lease(run_id, ...) as lease:` wraps the whole loop / single step | ✓ WIRED |
| `runner._run_current_role` | `persistence/mutations.apply_transition` | pause branch passes `human_interaction=HumanInteractionWrite(mode="ask")` + `expected_owner_token=lease.token` into one call | ✓ WIRED |
| `orchestrator/answers.submit_answer` | `persistence/mutations.apply_transition` | exactly one guarded call, `human_interaction=HumanInteractionWrite(mode="answer")`, no direct ORM writes | ✓ WIRED |
| `runner._run_current_role` | `persistence/repositories.load_run_state` | execute-vs-resume read from `latest.status == "RESUMING"` (persisted column, never in-memory) | ✓ WIRED |
| `cli.resume --answer` | `orchestrator/answers.submit_answer` | called before the drive loop; command holds no lifecycle logic | ✓ WIRED |
| `mutations.apply_transition` | `runs.owner_token` (already-locked row) | `LeaseLost` if `expected_owner_token != run.owner_token` — free fence, no second select | ✓ WIRED |
| `mutations.apply_transition` | `runs.owner_token`/`lock_expires_at` | cleared to NULL when `next_status ∈ STOP_STATUSES` — atomic with the state change | ✓ WIRED |

## Data-Flow Trace

| Value | Source | Status |
| ----- | ------ | ------ |
| `human_interactions.question` | `"\n".join(result.questions)` from the worker's `NEEDS_INPUT` result → `redact()` → INSERT in `_write_human_interaction` | ✓ FLOWING |
| `human_interactions.answer` | `--answer` argv → `submit_answer` → `HumanInteractionWrite(mode="answer")` → `redact()` → UPDATE of the run's single `WAITING` row located inside the txn | ✓ FLOWING |
| `RunState.pending_answer` | `SELECT answer FROM human_interactions WHERE role_execution_id = latest.id AND status = 'ANSWERED'` | ✓ FLOWING |
| resume dispatch decision | `role_executions.status == 'RESUMING'` (persisted) | ✓ FLOWING |
| `lock_expires_at` | `func.now() + timedelta(seconds=ttl)` — server clock, both write and compare | ✓ FLOWING |

## Behavioural Spot-Checks

| Behaviour | Command | Result | Status |
| --------- | ------- | ------ | ------ |
| unit + contract tier | `uv run pytest -q -m "unit or contract"` | 200 passed, 164 deselected (0.43 s) | ✓ PASS |
| strict typing | `uv run mypy src/dark_factory` | Success: no issues in 39 files | ✓ PASS |
| lint | `uv run ruff check src tests migrations` | All checks passed | ✓ PASS |
| lease.py — no process clock | `grep -c 'datetime\.now\|datetime\.utcnow'` (comments stripped) | 0 | ✓ PASS |
| lease.py — no second coordination primitive | `grep -c 'pg_advisory\|SKIP LOCKED\|skip_locked'` | 0 | ✓ PASS |
| lease.py — no liveness probe | `grep -c 'pg_stat_activity\|os.getpid\|psutil'` | 0 | ✓ PASS |
| acceptance gate — no skip | `grep -c 'pytest.skip' tests/integration/test_phase2_acceptance.py` | 0 | ✓ PASS |
| all 12 mapped proof files present + non-empty + contain `def test_` | filesystem check | 12/12 | ✓ PASS |
| debt markers in phase source | `grep -nE 'TODO\|FIXME\|XXX\|HACK\|PLACEHOLDER\|not implemented'` over 14 impl files + migration | none | ✓ PASS |
| db / integration tiers | — | not runnable (no PostgreSQL reachable) | ? SKIP → human_needed |

## Probe Execution

No project probes (`scripts/*/tests/probe-*.sh`) exist; this is not a
migration/tooling phase in the probe sense. The phase's own acceptance mechanism
is `tests/integration/test_phase2_acceptance.py` (assessed above under Required
Artifacts and Behavioural Spot-Checks).

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | — | — | None. No debt markers, no stub returns, no hardcoded empty data feeding a rendered value, no disabled tests linked to a requirement. |

## Code-Review Findings Carried From 02-REVIEW.md (assessed against Phase 2 SCs + invariants)

| ID | Finding | Undermines a SC / invariant? | Disposition |
| -- | ------- | ---------------------------- | ----------- |
| WR-01 | `_heartbeat` treats any `renew_lease` exception (transient dropped connection / Neon cold start) as a permanent lease loss with no retry, so a one-off blip makes an otherwise-successful long step exit 2. | No. SC5 concerns *not being falsely stolen by a competitor*; the invariants require DB-clock expiry and no held transaction — all hold. This is an availability/robustness gap on the owner's own connection. | ⚠️ WARNING — flagged for Phase 7 (real agent runtimes). Does not block the phase goal. Recommend the bounded-retry fix in 02-REVIEW.md before credentialled workers land. |
| WR-02 | The worker call is not bounded by lease validity; a *stalled* owner (SIGSTOP / GC / VM pause) past its full TTL could let a second process run the same role's worker concurrently. Durable state stays single-owner (the `expected_owner_token` fence rejects the stale commit, proven by `test_lease_lost_aborts_step.py`). | Partially — the HITL-07 wording "two processes cannot *execute* the same run simultaneously" is violated for that pathological window, though "no concurrent *durable mutation*" holds. Benign for Phase 2 (`FakeWorker` has no side effects). | ⚠️ WARNING — 02-REVIEW.md itself says "No change required for Phase 2; record the limitation." Recommend adding the "no concurrent durable mutation, not no concurrent execution" note to the lease module docstring, and addressing (subprocess-group kill on loss, or pre-side-effect lease re-verification) before Phase 7. |
| WR-03 | Bare `LookupError` / `ValueError` from `apply_transition` and its helpers are not in `_ORCHESTRATION_ERRORS`, so they escape as Typer's default exit 1 (the code D-05 reserves for a persisted FAILED) instead of exit 2. Triggers are narrow (a row vanishes mid-operation / internal inconsistency). | No. The SC-relevant exit codes (clean pause = 0, declined race = 0) are handled correctly. | ⚠️ WARNING — small D-05 exit-code contract gap. Recommend adding `LookupError, ValueError` to `_ORCHESTRATION_ERRORS` (one-line fix in 02-REVIEW.md). |

## Observations (non-blocking)

- **`02-VALIDATION.md` frontmatter is stale**: `status: draft`, `nyquist_compliant: false`, `wave_0_complete: false`. The document was seeded by plan-phase and never advanced to `validated` by `/gsd-validate-phase`. The *substance* it specifies (the per-requirement test map) is fully delivered and is enforced by `tests/integration/test_phase2_acceptance.py`'s drift-guard, so this is a process-hygiene gap, not a coverage gap. Recommend running `/gsd-validate-phase` to reconcile the frontmatter, or note the phase was validated ad hoc.
- **Split commit authorship** on plans 02-04 and 02-07 (rate-limit interruptions, closed out by continuation executors). The pre-existing task commits (`3e46670`, `dc18ef4`, `ca0b3e1`, `3cfc4ec`) were confirmed present in history and sound; not a correctness concern.
- **`deferred-items.md`** records two out-of-scope discoveries correctly bounded to later phases: multi-node `role_executions` row reuse → Phase 3 (config-driven pipeline); `ruff format` on planning-doc code fences → non-source, resolved via `[tool.ruff] extend-exclude`.

## Human Verification Required

Automated criteria hold on static inspection + the acceptance gate + the
`unit`/`contract` tier + `mypy`/`ruff` + executor-recorded `db`/`integration`
runs. The following need human confirmation (routed to `/gsd-verify-work`):

1. **Fresh-eyes README pause/resume walkthrough against real Neon** — legibility judgment; a stranger follows the README literally and pauses+resumes a run with no guessed steps, and the exit-code table makes clean-pause / declined-race unmistakably successes.
2. **Production-scale lease timing (900 s TTL / 300 s heartbeat) against a real Neon PgBouncer endpoint** — kill the owner, confirm no early steal before `lock_expires_at`, then a reclaim after; run a slow step and watch `lock_expires_at` advance. The mechanism is proven at 6 s/2 s (same TTL/3 ratio); production-scale timing is an operator smoke check.
3. **Confirm the 900 s/300 s defaults are acceptable** (up-to-~15-min dead-owner reclaim delay, no force-steal in this phase) — a one-line `Settings` edit if not.
4. **Accept the PostgreSQL 18.6 (not 17) test environment** — operator-approved deviation carried since 01-01; no PostgreSQL was reachable here so the `db`/`integration` tiers were not re-executed by the verifier.

## Gaps Summary

No gaps block the phase goal. Every success criterion has a substantive,
correctly-asserting proof file, mapped and existence-enforced by the acceptance
gate; every phase invariant holds under static inspection and independent code
review; all six requirement ids are covered and marked Complete. The three
02-REVIEW.md Warnings are robustness / contract-consistency items that do not
falsify a Phase 2 success criterion or invariant and are appropriately
Phase-7-scoped. The phase is `human_needed` (not `passed`) solely because the
`db`/`integration` behavioural proofs could not be re-executed in the
verification environment and four genuinely human-observable confirmations
remain outstanding.

---

_Verified: 2026-09-10_
_Verifier: Claude (gsd-verifier)_
