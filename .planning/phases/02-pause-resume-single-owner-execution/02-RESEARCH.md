# Phase 2: Pause, Resume & Single-Owner Execution - Research

**Researched:** 2026-09-09
**Domain:** Durable orchestration — PostgreSQL leases, single-owner execution, pause/resume, no transaction across a subprocess call
**Confidence:** HIGH (pattern + codebase), MEDIUM (concrete TTL/heartbeat numbers — see Assumptions Log)

## Summary

Phase 2 adds three things to the Phase 1 walking skeleton, all of them pure orchestration/persistence — no AI, no GitHub, no git, no UI, and **no new third-party dependency**. First, a `human_interactions` table plus a generic pause path: any role that returns `WorkerResult(status=NEEDS_INPUT, questions=[…])` is turned by the orchestrator into a `WAITING_HUMAN` run, with the worker result, the `worker_session_id`, the current role, the question, and two new audit events all committed in the single existing mutation transaction. Second, a Postgres lease on `runs` (`owner_token` uuid + `lock_expires_at` timestamptz) claimed with one conditional `UPDATE … WHERE (owner_token IS NULL OR lock_expires_at < now()) RETURNING …` — "claim-don't-check": the process that gets a row back is the sole owner, the process that gets zero rows exits 0 without mutating. Third, a daemon heartbeat thread that renews `lock_expires_at = now() + ttl` while the worker subprocess runs outside any transaction, so a legitimately slow step is never falsely stolen, while a dead owner's lease simply expires and the next process reclaims it.

The load-bearing invariants are already anticipated in the Phase 1 code: `STOP_STATUSES` is a named constant kept separate from `TERMINAL_STATUSES` precisely so Phase 2 adds `WAITING_HUMAN` to one of them `[VERIFIED: src/dark_factory/domain/status.py:35-42]`; `Signal.ROLE_NEEDS_INPUT` and the `NEEDS_INPUT → ROLE_NEEDS_INPUT` mapping already exist but are unhandled by the runner `[VERIFIED: src/dark_factory/domain/signal.py:24-35]`; the `CodingWorker.resume(context, previous, answer)` method already ships and `FakeWorker` implements it `[VERIFIED: src/dark_factory/workers/base.py:23-27]` `[VERIFIED: src/dark_factory/workers/fake.py:73-76]`; `apply_transition` already opens exactly one `with session.begin()` block and already row-locks `runs` with `with_for_update=True` `[VERIFIED: src/dark_factory/persistence/mutations.py:199-206]`. The phase is mostly "extend the one mutation path, add one table + one migration, add the lease claim/heartbeat/release around the drive loop, teach `advance` execute-vs-resume, add `--answer` to the existing `resume` command."

**Primary recommendation:** Add lease columns + `human_interactions` in Alembic revision `0003`; make `apply_transition` (a) fence every write on `expected_owner_token` and (b) clear the lease columns whenever `next_status` is a stop status; wrap the `drive()` body (and a directly-called `advance()`) in a `run_lease(run_id)` context manager that claims via conditional `UPDATE … RETURNING`, runs a `threading.Thread` heartbeat every `TTL/3`, and releases on exit; handle `Signal.ROLE_NEEDS_INPUT` generically in `_run_current_role`; add `submit_answer(run_id, answer)` and route `dark-factory resume <id> --answer "…"` through it before re-entering the same `drive()` loop. Recommended MVP numbers: **lease TTL 900 s, heartbeat 300 s (TTL/3), both from `Settings` so tests inject 2 s / 1 s.** All time comparisons use PostgreSQL `now()`, never a Python clock.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Single-owner enforcement | Persistence (Neon — conditional `UPDATE … RETURNING`) | Orchestrator (claim call sites) | Postgres row-level write atomicity *is* the lock; no in-process lock is authoritative or survives `kill -9` |
| Lease expiry / "is the owner alive" | Persistence (`now()` on the server) | — | Only the database clock is shared across machines (Phase 11); a process clock cannot arbitrate |
| Lease renewal (heartbeat) | Orchestrator (daemon thread + its own Session) | Persistence (`UPDATE … WHERE owner_token = :tok`) | Liveness is a property of the owning process — it must actively prove it |
| Pause decision (`NEEDS_INPUT` → `WAITING_HUMAN`) | Orchestrator (`lifecycle.transition`) | Worker (emits the typed signal only) | ORCH-05 / cross-cutting invariant: a worker result is a typed signal, never a transition |
| Question + answer persistence | Persistence (`human_interactions` via the one mutation path) | Orchestrator | STATE-04 + ORCH-06: same single transaction as the status change |
| Answer intake | CLI trigger (`resume --answer`) | Orchestrator (`submit_answer`) | Triggers carry no lifecycle logic (TRIG-01 direction of travel) |
| Resume re-dispatch | Orchestrator (`advance` → `worker.resume`) | Worker (native session or context reconstruction) | Orchestrator issues the identical `worker.resume(...)` call regardless of runtime |
| Context rebuild for the resumed role | Orchestrator (`_build_context` from columns + the stored answer) | Persistence (`load_run_state`) | Cross-cutting invariant: every resume input is a persisted column, zero in-memory carryover |

## Project Constraints (from CLAUDE.md)

These have the same authority as locked decisions. Research does not propose anything that contradicts them.

- **Stack is fixed:** Python 3.12 (`requires-python = ">=3.12"` `[VERIFIED: pyproject.toml:9]`), Neon PostgreSQL, SQLAlchemy 2.0 **synchronous** API, Alembic, psycopg 3 (`postgresql+psycopg://`). No async core — explicitly out of scope.
- **Treat Neon as plain Postgres:** `DATABASE_URL` only; no `neon`-specific import or hostname in application code (STATE-01).
- **No separate distributed-lock service** (no Redis/etcd/ZooKeeper/Consul). Concurrency only via `UPDATE … WHERE`, `SELECT … FOR UPDATE`, `pg_advisory_xact_lock`.
- **No Temporal / Celery / broker / arbitrary-DAG engine.** "Resume" is an externally-triggered call into the same deterministic `advance(run_id)` entrypoint; the DB claim decides ownership.
- **One mutation path, one transaction:** every lifecycle mutation (store result, transition state, **create interaction**, emit event) commits in ONE transaction through `persistence/mutations.py`. `tests/unit/test_single_mutation_path.py` is an AST guard that fails if any other module constructs `RunEvent` / `RoleExecution` (Phase 2: extend it to also cover `HumanInteraction`).
- **A database transaction is never held open across a subprocess call** (HITL-08, cross-cutting invariant from this phase). `txn { load } → (no DB) worker.execute()/resume() → txn { apply_transition }`.
- **Claim-don't-check concurrency:** conditional `UPDATE` lease + guarded status update. All expiry checks use the database clock, never a process clock.
- **Redaction is not retrofitted:** new persisted fields (question text, answer text, worker results) must flow through the existing `redact()` / `scrub_known_values()` call site inside `mutations.py` and the `structlog` processor (SEC-01, SEC-02).
- **Neon connection shape (already implemented, do not regress):** `poolclass=NullPool`, `pool_pre_ping=True`, `connect_args={"prepare_threshold": None}` `[VERIFIED: src/dark_factory/persistence/engine.py:63-69]`; Alembic DDL runs against the **direct** (non-pooled) endpoint via `migrations/env.py` resolution order `DATABASE_URL_DIRECT → DATABASE_URL → DARK_FACTORY_TEST_DATABASE_URL` `[VERIFIED: migrations/env.py:51-55]`.
- **No worker-name branching outside adapters** (CI-enforced from Phase 7; keep the habit now).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STATE-04 | A `human_interactions` table persists questions, answers, and status (`WAITING` \| `ANSWERED` \| `CANCELLED`) | § "Pattern 1: The `human_interactions` table + Alembic 0003"; § "Code Examples" (ORM model, migration skeleton). Enum via `sa.Enum(…, native_enum=False, create_constraint=True)` mirroring the existing `_RUN_STATUS` pattern `[VERIFIED: src/dark_factory/persistence/models.py:65-72]` |
| HITL-01 | Any role can ask the human for clarification through one identical mechanism | § "Pattern 2: The one pause mechanism" — the *only* mechanism is `WorkerResult(status=NEEDS_INPUT, questions=[…])`; `signal_from_result` already maps it to `Signal.ROLE_NEEDS_INPUT` `[VERIFIED: src/dark_factory/domain/signal.py:31-35]`; the runner handles that signal generically for every pipeline node — no per-role code |
| HITL-02 | On `NEEDS_INPUT`: store result + worker session, create a human interaction, persist `WAITING_HUMAN`, release the execution so the process can terminate safely | § "Pattern 3: Pause path in one transaction" — extend `apply_transition` with an optional `human_interaction` write + lease-clear; emit `QUESTION_CREATED` + `RUN_PAUSED`; `drive()` returns `WAITING_HUMAN` (∈ `STOP_STATUSES`), CLI exits 0 |
| HITL-03 | Operator resumes locally — `dark-factory resume <run-id> --answer "..."` — from a brand-new process with no in-memory state | § "Pattern 5: `resume --answer` + fresh-process re-entry" — add `--answer` to the existing `resume` command `[VERIFIED: src/dark_factory/cli.py:133-146]`; `submit_answer` reads only columns; re-enters the same `drive()`/`advance()` loop; `worker.resume(...)` already in the `CodingWorker` contract `[VERIFIED: src/dark_factory/workers/base.py:23-27]` |
| HITL-07 | Two processes cannot execute the same run simultaneously — PostgreSQL transactions / row locking / conditional updates, no lock service | § "Pattern 4: The Postgres lease (claim-don't-check)" — conditional `UPDATE runs SET owner_token=…, lock_expires_at=now()+ttl WHERE id=… AND (owner_token IS NULL OR lock_expires_at < now()) RETURNING id`; zero rows ⇒ loser exits 0 clean `[CITED: netdata.cloud/academy/update-skip-locked]` |
| HITL-08 | A DB transaction is never held open across a worker subprocess call; ownership is a lease with database-clock expiry | § "Pattern 6: No transaction across the worker call" + § "Pattern 7: Heartbeat". `apply_transition`'s single `with session.begin()` never spans `worker.execute()` `[VERIFIED: src/dark_factory/persistence/mutations.py:199-229]`; lease `lock_expires_at` set with `func.now()` (DB clock) `[VERIFIED: src/dark_factory/persistence/models.py:26-29]` |

