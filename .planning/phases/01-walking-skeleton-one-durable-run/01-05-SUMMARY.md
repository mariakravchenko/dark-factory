---
phase: 01-walking-skeleton-one-durable-run
plan: 05
subsystem: persistence
tags: [sqlalchemy, postgresql, single-transaction, redaction, resume-first, tdd, security]

requires:
  - phase: 01-02
    provides: "RunStatus, NormalizedTask, EventType"
  - phase: 01-03
    provides: "redact() / scrub_known_values() (D-14/D-18), Settings + known_secret_values() (D-16)"
  - phase: 01-04
    provides: "Base / Run / RoleExecution / RunEvent ORM models; migration 0001 applied; conftest db_session (create_savepoint) + _schema_at_head hook"
provides:
  - "persistence/mutations.py — create_run() and apply_transition(): the one lifecycle mutation path. Each opens exactly one `with session.begin():` and commits once; no explicit commit call. redact() applied at the single call site before every result/error/payload write (SEC-02). role_executions.attempt = SQL MAX(attempt)+1 per run+role inside the transaction (STATE-03/D-19). ConcurrentTransition on stale expected_status; ValueError on a status change with empty events (ORCH-06)."
  - "persistence/mutations.py exports: create_run, apply_transition, ConcurrentTransition, RoleExecutionWrite, EventWrite"
  - "persistence/repositories.py — load_run_state() and RunState: reconstruct the full Phase-1 resume-value set from runs + the single latest role_executions row into a frozen, detached value object; never queries run_events; imports nothing from dark_factory.events (STATE-06/STATE-08)"
  - "persistence/repositories.py exports: load_run_state, RunState, LatestExecution"
  - "tests/unit/test_single_mutation_path.py — AST source-tree guard: no module outside persistence/mutations.py constructs RunEvent/RoleExecution or assigns .status"
  - "tests/conftest.py — fake_settings / use_fake_secrets fixtures + polyfactory NormalizedTask / WorkerResult factories"
affects: [01-06, 01-07, 01-08, 01-09]

actuals:
  tokens: 10500
  tasks: 2
  commits: 4
  plan_head_before: a45f053032a14f43b74d854b0ef50d32f845817f

tech-stack:
  added: []
  patterns:
    - "One mutation path = one module, one transaction discipline, one redaction call (not one function): create_run is a sibling of apply_transition in mutations.py because the first insert has no row to guard with expected_status (RESEARCH Open Question 3)"
    - "with session.begin() is the only atomicity primitive — no explicit commit call anywhere in the module; asserted by a test that greps the module source for `session.commit(`"
    - "Call-shape models (RoleExecutionWrite / EventWrite) are frozen pydantic and carry RAW payloads; redaction is the module's responsibility so a caller cannot forget it (T-01-01)"
    - "role_executions.attempt computed as `select(func.coalesce(func.max(attempt), 0) + 1)` scoped to run_id + role, inside the mutation transaction — never an in-memory counter (T-01-02: bound parameters, no string SQL)"
    - "RunState is a frozen pydantic value object built from scalar column values — no Session, no ORM instance, no lazy-load proxy; the resume path cannot depend on session identity"
    - "load_run_state imports nothing from dark_factory.events and issues no run_events query — STATE-06 as an import-graph constraint, not just behaviour"
    - "The single-writer invariant is proven by an AST walk (ast.Call to RunEvent/RoleExecution; ast.Assign/AugAssign to a .status attribute), so docstrings mentioning those names do not trip it and failures name file:line"
    - "db-tier tests obey the create_savepoint rule: back-to-back `with session.begin()` is fine, but a bare read autobegins a transaction that must be `session.rollback()`-released before the next mutation"

key-files:
  created:
    - "src/dark_factory/persistence/mutations.py"
    - "src/dark_factory/persistence/repositories.py"
    - "tests/db/test_create_run.py"
    - "tests/db/test_apply_transition.py"
    - "tests/db/test_load_run_state.py"
    - "tests/unit/test_single_mutation_path.py"
  modified:
    - "tests/conftest.py — added fake_settings / use_fake_secrets fixtures + polyfactory factories; moved the FakeWorker-injection marker to Plan 06"

