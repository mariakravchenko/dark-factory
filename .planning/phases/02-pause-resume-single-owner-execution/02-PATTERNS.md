# Phase 2: Pause, Resume & Single-Owner Execution - Pattern Map

**Mapped:** 2026-09-09
**Files analyzed:** 20 (7 new, 13 modified) + 12 Wave-0 test files
**Analogs found:** 20 / 20 (every file extends or mirrors an existing Phase 1 module)

All analog paths below are git-tracked source under `src/dark_factory/`, `tests/`,
and `migrations/` (verified `git ls-files`). No gitignored mirror paths.

Phase 2 adds **no new third-party dependency**. Every new file either extends an
existing module in place or is a near-verbatim mirror of a Phase 1 sibling.

---

## File Classification

### Source files

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/dark_factory/domain/interaction.py` (NEW) | domain enum | transform | `src/dark_factory/domain/signal.py` (`Signal` StrEnum) / `domain/status.py` | exact |
| `src/dark_factory/domain/status.py` (MOD: `STOP_STATUSES += WAITING_HUMAN`) | domain constant | transform | itself — `STOP_STATUSES` at `status.py:35-42` (change already anticipated in docstring) | exact |
| `src/dark_factory/domain/signal.py` (no change expected; `ROLE_NEEDS_INPUT` already present `signal.py:28,34`) | domain enum | transform | — | n/a (already done) |
| `src/dark_factory/events/catalog.py` (MOD: +4 `EventType` members) | domain enum | event-driven | itself — `EventType` at `catalog.py:16-24` | exact |
| `src/dark_factory/config/settings.py` (MOD: +`lease_ttl_seconds`, +`lease_heartbeat_seconds`) | config | request-response | itself — `Settings` fields at `settings.py:43-46` | exact |
| `src/dark_factory/persistence/models.py` (MOD: `Run` +2 cols; NEW `HumanInteraction`; NEW `_INTERACTION_STATUS`) | model | CRUD | `Run` cols `models.py:98-117`; `RoleExecution` class `models.py:120-156`; `_RUN_STATUS` `models.py:65-72` | exact |
| `src/dark_factory/persistence/mutations.py` (MOD: `apply_transition` +`human_interaction`, +`expected_owner_token`, lease-clear-on-stop) | service | CRUD / transaction | itself — `apply_transition` `mutations.py:153-229`, `_write_role_execution` `mutations.py:232-277` | exact |
| `src/dark_factory/orchestrator/lease.py` (NEW: `claim_lease` / `renew_lease` / `release_lease` + `run_lease` ctx mgr + heartbeat `Thread`) | service / orchestrator | event-driven (periodic) | `persistence/engine.py:101-107` (`new_session`), `mutations.py:199-229` (`with session.begin()` + `sa.update(...).returning(...)` shape from RESEARCH Code Examples) | role-match |
| `src/dark_factory/orchestrator/answers.py` (NEW: `submit_answer(run_id, answer)`) — or fold into `runner.py` | orchestrator | request-response | `orchestrator/runner.py:210-246` (`_enter_first_role` — single guarded `apply_transition` call) | role-match |
| `src/dark_factory/orchestrator/lifecycle.py` (MOD: +`ROLE_NEEDS_INPUT` arm) | orchestrator (pure FSM) | transform | itself — `ROLE_FAILED` arm `lifecycle.py:98-99` | exact |
| `src/dark_factory/orchestrator/runner.py` (MOD: `_run_current_role` execute-vs-resume + `NEEDS_INPUT` branch; `advance`/`drive` wrap `run_lease`; `advance` early-return on `WAITING_HUMAN`) | orchestrator | request-response / event-driven | itself — `_run_current_role` `runner.py:248-326`, `advance` guard `runner.py:195-198`, `drive` loop `runner.py:329-368` | exact |
| `src/dark_factory/persistence/repositories.py` (MOD: `LatestExecution +result`; `RunState +pending_answer`; load `ANSWERED` interaction) | model / read path | request-response | itself — `LatestExecution` `repositories.py:48-58`, `load_run_state` second `select` `repositories.py:103-124` | exact |
| `src/dark_factory/cli.py` (MOD: `resume` +`--answer` option; `_drive_and_exit` exit 0 on `WAITING_HUMAN`) | controller (CLI) | request-response | itself — `resume` `cli.py:133-146`, `_drive_and_exit` `cli.py:106-117` | exact |
| `src/dark_factory/workers/fake.py` (MOD: `DARK_FACTORY_FAKE_SLEEP_MS` knob) | utility / test-double | transform | itself — `_SCRIPT_ENV_VAR` handling `fake.py:29,46-50`, `resume` `fake.py:73-76` | exact |
| `migrations/versions/0003_pause_resume_lease.py` (NEW) | migration | DDL / batch | `migrations/versions/0002_role_exec_uniqueness.py:1-41` | exact |
| `migrations/env.py` (MOD: `_OWNED_TABLES += "human_interactions"`) | config | DDL | itself — `_OWNED_TABLES` `env.py:44` | exact |

### Wave 0 test-infra + test files (all NEW unless "extend")

| File | Role | Closest Analog | Match |
|------|------|----------------|-------|
| `tests/support/subprocess_runner.py` (NEW — lift `_ENV_ALLOWLIST` / `_child_env` / `_spawn` + `fake_sleep_ms` param) | test helper | `tests/integration/test_fresh_process_resume.py:43-83` | exact |
| `tests/conftest.py` (extend: `use_lease_settings` fixture + `force_lease_expiry(run_id)` fixture) | test fixture | `use_fake_secrets` `conftest.py:272-280`; `fake_worker_registry` `conftest.py:342-354` | exact |
| `tests/unit/test_single_mutation_path.py` (EXTEND: add `HumanInteraction` to `_LIFECYCLE_CTORS`) | AST guard | itself — `_LIFECYCLE_CTORS` `test_single_mutation_path.py:32` | exact |
| `tests/db/test_human_interactions_schema.py` (NEW) | db test | `tests/db/test_schema_shape.py`, `test_transition_atomic.py` | role-match |
| `tests/db/test_pause_path_atomic.py` / `test_lease_lost_aborts_step.py` (NEW) | db test (crash injection) | `tests/db/test_transition_atomic.py:52-181` (`after_cursor_execute` recipe) | exact |
| `tests/db/test_lease_claim_atomic.py` (NEW — N-thread race) | db test | `tests/db/test_transition_atomic.py` (real engine, `real_session_factory` `:62-71`) | role-match |
| `tests/integration/test_resume_with_answer.py` / `test_single_owner_race.py` / `test_lease_expiry_reclaim.py` / `test_heartbeat_slow_step.py` / `test_no_txn_across_worker.py` (NEW) | integration test (two real processes) | `tests/integration/test_fresh_process_resume.py:93-163` | exact |
| `tests/unit/test_lifecycle.py`, `tests/unit/test_domain_enums.py`, `tests/db/test_terminal_advance_noop.py`, `tests/contract/test_coding_worker_contract.py` (EXTEND) | existing suites | themselves | exact |

---

## Pattern Assignments

### `src/dark_factory/domain/interaction.py` (NEW — domain enum)

**Analog:** `src/dark_factory/domain/signal.py:22-28` (StrEnum, value == name, module docstring, `__all__`).

Mirror shape (from RESEARCH Code Examples):
```python
from enum import StrEnum