</phase_requirements>

## Standard Stack

### Core — everything is already pinned in Phase 1; Phase 2 adds nothing

| Library | Version (pinned) | Purpose in Phase 2 | Why standard |
|---------|------------------|--------------------|--------------|
| SQLAlchemy | `>=2.0.40,<2.1` `[VERIFIED: pyproject.toml:11]` | `sa.update(Run).where(...).returning(Run.id)` for the atomic claim; `session.get(Run, id, with_for_update=True)` already used for the guard | Named in the spec; typed 2.0 Core `UPDATE … RETURNING` is a first-class construct |
| psycopg | `>=3.2,<4` `[VERIFIED: pyproject.toml:12]` | driver; renders Python `timedelta` as a bound `INTERVAL` parameter; `prepare_threshold=None` keeps it PgBouncer-safe | psycopg2 is maintenance-only; v3.2+ is the Neon-pooler-safe choice |
| Alembic | `>=1.19,<2` `[VERIFIED: pyproject.toml:13]` | revision `0003` — `human_interactions` table + `runs.owner_token` / `runs.lock_expires_at` | The migration tool for SQLAlchemy; autogenerate from the 2.0 models; run against the direct endpoint |
| Typer | `>=0.27,<1` `[VERIFIED: pyproject.toml:16]` | `--answer` option on the existing `resume` command | Type-hint-driven; `resume` command already exists `[VERIFIED: src/dark_factory/cli.py:133]` |
| pydantic-settings | (via Phase 1 `Settings`) | new `lease_ttl_seconds` / `lease_heartbeat_seconds` fields with production defaults; the single choke point tests override | Typed settings with env precedence; the existing `use_fake_secrets` fixture pattern `[VERIFIED: tests/conftest.py:272-280]` extends cleanly |
| structlog | `>=25,<27` `[VERIFIED: pyproject.toml:17]` | "lost the race, exiting" / "lease renewed" / "lease lost mid-step" log lines, bound to `run_id` context | Redaction processor already installed; `bind_contextvars(run_id=…, role=…, attempt=…)` already in `advance()` `[VERIFIED: src/dark_factory/orchestrator/runner.py:201]` |

### Standard library (no dependency, called out because it is load-bearing)

| Module | Purpose | Notes |
|--------|---------|-------|
| `threading` | one daemon `Thread` running the heartbeat loop + a `threading.Event` ("lease lost") the main thread checks after the worker call | The `Session` is **not** thread-safe — the heartbeat thread must own its own `Session`/connection (`new_session()` returns a fresh one; `NullPool` means a fresh socket) `[VERIFIED: src/dark_factory/persistence/engine.py:101-107]` |
| `uuid` | `uuid.uuid4()` for `owner_token` | Matches the existing client-side `default=uuid.uuid4` on every PK `[VERIFIED: src/dark_factory/persistence/models.py:85-87]`. It is an opaque fence token, not a security credential (see Security Domain) |
| `datetime.timedelta` | the TTL *duration* passed to `func.now() + timedelta(seconds=ttl)` | A duration, not a clock reading — never `datetime.now()` for an expiry value |
| `time` / `time.monotonic` | the heartbeat thread's sleep between renewals | `time.sleep(interval)` between renewals is fine — it is a delay, not a timestamp used in a correctness decision |

### Alternatives Considered

| Instead of | Could Use | Tradeoff / why rejected here |
|------------|-----------|------------------------------|
| Conditional `UPDATE … RETURNING` lease | `SELECT … FOR UPDATE SKIP LOCKED` | Valid Postgres single-owner pattern `[CITED: prisma.io/blog/you-dont-need-a-job-queue-postgres-already-has-skip-locked]`, and worth knowing, but it locks only for the enclosing transaction — this phase needs ownership to *outlive* many short transactions across a multi-minute worker call, which is exactly the "job lifetime lock" case `SKIP LOCKED` alone does not cover `[CITED: crunchydata.com/blog/postgres-locking-when-is-it-concerning]`. The conditional-UPDATE + TTL column *is* the documented add-on (`locked_at` + reaper) for that case. |
| Conditional `UPDATE` lease | `pg_advisory_xact_lock(run_key)` | Safe under PgBouncer transaction pooling (auto-released on COMMIT) `[CITED: pgbouncer.org / crunchydata]`, and permitted by CLAUDE.md. But it too is transaction-scoped, so it cannot span the worker call, and it adds a second concurrency mechanism for no benefit. Keep it in reserve for a future "serialize a single critical section" need. |
| Conditional `UPDATE` lease | `pg_advisory_lock` (session-scoped) | **Unsafe** with Neon's PgBouncer transaction pooling: a session-level advisory lock survives COMMIT, the connection returns to the pool, and the lock can leak to an unrelated client `[CITED: pgbouncer.org FAQ; crunchydata.com/blog/postgres-locking-when-is-it-concerning]`. Do not use. |
| `threading.Thread` heartbeat | `APScheduler` / `asyncio` task / `sched` | New dependency or an event loop in a sync codebase, for one periodic `UPDATE`. A daemon thread + `Event` is the minimum. |
| `func.now() + timedelta(...)` in SQL | compute `expires_at` in Python, store the absolute value | Reintroduces the process clock into a correctness decision — the exact thing HITL-08 and the cross-cutting invariant forbid. |

**Installation:** none. `uv sync --all-extras --dev` already provides everything (`time-machine>=3,<4` `[VERIFIED: pyproject.toml:30]` is present but see Pitfall 4 — it cannot move the Postgres clock).

## Package Legitimacy Audit

**No external packages are introduced in this phase.** Every mechanism uses the Phase 1 pinned stack (SQLAlchemy 2.0, psycopg 3, Alembic, Typer, pydantic-settings, structlog) plus the Python standard library (`threading`, `uuid`, `datetime`, `time`). The Package Legitimacy Gate is **N/A** — there is nothing to `npm view` / `pip index versions`.

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
  dark-factory run text:"..."                 dark-factory resume <id> [--answer "..."]
            │                                              │
            ▼                                              ▼
      start_run() ──► create_run (CREATED)      run_state() exists?  ──no──► exit 2
            │                                              │ yes
            └──────────────┬───────────────────────────────┘
                           ▼
                 ┌──────────────────────┐
                 │  run_lease(run_id)   │   claim:  UPDATE runs
                 │  __enter__           │     SET owner_token=:tok, lock_expires_at = now() + :ttl
                 │                      │     WHERE id=:id AND status NOT IN (COMPLETED,FAILED)
                 │                      │       AND (owner_token IS NULL OR lock_expires_at < now())
                 │                      │     RETURNING id
                 └───────┬──────────────┘
                  0 rows │              │ 1 row  ─────────────────────────────┐
                         ▼              ▼                                     │
             log "owned by another   start heartbeat Thread                  │
             process"; return        (every TTL/3:                           │
             current status;           UPDATE runs SET lock_expires_at =     │
             exit 0  (SC3)             now()+:ttl WHERE id=:id AND           │
                                       owner_token=:tok RETURNING id;        │
                                       0 rows ⇒ set lease_lost Event)        │
                                              │                              │
       ┌── (--answer given) ──► submit_answer():                             │
       │      ONE txn via apply_transition:                                  │
       │        human_interactions: answer=redact(text), status=ANSWERED,    │
       │                            answered_at=now()                        │
       │        runs: WAITING_HUMAN ──► <current_role>  (owner_token kept)   │
       │        role_executions(latest, same attempt): status="RESUMING"     │
       │        events: HUMAN_ANSWER_RECEIVED, RUN_RESUMED                    │
       │                                                                     ▼
       │                              drive() loop:  while status ∉ STOP_STATUSES:
       │                                                 advance(run_id):
       │                                                   load_run_state (columns only)
       │                                    ┌──────────────  status == CREATED ─► _enter_first_role
       │                                    │               status is <role>:
       │                                    │                 latest.status == "RESUMING"?
       │                                    │                    yes ─► worker.resume(ctx, previous, answer)
       │                                    │                    no  ─► worker.execute(ctx)
       │                                    │                 ── NO DB TXN OPEN DURING THE CALL ──
       │                                    │                 check lease_lost Event ─► set? abort, no write, exit≠0
       │                                    │                 map result.status ─► Signal
       │                                    │                 lifecycle.transition(state, signal, pipeline)
       │                                    │                 apply_transition (ONE txn, fenced on owner_token):
       │                                    │                   role_executions(update, same attempt)
       │                                    │                   runs.status/current_role/current_step
       │                                    │                   if next_status ∈ STOP_STATUSES:
       │                                    │                        owner_token=NULL, lock_expires_at=NULL
       │                                    │                   + ROLE_NEEDS_INPUT arm:
       │                                    │                        human_interactions INSERT (status=WAITING,
       │                                    │                          question=redact(join(questions)))
       │                                    │                        events: QUESTION_CREATED, RUN_PAUSED
       │                                    └──────────────────────────────────────────────────────
       │                                              status returned
       │                              run_lease.__exit__: stop+join heartbeat thread;
       │                                                  best-effort release
       │                                                  (UPDATE runs SET owner_token=NULL,
       │                                                   lock_expires_at=NULL WHERE owner_token=:tok)
       ▼
   CLI prints summary; exit 0 for COMPLETED or WAITING_HUMAN, 1 for FAILED