key-decisions:
  - "create_run is a sibling function, not a call into apply_transition (RESEARCH Open Question 3 recommendation): the ∅→CREATED insert has no pre-existing row for the with_for_update / expected_status guard. Both share mutations.py, one `with session.begin():`, and the same redact() call."
  - "normalized_task and source_ref are persisted through scrub_known_values() (redact patterns=False, D-18) — known live secret values are removed, generic connection-string wording is preserved. The RUN_CREATED payload gets full pattern redaction like every other event payload."
  - "The empty-events guard (status change with no audit row) raises ValueError BEFORE `with session.begin():` opens, so nothing is even attempted. Same for an unknown counter name in counter_increments."
  - "counter_increments is restricted to {qa_developer_iterations, quality_gate_iterations} (D-19); any other key is a ValueError."
  - "load_run_state orders role_executions by attempt DESC LIMIT 1 scoped to the run (Phase 1 has one role, so this is unambiguous); latest_execution is None when no row exists rather than raising."
  - "RunState / LatestExecution are extra='forbid' frozen pydantic; equality is structural so the two-independent-sessions and injected-run_events tests compare with ==."
  - "test_single_mutation_path.py implemented as an AST walk rather than text/grep so mutations.py mentioning the names in its docstring is irrelevant and the allowed-module set is a single Path."
  - "ruff format run alongside ruff check (CLAUDE.md mandates both; plan <verify> lists only ruff check) — formatting-only, folded into the task commits, same call the 01-02/01-03/01-04 executors made."

patterns-established:
  - "The one write path and the one read path for lifecycle state now exist; Plans 06-09 import create_run / apply_transition / load_run_state and never touch runs.status / role_executions / run_events directly (enforced by tests/unit/test_single_mutation_path.py)."

requirements-completed: [ORCH-06, STATE-03, STATE-06, SEC-02]

coverage:
  - id: D1
    description: "create_run inserts one CREATED runs row + one RUN_CREATED event in one transaction; returns the id; counters at column default 0; persisted task text scrubbed for known values only (D-18); RUN_CREATED payload pattern-redacted"
    requirement: "ORCH-06"
    verification:
      - kind: integration
        ref: "tests/db/test_create_run.py (6 tests vs live PostgreSQL 18.6)"
        status: pass
  - id: D2
    description: "apply_transition writes role_executions + runs columns + run_events atomically in one `with session.begin():`; ConcurrentTransition on stale expected_status with zero writes; ValueError on a status change with empty events; an exception mid-write rolls back every table; attempt = SQL MAX+1 in-transaction (1 then 2); counter_increments scoped"
    requirement: "STATE-03"
    verification:
      - kind: integration
        ref: "tests/db/test_apply_transition.py (11 tests vs live PostgreSQL 18.6)"
        status: pass
  - id: D3
    description: "redact() applied inside apply_transition immediately before each session.add / assignment: a result URI with credentials stores [redacted:database_url] and no password; an event payload containing the live known DATABASE_URL value stores a [redacted: token and not the value"
    requirement: "SEC-02"
    verification:
      - kind: integration
        ref: "tests/db/test_apply_transition.py::test_role_execution_result_uri_is_stored_redacted / ::test_event_payload_known_secret_value_is_stored_redacted; tests/db/test_create_run.py::test_persisted_task_text_scrubs_known_value_only_not_generic_uri_talk / ::test_run_created_event_payload_is_pattern_redacted"
        status: pass
  - id: D4
    description: "load_run_state reconstructs run_id, status, current_role, current_step, normalized_task (as NormalizedTask), workflow, both iteration counters and the latest role-execution record from columns; None for an unknown id; None latest when no role_executions row; survives the producing session closing; equal across two independent sessions; unaffected by an injected run_events row; no import from dark_factory.events"
    requirement: "STATE-06"
    verification:
      - kind: integration
        ref: "tests/db/test_load_run_state.py (7 tests vs live PostgreSQL 18.6)"
        status: pass
  - id: D5
    description: "persistence/mutations.py is the sole module that constructs RunEvent/RoleExecution or assigns .status, proven by a source-tree AST walk"
    requirement: "ORCH-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_single_mutation_path.py (2 tests); tests/db/test_create_run.py::test_mutations_module_never_calls_session_commit"
        status: pass