__all__ = ["InteractionStatus"]

class InteractionStatus(StrEnum):
    WAITING = "WAITING"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"
```
`CANCELLED` is declared but written nowhere this phase (RESEARCH Open Q 3) — safe for a CHECK value, unlike an unwritten `EventType`.

---

### `src/dark_factory/persistence/models.py` (MOD)

**Analog:** itself.

**Lease columns on `Run`** — mirror the "present now, nullable, unused until a later phase" pattern of `base_branch` / `working_branch` at `models.py:98-100`:
```python
owner_token: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)
lock_expires_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True
)
```
`datetime` is already imported (`models.py:51`); `uuid` at `models.py:50`.

**`_INTERACTION_STATUS`** — exact mirror of `_RUN_STATUS` at `models.py:65-72` (VARCHAR + CHECK, `native_enum=False`, `create_constraint=True`, `values_callable`):
```python
_INTERACTION_STATUS = sa.Enum(
    InteractionStatus, native_enum=False, create_constraint=True, length=16,
    name="interaction_status",
    values_callable=lambda enum: [member.value for member in enum],
)
```

**`HumanInteraction` model** — structure mirrors `RoleExecution` at `models.py:120-156`: `sa.Uuid()` PK with `default=uuid.uuid4`, `run_id` FK `sa.ForeignKey("runs.id")` NOT NULL indexed (`models.py:138-140`), `role_execution_id` FK (mirror `RunEvent.role_execution_id` `models.py:180-182` but NOT NULL), `created_at` with `server_default=sa.func.now()` (`models.py:148-150`). `__table_args__` partial unique index mirrors `RoleExecution.__table_args__` `models.py:131-133`. Full body is in RESEARCH lines 472-495.

**Guard note:** add `HumanInteraction` (and `_INTERACTION_STATUS`) to `__all__` at `models.py:60`.

---

### `src/dark_factory/persistence/mutations.py` (MOD — the one mutation path)

**Analog:** itself — `apply_transition` `mutations.py:153-229`.

**Existing transaction block to extend** (`mutations.py:199-229`):
```python
with session.begin():
    run = session.get(Run, run_id, with_for_update=True)   # row lock — reuse for the token fence
    if run is None:
        raise LookupError(run_id)
    if run.status != expected_status:
        raise ConcurrentTransition(...)
    if role_execution is not None:
        _write_role_execution(session, run_id, role_execution, known)
    run.status = next_status
    run.current_role = next_current_role
    run.current_step = next_current_step
    run.updated_at = func.now()
    for name, delta in increments.items():
        setattr(run, name, getattr(run, name) + delta)
    for event in events:
        session.add(RunEvent(..., payload=redact(event.payload, known_secrets=known)))
