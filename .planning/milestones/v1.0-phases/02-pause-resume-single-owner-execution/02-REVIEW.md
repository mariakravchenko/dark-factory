---
phase: 02-pause-resume-single-owner-execution
reviewed: 2026-09-10T00:00:00Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - .env.example
  - README.md
  - migrations/env.py
  - migrations/versions/0003_pause_resume_lease.py
  - pyproject.toml
  - src/dark_factory/cli.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/domain/interaction.py
  - src/dark_factory/domain/status.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/orchestrator/answers.py
  - src/dark_factory/orchestrator/lease.py
  - src/dark_factory/orchestrator/lifecycle.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/engine.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/workers/fake.py
  - tests/conftest.py
  - tests/contract/test_coding_worker_contract.py
  - tests/db/test_human_interactions_schema.py
  - tests/db/test_lease_claim_atomic.py
  - tests/db/test_lease_lost_aborts_step.py
  - tests/db/test_migrations.py
  - tests/db/test_pause_mechanism_generic.py
  - tests/db/test_pause_path_atomic.py
  - tests/db/test_terminal_advance_noop.py
  - tests/integration/test_exit_codes.py
  - tests/integration/test_fresh_process_resume.py
  - tests/integration/test_heartbeat_slow_step.py
  - tests/integration/test_lease_expiry_reclaim.py
  - tests/integration/test_no_txn_across_worker.py
  - tests/integration/test_pause_exit_zero.py
  - tests/integration/test_phase2_acceptance.py
  - tests/integration/test_redaction_interactions.py
  - tests/integration/test_resume_with_answer.py
  - tests/integration/test_single_owner_race.py
  - tests/support/subprocess_runner.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_lifecycle.py
  - tests/unit/test_persistence.py
  - tests/unit/test_settings.py
  - tests/unit/test_single_mutation_path.py
  - tests/unit/test_workers.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-09-10
**Depth:** standard
**Files Reviewed:** 45
**Status:** issues_found

## Summary

Phase 2 adds pause/resume (`human_interactions` table, `submit_answer`, the
`WAITING_HUMAN` stop status, four new event types) and single-owner execution
(the `runs.owner_token` / `runs.lock_expires_at` lease, `orchestrator/lease.py`,
the `expected_owner_token` fence in `apply_transition`). I reviewed every listed
source and test file, tracing the resume-first `advance`/`drive` path, the lease
lifecycle including the heartbeat thread, the one mutation path, redaction of the
new text columns, and the CLI exit-code contract.

The four project invariants called out for this phase all hold under review:

- **No DB transaction across a worker call.** `_advance_once` closes its read
  session before `_run_current_role` runs the worker and opens the write session
  only for the commit; the heartbeat renews on its own short `with
  session.begin()` block. Verified in code and by `test_no_txn_across_worker.py`.
- **Claim-don't-check single owner.** `claim_lease` is one conditional
  `UPDATE ... RETURNING`; no advisory lock, no `SELECT ... FOR UPDATE SKIP
  LOCKED`. The plain `with_for_update` in `apply_transition` is row locking,
  which PROJECT.md permits.
- **Database clock only.** Every lease expiry value and comparison is a SQL
  expression over `func.now()`; the only process-clock use is the heartbeat's
  `Event.wait` sleep.
- **Credential boundary.** `question` / `answer` reach `redact()` inside
  `_write_human_interaction` at the single mutation-path call site; the child
  process env is an explicit allowlist. Verified by
  `test_redaction_interactions.py` and `test_single_mutation_path.py`.

No BLOCKER/Critical defect was found. The findings below are robustness and
contract-consistency gaps (Warnings) plus quality/latent issues (Info). Several
are explicitly forward-looking: the shipped worker is `FakeWorker` with no side
effects, so some windows that are benign now become load-bearing when real agent
runtimes land in Phase 7+.

## Warnings

### WR-01: A single transient heartbeat-renewal error aborts an in-flight step with no retry