duration: 35min
completed: 2026-09-08
status: complete
---

# Phase 01 Plan 05: The One Mutation Path Summary

**`create_run` and `apply_transition` in `persistence/mutations.py` are the entire write surface for lifecycle state — each one `with session.begin():` block, one commit, no explicit commit call, `redact()` at the single call site before every JSONB write, `role_executions.attempt` computed in SQL inside the transaction; `load_run_state` in `persistence/repositories.py` reconstructs the full Phase-1 resume set from columns into a frozen detached `RunState` that never folds the event log — all proven RED→GREEN against real PostgreSQL 18.6, with an AST source-tree test proving `mutations.py` is the only lifecycle writer.**

## Contract record (Plans 06/07/08 are written against these)

### `create_run`

```python
def create_run(
    session: Session,
    *,
    task: NormalizedTask,
    workflow: dict[str, Any],
) -> UUID
```

Opens one `with session.begin():`. Inserts the `runs` row with `status=RunStatus.CREATED`, `current_role=None`, `current_step=None`, both iteration counters left at their `server_default` `0`, `normalized_task` = `scrub_known_values(task.model_dump(mode="json"))` and `source_ref` = `scrub_known_values(task.source_ref)` (D-18 known-value-only). Adds one `RUN_CREATED` event whose payload — `{"source_kind", "source_ref", "title"}` — is passed through `redact()` with patterns enabled. Returns the new `run_id` (a client-side `uuid4`).

### `apply_transition`

```python
def apply_transition(
    session: Session,
    *,
    run_id: UUID,
    expected_status: RunStatus,
    next_status: RunStatus,
    next_current_role: str | None,
    next_current_step: int | None,
    role_execution: RoleExecutionWrite | None = None,
    events: Sequence[EventWrite] = (),
    counter_increments: Mapping[str, int] | None = None,
) -> RunStatus
```

Before the transaction: raises `ValueError` if `next_status != expected_status and not events`, or if `counter_increments` names anything outside `{"qa_developer_iterations", "quality_gate_iterations"}`.

Inside one `with session.begin():`, in order:
1. `session.get(Run, run_id, with_for_update=True)` — `LookupError` if absent.
2. `ConcurrentTransition` if `run.status != expected_status` — nothing written.
3. If `role_execution` is not `None`: insert (with `attempt = SELECT coalesce(max(attempt),0)+1 WHERE run_id=… AND role=…`) or update (`session.get(RoleExecution, spec.id, with_for_update=True)`). `result` / `error` pass through `redact()` before assignment.
4. `run.status`, `run.current_role`, `run.current_step`, `run.updated_at = func.now()`.
5. Each `counter_increments` entry: `setattr(run, name, getattr(run, name) + delta)`.
6. One `RunEvent` per `EventWrite`, `payload=redact(event.payload, …)`.

Returns `next_status`. No explicit commit call — the context manager commits once or rolls everything back.

### Call-shape models (frozen, `extra="forbid"`, raw payloads)

```python
class RoleExecutionWrite(BaseModel):
    mode: Literal["insert", "update"]
    role: str
    worker: str
    status: str
    id: UUID | None = None            # required for mode="update"
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

class EventWrite(BaseModel):
    type: EventType
    role_execution_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

class ConcurrentTransition(RuntimeError): ...
```

### `RunState` (frozen, `extra="forbid"`, detached)

```python
class LatestExecution(BaseModel):
    id: UUID
    role: str
    worker: str
    status: str
    attempt: int
    worker_session_id: str | None = None

class RunState(BaseModel):
    run_id: UUID
    status: RunStatus
    current_role: str | None
    current_step: int | None
    normalized_task: NormalizedTask
    workflow: dict[str, Any]
    qa_developer_iterations: int
    quality_gate_iterations: int
    latest_execution: LatestExecution | None

def load_run_state(session: Session, run_id: UUID) -> RunState | None
```