```

### Recommended Project Structure (delta only — Phase 2 touches existing modules)

```
src/dark_factory/
├── domain/
│   ├── status.py            # STOP_STATUSES += WAITING_HUMAN (one line, D-06)
│   └── interaction.py       # NEW: InteractionStatus StrEnum (WAITING|ANSWERED|CANCELLED)
├── events/
│   └── catalog.py           # += QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED
├── config/
│   └── settings.py          # += lease_ttl_seconds=900, lease_heartbeat_seconds=300
├── persistence/
│   ├── models.py            # Run += owner_token, lock_expires_at; NEW HumanInteraction model
│   ├── mutations.py         # apply_transition += human_interaction write, owner-token fence,
│   │                        #   lease-clear on stop; NEW claim_lease / renew_lease / release_lease
│   │                        #   (or a persistence/lease.py sibling module — still "one mutation
│   │                        #    path" for lifecycle state; the lease columns are ownership, not
│   │                        #    lifecycle — decide with the planner, see Open Question 2)
│   └── repositories.py      # RunState += latest_execution.result, pending_answer; load the
│                            #   single non-consumed ANSWERED interaction
├── orchestrator/
│   ├── lifecycle.py         # transition() += ROLE_NEEDS_INPUT arm ─► (WAITING_HUMAN, role, step)
│   ├── lease.py             # NEW: run_lease(run_id) context manager + Heartbeat thread
│   └── runner.py            # _run_current_role: execute-vs-resume; ROLE_NEEDS_INPUT branch;
│   │                        #   wrap drive() / direct advance() in run_lease(); WAITING_HUMAN
│   │                        #   early-return in advance()
│   └── answers.py           # NEW: submit_answer(run_id, answer)  (or fold into runner.py)
├── migrations/versions/
│   └── 0003_pause_resume_lease.py   # Revises: 0002_role_exec_uniqueness
└── cli.py                   # resume(): += --answer option; _drive_and_exit: exit 0 on WAITING_HUMAN
```

### Pattern 1: The `human_interactions` table + Alembic 0003 (STATE-04)

**What:** one table, one row per question asked. Columns follow the Phase 1 conventions verbatim: `uuid` PK with client-side `default=uuid.uuid4`; `timestamptz` with `server_default=func.now()`; a `VARCHAR + CHECK` status column, **not** a native PG `ENUM`, so a future value edit is `ALTER TABLE … CHECK`, never `ALTER TYPE … ADD VALUE` `[VERIFIED: src/dark_factory/persistence/models.py:16-24, 65-72]`.

**Columns (recommended):**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `sa.Uuid()` PK, `default=uuid.uuid4` | matches every other PK `[VERIFIED: src/dark_factory/persistence/models.py:85-87]` |
| `run_id` | `sa.Uuid()`, `ForeignKey("runs.id")`, NOT NULL, indexed | same shape as `role_executions.run_id` `[VERIFIED: src/dark_factory/persistence/models.py:138-140]` |
| `role_execution_id` | `sa.Uuid()`, `ForeignKey("role_executions.id")`, **NOT NULL** | every question originates in a role attempt (see Assumptions A3) |
| `question` | `sa.Text`, NOT NULL | `redact("\n".join(result.questions))` — `WorkerResult.questions` is `list[str]`, guaranteed non-empty for `NEEDS_INPUT` `[VERIFIED: src/dark_factory/domain/worker.py:62, 69-75]` (see Assumptions A2 for the JSONB alternative) |
| `answer` | `sa.Text`, NULL | `redact(answer_text)` on resume |
| `status` | `sa.Enum(InteractionStatus, native_enum=False, create_constraint=True, length=16, name="interaction_status", values_callable=lambda e: [m.value for m in e])` | values **`WAITING`**, **`ANSWERED`**, **`CANCELLED`** verbatim per STATE-04 |
| `created_at` | `sa.DateTime(timezone=True)`, `server_default=func.now()`, NOT NULL | DB clock |
| `answered_at` | `sa.DateTime(timezone=True)`, NULL | set to `func.now()` when the answer is written |

**Defence-in-depth index (recommended):** a partial unique index so at most one open question per run —
`sa.Index("uq_one_waiting_interaction_per_run", "run_id", unique=True, postgresql_where=sa.text("status = 'WAITING'"))`.
This makes "the pending interaction" a single-row lookup and makes a duplicate-pause a constraint violation rather than a silent second row (same philosophy as `uq_role_exec_attempt` in revision `0002` `[VERIFIED: migrations/versions/0002_role_exec_uniqueness.py:1-16]`).

**Migration:** `0003_pause_resume_lease.py`, `down_revision = "0002_role_exec_uniqueness"` `[VERIFIED: migrations/versions/0002_role_exec_uniqueness.py:25-26]`. It (a) `op.create_table("human_interactions", …)` + the partial unique index, and (b) `op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))` + `op.add_column("runs", sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True))`. Both new `runs` columns are nullable with no default — an unclaimed run has `NULL` in both. Splitting into `0003` (lease) + `0004` (table) is acceptable (see Assumptions A4); one revision keeps the "one vertical slice" shape. `migrations/env.py`'s `_OWNED_TABLES` set must gain `"human_interactions"` so `alembic check` does not propose to drop it `[VERIFIED: migrations/env.py:42-44]`. The autouse `_schema_at_head` fixture already runs `alembic upgrade head`, so tests pick `0003` up with no fixture change `[VERIFIED: tests/conftest.py:197-219]`.

### Pattern 2: The one pause mechanism (HITL-01)

**What:** the *only* way any role asks a question is by returning `WorkerResult(status=NEEDS_INPUT, questions=[…])`. There is no per-role code, no special role, no side channel. The mapping already exists:

```python
# src/dark_factory/domain/signal.py:31-35  [VERIFIED]
_RESULT_STATUS_TO_SIGNAL: dict[WorkerResultStatus, Signal] = {
    WorkerResultStatus.COMPLETED: Signal.ROLE_COMPLETED,
    WorkerResultStatus.FAILED: Signal.ROLE_FAILED,
    WorkerResultStatus.NEEDS_INPUT: Signal.ROLE_NEEDS_INPUT,
}
```

`Signal.ROLE_NEEDS_INPUT` is defined `[VERIFIED: src/dark_factory/domain/signal.py:24-28]` but `lifecycle.transition()` currently has no arm for it and `_run_current_role` raises on it `[VERIFIED: src/dark_factory/orchestrator/runner.py:299-300]`. Phase 2 adds exactly one arm in each place; because the runner branches on the *signal*, not the role name, every current and future pipeline node gets the mechanism for free.

**`WorkerResult` already guards the degenerate case:** a `NEEDS_INPUT` with an empty `questions` list is rejected by `_require_question_for_needs_input` at construction `[VERIFIED: src/dark_factory/domain/worker.py:69-75]` — the orchestrator can assume `questions` is non-empty.

### Pattern 3: Pause path in one transaction (HITL-02, SC1)

**What:** on `Signal.ROLE_NEEDS_INPUT`, `_run_current_role` builds a single `apply_transition` call that, inside the one `with session.begin()` block `[VERIFIED: src/dark_factory/persistence/mutations.py:199-229]`:

1. updates the **same** `role_executions` row (`mode="update"`, `id=latest.id`) — status → a new marker string `"WAITING_HUMAN"`, `result = redact(needs_input_result_dict)`, `worker_session_id = result.worker_session_id`. `role_executions.status` is a plain `sa.String(32)` with no CHECK `[VERIFIED: src/dark_factory/persistence/models.py:143]`, so new marker strings need **no migration**.
2. sets `runs.status = WAITING_HUMAN`, keeps `current_role` (so resume knows where to return — same as the `ROLE_FAILED` arm which retains `role` `[VERIFIED: src/dark_factory/orchestrator/lifecycle.py:98-99]`).
3. **clears the lease** (`owner_token = NULL`, `lock_expires_at = NULL`) because `WAITING_HUMAN ∈ STOP_STATUSES` — a crash immediately after this commit then leaves no lease to wait out.
4. **inserts the `human_interactions` row** (`status = WAITING`, `question = redact("\n".join(questions))`, `role_execution_id = latest.id`).
5. appends two events: `QUESTION_CREATED` (payload `{"role": …, "questions": […]}`) and `RUN_PAUSED` (payload `{"role": …}`).

**Recommended shape:** extend `apply_transition` with two optional params — `human_interaction: HumanInteractionWrite | None = None` and `expected_owner_token: UUID | None = None` — and a rule "clear `owner_token`/`lock_expires_at` when `next_status in STOP_STATUSES`". This keeps the ORCH-06 invariant literally true (one transaction, one redaction call site). `EventType` gains `QUESTION_CREATED`, `RUN_PAUSED`, `HUMAN_ANSWER_RECEIVED`, `RUN_RESUMED` — **only these four**, the ones actually written this phase; the `catalog.py` docstring's claim that the rest arrive "in Phase 12" stays true for the others `[VERIFIED: src/dark_factory/events/catalog.py:1-9]` (update that docstring to note Phase 2 adds four).

**`drive()` stop:** `STOP_STATUSES` becomes `frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_HUMAN})`; `TERMINAL_STATUSES` is **unchanged** — `WAITING_HUMAN` is a stop, not a terminal `[VERIFIED: src/dark_factory/domain/status.py:30-42]`. `advance()` also early-returns without mutating when `state.status is RunStatus.WAITING_HUMAN` (today it only early-returns on `TERMINAL_STATUSES` `[VERIFIED: src/dark_factory/orchestrator/runner.py:197-198]`) — otherwise a bare `advance()` on a paused run would try to run the role again with no answer.

**CLI exit code:** `_drive_and_exit` currently does `raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)` `[VERIFIED: src/dark_factory/cli.py:117]`. Change to exit **0** for `COMPLETED` **or** `WAITING_HUMAN` (a clean pause is not a failure), 1 for `FAILED`.

### Pattern 4: The Postgres lease — claim-don't-check (HITL-07, SC3)

**What:** ownership of a run is `runs.owner_token` (uuid) + `runs.lock_expires_at` (timestamptz). A process claims with **one statement**:

```sql
UPDATE runs
   SET owner_token     = :new_token,
       lock_expires_at = now() + :ttl_interval,   -- now() = statement/transaction time on the SERVER
       updated_at      = now()
 WHERE id = :run_id
   AND status <> 'COMPLETED' AND status <> 'FAILED'
   AND (owner_token IS NULL OR lock_expires_at < now())