**File:** `src/dark_factory/orchestrator/lease.py:215-231`
**Issue:** `_heartbeat` treats *any* exception from `renew_lease` (dropped
connection, Neon scale-to-zero cold start, momentary DNS/TCP failure) as a lost
lease: it logs, sets `lease_lost`, and returns, permanently stopping renewal for
the life of the `run_lease` context. `_run_current_role` then raises `LeaseLost`
after the worker call, the step is discarded, and the CLI exits 2. But the lease
row in the database is *not* actually lost — `lock_expires_at` is still `ttl`
seconds in the future from the last successful renewal, and the commit-time
token fence would have passed. A one-off network blip on any single beat thus
makes an otherwise-successful long step un-completable, and `engine.py`
deliberately does not wrap this call in `tenacity`. Against a scale-to-zero Neon
endpoint with a multi-role pipeline this is a realistic availability problem.
**Fix:** Distinguish "renewal raised" from "renewal returned False". On an
exception, retry the renewal a bounded number of times within the remaining TTL
before declaring the lease lost; only a renewal that *executes and matches no
row* is an authoritative loss:
```python
def _heartbeat() -> None:
    consecutive_errors = 0
    while not stop.wait(interval):
        hb_session = session_factory()
        try:
            still_ours = renew_lease(hb_session, run_id, token, ttl_seconds=ttl)
        except Exception:
            consecutive_errors += 1
            _log.warning("lease.renew_error", run_id=str(run_id),
                         attempt=consecutive_errors, exc_info=True)
            # give up only once repeated failures have eaten most of the TTL
            if consecutive_errors * interval >= ttl - interval:
                lease_lost.set()
                return
            continue
        finally:
            hb_session.close()
        consecutive_errors = 0
        if not still_ours:
            _log.warning("lease.lost", run_id=str(run_id))
            lease_lost.set()
            return
```

### WR-02: The worker runs outside the lease-validity window; concurrent execution is possible if an owner stalls past its TTL

**File:** `src/dark_factory/orchestrator/runner.py:336-352`
**Issue:** `_run_current_role` calls `worker.execute` / `worker.resume` and only
checks `lease.lease_lost.is_set()` *after* it returns. The worker call itself is
not bounded by lease validity and is not cancellable. If the owning process
stalls (GC pause, `SIGSTOP`, VM pause, or a network partition that also starves
the heartbeat thread) for longer than `lease_ttl_seconds`, a second process
legitimately claims the lease and starts executing the *same* role's worker
while the first process's worker is still running. Durable state is still
protected — when the first process finally returns, the `expected_owner_token`
fence in `apply_transition` rejects its commit (`LeaseLost`, nothing written),
proven by `test_lease_lost_aborts_step.py`. But the project invariant as written
("two processes must not execute the same run simultaneously") is violated for
that window. It is harmless for Phase 2 (`FakeWorker` has no side effects) and
becomes real when Phase 7 introduces credentialled agent subprocesses operating
on a shared worktree.
**Fix:** No change required for Phase 2; record the limitation explicitly and
address before real workers land. Options: check `lease.lease_lost` on a timer
during the worker call and kill the subprocess process-group on loss; or have
the worker adapter re-verify lease ownership immediately before performing any
irreversible side effect. At minimum, add a note to the lease module docstring
that the guarantee is "no concurrent *durable mutation*", not "no concurrent
*execution*".

### WR-03: Uncaught exception types from the mutation path bypass the D-05 exit-code contract

**File:** `src/dark_factory/cli.py:64-74`, `src/dark_factory/persistence/mutations.py:259-261,338-339,391-392`
**Issue:** `_ORCHESTRATION_ERRORS` enumerates the exceptions the CLI converts to
a clean exit-2 diagnostic. `apply_transition` and its helpers can raise
`LookupError` directly — `LookupError(run_id)` when the `runs` row is absent at
lock time, `LookupError(spec.id)` when a `role_executions` row to update is gone,
`LookupError("no WAITING human_interaction for run ...")` in `answer` mode. None
of these is in `_ORCHESTRATION_ERRORS` (note `RunNotFoundError` is a distinct
type raised earlier by the runner, not the bare `LookupError` from
`apply_transition`). If any fires, it escapes `drive` / `submit_answer` as an
unhandled traceback and Typer exits 1 — the code the D-05 contract reserves for
"persisted FAILED", which an operator scripting the contract will misread. The
triggers are narrow (they require a row to vanish mid-operation or an internal
inconsistency), but the contract violation is real.
**Fix:** Either raise a domain error type that is already in
`_ORCHESTRATION_ERRORS` from these sites, or add `LookupError` (and
`ValueError`, raised by the `RoleExecutionWrite` / `HumanInteractionWrite`
guards) to `_ORCHESTRATION_ERRORS`:
```python
_ORCHESTRATION_ERRORS = (
    ConcurrentTransition, IllegalTransitionError, DriveLoopExhausted,
    RunNotFoundError, ScriptExhaustedError, UnknownWorkerError, LeaseLost,
    NotWaitingForHuman, NoPendingInteraction, LookupError, ValueError,
)
```

## Info

### IN-01: `resume <run-id>` without `--answer` on a `WAITING_HUMAN` run is a silent exit-0 no-op

