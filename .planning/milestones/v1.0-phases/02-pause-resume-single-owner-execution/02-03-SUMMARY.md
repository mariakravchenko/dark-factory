---
phase: 02-pause-resume-single-owner-execution
plan: 03
subsystem: orchestration
tags: [postgres, lease, pause-resume, sqlalchemy, threading, structlog, typer, tdd]

requires:
  - phase: 02-01
    provides: "human_interactions table + partial unique index; runs.owner_token / runs.lock_expires_at columns; Alembic 0003; InteractionStatus enum"
  - phase: 02-02
    provides: "WAITING_HUMAN in STOP_STATUSES; the four Phase-2 EventType members; Settings.lease_ttl_seconds / lease_heartbeat_seconds; slow FakeWorker; tests/support/subprocess_runner.py; use_lease_settings / force_lease_expiry fixtures"
  - phase: 01
    provides: "the one mutation path (apply_transition); resume-first advance/drive; load_run_state; the CodingWorker.resume port; the two-real-process test harness; DARK_FACTORY_CRASH_AFTER"
provides:
  - "orchestrator/lease.py — claim-don't-check Postgres lease: claim_lease / renew_lease / release_lease + the run_lease context manager owning a daemon heartbeat thread"
  - "orchestrator/answers.py — submit_answer: the one guarded transition out of WAITING_HUMAN"
  - "apply_transition extended with expected_owner_token (LeaseLost fence) and human_interaction (HumanInteractionWrite ask/answer); lease columns cleared on any stop-status transition"
  - "repositories: LatestExecution.result, RunState.pending_answer, pending_question()"
  - "lifecycle: the ROLE_NEEDS_INPUT -> WAITING_HUMAN arm (role retained); WAITING_HUMAN explicitly illegal to leave"
  - "runner: advance/drive claim the lease once, early-return on the whole STOP set, dispatch execute-vs-resume off the persisted RESUMING marker, pause on the needs-input signal (never a role name), abort on lease-loss before any write"
  - "cli: resume --answer; exit 0 for COMPLETED or WAITING_HUMAN; exit 0 + notice when another process owns the run"
  - "SC1 + SC2 proven across a real process boundary"
affects: ["02-04", "02-05", "02-06", "02-07", "phase-10-webhook-resume", "phase-11-cross-machine-resume"]

actuals:
  tokens: 18000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "claim-don't-check ownership: one conditional UPDATE ... RETURNING; no FOR UPDATE / advisory lock / row-skip clause layered on top"
    - "DB-clock-only expiry: every lease value is func.now() + timedelta(...); every comparison is lock_expires_at < func.now(); no process clock in a correctness decision"
    - "lease as a context manager: __exit__ always stops the heartbeat, joins, best-effort releases — on every exit path"
    - "one Session per thread: the heartbeat opens its own session via the factory, never shares the caller's"
    - "column-driven execute-vs-resume: the RESUMING marker on the persisted role-execution row is the decision, survives a crash between storing the answer and dispatching"
    - "token fence in the one mutation path: apply_transition compares expected_owner_token against the already-locked runs row — a free correct fence, no second select"
    - "atomic lease release: the clear lives in apply_transition (stop-status branch), so a crash between 'run is WAITING_HUMAN' and 'lease is free' is impossible"

key-files:
  created:
    - "src/dark_factory/orchestrator/lease.py"
    - "src/dark_factory/orchestrator/answers.py"
    - "tests/integration/test_pause_exit_zero.py"
    - "tests/integration/test_resume_with_answer.py"
  modified:
    - "src/dark_factory/persistence/mutations.py"
    - "src/dark_factory/persistence/repositories.py"
    - "src/dark_factory/orchestrator/lifecycle.py"
    - "src/dark_factory/orchestrator/runner.py"
    - "src/dark_factory/cli.py"
    - "tests/unit/test_lifecycle.py"
    - "tests/db/test_terminal_advance_noop.py"
    - "tests/integration/test_exit_codes.py"
    - "tests/integration/test_fresh_process_resume.py"