RETURNING id;
```

- **1 row returned** → this process holds the lease; keep `:new_token` in memory for the heartbeat and for `expected_owner_token` on every `apply_transition`.
- **0 rows returned** → another live owner holds an unexpired lease. Log `run <id> is owned by another process; exiting cleanly`, return the run's current status **without any mutation**, exit 0. This is SC3's "the other exits cleanly without changing status and without duplicating work."

**Why this is sufficient without `FOR UPDATE` / advisory locks:** the `UPDATE` takes a row lock for its own duration; two concurrent claim `UPDATE`s serialize, the second re-evaluates its `WHERE` against the now-committed row and matches 0 rows. `RETURNING` tells the winner in the same round trip — no separate `SELECT`, so no check-then-act (TOCTOU) window. This is the documented "claim-don't-check" pattern; adding `SKIP LOCKED` or `pg_advisory_xact_lock` would be a second mechanism for the same guarantee `[CITED: netdata.cloud/academy/update-skip-locked]` `[CITED: crunchydata.com/blog/postgres-locking-when-is-it-concerning]`.

**Why `now()` (the DB clock) and never `datetime.now()`:** the write (`lock_expires_at = now() + ttl`) and every expiry test (`lock_expires_at < now()`) are then evaluated in **one clock domain — the server's**. Two processes on two machines (Phase 11) with skewed wall clocks cannot disagree about whether a lease is expired. This is the same reason every `created_at`/`updated_at` in Phase 1 uses `server_default=func.now()` `[VERIFIED: src/dark_factory/persistence/models.py:26-29]`. In SQLAlchemy: `func.now() + timedelta(seconds=ttl)` — the `timedelta` is a *duration* rendered as an `INTERVAL` bound parameter, not a timestamp.

**Reclaim after a kill (SC4):** a killed owner never clears its lease. The next `advance()` claim `UPDATE` fails the `WHERE` (`lock_expires_at` is still in the future) and returns 0 rows → the new process exits 0 without stealing. Once `now()` passes `lock_expires_at`, the same claim `UPDATE` matches, `RETURNING` yields a row, and the new process continues from the last committed step (attempt unchanged — see Pattern 5). No reaper process is needed: expiry *is* the reaper, evaluated lazily on the next claim attempt.

**Release on clean stop:** `apply_transition` clears both columns whenever `next_status ∈ STOP_STATUSES` (Pattern 3), and `run_lease.__exit__` does a best-effort `UPDATE runs SET owner_token=NULL, lock_expires_at=NULL WHERE id=:id AND owner_token=:tok`. Either makes the next process's claim instant instead of TTL-delayed.

### Pattern 5: `resume --answer` + fresh-process re-entry (HITL-03, SC2)

**What:** `dark-factory resume <run-id> --answer "..."` from a brand-new process. The `resume` command already exists and takes only `run_id` `[VERIFIED: src/dark_factory/cli.py:133-146]`; Phase 2 adds `answer: str | None = typer.Option(None, "--answer")`.

- **`resume <id>` (no `--answer`)** keeps its Phase 1 meaning: re-drive a run that stopped for a non-human reason (crash mid-step). Still valid.
- **`resume <id> --answer "…"`** routes through a new `submit_answer(run_id, answer)` *before* the `drive()` loop:
  1. Acquire the lease (same conditional `UPDATE` — a second process racing `resume --answer` loses here too).
  2. `load_run_state`; if `status != WAITING_HUMAN` → error, exit 2, **nothing persisted** (so a second `--answer` after the first was accepted is rejected — the answer is accept-once).
  3. Find the single `WAITING` `human_interactions` row for this run (the partial unique index guarantees ≤ 1). None → error.
  4. In **one** `apply_transition` transaction: update the interaction (`answer = redact(text)`, `status = ANSWERED`, `answered_at = func.now()`); transition `runs` `WAITING_HUMAN → <current_role>` (the retained `current_role`); set the latest `role_executions` row (same `id`, **same `attempt`**) status → `"RESUMING"`; emit `HUMAN_ANSWER_RECEIVED` + `RUN_RESUMED`. The lease stays held (`<role>` is not a stop status, so `apply_transition` does not clear it).
  5. Enter the same `drive()` loop.

**Execute-vs-resume in `_run_current_role`:** the run is now in status `<role>` with a latest `role_executions` row whose status is `"RESUMING"`. The runner branches on that column:

```python
if latest.status == "RESUMING":
    previous = WorkerResult.model_validate(latest.result)      # the persisted NEEDS_INPUT result
    result = worker.resume(context, previous, state.pending_answer)
else:
    result = worker.execute(context)
```

This is **column-driven**, so it survives a crash between `submit_answer` and the resume `advance()`: a fresh process reads `status=<role>`, `latest.status="RESUMING"`, the `ANSWERED` interaction's `answer`, and calls `worker.resume(...)` — fully reconstructed from Neon, zero carryover (SC2). `worker.resume(context, previous, answer)` is already in the `CodingWorker` ABC and `FakeWorker` `[VERIFIED: src/dark_factory/workers/base.py:23-27]` `[VERIFIED: src/dark_factory/workers/fake.py:73-76]`.

**`RunState` / `load_run_state` must surface two more values** (both are columns in state tables, not folded events — the STATE-06 spirit holds) `[VERIFIED: src/dark_factory/persistence/repositories.py:45-79]`:
- `latest_execution.result` — the persisted `WorkerResult` dict (today `LatestExecution` carries only `id, role, worker, status, attempt, worker_session_id` `[VERIFIED: src/dark_factory/persistence/repositories.py:53-58]`).
- `pending_answer: str | None` — the `answer` of the single `ANSWERED` interaction for a run currently in `<role>` with `latest.status == "RESUMING"` (one extra `SELECT` on `human_interactions`).

**`_build_context`** (today returns `run_id, role, worker, attempt, task` `[VERIFIED: src/dark_factory/orchestrator/runner.py:104-118]`) gains `"answer": state.pending_answer` and optionally `"questions": previous.questions`. `FakeWorker` ignores context; Phase 7's real adapter consumes it.

**No new run, no new attempt:** `submit_answer` never calls `create_run`; the `resume` CLI already exits 2 on an unknown id `[VERIFIED: src/dark_factory/cli.py:142-144]`. Every `role_executions` write in the pause→resume cycle is `mode="update"` on `latest.id`, so `attempt` never changes — `tests/integration/test_fresh_process_resume.py` already asserts `execs[0].attempt == 1` across a resume `[VERIFIED: tests/integration/test_fresh_process_resume.py:143-147]`.

### Pattern 6: No transaction across the worker call (HITL-08, SC1)

**What:** the shape is already correct in Phase 1 and must not regress — `_run_current_role` calls `worker.execute()` **before** opening any session, then opens a fresh session only for the `apply_transition` commit `[VERIFIED: src/dark_factory/orchestrator/runner.py:255-326]`. `apply_transition`'s single `with session.begin()` never spans the worker call `[VERIFIED: src/dark_factory/persistence/mutations.py:199-229]`. `SessionLocal` is `sessionmaker(expire_on_commit=False, future=True)` and `new_session()` returns a fresh session bound to the `NullPool` engine `[VERIFIED: src/dark_factory/persistence/engine.py:101-107]`, so each mutation gets its own short-lived connection that `NullPool` closes on session close.

**The lease heartbeat does not change this:** the heartbeat thread runs its own tiny autonomous `with session.begin(): UPDATE …` transactions on its **own** session — each opens and commits in milliseconds; none is held across anything.

**Testing "exits holding no open transaction":** set `application_name=dark-factory` on the engine (`connect_args={"prepare_threshold": None, "application_name": "dark-factory"}`), then while a deliberately slow `FakeWorker` is mid-call, from the test connection run
`SELECT count(*) FROM pg_stat_activity WHERE application_name = 'dark-factory' AND state = 'idle in transaction'` and assert `0`. Plus a cheap unit assertion: `assert not session.in_transaction()` after each mutation helper returns.

### Pattern 7: Heartbeat — keeping a slow step's lease alive (SC5, Open Decision 2)

**What:** `run_lease.__enter__` claims the lease and starts one daemon `threading.Thread`. The thread loops:

```python
while not stop_event.wait(timeout=heartbeat_interval):     # wakes early on stop
    with hb_session.begin():
        rows = hb_session.execute(
            sa.update(Run)
              .where(Run.id == run_id, Run.owner_token == my_token)
              .values(lock_expires_at=func.now() + timedelta(seconds=ttl))
              .returning(Run.id)
        ).all()
    if not rows:                     # someone else owns it now, or the row is gone
        lease_lost.set()
        return