```

**Phase 2 additions, all inside that same block:**
1. New param `expected_owner_token: UUID | None = None`. After the `expected_status` check, on the **already-locked** `run` row: `if expected_owner_token is not None and run.owner_token != expected_owner_token: raise LeaseLost(...)`. New exception class mirrors `ConcurrentTransition` at `mutations.py:63-66`; add to `__all__` (`mutations.py:48-54`).
2. New param `human_interaction: HumanInteractionWrite | None = None` — a frozen pydantic call-shape model mirroring `RoleExecutionWrite` at `mutations.py:69-83` (`model_config = ConfigDict(frozen=True, extra="forbid")`, **raw** text fields). A `_write_human_interaction(...)` helper mirrors `_write_role_execution` at `mutations.py:232-277`, applying `redact(spec.question, known_secrets=known)` / `redact(spec.answer, ...)` at the single call site (same as `mutations.py:240-243`).
3. Lease-clear rule: `if next_status in STOP_STATUSES: run.owner_token = None; run.lock_expires_at = None`. Import `STOP_STATUSES` from `dark_factory.domain.status` (module already imports `RunStatus` from there, `mutations.py:42`).
4. Redaction call site is unchanged — question/answer flow through the same `redact()` used for `result`/`error`/`payload`.

**Do NOT** add a parallel writer. Lease *claim/renew/release* (which touch only `owner_token`/`lock_expires_at`/`updated_at`, never lifecycle columns or audit rows) live in `orchestrator/lease.py` and do not trip `test_single_mutation_path.py` (guard is `RunEvent`/`RoleExecution` ctors + `.status` assignment only — `test_single_mutation_path.py:32,64-68`). The interaction row + status transition go **through** `apply_transition`.

---

### `src/dark_factory/orchestrator/lease.py` (NEW)

**Analogs:**
- Session creation: `persistence/engine.py:101-107` — `SessionLocal = sessionmaker(expire_on_commit=False, future=True)`, `new_session()` returns a fresh session on the `NullPool` engine. The heartbeat **Thread must call `new_session()` itself** — one `Session` per thread, never shared.
- Atomic claim `UPDATE ... RETURNING`: RESEARCH Code Examples lines 500-527 (verbatim `claim_lease`); mirrors the `sa.update(...).values(...).returning(...)` idiom and `with session.begin():` discipline from `mutations.py:199-229` and `_write_role_execution`'s `select(func.coalesce(...))` at `mutations.py:246-251`.
- DB-clock arithmetic: `func.now() + timedelta(seconds=ttl)` — same `func.now()` used for every timestamp column (`models.py:110-116`, `mutations.py:214`). Never `datetime.now()`.
- Test-only env-knob-read-at-call-time discipline: `_maybe_crash_after` at `runner.py:121-140` (`os.environ.get(...)` inside the function, never cached at import) — apply the same to any `DARK_FACTORY_*` knob the heartbeat honors.
- Context-manager cleanup guarantee: `_drive_and_exit` try/except at `cli.py:106-117` and the `try/finally: session.close()` pattern throughout `runner.py` (`:157-161`, `:221-245`, `:302-326`). `run_lease.__exit__` must always `stop_event.set()` → `thread.join(timeout=...)` → best-effort release, on every exit path (RESEARCH Pitfall 1).
- `structlog` bound context: `bind_contextvars(run_id=..., role=..., attempt=...)` at `runner.py:201` — bind `run_id` for "lost the race, exiting" / "lease renewed" / "lease lost mid-step" lines.

Retry: **none.** A lost claim is a clean `return current_status` + exit 0, not a `tenacity` retry (contrast the single sanctioned retry at `engine.py:72-83`).

---

### `src/dark_factory/orchestrator/lifecycle.py` (MOD — pure FSM)

**Analog:** the `ROLE_FAILED` arm at `lifecycle.py:98-99`:
```python
if signal is Signal.ROLE_FAILED:
    return RunStatus.FAILED, role, state.current_step