`load_run_state` returns `None` for an unknown id. Two selects only: `session.get(Run, run_id)` and `select(RoleExecution).where(run_id).order_by(attempt.desc()).limit(1)`. No `run_events` query; no `dark_factory.events` import.

## Task Commits

1. **Task 1 (RED):** `afb2ed9` `test(01-05)` — failing db tests for `create_run` + `apply_transition` (module absent) + conftest fixtures/factories
2. **Task 1 (GREEN):** `72e0fb9` `feat(01-05)` — `persistence/mutations.py`; 15 db tests green
3. **Task 2 (RED):** `0f548fd` `test(01-05)` — failing `test_load_run_state.py` (`repositories` absent) + `test_single_mutation_path.py`
4. **Task 2 (GREEN):** `ccc54e7` `feat(01-05)` — `persistence/repositories.py`; 24 db + 2 unit tests green

**Plan metadata:** docs commit (this SUMMARY + STATE + ROADMAP + REQUIREMENTS).

`plan_head_before = a45f053032a14f43b74d854b0ef50d32f845817f`; `git rev-list --count a45f053..HEAD` = 4 task commits.

## TDD Gate Compliance

| Task | RED (`test(01-05)`) | GREEN (`feat(01-05)`) | REFACTOR | Status |
|------|---------------------|-----------------------|----------|--------|
| 1 | `afb2ed9` | `72e0fb9` | — | Pass |
| 2 | `0f548fd` | `ccc54e7` | — | Pass |

`workflow.tdd_mode` is not enabled in `.planning/config.json`, so the plan-level `check tdd-red-evidence` verb gate is not enforced. Each RED commit failed on the target module being absent (`ImportError` / `ModuleNotFoundError`), continuing the 01-02/01-03/01-04 convention.

**Task 2 note:** `test_single_mutation_path.py` *passed* at RED time — it is a regression guard encoding an architectural invariant that already held (no module outside `mutations.py` writes lifecycle state), the same shape as 01-02's `test_no_worker_name_leak.py` / `test_no_environ_copy.py`. The genuine RED for Task 2 was `test_load_run_state.py` failing on `ModuleNotFoundError: dark_factory.persistence.repositories`. Not a gate violation — the guard test is green before and after GREEN by design.

## Verification Results