key-decisions:
  - "submit_answer checks run status / pending question BEFORE claiming the lease (plan prose said lease-first). Lease-first makes a terminal or non-waiting run raise LeaseNotAcquired (exit 0) where the plan's own truths and the CLI acceptance criteria require NotWaitingForHuman (exit 2). The lease still wraps the mutating transition; a race between the pre-check and the claim is caught by a re-read inside the lease and ultimately by apply_transition's expected_status guard."
  - "LeaseNotAcquired carries `.observed_status` (not `.status`) so the AST single-mutation-path guard — which flags any `.status =` assignment outside mutations.py — stays green."
  - "role_executions.status markers are the literal strings WAITING_HUMAN and RESUMING (A5): the column is an unconstrained VARCHAR(32), so only the values are a choice."
  - "run_lease heartbeat thread uses stop_event.wait(interval) so it wakes immediately on shutdown; __exit__ joins with a 5s bound then best-effort releases, swallowing+logging a release failure rather than masking the body's exception."

patterns-established:
  - "claim-don't-check Postgres lease (single conditional UPDATE ... RETURNING)"
  - "context-managed lease + daemon heartbeat with a guaranteed __exit__ teardown"
  - "column-driven resume dispatch (persisted RESUMING marker, zero in-memory carryover)"
  - "token fence folded into the existing single mutation transaction"

requirements-completed: []

coverage:
  - id: D1
    description: "A role whose worker returns NEEDS_INPUT leaves the run in WAITING_HUMAN with the worker result, the worker session id and the current role persisted, exactly one WAITING human_interactions row, QUESTION_CREATED then RUN_PAUSED in the audit trail, both lease columns NULL, and the process exits 0 (SC1, HITL-02)"
    requirement: "HITL-02"
    verification:
      - kind: integration
        ref: "tests/integration/test_pause_exit_zero.py::test_run_pauses_persists_all_five_writes_releases_the_lease_and_exits_zero"
        status: pass
      - kind: db
        ref: "tests/db/test_terminal_advance_noop.py::test_advance_on_a_waiting_run_writes_nothing_and_never_calls_the_worker"
        status: pass
    human_judgment: false
  - id: D2
    description: "dark-factory resume <run-id> --answer \"...\" from a brand-new process continues the same role execution and the same attempt to a terminal state, creates no second run, needs nothing from the original process; a second answer / a non-waiting run exit 2 with 'not waiting' (SC2, HITL-03)"
    requirement: "HITL-03"
    verification:
      - kind: integration
        ref: "tests/integration/test_resume_with_answer.py (3 tests: fresh-process resume, non-waiting exits 2, second answer exits 2)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The only pause mechanism is a NEEDS_INPUT worker result; the runner branches on the signal, never on a role name (HITL-01)"
    requirement: "HITL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_legal_transitions_produce_documented_next_state[ROLE_NEEDS_INPUT arm, both pipelines]"
        status: pass
      - kind: integration
        ref: "tests/integration/test_pause_exit_zero.py (BA role pauses with no BA-specific code path)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Ownership is claimed by one conditional UPDATE that returns the claiming row; a process that gets no row back exits 0 having mutated nothing; the lease module has no process-clock read and no second coordination primitive (HITL-07 mechanism)"
    requirement: "HITL-07"
    verification:
      - kind: other
        ref: "grep -v '^#' src/dark_factory/orchestrator/lease.py | grep -c 'datetime\\.now\\|datetime\\.utcnow' == 0 ; ...'pg_advisory\\|SKIP LOCKED\\|skip_locked' == 0"
        status: pass
      - kind: integration
        ref: "tests/integration/test_fresh_process_resume.py::test_killed_after_first_commit_then_resumed_by_a_separate_process (stale lease blocks reclaim until expiry, then a fresh process reclaims)"
        status: pass
    human_judgment: true
    rationale: "The two-live-process race proof (two claims, one winner, loser exits 0, exactly one ROLE_COMPLETED) lands in 02-04. This plan ships the mechanism; its adversarial proof is a downstream deliverable."
  - id: D5
    description: "No DB transaction spans the worker call; the lease is a column with a DB-clock expiry renewed by a daemon thread on its own session; the heartbeat is always stopped on every context-manager exit (HITL-08 mechanism)"
    requirement: "HITL-08"
    verification:
      - kind: integration
        ref: "tests/integration/test_pause_exit_zero.py + test_resume_with_answer.py (run_lease wraps the loop; worker call is outside every session.begin())"
        status: pass
    human_judgment: true
    rationale: "The pg_stat_activity 'idle in transaction' == 0 assertion and the slow-step heartbeat proof land in 02-05. This plan ships the shape; its instrumented proof is downstream."