```
Add immediately after (RESEARCH lines 536-538):
```python
if signal is Signal.ROLE_NEEDS_INPUT:
    return RunStatus.WAITING_HUMAN, role, state.current_step   # current_role retained
```
`Signal.ROLE_NEEDS_INPUT` already imported via `from dark_factory.domain.signal import Signal` (`lifecycle.py:25`). Keep the function pure — no `Session`, no I/O (`lifecycle.py:1-19`).

---

### `src/dark_factory/orchestrator/runner.py` (MOD)

**Analog:** itself.

**`advance` early-return** — extend the guard at `runner.py:197-198`:
```python
if state.status in TERMINAL_STATUSES:      # existing
    return state.status
```
to also stop on `WAITING_HUMAN` (use `state.status in STOP_STATUSES`, already importable — `runner.py:41` imports both sets). RESEARCH Pitfall 7.

**`_run_current_role` execute-vs-resume** — at `runner.py:263-266`:
```python
worker = registry.get(node.worker)
result = worker.execute(_build_context(run_id, state, node))   # existing
```
becomes column-driven (RESEARCH lines 293-299):
```python
if latest.status == "RESUMING":
    previous = WorkerResult.model_validate(latest.result)
    result = worker.resume(_build_context(run_id, state, node), previous, state.pending_answer)
else:
    result = worker.execute(_build_context(run_id, state, node))