```

`run_lease.__exit__` sets `stop_event`, `join()`s the thread (short timeout), then best-effort releases the lease.

**The two-sided guarantee:**
- *Slow step is not stolen (SC5):* while `worker.execute()`/`resume()` runs, the heartbeat keeps pushing `lock_expires_at` forward, so a competing process's claim `UPDATE` keeps matching 0 rows.
- *Lease loss aborts the step:* after the worker call returns, and again inside `apply_transition`, ownership is re-checked. The main thread checks `lease_lost.is_set()` immediately after the worker call — if set, it **discards the worker result, writes nothing, logs, and exits non-zero**. Belt-and-braces: `apply_transition` takes `expected_owner_token` and, on the already-locked `runs` row `[VERIFIED: src/dark_factory/persistence/mutations.py:200-206]`, raises (`LeaseLost`, a new sibling of `ConcurrentTransition`) if `run.owner_token != expected_owner_token`. **The commit is fenced by the token**; the `Event` is only an early-abort. Because the worker result was never persisted, the next `advance()` re-runs the step on the same attempt — idempotent.

**Concrete recommendation for the MVP (resolves Open Decision 2):**

| Knob | Value | Rationale |
|------|-------|-----------|
| `lease_ttl_seconds` | **900** (15 min) | Top of the ROADMAP "5–15 min baseline". A genuinely dead owner is reclaimed within ≤ 15 min — acceptable for a human-speed delivery pipeline. Real agent steps run minutes-to-tens-of-minutes; 15 min comfortably exceeds a typical step, and the heartbeat covers longer ones. |
| `lease_heartbeat_seconds` | **300** (TTL / 3) | The lease / leader-election rule of thumb: renew at ≈ TTL/3 so **two** consecutive missed renewals (600 s) still fall inside the TTL before the lease is lost `[CITED: kubernetes.io/docs/concepts/architecture/leases]` `[CITED: singhajit.com/distributed-systems/lease]`. Kubernetes controller-manager uses 15 s lease / 10 s renew deadline; the ratio, not the absolute value, is what transfers. |
| Clock | PostgreSQL `now()` for the write and every comparison; Python only `time.sleep`s the *interval* between renewals | HITL-08 / cross-cutting invariant: no process clock in a correctness decision. |
| Jitter | optional: multiply the interval by `random.uniform(0.9, 1.1)` | Single-owner, so contention is near-zero; cheap insurance, not required for MVP. |
| On renewal failure | heartbeat thread sets `lease_lost` and stops; main thread aborts the step without persisting; process exits non-zero; run left at its last committed state with the lease now held by whoever took it | Prefer a redundant re-run of one step over two owners writing. |
| Distinguishing "slow" from "dead" | **you cannot, and you do not try.** Liveness == a fresh `lock_expires_at`. A live owner proves it by renewing; a dead owner stops and the lease expires. There is no PID check, no `pg_stat_activity` probe of the other process, no "is the step slow?" query. | This is the defensible core of the decision. |

**Deterministic test without waiting real minutes:** inject `Settings(lease_ttl_seconds=2, lease_heartbeat_seconds=1)` via env; a `FakeWorker` that sleeps ~6 s (new `DARK_FACTORY_FAKE_SLEEP_MS` knob alongside `DARK_FACTORY_FAKE_SCRIPT` `[VERIFIED: src/dark_factory/workers/fake.py:29]`); a competing process polls the claim every 0.5 s for the whole 6 s and never succeeds; after the owner commits, a process started *after* completion claims successfully. Total wall time ≈ 7 s. `time-machine` is **useless here** — see Pitfall 4.

### Anti-Patterns to Avoid

- **Computing `expires_at` in Python and storing the absolute timestamp.** Reintroduces process-clock skew into the expiry decision. Always `func.now() + timedelta(...)` in the SQL.
- **A `SELECT … FOR UPDATE` then an application-side `if owner is None or expired:` then an `UPDATE`.** That is check-then-act with a TOCTOU window and two round trips. Use one `UPDATE … WHERE <predicate> RETURNING`.
- **`os.environ.copy()` when spawning the heartbeat's environment / any subprocess.** The credential-boundary invariant; `tests/unit/test_no_environ_copy.py` guards it.
- **Sharing one `Session` between the main thread and the heartbeat thread.** `Session` is not thread-safe. The thread gets its own.
- **Wrapping the claim `UPDATE` in `tenacity`.** A lost claim is a clean exit, not a transient fault. `tenacity` is only for idempotent external calls (Phase 1 uses it once, around the Neon cold-start connect `[VERIFIED: src/dark_factory/persistence/engine.py:72-83]`).
- **Adding `WAITING_HUMAN` to `TERMINAL_STATUSES`.** It is a stop, not a terminal — `advance()` must still act on it once an answer arrives. Only `STOP_STATUSES` gets the new member.
- **A dedicated reaper process / cron to expire leases.** Lazy expiry on the next claim is the whole point of the pattern.
- **Pre-declaring the whole `EventType` catalog.** Phase 2 adds only the four types it writes; an enum member never emitted is a false signal in the audit surface `[VERIFIED: src/dark_factory/events/catalog.py:1-9]`.
- **Letting `resume`/`cli` inspect run status to decide what to do.** The CLI stays a thin wrapper over `drive()`; `submit_answer` is orchestrator code, not CLI code `[VERIFIED: src/dark_factory/cli.py:1-18]`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Single-owner execution across processes/machines | A `filelock`, a `threading.Lock`, a `runs.is_locked` boolean, a bespoke lock table | One conditional `UPDATE runs … WHERE (owner_token IS NULL OR lock_expires_at < now()) RETURNING` | In-process locks don't cross processes; a boolean has no expiry so a `kill -9` deadlocks the run forever; Postgres row-write atomicity already gives mutual exclusion `[CITED: crunchydata.com/blog/postgres-locking-when-is-it-concerning]` |
| "Is the previous owner still alive?" | PID files, `pg_stat_activity` scans for the other backend, an app-level ping | A TTL column the owner heartbeats; expiry == death | Liveness detection is a solved problem *if* you make the owner prove liveness rather than guessing about it `[CITED: singhajit.com/distributed-systems/lease]` |
| Periodic lease renewal | `APScheduler`, an `asyncio` task, `sched`, a cron entry | One `threading.Thread` + `threading.Event` | One periodic `UPDATE` does not justify a scheduler dependency or an event loop in a sync codebase |
| "Which question is pending?" | Scan all interactions, sort by `created_at`, take the last, check status | Partial unique index `WHERE status='WAITING'` → single-row `SELECT` | The index makes "≤ 1 open question per run" a database invariant, not application discipline |
| Retry/backoff of a lost claim | `tenacity`, a manual sleep-and-retry loop | Exit 0 immediately; the next trigger re-attempts | Losing the race is a normal outcome, not a fault to retry |
| Interval arithmetic / duration formatting | String-building `interval '900 seconds'`, `EXTRACT(EPOCH …)` math | `func.now() + datetime.timedelta(seconds=ttl)` (SQLAlchemy renders it as a bound `INTERVAL`) | Bound parameter, injection-safe, readable |

**Key insight:** every "distributed coordination" sub-problem in this phase collapses to *one atomic conditional write against a row you already have*. The moment a design reaches for a second coordination primitive (a lock, a scheduler, a probe, a retry loop), it has left the pattern the spec mandates.

## Runtime State Inventory

Phase 2 is **additive** (a new table, two new nullable columns, new code paths) — it renames nothing and migrates no existing data. The classic rename/refactor inventory does not apply. The one adjacent concern:

| Category | Finding | Action |
|----------|---------|--------|
| Stored data | No back-fill needed. Existing `runs` rows get `owner_token = NULL`, `lock_expires_at = NULL` (unclaimed) — which is exactly "claimable". No existing run is `WAITING_HUMAN` (only `CREATED/BA/COMPLETED/FAILED` are reachable in Phase 1 `[VERIFIED: src/dark_factory/domain/status.py:1-8]`), so no `human_interactions` back-fill. | Migration `0003` adds columns nullable-no-default; no data migration. |
| Live service config | None — no external service holds Phase 2 state. | — |
| OS-registered state | None. | — |
| Secrets / env vars | New **test-only** env knobs (`DARK_FACTORY_FAKE_SLEEP_MS`, plus `Settings` override for `lease_ttl_seconds`/`lease_heartbeat_seconds`). No new production secret. `owner_token` is not a secret. | Document in the plan; mirror the `DARK_FACTORY_FAKE_SCRIPT` / `DARK_FACTORY_CRASH_AFTER` test-only convention `[VERIFIED: src/dark_factory/workers/fake.py:29]` `[VERIFIED: src/dark_factory/orchestrator/runner.py:83]`. |
| Build artifacts | None. | — |

## Common Pitfalls

### Pitfall 1: The heartbeat renews a lease the owner has already logically lost
**What goes wrong:** the main thread decides to abort (e.g. worker raised), but the daemon heartbeat thread keeps renewing `lock_expires_at`, so no other process can ever reclaim the run.
**Why it happens:** the thread's stop condition is only `stop_event`; an exception path forgets to set it.
**How to avoid:** `run_lease` is a context manager; `__exit__` runs on **every** exit (normal, exception, `WAITING_HUMAN`) and always sets `stop_event`, `join()`s, and best-effort releases. Never start the thread outside a `with run_lease(...)`.
**Warning signs:** a run stuck in `<role>` with `lock_expires_at` always ~TTL in the future and no process making progress.

### Pitfall 2: Two owners because the token fence is missing from the commit
**What goes wrong:** the heartbeat detects loss and sets `lease_lost`, but the main thread already passed the check and calls `apply_transition`, which commits a second owner's write over the thief's work.
**Why it happens:** relying only on the in-memory `Event`, which races with the worker call returning.
**How to avoid:** `apply_transition` re-checks `run.owner_token == expected_owner_token` on the already-locked row and raises `LeaseLost` — the commit itself is fenced. The `Event` is just an optimization to fail faster.
**Warning signs:** two `ROLE_COMPLETED` events for the same attempt; `role_executions.result` changing after it was set.

### Pitfall 3: `now()` is not the clock you think it is
**What goes wrong:** using Python `datetime.now(tz=UTC)` for `lock_expires_at`, or comparing the DB `lock_expires_at` against a Python `datetime` in the app.
**Why it happens:** SQLAlchemy makes `datetime` columns feel like Python datetimes; it is one line to write the wrong side.
**How to avoid:** the expiry value is **always** `func.now() + timedelta(...)` in a SQL expression; the expiry test is **always** `Run.lock_expires_at < func.now()` in a `WHERE`. The app never materializes "is it expired?" in Python. Grep the diff for `datetime.now` / `datetime.utcnow` near lease code — there should be zero.
**Warning signs:** leases that expire "instantly" or "never" on a machine whose clock is off; tests that pass locally and fail in CI.

### Pitfall 4: `time-machine` cannot move the PostgreSQL clock
**What goes wrong:** a lease-expiry test wraps the body in `time_machine.travel(+20min)` expecting `lock_expires_at < now()` to become true, and nothing happens.
**Why it happens:** `time-machine` patches the *Python process's* clock; `now()` inside Postgres is the *server's* clock and is untouched.
**How to avoid:** for DB-clock expiry tests, either (a) inject a genuinely short `lease_ttl_seconds` (e.g. 2) and `time.sleep(2.5)` for real, or (b) force expiry with SQL: `UPDATE runs SET lock_expires_at = now() - interval '1 second' WHERE id = :id`, then attempt the claim. Use (b) as the fast primary test and one real-short-sleep test for honesty. `time-machine` still has a use — Python-side timeout logic, if any — but not here.
**Warning signs:** an expiry test that only passes because of an unrelated code path.

### Pitfall 5: The pause path forgets one of the five writes
**What goes wrong:** the run reaches `WAITING_HUMAN` but the `worker_session_id` (or the `result`, or the interaction row, or one event) was not persisted — resume then can't reconstruct.
**Why it happens:** the pause branch assembles its `apply_transition` call by hand and misses a field; SC1 enumerates *five* things that must all be persisted.
**How to avoid:** one `db` test that drives a scripted `NEEDS_INPUT` and asserts, in a session opened *after* the drive returns: `runs.status == WAITING_HUMAN`, `runs.current_role` set, `runs.owner_token IS NULL`, latest `role_executions.result` is the `NEEDS_INPUT` dict, latest `role_executions.worker_session_id` set, exactly one `human_interactions` row (`status=WAITING`, `question` non-empty and redacted), events contain `QUESTION_CREATED` and `RUN_PAUSED`.
**Warning signs:** `resume --answer` raising `KeyError`/`ValidationError` rebuilding `previous`.

### Pitfall 6: Secrets in the new persisted text fields
**What goes wrong:** an operator pastes a token into `--answer "use ghp_… as the key"`, or a worker's question echoes a connection string, and it lands unredacted in `human_interactions` / an event payload.
**Why it happens:** the new writes bypass the single `redact()` call site.
**How to avoid:** `question` and `answer` are redacted inside `apply_transition` at the same call site as `result`/`error`/`payload` `[VERIFIED: src/dark_factory/persistence/mutations.py:219-227]`; extend `tests/unit/test_single_mutation_path.py` (AST guard) to also assert `HumanInteraction` is only constructed in `mutations.py`, and add a redaction test seeding a fake secret in both the question and the answer.
**Warning signs:** `test_secret_redaction_e2e.py`-style sweep finding a seeded value in `human_interactions`.

### Pitfall 7: `advance()` auto-runs a `WAITING_HUMAN` run
**What goes wrong:** `advance()` early-returns only on `TERMINAL_STATUSES` `[VERIFIED: src/dark_factory/orchestrator/runner.py:197-198]`; a `WAITING_HUMAN` run therefore falls through to `_run_current_role`, which calls the worker again with no answer.
**How to avoid:** add `WAITING_HUMAN` to the early-return guard in `advance()` (or check `state.status in STOP_STATUSES`). Only `submit_answer` moves a run out of `WAITING_HUMAN`.
**Warning signs:** a paused run advancing on a bare `dark-factory resume <id>` with no `--answer`.

## Code Examples

### Lease model columns (add to `Run`)

```python
# src/dark_factory/persistence/models.py — inside class Run
# Pattern mirrors the existing base_branch/working_branch "present now, nullable" columns
# [VERIFIED: src/dark_factory/persistence/models.py:98-100]
owner_token: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)
lock_expires_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True
)
```

### `InteractionStatus` + `HumanInteraction` model

```python
# src/dark_factory/domain/interaction.py
from enum import StrEnum