duration: 95min
completed: 2026-09-09
status: complete
---

# Phase 2 Plan 03: Pause, Resume & Single-Owner Execution (the tracer slice) Summary

**A durable run now stops mid-role to ask a human a question, releases its process cleanly under a claim-don't-check Postgres lease, and is resumed to completion — same attempt, no second run — by a brand-new `dark-factory resume <id> --answer "..."` process that has nothing but the run id and the database.**

## Performance

- **Duration:** ~95 min
- **Started:** 2026-09-09
- **Completed:** 2026-09-09
- **Tasks:** 2 (Task 1 = tracer, TDD; Task 2 = database-free coverage)
- **Files modified:** 13 (4 created, 9 modified)

## Accomplishments

- **`orchestrator/lease.py`** (new) — `claim_lease` is one `UPDATE runs SET owner_token=…, lock_expires_at=func.now()+interval, updated_at=func.now() WHERE id=… AND status NOT IN (terminal) AND (owner_token IS NULL OR lock_expires_at < func.now()) RETURNING id`. `renew_lease` / `release_lease` are token-fenced one-statement updates. `run_lease` is a `contextlib.contextmanager` that claims through a short-lived session, raises `LeaseNotAcquired` (with the run id and observed status) when nothing comes back, starts one daemon heartbeat thread that renews on **its own** session and sets a `lease_lost` `Event` if a renewal matches no row, and whose `__exit__` — on every path — stops the thread, joins it (5 s bound), and best-effort releases.
- **`orchestrator/answers.py`** (new) — `submit_answer(run_id, answer)` validates preconditions, then inside `run_lease` performs exactly one `apply_transition`: `WAITING_HUMAN → <retained role>`, the same role-execution row marked `RESUMING`, the `WAITING` interaction filled in (`answer`, `ANSWERED`, `answered_at=func.now()`), and `HUMAN_ANSWER_RECEIVED` then `RUN_RESUMED`. Constructs no ORM row itself.
- **`persistence/mutations.py`** — `apply_transition` gains `expected_owner_token` (raises `LeaseLost` against the already-locked `runs` row — a free fence) and `human_interaction: HumanInteractionWrite` (`ask` inserts the `WAITING` row, `answer` locates the run's single `WAITING` row inside the transaction and fills it). On any transition into a stop status it clears both lease columns — atomic with the state change. `question` / `answer` flow through the same `redact()` call site as every result/error/payload.
- **`persistence/repositories.py`** — `LatestExecution.result`, `RunState.pending_answer` (the `ANSWERED` interaction bound to the latest attempt), `pending_question()`.
- **`orchestrator/lifecycle.py`** — one arm: `ROLE_NEEDS_INPUT → WAITING_HUMAN`, role retained. `WAITING_HUMAN` is explicitly rejected for every signal (leaving it is `submit_answer`'s job). Still pure — imports nothing from `dark_factory.persistence`.
- **`orchestrator/runner.py`** — the per-step body is a private `_advance_once` that assumes the lease is held. `advance` pre-reads and returns for the whole `STOP` set without claiming, else claims once for its single step; `drive` returns immediately for a stopped run, else claims once for the whole loop. `_run_current_role` reads the persisted `RESUMING` marker to call `worker.resume(context, previous, answer)` instead of `worker.execute`, checks `lease.lease_lost` immediately after the worker returns (discard + `LeaseLost`, write nothing), and pauses on the needs-input **signal** with a `QUESTION_CREATED`/`RUN_PAUSED` pair and an `ask` `HumanInteractionWrite`. Every `apply_transition` call passes `expected_owner_token=lease.token`. `_build_context` gains `"answer"`.
- **`cli.py`** — `resume --answer` routes through `submit_answer` before the drive loop; `_drive_and_exit` exits **0** for `COMPLETED` **or** `WAITING_HUMAN`; `LeaseNotAcquired` is caught first and exits **0** with a stderr notice naming the run; `LeaseLost` / `NotWaitingForHuman` / `NoPendingInteraction` join the exit-2 orchestration-error tuple.

## Task Commits

1. **Task 1 (tracer, TDD) — RED:** `e6b9739` (test) — failing `test_pause_exit_zero.py` + `test_resume_with_answer.py` (4 tests: pause exits 2 on `IllegalTransitionError`, `--answer` is not an option yet).
2. **Task 1 — GREEN:** `360f594` (feat) — `lease.py`, `answers.py`, the `mutations` / `repositories` / `lifecycle` / `runner` / `cli` changes; 4/4 integration tests pass, mypy `--strict` clean, both `lease.py` invariant greps return 0. (No REFACTOR commit — the GREEN implementation was already at target shape.)
3. **Task 2 (database-free coverage):** `90bf6cb` (test) — `test_lifecycle.py` legal/illegal tables gain the needs-input edge and the `WAITING_HUMAN`-is-illegal rows; `test_terminal_advance_noop.py` gains the `WAITING_HUMAN` no-op sibling + two drive-loop cases.
4. **Deviation fix (Rule 1):** `487f45d` (test) — `test_fresh_process_resume.py` forces the stale lease to expire before the SC2 crash-resume, since the hard-killed process never releases it.

**Plan metadata:** _(this commit)_ — SUMMARY.md, STATE.md, ROADMAP.md.

## Files Created/Modified

- `src/dark_factory/orchestrator/lease.py` — the claim-don't-check lease + `run_lease` context manager + heartbeat.
- `src/dark_factory/orchestrator/answers.py` — `submit_answer`, `NotWaitingForHuman`, `NoPendingInteraction`.
- `src/dark_factory/persistence/mutations.py` — `LeaseLost`, `HumanInteractionWrite`, `apply_transition` params, `_write_human_interaction`, lease-clear on stop.
- `src/dark_factory/persistence/repositories.py` — `LatestExecution.result`, `RunState.pending_answer`, `pending_question`.
- `src/dark_factory/orchestrator/lifecycle.py` — the needs-input arm; `WAITING_HUMAN` illegal to leave.
- `src/dark_factory/orchestrator/runner.py` — `_advance_once`, lease-wrapped `advance`/`drive`, execute-vs-resume, needs-input branch, lease-loss abort.
- `src/dark_factory/cli.py` — `resume --answer`, exit-code mapping, `LeaseNotAcquired` handling.
- `tests/integration/test_pause_exit_zero.py` (new) — SC1 proof.
- `tests/integration/test_resume_with_answer.py` (new) — SC2 proof + two negative cases.
- `tests/unit/test_lifecycle.py` — needs-input edge in the legal graph; `WAITING_HUMAN` illegal for every signal; parametrised purity.
- `tests/db/test_terminal_advance_noop.py` — `WAITING_HUMAN` zero-write no-op + drive-loop stop cases.
- `tests/integration/test_exit_codes.py` — orchestration-error case repointed (deviation).
- `tests/integration/test_fresh_process_resume.py` — force lease expiry before crash-resume (deviation).

## Recorded interface (for 02-04..02-07 to assert against)

```
claim_lease(session: Session, run_id: UUID, *, ttl_seconds: int) -> UUID | None
renew_lease(session: Session, run_id: UUID, token: UUID, *, ttl_seconds: int) -> bool
release_lease(session: Session, run_id: UUID, token: UUID) -> None
run_lease(run_id: UUID, *, session_factory: Callable[[], Session] = new_session,
          ttl_seconds: int | None = None, heartbeat_seconds: int | None = None)
          -> Iterator[LeaseHandle]                      # contextlib.contextmanager
submit_answer(run_id: UUID, answer: str, *,
              session_factory: Callable[[], Session] = new_session) -> RunStatus

apply_transition(session, *, run_id, expected_status, next_status,
                 next_current_role, next_current_step,
                 role_execution: RoleExecutionWrite | None = None,
                 events: Sequence[EventWrite] = (),
                 counter_increments: Mapping[str, int] | None = None,
                 expected_owner_token: UUID | None = None,
                 human_interaction: HumanInteractionWrite | None = None) -> RunStatus
```

- `HumanInteractionWrite` (frozen, `extra="forbid"`): `mode: Literal["ask","answer"]`, `role_execution_id: UUID | None = None`, `question: str | None = None`, `answer: str | None = None`.
- `LeaseHandle` (frozen dataclass): `token: UUID`, `lease_lost: threading.Event`.
- `LeaseNotAcquired(RuntimeError)`: `.run_id: UUID`, `.observed_status: str | None`.
- `role_executions.status` markers added: **`"WAITING_HUMAN"`**, **`"RESUMING"`** (unconstrained VARCHAR(32); values only).
- Transition graph as implemented:
  `CREATED --ENTER--> <first role>` · `<role> --ROLE_COMPLETED--> <next role | COMPLETED>` ·
  `<role> --ROLE_FAILED--> FAILED (role retained)` · `<role> --ROLE_NEEDS_INPUT--> WAITING_HUMAN (role retained)` ·
  every `(WAITING_HUMAN, *)` and every `(terminal, *)` pair is `IllegalTransitionError`.
- CLI exit codes (`run` / `resume`): `0` = reached `COMPLETED` **or** `WAITING_HUMAN`; `1` = reached `FAILED`;
  `2` = orchestration error, nothing new persisted (`LeaseLost`, `NotWaitingForHuman`, `NoPendingInteraction`,
  `ConcurrentTransition`, `IllegalTransitionError`, `DriveLoopExhausted`, `RunNotFoundError`,
  `ScriptExhaustedError`, `UnknownWorkerError`) **or** bad invocation (unknown run id, bad uuid, unresolvable
  source); `0` + stderr notice = `LeaseNotAcquired` (another process owns the run).

## TDD cycle (Task 1)

- **RED** (`e6b9739`): both new integration files fail on behaviour, not collection — the pause process exits 2 with `IllegalTransitionError: no transition from BA on ROLE_NEEDS_INPUT`, and `resume --answer` fails Typer arg parsing (`--answer` unknown). Target tests, planned assertions.
- **GREEN** (`360f594`): implemented all seven source files; `pytest -m integration tests/integration/test_pause_exit_zero.py tests/integration/test_resume_with_answer.py` → 4 passed; `mypy --strict src/dark_factory` clean; `grep` invariants on `lease.py` both 0.
- **REFACTOR:** none — no `refactor(02-03)` commit. The GREEN implementation matched the plan's target shape (private `_advance_once`, one clock domain, context-managed lease); no cleanup pass changed behaviour.

## Tracer feedback gate

Task 1 is `type="tracer"`. Its `<verify>` block is automated-only (no `<human-check>`, no `gate="blocking-human"`) and `workflow.human_verify_mode` is `end-of-phase`, so per the precedence chain the tracer `<verify>` was **re-run end to end** after the GREEN commit: `test_pause_exit_zero.py` + `test_resume_with_answer.py` → 4 passed (148 s), plus the two `lease.py` greps (0/0) and `mypy --strict` (clean). All green → `⚡ Tracer verified end-to-end — expanding` → proceeded to Task 2. No human checkpoint synthesised.

## Decisions Made

See `key-decisions` frontmatter. The load-bearing one: **`submit_answer` checks status/pending-question before claiming the lease.** The plan's prose described lease-first, but lease-first turns "answer a run that already completed" and "answer twice" into `LeaseNotAcquired` (a terminal run fails `claim_lease`'s `status NOT IN (terminal)` predicate) → CLI exit 0, contradicting the plan's own truth ("`submit_answer` on a run that is not in `WAITING_HUMAN` raises `NotWaitingForHuman`, writes nothing") and its acceptance criterion ("`resume --answer` against a run that is not in the waiting status exits 2 and its stderr contains `not waiting`"). The lease still wraps the mutating `apply_transition`; a concurrent second answerer still loses at the lease and gets `LeaseNotAcquired`; a race between the pre-check and the claim is caught by a re-read inside the lease and finally by the `expected_status` guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `submit_answer` precondition ordering vs the lease**
- **Found during:** Task 1 (GREEN — `test_resume_with_answer.py` negative cases)
- **Issue:** The plan's `answers.py` prose opens `run_lease` *then* loads state. A terminal or otherwise non-`WAITING_HUMAN` run fails `claim_lease`'s `status NOT IN ('COMPLETED','FAILED')` predicate, so `run_lease` raises `LeaseNotAcquired` → CLI exit 0 — but the plan's truths and acceptance criteria require `NotWaitingForHuman` → exit 2 with "not waiting", and "the answer is accept-once".
- **Fix:** `submit_answer` does a lease-free read first (`RunNotFoundError` / `NotWaitingForHuman` / `NoPendingInteraction`), then opens `run_lease` and re-reads inside it before the single `apply_transition`. Race semantics preserved (concurrent answerers still collide at the lease; the `expected_status` guard is still the final authority).
- **Files modified:** `src/dark_factory/orchestrator/answers.py`
- **Verification:** `test_resume_with_answer.py::test_resume_answer_against_a_non_waiting_run_exits_two` and `::test_a_second_answer_for_the_same_pause_is_rejected` pass.
- **Committed in:** `360f594` (Task 1 GREEN)

**2. [Rule 1 - Bug] `test_exit_codes.py` orchestration-error case pinned on the now-obsolete NEEDS_INPUT behaviour**
- **Found during:** Task 1 (GREEN — full suite)
- **Issue:** `test_orchestration_error_exits_2_with_a_diagnostic_not_a_traceback` drove a scripted `NEEDS_INPUT` result expecting `IllegalTransitionError` → exit 2. Phase 2 makes that a clean pause → exit 0, so the test would fail.
- **Fix:** Repointed at an empty fake script (`DARK_FACTORY_FAKE_SCRIPT=[]` → `FakeWorker` exhausts immediately → `ScriptExhaustedError`, still one of `_ORCHESTRATION_ERRORS`). The test's intent (an orchestration error surfaces as exit 2 with a one-line diagnostic, never a traceback) is preserved.
- **Files modified:** `tests/integration/test_exit_codes.py`
- **Verification:** test passes in the full-suite run.
- **Committed in:** `360f594` (Task 1 GREEN)

**3. [Rule 1 - Bug] `LeaseNotAcquired.status` tripped the single-mutation-path AST guard**
- **Found during:** Task 1 (GREEN — `tests/unit/test_single_mutation_path.py`)
- **Issue:** `tests/unit/test_single_mutation_path.py` flags **any** `.status = …` assignment outside `persistence/mutations.py`. `LeaseNotAcquired.__init__` stored `self.status = status`.
- **Fix:** Renamed the attribute to `self.observed_status` (and the parameter to `observed_status`). Nothing reads it yet; the constructor message is unchanged in substance.
- **Files modified:** `src/dark_factory/orchestrator/lease.py`
- **Verification:** `test_single_mutation_path.py` passes (2 passed).
- **Committed in:** `360f594` (Task 1 GREEN)

**4. [Rule 1 - Bug] Phase 1 SC2 crash-resume regressed under the new lease**
- **Found during:** Full `<verification>` suite run (post Task 2)
- **Issue:** `test_fresh_process_resume.py::test_killed_after_first_commit_then_resumed_by_a_separate_process` — the first process is hard-killed with `os._exit`, so `run_lease.__exit__` never runs and its lease sits held with a ~900 s expiry. The second process's `claim_lease` correctly returns nothing and it exits 0 ("owned by another process") without driving the run.
- **Fix:** The test now calls the shared `force_lease_expiry` fixture (a server-clock `UPDATE lock_expires_at = now() - interval '1 second'`) between verifying the crashed intermediate state and spawning the resumer — the deterministic stand-in for waiting out the TTL, and exactly the mechanism the dedicated reclaim proofs in 02-04 / 02-05 use. Test intent unchanged (same run, same attempt, no second run, reached `COMPLETED` by a fresh process).
- **Files modified:** `tests/integration/test_fresh_process_resume.py`
- **Verification:** `pytest tests/integration/test_fresh_process_resume.py` → 3 passed.
- **Committed in:** `487f45d`

---

**Total deviations:** 4 auto-fixed (all Rule 1). Three are test-only (`test_exit_codes.py`, `test_fresh_process_resume.py`, and the `LeaseNotAcquired` attribute rename motivated by the AST guard); one is a source ordering fix in `answers.py` that makes the plan's own truths and acceptance criteria hold.
**Impact on plan:** No scope creep. Every fix keeps a stated success criterion true. The `answers.py` ordering is the only behavioural departure from the plan prose and is documented as a key decision.

## Issues Encountered

- Full suite runs ~16.5 min against the shared Neon endpoint (db + integration tiers). One failure surfaced (deviation #4) and was fixed; re-verified in isolation (3 passed). All other 309 tests passed in the full run.

## Verification results

| Check | Result |
|---|---|
| `pytest -q` (full suite, all markers) | 310 passing — 309 green in the 16m29s full run + the 1 regression (deviation #4) fixed and re-verified `tests/integration/test_fresh_process_resume.py` → 3 passed |
| `mypy src/dark_factory` (`--strict`) | Success: no issues found in 39 source files |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 9 files reported — **all outside scope** (`.claude/gsd-core/templates/*.md`, pre-existing `.planning/phases/01-*/*-SUMMARY.md` code fences); **0 files under `src/` or `tests/`**. Logged to `deferred-items.md`. |
| `grep -v '^#' src/dark_factory/orchestrator/lease.py \| grep -c 'datetime\.now\|datetime\.utcnow'` | `0` |
| `grep -v '^#' src/dark_factory/orchestrator/lease.py \| grep -c 'pg_advisory\|SKIP LOCKED\|skip_locked'` | `0` |
| Task 1 `<verify>` (integration pair + greps + mypy) | pass (re-run for the tracer gate) |
| Task 2 `<verify>` (unit lifecycle/enums + db terminal-advance-noop) | 35 unit + 6 db passed |
| Manual end-to-end walk | Not executed by the executor (subprocess proofs cover it); the phase `<human-check>` for operator legibility is deferred to `/gsd-verify-work`. |

## Known Stubs

None. Every path is wired: the lease claims/renews/releases against real rows, `submit_answer` performs a real `apply_transition`, the resume dispatch reads a real persisted column, and both SC proofs run real processes end to end.

## Requirements status (shared-ID gate)

The plan's `requirements: [HITL-01, HITL-02, HITL-03, HITL-07, HITL-08]` all remain **Pending** in `REQUIREMENTS.md`: every one is also owed by a downstream plan in this phase —
HITL-01 (02-06, 02-07), HITL-02 (02-06, 02-07), HITL-03 (02-07), HITL-07 (02-04, 02-05, 02-07), HITL-08 (02-05, 02-07).
This plan ships and proves the **mechanism** for each (SC1 + SC2 end to end); the adversarial / instrumented proofs (two-process race, expiry reclaim, `idle in transaction` == 0, slow-step heartbeat, generic-mechanism sweep, redaction sweep, phase acceptance) are 02-04 through 02-07, and 02-07 marks the IDs complete.

## Next Phase Readiness

- **02-04** (race + reclaim): `claim_lease` / `run_lease` / `expected_owner_token` are in place; `force_lease_expiry` and the two-real-process harness are proven usable against the lease.
- **02-05** (heartbeat + no-txn): the daemon heartbeat renews on its own session with `application_name="dark-factory"` already on the engine; `DARK_FACTORY_FAKE_SLEEP_MS` + `use_lease_settings` are ready.
- **02-06** (generic mechanism + redaction): the needs-input branch keys off the signal only; `question`/`answer` already pass through the one `redact()` call site — the sweep just needs to assert it.
- **02-07** (phase acceptance): every symbol, marker string and exit code is recorded above for the acceptance gate to assert.

---
*Phase: 02-pause-resume-single-owner-execution*
*Completed: 2026-09-09*

## Self-Check: PASSED

- All created files present on disk: `orchestrator/lease.py`, `orchestrator/answers.py`, `tests/integration/test_pause_exit_zero.py`, `tests/integration/test_resume_with_answer.py`, `02-03-SUMMARY.md`, `deferred-items.md`.
- All task commits present in history: `e6b9739` (RED), `360f594` (GREEN), `90bf6cb` (Task 2), `487f45d` (deviation #4 fix).