```
`worker.resume(context, previous, answer)` is already in the ABC (`workers/base.py:24-27`) and `FakeWorker` (`fake.py:73-76`).

**`NEEDS_INPUT` branch** — the `if/elif/else` at `runner.py:269-300` currently has `ROLE_COMPLETED` / `ROLE_FAILED` / `raise`. Add a `elif signal is Signal.ROLE_NEEDS_INPUT:` arm mirroring the `ROLE_FAILED` arm shape (`runner.py:288-298`): `re_status = "WAITING_HUMAN"`, `re_result = outcome` (the NEEDS_INPUT dict — needed for `previous` on resume), `worker_session_id=result.worker_session_id`, events `[QUESTION_CREATED, RUN_PAUSED]`, plus build a `HumanInteractionWrite(status="WAITING", question="\n".join(result.questions), role_execution_id=latest.id)` and pass it + `expected_owner_token=<held token>` into the existing `apply_transition` call at `runner.py:304-322`.

**Lease wrap** — RESEARCH Open Q 2 / A6: refactor the per-step body into a private `_step(...)` that assumes the lease is held; `drive()` (`runner.py:329-368`) wraps its whole loop in `with run_lease(run_id, ...)`; a directly-called `advance()` wraps its single body. `_maybe_crash_after` calls (`runner.py:242,323`) stay.

**`_build_context`** (`runner.py:104-118`) gains `"answer": state.pending_answer`.

---

### `src/dark_factory/persistence/repositories.py` (MOD — read path)

**Analog:** itself.

- `LatestExecution` (`repositories.py:48-58`) gains `result: dict[str, Any] | None = None`; populate it from `latest_row.result` in the constructor call at `repositories.py:114-122`.
- `RunState` (`repositories.py:61-79`) gains `pending_answer: str | None`.
- Add one bound-parameterised `select` on `human_interactions` for the single `ANSWERED` row of a run in `<role>` with `latest.status == "RESUMING"` — mirror the second `select(RoleExecution)...limit(1)` at `repositories.py:103-112`. This module still imports nothing from the events package (STATE-06, `repositories.py:26-30`) — `human_interactions` is a state table, allowed.

---

### `src/dark_factory/cli.py` (MOD — CLI controller)

**Analog:** itself.

- `resume` at `cli.py:133-146` gains `answer: str | None = typer.Option(None, "--answer")` (mirror the `output_json` option style at `cli.py:152-154`). When `answer` is not None, route through `submit_answer(parsed, answer)` (orchestrator code) **before** `_drive_and_exit(parsed)`. Keep the `run_state(parsed) is None → exit 2` check at `cli.py:142-144`. The CLI must not inspect run status to branch (`cli.py:1-6`, RESEARCH anti-pattern).
- `_drive_and_exit` at `cli.py:117`: `raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)` → exit **0** for `COMPLETED` **or** `WAITING_HUMAN`, else 1.
- Add `LeaseLost` to `_ORCHESTRATION_ERRORS` (`cli.py:58-65`) so a mid-step steal exits 2 ("nothing new persisted"), not a traceback.

---

### `src/dark_factory/events/catalog.py` (MOD)

**Analog:** `EventType` at `catalog.py:16-24`. Add exactly four members actually written this phase (RESEARCH A9): `QUESTION_CREATED`, `RUN_PAUSED`, `HUMAN_ANSWER_RECEIVED`, `RUN_RESUMED`. Update the docstring (`catalog.py:1-9`) to note Phase 2 adds these four; the rest stay "Phase 12". Do **not** pre-declare the rest (RESEARCH anti-pattern — an unwritten member is a false audit signal).

---

### `src/dark_factory/config/settings.py` (MOD)

**Analog:** `Settings` scalar fields at `settings.py:43-46`. Add:
```python
lease_ttl_seconds: int = 900
lease_heartbeat_seconds: int = 300
```
Plain `int` fields with production defaults (not `SecretStr` — not secrets). `known_secret_values()` (`settings.py:61-78`) already skips non-`SecretStr` fields, so no change there. Tests override via a fixture (see below).

---

### `src/dark_factory/domain/status.py` (MOD)

**Analog:** itself — `STOP_STATUSES` at `status.py:35-42`, whose docstring already says "Phase 2 adds `WAITING_HUMAN` to *this* set (and only this set)". One line:
```python
STOP_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_HUMAN}
)
```
`TERMINAL_STATUSES` (`status.py:30-32`) is **unchanged** (RESEARCH anti-pattern). `RunStatus.WAITING_HUMAN` already exists (`status.py:26`).

---

### `src/dark_factory/workers/fake.py` (MOD)

**Analog:** itself — `_SCRIPT_ENV_VAR` / `_script_from_env` at `fake.py:29,46-50`, read via `os.environ.get` at call time. Add a `DARK_FACTORY_FAKE_SLEEP_MS` module constant + a `time.sleep(ms/1000)` at the top of `execute()` (`fake.py:64-71`) when set. Mirrors the test-only env-knob convention of `DARK_FACTORY_FAKE_SCRIPT` and `DARK_FACTORY_CRASH_AFTER`. `resume()` (`fake.py:73-76`) already delegates to `execute()`, so it inherits the sleep.

---

### `migrations/versions/0003_pause_resume_lease.py` (NEW)

**Analog:** `migrations/versions/0002_role_exec_uniqueness.py:1-41` — the full revision skeleton:
```python
from __future__ import annotations
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0003_pause_resume_lease"
down_revision: str | Sequence[str] | None = "0002_role_exec_uniqueness"   # 0002:26
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table("human_interactions", ...)            # cols per RESEARCH 203-213
    op.create_index("uq_one_waiting_interaction_per_run", "human_interactions",
                    ["run_id"], unique=True,
                    postgresql_where=sa.text("status = 'WAITING'"))
    op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))
    op.add_column("runs", sa.Column("lock_expires_at",
                  sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("runs", "lock_expires_at")
    op.drop_column("runs", "owner_token")
    op.drop_index("uq_one_waiting_interaction_per_run", table_name="human_interactions")
    op.drop_table("human_interactions")
```
Keep the revision id ≤ 32 chars (`0002` docstring note). Both new `runs` columns nullable, no default. Runs against the **direct** endpoint via `migrations/env.py:49-55` resolution order — no change needed there for the URL.

---

### `migrations/env.py` (MOD)

**Analog:** `_OWNED_TABLES` at `env.py:44`:
```python
_OWNED_TABLES = {"runs", "role_executions", "run_events"}
```
→ add `"human_interactions"`. Otherwise `alembic check` / autogenerate proposes to drop it (`env.py:18-22,82-85`).

---

## Shared Patterns

### DB-clock everything (HITL-08)
**Source:** `src/dark_factory/persistence/models.py:109-117` (`server_default=sa.func.now()`, `onupdate=sa.func.now()`), `mutations.py:214` (`run.updated_at = func.now()`).
**Apply to:** `lease.py` (claim/renew), `mutations.py` lease-clear, migration `0003`.
**Rule:** the expiry *value* is always `func.now() + timedelta(seconds=ttl)` in a SQL expression; the expiry *test* is always `Run.lock_expires_at < func.now()` in a `WHERE`. Grep the Phase 2 diff for `datetime.now` / `datetime.utcnow` near lease code — must be zero (RESEARCH Pitfall 3).

### One transaction, one redaction call site (ORCH-06, SEC-01/02)
**Source:** `src/dark_factory/persistence/mutations.py:199-229` (single `with session.begin():`), `:219-227` and `:240-243` (the `redact(..., known_secrets=known)` call site).
**Apply to:** every persisted question/answer/worker-result string in the pause and resume paths — they flow through `apply_transition`'s existing `redact()` calls, never a new one.

### Row-lock reuse for the ownership fence
**Source:** `mutations.py:200` — `run = session.get(Run, run_id, with_for_update=True)`.
**Apply to:** the `expected_owner_token` check in `apply_transition` — compare against `run.owner_token` on the row **already** `FOR UPDATE`-locked, no second `SELECT` (RESEARCH Pitfall 2).

### Guarded single `apply_transition` call from an orchestrator entry point
**Source:** `src/dark_factory/orchestrator/runner.py:210-246` (`_enter_first_role`): open session via `session_factory()`, one `apply_transition(...)` with `expected_status` / `role_execution=RoleExecutionWrite(...)` / `events=[EventWrite(...)]`, `try/finally: session.close()`.
**Apply to:** `submit_answer` (the `WAITING_HUMAN → <role>` transition + interaction update + `HUMAN_ANSWER_RECEIVED` / `RUN_RESUMED` events).

### Test-only env knob, read at call time, never cached at import
**Source:** `src/dark_factory/orchestrator/runner.py:121-140` (`_maybe_crash_after`) + its AST guard `tests/integration/test_fresh_process_resume.py:175-207`.
**Apply to:** `DARK_FACTORY_FAKE_SLEEP_MS` in `fake.py`, any lease knob.

### One `Session` per thread
**Source:** `src/dark_factory/persistence/engine.py:101-107` (`SessionLocal` / `new_session`), NullPool = fresh socket per session.
**Apply to:** the heartbeat `threading.Thread` in `lease.py` — it calls `new_session()` itself; never shares the main thread's session (RESEARCH anti-pattern).

### AST source-tree guard extension
**Source:** `tests/unit/test_single_mutation_path.py:32` (`_LIFECYCLE_CTORS = {"RunEvent", "RoleExecution"}`).
**Apply to:** add `"HumanInteraction"` so it can only be constructed in `mutations.py`.

---

## Test Infrastructure Patterns (Wave 0)

### Two-real-process race / resume harness
**Source:** `tests/integration/test_fresh_process_resume.py:38-83` — `_REPO_ROOT`, `_ENV_ALLOWLIST` (explicit, no `os.environ.copy()`), `_child_env(pg_url, crash_after=...)`, `_spawn(args, env)` (`subprocess.run([sys.executable, "-m", "dark_factory", *args], ...)`).
**Lift to:** `tests/support/subprocess_runner.py`, add `fake_sleep_ms: int | None` (sets `DARK_FACTORY_FAKE_SLEEP_MS`). Use for `test_single_owner_race.py`, `test_resume_with_answer.py`, `test_lease_expiry_reclaim.py`, `test_heartbeat_slow_step.py` (RESEARCH lines 552-562).

### Mid-transaction crash injection
**Source:** `tests/db/test_transition_atomic.py:52-181` — `after_cursor_execute` listener keyed on an upper-cased statement prefix (`_INJECTION_POINTS`), `real_session_factory` (fresh `Session(bind=engine)` per call, real commits, NullPool discards on close, `:62-71`), `cleanup_runs` fixture (`:74-83`), listener registered/removed inside the test body, post-crash assertions through a session opened after removal.
**Apply to:** `tests/db/test_pause_path_atomic.py` (parametrize the injection over the `human_interactions` INSERT and the `runs` UPDATE) and `tests/db/test_lease_lost_aborts_step.py`.

### Settings override fixture
**Source:** `tests/conftest.py:261-280` — `fake_settings` builds a `Settings(_env_file=None, ...)`; `use_fake_secrets` does `monkeypatch.setattr(mutations, "get_settings", lambda: fake_settings)`.
**Apply to:** a `use_lease_settings` fixture yielding `Settings(..., lease_ttl_seconds=2, lease_heartbeat_seconds=1)` and monkeypatching wherever `get_settings` is read for the lease (likely `orchestrator/lease.py`). Note `get_settings` is `functools.lru_cache`d (`settings.py:81-83`) — patch the reference in the consuming module, as `use_fake_secrets` does, not the cache.

### Forced lease expiry (time-machine cannot move the PG clock — RESEARCH Pitfall 4)
**Source:** the raw-SQL teardown idiom in `tests/db/test_transition_atomic.py:78-82` (`engine.begin()` + `conn.execute(sa.update/delete...)`).
**New fixture:** `force_lease_expiry(run_id)` → `UPDATE runs SET lock_expires_at = now() - interval '1 second' WHERE id = :id`. Primary fast path for reclaim tests; pair with one real `lease_ttl_seconds=2` + `time.sleep(2.5)` test for honesty.

### `fake_worker_registry` builder
**Source:** `tests/conftest.py:342-354` — `build(script) -> WorkerRegistry` with `"fake"` → `FakeWorker(list(script))`. Already used by `test_transition_atomic.py:128,132`. Reuse for every Phase 2 orchestration test; extend with a variant that honors `sleep_ms` for the heartbeat slow-step test.

### `application_name` on the engine (for the `idle in transaction` assertion — HITL-08)
**Source:** `src/dark_factory/persistence/engine.py:63-69` — `connect_args={"prepare_threshold": None}`.
**Change:** add `"application_name": "dark-factory"` to that dict so `test_no_txn_across_worker.py` can filter `pg_stat_activity WHERE application_name = 'dark-factory' AND state = 'idle in transaction'`.

---

## No Analog Found

None. Every Phase 2 file extends an existing module or mirrors a Phase 1 sibling
of the same role and data flow. The two genuinely new modules (`orchestrator/lease.py`,
`orchestrator/answers.py`) compose existing patterns (`new_session` + `with session.begin()`
+ `sa.update().returning()` + context-manager cleanup + `structlog` bound context)
rather than introducing an unprecedented shape.

---

## Metadata

**Analog search scope:** `src/dark_factory/**` (all 40 modules), `tests/{unit,db,integration,contract,support}/**`, `migrations/**`.
**Files scanned in full:** `persistence/{models,mutations,repositories,engine}.py`, `orchestrator/{runner,lifecycle}.py`, `cli.py`, `domain/{status,signal}.py`, `events/catalog.py`, `config/settings.py`, `workers/{base,fake}.py`, `migrations/env.py`, `migrations/versions/0002_role_exec_uniqueness.py`, `tests/conftest.py` (fixtures), `tests/db/test_transition_atomic.py`, `tests/integration/test_fresh_process_resume.py`, `tests/unit/test_single_mutation_path.py`, `domain/worker.py` (grep).
**Tracked-source gate:** all analog paths verified under `git ls-files` (`src/`, `tests/`, `migrations/` are tracked; no `.gsd/capabilities` mirror in play).
**Pattern extraction date:** 2026-09-09