class InteractionStatus(StrEnum):
    WAITING = "WAITING"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"
```

```python
# src/dark_factory/persistence/models.py
_INTERACTION_STATUS = sa.Enum(
    InteractionStatus,
    native_enum=False, create_constraint=True, length=16,
    name="interaction_status",
    values_callable=lambda enum: [m.value for m in enum],
)  # exact mirror of _RUN_STATUS [VERIFIED: src/dark_factory/persistence/models.py:65-72]

class HumanInteraction(Base):
    __tablename__ = "human_interactions"
    __table_args__ = (
        sa.Index(
            "uq_one_waiting_interaction_per_run", "run_id", unique=True,
            postgresql_where=sa.text("status = 'WAITING'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), sa.ForeignKey("runs.id"), nullable=False, index=True
    )
    role_execution_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), sa.ForeignKey("role_executions.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[InteractionStatus] = mapped_column(_INTERACTION_STATUS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
```

### The atomic claim (SQLAlchemy 2.0 Core `UPDATE … RETURNING`)

```python
# src/dark_factory/orchestrator/lease.py  (or persistence/lease.py)
from datetime import timedelta
from uuid import UUID, uuid4
import sqlalchemy as sa
from sqlalchemy import func
from dark_factory.persistence.models import Run

def claim_lease(session: sa.orm.Session, run_id: UUID, ttl_seconds: int) -> UUID | None:
    """Return a fresh owner_token if the lease was claimed, else None (someone else owns it)."""
    token = uuid4()
    with session.begin():
        row = session.execute(
            sa.update(Run)
            .where(
                Run.id == run_id,
                Run.status.notin_(["COMPLETED", "FAILED"]),
                sa.or_(Run.owner_token.is_(None), Run.lock_expires_at < func.now()),
            )
            .values(
                owner_token=token,
                lock_expires_at=func.now() + timedelta(seconds=ttl_seconds),
                updated_at=func.now(),
            )
            .returning(Run.id)
        ).first()
    return token if row is not None else None
```

### `transition()` gains one arm (mirrors the `ROLE_FAILED` arm)

```python
# src/dark_factory/orchestrator/lifecycle.py — after the ROLE_FAILED arm
# existing: [VERIFIED: src/dark_factory/orchestrator/lifecycle.py:98-99]
#   if signal is Signal.ROLE_FAILED:
#       return RunStatus.FAILED, role, state.current_step
if signal is Signal.ROLE_NEEDS_INPUT:
    return RunStatus.WAITING_HUMAN, role, state.current_step   # current_role retained
```

### `STOP_STATUSES` one-line change (D-06, already anticipated)

```python
# src/dark_factory/domain/status.py
# [VERIFIED: src/dark_factory/domain/status.py:35-42] — TERMINAL_STATUSES stays as-is
STOP_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_HUMAN}
)
```

### Two-real-process race harness (generalize the Phase 1 helper)

```python
# tests/support/subprocess_runner.py  — lift _ENV_ALLOWLIST / _child_env / _spawn
# verbatim from [VERIFIED: tests/integration/test_fresh_process_resume.py:43-83]
# then, for SC3:
p_a = spawn(["run", "text:race me"], child_env(pg_url, fake_sleep_ms=4000))
# ... once p_a has printed its run id and is mid-worker (poll runs.status == 'BA') ...
p_b = spawn(["resume", run_id], child_env(pg_url))
# assert exactly one of {p_a, p_b} emitted a "BA → COMPLETED" transition line;
# assert the other logged "owned by another process" and exited 0;
# assert exactly one ROLE_COMPLETED event for the run.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `SELECT … FOR UPDATE`, then app-side check, then `UPDATE` | `UPDATE … WHERE <predicate> RETURNING` (claim-don't-check) | Postgres 9.5+ (`SKIP LOCKED`), long-standing for `RETURNING` | One round trip, no TOCTOU window `[CITED: netdata.cloud/academy/update-skip-locked]` |
| Session-level advisory locks for app-lifetime locks | Transaction-scoped locks (`pg_advisory_xact_lock`) **or** a conditional-UPDATE lease column | Rise of transaction-pooling poolers (PgBouncer) | Session advisory locks leak across pooled clients — unusable with Neon's pooler `[CITED: pgbouncer.org FAQ; crunchydata.com/blog/postgres-locking-when-is-it-concerning]` |
| `freezegun` for time control in tests | `time-machine` (C-based, faster) | ~2021 onward | Already pinned `[VERIFIED: pyproject.toml:30]`; neither can move the Postgres clock (Pitfall 4) |
| `after_transaction_end` savepoint-restart recipe for test isolation | `Session(bind=conn, join_transaction_mode="create_savepoint")` | SQLAlchemy 2.0 | Already adopted in `tests/conftest.py` `[VERIFIED: tests/conftest.py:164-180]` |
| External durable-execution engine (Temporal/Celery) for pause/resume | Hand-rolled enum FSM + Neon checkpoint + lease | project decision | Spec-mandated; this phase is the proof |