**File:** `src/dark_factory/cli.py:162-196`
**Issue:** When a run is in `WAITING_HUMAN` and the operator runs `resume`
without `--answer`, `_drive_and_exit` → `drive` sees a stop status and returns
immediately; the command prints the run id and the summary block, exits 0, and
gives no hint that an answer is required. An operator who forgot the flag gets
no signal that nothing happened.
**Fix:** After `drive` returns, if `final is RunStatus.WAITING_HUMAN` and no
`--answer` was supplied, emit a one-line stderr hint (`run <id> is waiting for a
human answer; re-run with --answer "..."`). Keep exit 0.

### IN-02: `migrations/env.py` falls back to the pooled `DATABASE_URL` for DDL, contradicting its own rule

**File:** `migrations/env.py:52-56,66-80`
**Issue:** The module docstring says "Never point Alembic at a -pooler host", but
`_URL_ENV_VARS` lists `DATABASE_URL` as the second fallback, so an environment
with only the pooled URL set will silently run migrations through PgBouncer
transaction pooling — the exact failure mode the docstring warns about.
**Fix:** Drop `DATABASE_URL` from the resolution list (keep
`DATABASE_URL_DIRECT` and `DARK_FACTORY_TEST_DATABASE_URL`), or detect a
`-pooler` host in the resolved URL and raise rather than proceed.

### IN-03: The persisted `workflow` snapshot is loaded but never used to reconstruct the pipeline

**File:** `src/dark_factory/persistence/repositories.py:85-92,152-163`, `src/dark_factory/orchestrator/runner.py:194-229`
**Issue:** `RunState.workflow` is populated from `runs.workflow`, but `advance` /
`drive` / `_run_current_role` operate against the `pipeline` argument, which
defaults to the in-process `DEFAULT_PIPELINE` constant. A run created under one
pipeline and resumed by a process with a different `DEFAULT_PIPELINE` (a future
config change, or a version skew between machines in Phase 11) would be driven
against the wrong role list with no detection. Benign now (`DEFAULT_PIPELINE` is
the hardcoded `["BA"]`), but the stored snapshot exists precisely to prevent
this and is currently inert.
**Fix:** When it becomes load-bearing (Phase 3 config), reconstruct the
`Pipeline` from `state.workflow` instead of taking a caller default, or assert
the caller's pipeline shape matches the snapshot and fail loudly on mismatch.

### IN-04: CLI orchestration-error output interpolates exception text without redaction

**File:** `src/dark_factory/cli.py:118-124`
**Issue:** `_report_orchestration_error` writes `f"... ({type(exc).__name__}):
{exc}; ..."` to stderr with no `redact()` pass. None of the current
`_ORCHESTRATION_ERRORS` carries worker-provided or task-derived text (they carry
UUIDs, status names, counters, worker names), so there is no leak today. But the
structlog chain on the advance path *is* redacted, and this stderr path is not —
a future orchestration error that embeds task text or a worker error string
would leak to the console unredacted.
**Fix:** Route the message through the same
`redact(..., known_secrets=get_settings().known_secret_values())` partial the
`status --json` path already builds, or keep the interpolation to
`type(exc).__name__` plus the run id only.

### IN-05: `interaction_status` enum is defined twice with a manual "byte-for-byte" contract

**File:** `src/dark_factory/persistence/models.py:81-88`, `migrations/versions/0003_pause_resume_lease.py:47-55`
**Issue:** `_INTERACTION_STATUS` is constructed independently in the model and in
migration 0003, each carrying a comment that it "must stay byte-for-byte
equivalent" to the other. Drift is caught only by
`test_migrations.py::test_alembic_check_reports_no_drift_between_orm_and_schema`,
which requires a live database. This mirrors the pre-existing `_RUN_STATUS`
pattern, so it is consistent with the codebase, but it is duplication of a
security/schema-relevant constant.
**Fix:** Optionally import the shared `sa.Enum` factory from a single module used
by both the model and the migration, so the two cannot diverge without a code
change.

### IN-06: `run_lease.__exit__` can return before the heartbeat thread has actually stopped

**File:** `src/dark_factory/orchestrator/lease.py:239-250`
**Issue:** `thread.join(timeout=_JOIN_TIMEOUT_SECONDS)` (5 s) can return while the
daemon heartbeat is still blocked inside a slow `renew_lease` round-trip (Neon
cold start, or a TCP timeout measured in tens of seconds). `__exit__` then runs
`release_lease` on a fresh session concurrently with the still-live heartbeat's
`renew_lease` on its own session. The outcome is benign in all interleavings
(both are token-guarded single-statement `UPDATE`s; the zombie renew either
matches no row and returns False, or pushes an expiry that a subsequent claim
still overrides), and the thread is a daemon so it cannot outlive the process.
**Fix:** Acceptable as-is; if tightening is wanted, have the heartbeat use a
short `statement_timeout` on its session so a stuck renew cannot outlast the
join window, or log at warning level when `thread.is_alive()` is still true
after the join.

---

_Reviewed: 2026-09-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