| Command | Result |
|---------|--------|
| `uv run pytest -m db -q` | 37 passed, 118 deselected (0:02:10) |
| `uv run pytest -m db -q tests/db/test_create_run.py tests/db/test_apply_transition.py` | 15 passed (plan floor ≥ 10) |
| `uv run pytest -m db -q tests/db/test_load_run_state.py` | 7 passed (plan floor ≥ 6) |
| `uv run pytest -m unit -q tests/unit/test_single_mutation_path.py` | 2 passed |
| `uv run pytest -m unit -q` | 114 passed, 41 deselected — no marker warnings |
| `uv run mypy src/dark_factory` (strict) | Success: no issues found in 21 source files |
| `uv run mypy src/dark_factory/persistence` | Success: no issues found in 4 source files |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check src tests migrations` | all files formatted |

## Deviations from Plan

### 1. [Rule 3 - Tooling] `ruff format` run alongside `ruff check`

- **Found during:** Task 1 and Task 2 verification.
- **Issue:** `.claude/CLAUDE.md` mandates `ruff check` + `ruff format`; the plan `<verification>` lists only `ruff check .`. `ruff format --check` flagged whitespace/line-wrap in the new test files.
- **Fix:** `uv run ruff format` on the changed files — no logic change. Folded into the task commits. Same call the 01-02/01-03/01-04 executors made.
- **Files:** `tests/db/test_create_run.py`, `tests/db/test_apply_transition.py`, `tests/db/test_load_run_state.py`, `tests/conftest.py`.
- **Committed in:** `afb2ed9`, `72e0fb9`, `0f548fd`, `ccc54e7`.

### 2. [Rule 2 - Missing helper] `_write_role_execution` private helper in `mutations.py`

- **Found during:** Task 1 GREEN.
- **Issue:** The plan describes `apply_transition` as a single function. The insert-or-update branch plus its redaction is ~30 lines; inlining it made the `with session.begin():` body hard to read and pushed one line over the ruff line length.
- **Change:** Extracted a module-private `_write_role_execution(session, run_id, spec, known)` called only from inside `apply_transition`'s transaction. It is in the same module, holds no transaction of its own, and does not widen the public surface. "One mutation path" (one module, one transaction discipline, one redaction call) is preserved.
- **Files:** `src/dark_factory/persistence/mutations.py`.
- **Committed in:** `72e0fb9`.

### 3. [Rule 3 - Test infra] db-tier tests must release an autobegun read transaction before the next mutation

- **Found during:** Task 1 test authoring; confirmed with a throwaway probe against the live DB.
- **Issue:** Under the `db_session` fixture's `join_transaction_mode="create_savepoint"`, back-to-back `with session.begin():` blocks work, but a bare `session.get` / `session.scalars` autobegins a transaction, and the *next* `with session.begin():` then raises `InvalidRequestError: A transaction is already begun on this Session`.
- **Change:** Every db test in this plan does all mutations first where possible; where a read must precede another mutation, the test calls `db_session.rollback()` (a no-op on data, releases the autobegun read transaction) first. Documented in each test module's docstring. No production-code impact — `apply_transition` / `create_run` are unchanged.
- **Files:** `tests/db/test_apply_transition.py`, `tests/db/test_load_run_state.py`.
- **Committed in:** `afb2ed9`, `72e0fb9`, `0f548fd`.

---

**Total deviations:** 1 tooling, 1 in-module helper extraction, 1 test-infra accommodation. No scope creep — every file in the plan's `files_modified` list was produced with the specified exports and behaviour.

## Threat surface / stub scan

- **T-01-01 (Information Disclosure):** `redact()` is called inside `apply_transition` / `create_run` immediately before every `session.add` / attribute assignment, at the single call site; `RoleExecutionWrite` / `EventWrite` carry raw payloads so no caller can bypass it. Proven by db-tier assertions (result URI, known event-payload value, RUN_CREATED payload).
- **T-01-02 (SQL injection):** the `attempt` aggregate and every read/write are SQLAlchemy Core/ORM constructs with bound parameters; no f-string / `%`-format / concatenated SQL in the module.
- **T-01-04 (Repudiation):** one `with session.begin():` per lifecycle event with all writes inside; no explicit commit call (asserted); a status change with empty `events` is rejected outright. The crash-injection proof against a mid-statement failure is Plan 07's SC4 test — deliberately not duplicated here; this plan proves the after-flush rollback variant.
- **T-01-22 (Tampering — second writer):** `tests/unit/test_single_mutation_path.py` AST-walks the source tree and fails on any `RunEvent` / `RoleExecution` construction or `.status` assignment outside `mutations.py`.
- **T-01-23 (Tampering — interleaved writers):** the `runs` row is loaded `with_for_update=True` and the `expected_status` guard raises `ConcurrentTransition` before any write. Phase 2 adds the lease on top of this guard.
- No new network endpoints, auth paths or trust-boundary schema changes. No stubs, placeholders, or skipped tests introduced.

## Self-Check: PASSED

- Files on disk: `src/dark_factory/persistence/mutations.py`, `src/dark_factory/persistence/repositories.py`, `tests/db/test_create_run.py`, `tests/db/test_apply_transition.py`, `tests/db/test_load_run_state.py`, `tests/unit/test_single_mutation_path.py` — all present; `tests/conftest.py` modified.
- Commits in `git log` on `gsd/phase-01-walking-skeleton-one-durable-run`: `afb2ed9`, `72e0fb9`, `0f548fd`, `ccc54e7` — all present.
- Re-ran every plan `<verification>` command post-commit: all green (table above).

---
*Phase: 01-walking-skeleton-one-durable-run*
*Completed: 2026-09-08*