**Deprecated / do not use here:** `pg_advisory_lock` (session-scoped); `psycopg2`; async SQLAlchemy; any `if worker == "…":` branch; a lock service.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `lease_ttl_seconds = 900`, `lease_heartbeat_seconds = 300` are the right MVP values | Pattern 7 | Too long ⇒ a crashed run is unclaimable for up to 15 min (annoying, not unsafe). Too short ⇒ a real agent step with a stalled heartbeat (GC pause, slow DB) is falsely stolen. Mitigated by making both `Settings` fields — a one-line change later. Needs product confirmation that a ≤ 15-min reclaim delay is acceptable. |
| A2 | `human_interactions.question` is a single `TEXT` column holding `"\n".join(result.questions)` | Pattern 1 | If a downstream phase needs per-question structure (answering questions individually), a `JSONB` `questions` column would have been better. Low risk for MVP — `WorkerResult.questions` is already `list[str]` and the join is reversible enough for display. |
| A3 | `human_interactions.role_execution_id` is `NOT NULL` (every question comes from a role attempt) | Pattern 1 | If a future non-role actor (e.g. a pre-flight config check) needs to ask a question, the column must become nullable. No such actor exists in the roadmap. |
| A4 | One Alembic revision `0003` covers both the lease columns and the table | Pattern 1 | None functionally; two revisions (`0003` lease, `0004` table) give a cleaner rollback story. Planner's call. |
| A5 | New `role_executions.status` marker strings `"WAITING_HUMAN"` and `"RESUMING"` | Patterns 3, 5 | Column is unconstrained `VARCHAR(32)` `[VERIFIED: src/dark_factory/persistence/models.py:143]` so no migration; only the string *values* are a naming guess. Any distinct, stable strings work. |
| A6 | Lease scope is the `drive()` invocation (claim once, heartbeat, release at stop), and a directly-called `advance()` wraps the same context manager | Patterns 4, 7; Structure | If Phase 11's webhook path calls `advance()` per step in a tight external loop, re-claiming each call is wasteful but still correct (the same process re-matches its own token instantly). See Open Question 2. |
| A7 | `resume` with no `--answer` keeps its Phase 1 meaning; `--answer` is purely additive | Pattern 5 | If product wants `resume` to *require* `--answer` for `WAITING_HUMAN` runs, add a status check. Current design already errors (exit 2) if `--answer` is given for a non-`WAITING_HUMAN` run. |
| A8 | `owner_token = uuid.uuid4()` is sufficient (opaque fence token, not a security credential) | Pattern 4; Security | Correct for a single-tenant local/CI tool. If leases ever gate a security boundary, switch to `secrets.token_hex`. Not the case in the roadmap. |
| A9 | `QUESTION_CREATED`, `RUN_PAUSED`, `HUMAN_ANSWER_RECEIVED`, `RUN_RESUMED` are the exact four event types to add now | Pattern 3 | OBS-02 lists more; adding only the four written this phase matches the `catalog.py` "no unreachable members" rule `[VERIFIED: src/dark_factory/events/catalog.py:1-9]`. Phase 12 adds the rest. |
| A10 | The web-sourced lease/lock guidance (TTL÷3, session-advisory-lock hazard, claim-don't-check) is accurate | Patterns 4, 7; State of the Art | Cross-checked against CLAUDE.md's own constraints (which independently forbid session advisory locks and mandate conditional-UPDATE). The confidence seam rates raw web search LOW; treat the *numbers* as a starting recommendation to validate with the SC5 test, per the phase's own Decision note. |

## Open Questions

1. **Should a killed-owner run be reclaimable immediately by an explicit operator command** (`resume --steal` / `--force`) rather than only after TTL expiry?
   - What we know: SC4 only requires clock-expiry reclaim; the TTL default is 15 min.
   - What's unclear: whether an operator staring at a stuck run will tolerate a 15-min wait.
   - Recommendation: MVP = TTL only. If it bites, a later phase adds an explicit `--steal` that sets `lock_expires_at = now()` (making the lease immediately claimable) guarded by a confirmation prompt. Do not build it now.

2. **Where does the heartbeat thread live when `advance()` is called directly** (Phase 11 webhook path) vs. via `drive()`?
   - What we know: `drive()` loops `advance()`; both are public `[VERIFIED: src/dark_factory/orchestrator/runner.py:181-368]`.
   - Recommendation: put the lease/heartbeat in a `run_lease(run_id)` context manager; `drive()` wraps its whole loop in it; a standalone `advance()` wraps its single body in it. Refactor the per-step logic into a private `_step(...)` that assumes the lease is held, so `drive()` claims once and `_step` never re-claims.

3. **Does `CANCELLED` get a code path this phase?**
   - What we know: STATE-04 requires the *value* to exist in the enum + CHECK. No requirement wires a `cancel` command.
   - Recommendation: define `InteractionStatus.CANCELLED`, write it nowhere yet. A future "abort a waiting run" feature (or Phase 12 observability) uses it. A CHECK value that is never written is harmless (unlike an unwritten *event* type).

4. **One outstanding question per run — is that the intended model?**
   - The partial unique index enforces it. Every roadmap scenario (one role pausing once) fits. Confirm no future role needs to ask two independent questions before any answer. Recommendation: keep the constraint; it is trivially droppable later.

5. **Should `submit_answer` and the lease helpers live in `persistence/mutations.py` or a sibling module?**
   - The lease columns are *ownership*, not *lifecycle state*; the `test_single_mutation_path.py` guard is specifically about lifecycle writes (`RunEvent`/`RoleExecution`/`.status`). Recommendation: lease claim/renew/release in `orchestrator/lease.py` (they touch only `owner_token`/`lock_expires_at`/`updated_at`); the interaction row + status transition go **through** `apply_transition` (extended params) so the lifecycle-write guard still holds. Confirm with the planner how strictly "one mutation path" reads.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 17+ (reachable) | every `db` / `integration` test; the lease `now()` semantics | ✓ (Phase 1 rung 3) | operator-supplied via `DARK_FACTORY_TEST_DATABASE_URL` (PG 18.6 used in Phase 1; "17+ floor" by explicit decision) | none — SQLite/mocks explicitly unacceptable `[VERIFIED: tests/conftest.py:140-145]` |
| Docker / `initdb` 17 | preferred test-Postgres rungs | ✗ | — | rung 3 external URL (already in use) |
| `time-machine` | Python-side time control (not lease-expiry) | ✓ | `>=3,<4` `[VERIFIED: pyproject.toml:30]` | real short sleeps |
| `threading` (stdlib) | heartbeat | ✓ | 3.12 | — |
| Two-process test capability (`subprocess` + `sys.executable -m dark_factory`) | SC3/SC4 real-process races | ✓ (Phase 1 already does this) | — `[VERIFIED: tests/integration/test_fresh_process_resume.py:74-83]` | in-process threads (weaker; keep as a secondary test) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Docker/initdb → external test URL (status quo).

## Validation Architecture

`workflow.nyquist_validation` is `true` `[VERIFIED: .planning/config.json]` — this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (`unit` / `db` / `integration` / `contract` markers `[VERIFIED: pyproject.toml:44-49]`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) `[VERIFIED: pyproject.toml:42-49]` |
| Quick run command | `uv run pytest -m "unit or contract"` (~0.2 s, no DB) |
| Full suite command | `set -a; . ./.env; set +a && uv run pytest` (`db`/`integration` need `DARK_FACTORY_TEST_DATABASE_URL`) |
| Static gates | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/dark_factory` (strict) |
| Schema | autouse `_schema_at_head` runs `alembic upgrade head` → picks up `0003` with no fixture change `[VERIFIED: tests/conftest.py:197-219]` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STATE-04 | `human_interactions` row shape, enum CHECK, partial unique index rejects a 2nd `WAITING` | db | `uv run pytest tests/db/test_human_interactions_schema.py -x` | ❌ Wave 0 |
| HITL-01 | any pipeline node returning `NEEDS_INPUT` pauses via the same code (parametrize over a 2-node test pipeline) | db | `uv run pytest tests/db/test_pause_mechanism_generic.py -x` | ❌ Wave 0 |
| HITL-02 | pause path persists all 5 things (result, session id, current_role, interaction, events) in one txn; lease cleared; exit 0 | db + integration | `uv run pytest tests/db/test_pause_path_atomic.py tests/integration/test_pause_exit_zero.py -x` | ❌ Wave 0 |
| HITL-03 | `resume <id> --answer` from a fresh subprocess → same run, same attempt, `worker.resume` path, interaction `ANSWERED` | integration | `uv run pytest tests/integration/test_resume_with_answer.py -x` | ❌ Wave 0 |
| HITL-07 | two racing processes → exactly one advances; loser exits 0, no status change, no duplicate `ROLE_COMPLETED` | integration | `uv run pytest tests/integration/test_single_owner_race.py -x` | ❌ Wave 0 |
| HITL-07 | N threads call `claim_lease` concurrently → exactly one token | db | `uv run pytest tests/db/test_lease_claim_atomic.py -x` | ❌ Wave 0 |
| HITL-08 | no `idle in transaction` backend during the worker call (`pg_stat_activity` by `application_name`) | integration | `uv run pytest tests/integration/test_no_txn_across_worker.py -x` | ❌ Wave 0 |
| SC4 | killed owner → lease not stolen before expiry; reclaimed after (forced-past-expiry SQL + one real short sleep) | integration | `uv run pytest tests/integration/test_lease_expiry_reclaim.py -x` | ❌ Wave 0 |
| SC5 | slow step (short TTL, sleeping fake) heartbeats; competing process never claims during the step; `lock_expires_at` advances ≥ 3× | integration | `uv run pytest tests/integration/test_heartbeat_slow_step.py -x` | ❌ Wave 0 |
| SC5 | heartbeat failure (token stolen mid-step) → main thread aborts, nothing persisted, exit ≠ 0; `apply_transition` `LeaseLost` fence | db | `uv run pytest tests/db/test_lease_lost_aborts_step.py -x` | ❌ Wave 0 |
| SEC-01/02 | fake secret seeded in question **and** answer → zero occurrences in `human_interactions`, events, logs | integration + unit | `uv run pytest tests/integration/test_redaction_interactions.py tests/unit/test_single_mutation_path.py -x` | ⚠️ extend existing `test_single_mutation_path.py` |
| regression | `transition()` `ROLE_NEEDS_INPUT` arm; `advance()` early-returns on `WAITING_HUMAN`; `STOP_STATUSES` membership | unit | `uv run pytest tests/unit/test_lifecycle.py tests/unit/test_domain_enums.py -x` | ⚠️ extend existing |
| contract | `FakeWorker.resume()` returns a valid `WorkerResult` | contract | `uv run pytest -m contract -x` | ⚠️ extend `tests/contract/test_coding_worker_contract.py` |

### Sampling Rate
- **Per task commit:** `uv run pytest -m "unit or contract"` (~0.2 s).
- **Per wave merge:** full `uv run pytest` with `.env` sourced.
- **Phase gate:** full suite green + `ruff` + `mypy --strict` before `/gsd-verify-work`.
- **Max feedback latency:** ~0.2 s (unit/contract tier); the two heartbeat/expiry integration tests are the slowest at ~7 s each (bounded by design — short injected TTLs, no real minutes).

### Properties covered by the existing FakeWorker orchestration suite (extended, not new files)
- Transition-graph legality with the new `ROLE_NEEDS_INPUT` arm — `tests/unit/test_lifecycle.py`.
- Drive-loop stop on `WAITING_HUMAN` — `tests/db/test_terminal_advance_noop.py` (extend: `WAITING_HUMAN` is a stop, not terminal).
- Fresh-process resume mechanics (attempt unchanged, no new run) — `tests/integration/test_fresh_process_resume.py` already proves the no-answer path; the `--answer` path is a sibling test.
- Crash-consistency of the pause transition — reuse the `after_cursor_execute` injection recipe from `tests/db/test_transition_atomic.py` `[VERIFIED: tests/db/test_transition_atomic.py:1-55]`, parametrized over the interaction-insert and the runs-update sub-writes.

### Wave 0 Gaps
- [ ] `Settings.lease_ttl_seconds` (default 900) + `Settings.lease_heartbeat_seconds` (default 300) + a test override fixture (mirror `use_fake_secrets` `[VERIFIED: tests/conftest.py:272-280]`).
- [ ] `FakeWorker` slow knob: `DARK_FACTORY_FAKE_SLEEP_MS` env var (and/or a `sleep_ms` field on the scripted `WorkerResult` metadata) + a `fake_worker_registry` variant that honors it.
- [ ] `application_name=dark-factory` in the engine `connect_args` `[VERIFIED: src/dark_factory/persistence/engine.py:63-69]` so the `pg_stat_activity` assertion can filter.
- [ ] `tests/support/subprocess_runner.py` — lift `_ENV_ALLOWLIST` / `_child_env` / `_spawn` out of `tests/integration/test_fresh_process_resume.py` `[VERIFIED: tests/integration/test_fresh_process_resume.py:43-83]` into a shared helper, add a `fake_sleep_ms` param.
- [ ] `tests/conftest.py` fixture: `force_lease_expiry(run_id)` → `UPDATE runs SET lock_expires_at = now() - interval '1 second'`.
- [ ] Extend `tests/unit/test_single_mutation_path.py` AST guard to include `HumanInteraction` construction.
- [ ] `migrations/env.py` `_OWNED_TABLES` += `"human_interactions"` `[VERIFIED: migrations/env.py:42-44]` (otherwise `alembic check` proposes to drop it).
- [ ] Alembic revision `0003_pause_resume_lease.py` (Wave 0 blocking — every `db` test needs the schema).

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1` `[VERIFIED: .planning/config.json]`. This phase adds no authentication, no network listener, no HTML rendering — the surface is a CLI string argument and two new persisted text fields.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | local CLI, no principals |
| V3 Session Management | no | `worker_session_id` is an opaque worker handle, not a user session; `owner_token` is a lease fence, not a credential |
| V4 Access Control | no | single local operator |
| V5 Input Validation | **yes** | `--answer` is untrusted operator text persisted to `human_interactions.answer` and later fed into role context / a worker prompt (Phase 7). Controls: (1) route through the existing `redact()` at the one mutation-path call site `[VERIFIED: src/dark_factory/persistence/mutations.py:219-227]`; (2) SQLAlchemy bound parameters only — never string-build SQL; (3) never `shell=True` with the answer; (4) consider a max length (e.g. 64 KiB) to bound the JSONB/row size — MVP-optional. |
| V6 Cryptography | no | `owner_token = uuid.uuid4()` is an opaque identifier for mutual exclusion, not a secret or a bearer token (Assumptions A8). No hand-rolled crypto. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A stale/killed process resurrects after a long human pause and double-writes the run | Tampering | `apply_transition` fenced on `expected_owner_token` against the row it already `SELECT … FOR UPDATE`s `[VERIFIED: src/dark_factory/persistence/mutations.py:200-206]`; a lost lease ⇒ `LeaseLost`, no commit |
| A second live process steals an in-flight run's lease mid-step | Denial of Service (progress loss) | daemon heartbeat renews `lock_expires_at` every TTL/3; competing claim keeps matching 0 rows |
| Infrastructure credential pasted into `--answer` or echoed in a worker question lands unredacted in Neon / events / logs | Information Disclosure | `redact()` / `scrub_known_values()` at the single `mutations.py` call site; AST guard extended to `HumanInteraction`; e2e redaction sweep over `human_interactions` (SEC-01) |
| SQL injection via `--answer` or the question text | Tampering | SQLAlchemy Core/ORM bound parameters exclusively; no f-string SQL anywhere in the lease/interaction code |
| Lease starvation: a run whose `lock_expires_at` is never reached because a buggy heartbeat over-renews after logical abort | Denial of Service | `run_lease` is a context manager — `__exit__` always stops the thread and releases; Pitfall 1 test |
| `owner_token` guessing to hijack a run | Spoofing | 122-bit `uuid4`; and hijacking only lets you do what any process can already do to a claimable run (single-tenant local tool) — not a trust boundary |

## Sources

### Primary (HIGH confidence — read this session)
- `src/dark_factory/domain/status.py`, `domain/signal.py`, `domain/worker.py`, `events/catalog.py` — enums, `STOP_STATUSES` / `TERMINAL_STATUSES`, `Signal.ROLE_NEEDS_INPUT`, `WorkerResult` validator.
- `src/dark_factory/persistence/models.py`, `mutations.py`, `repositories.py`, `engine.py` — table shapes, `apply_transition` single-transaction + row-lock + redaction call site, `RunState` field set, engine pooling config.
- `src/dark_factory/orchestrator/runner.py`, `lifecycle.py` — `advance` / `drive` / `_run_current_role` / `_enter_first_role`, `transition()` arms, `DARK_FACTORY_CRASH_AFTER` seam.
- `src/dark_factory/cli.py` — `run` / `resume` / `status` commands, `_drive_and_exit` exit-code logic.
- `src/dark_factory/workers/base.py`, `workers/fake.py`, `roles/registry.py`, `workflows/pipeline.py` — `CodingWorker.resume` contract, `FakeWorker` script env var, pipeline shape.
- `migrations/env.py`, `migrations/versions/0002_role_exec_uniqueness.py` — DDL URL resolution, `_OWNED_TABLES`, revision chaining.
- `tests/conftest.py`, `tests/integration/test_fresh_process_resume.py`, `tests/db/test_transition_atomic.py` — fixture ladder, savepoint isolation, two-subprocess pattern, mid-transaction crash-injection recipe.
- `pyproject.toml`, `.planning/config.json` — pins, markers, `requires-python`, workflow toggles.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/phases/01-*/01-RESEARCH.md` (§ lease/pause references), `01-VALIDATION.md` — requirement text, Open Decision 2, D-06 seam, Phase 1 validation format.
- CLAUDE.md — fixed stack, concurrency constraints, credential boundary, "one mutation path".

### Secondary (MEDIUM confidence — web, cross-checked against CLAUDE.md's own constraints)
- Netdata — "Using FOR UPDATE SKIP LOCKED For Queue Workflows" — claim-don't-check, composite index, crash-safety of transaction-scoped locks. https://www.netdata.cloud/academy/update-skip-locked/
- Prisma blog — "Build a Postgres Job Queue with SKIP LOCKED" — `locked_at` + reaper for jobs longer than one transaction. https://www.prisma.io/blog/you-dont-need-a-job-queue-postgres-already-has-skip-locked
- Crunchy Data — "Postgres Locking: When is it Concerning?" — session vs. transaction advisory locks; job-lifetime locks need more than a single transaction. https://www.crunchydata.com/blog/postgres-locking-when-is-it-concerning
- PgBouncer FAQ / issue threads — session-level advisory locks unsafe under transaction pooling; use `pg_advisory_xact_lock`. https://github.com/ClosureTree/with_advisory_lock/issues/43
- Kubernetes docs — "Leases" (15 s lease / 10 s renew deadline / 2 s retry) — the TTL:heartbeat ratio. https://kubernetes.io/docs/concepts/architecture/leases/
- Ajit Singh — "Lease Pattern in Distributed Systems" — renew at ~TTL/3; a lease is a lock with an expiry. https://singhajit.com/distributed-systems/lease/

### Tertiary (LOW confidence)
- The confidence seam (`gsd_run query classify-confidence --provider websearch`) rates raw web search LOW. The concrete numbers (TTL 900 / heartbeat 300) are a **recommendation to validate** via the SC5 slow-step test, exactly as the phase's own Decision note requires — not a locked fact.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every symbol referenced was read in the Phase 1 source this session.
- Architecture patterns: HIGH — the lease + heartbeat + pause/resume design maps directly onto existing seams (`STOP_STATUSES`, `Signal.ROLE_NEEDS_INPUT`, `CodingWorker.resume`, `apply_transition` row-lock) and onto the spec's mandated "claim-don't-check" wording.
- Concurrency correctness (claim-don't-check, DB clock, token fence): HIGH — standard Postgres semantics, corroborated by multiple sources and CLAUDE.md.
- Concrete TTL / heartbeat numbers: MEDIUM — ratio (TTL/3) is well-established; absolute values are a defensible starting point pending the SC5 test.
- Pitfalls: HIGH — each is either observed in the Phase 1 code shape or a direct consequence of the pooling/clock constraints.

**Research date:** 2026-09-09
**Valid until:** ~2026-10-09 for the (unchanging) stack; the architecture guidance is stable for the life of the milestone.
