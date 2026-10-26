---
phase: 01-walking-skeleton-one-durable-run
plan: 06
subsystem: orchestrator
tags: [typer, resume-first, state-machine, tracer, sqlalchemy, structlog]

requires:
  - phase: 01-02
    provides: "RunStatus / STOP_STATUSES / TERMINAL_STATUSES, Signal + signal_from_result, EventType, NormalizedTask, WorkerResult, CodingWorker, WorkerRegistry / default_registry, FakeWorker"
  - phase: 01-05
    provides: "create_run, apply_transition (RoleExecutionWrite / EventWrite), load_run_state / RunState / LatestExecution; conftest db_session + fake_settings / use_fake_secrets"
provides:
  - "input/resolver.py — classify(raw) -> (SourceKind, remainder): pure prefix match, no I/O, no run creation (INTAKE-04); SourceKind = TEXT|SPEC|GITHUB; UnresolvableSourceError"
  - "input/loaders.py — load(kind, locator) -> NormalizedTask via a {SourceKind: loader} mapping; text loader real (quote/whitespace strip, empty body -> UnresolvableSourceError); spec/github loaders raise SourceNotSupportedError naming Phase 4 / Phase 10"
  - "workflows/pipeline.py — RoleNode, Pipeline (ordered, no role count), current_node, next_node, DEFAULT_PIPELINE = one BA node"
  - "roles/registry.py — Role dataclass + ba_role (name='BA', worker='fake')"
  - "orchestrator/lifecycle.py — transition(state, signal, pipeline) -> (next_status, next_current_role, next_current_step): pure, the only code computing a status change; IllegalTransitionError for any pair outside the graph"
  - "orchestrator/runner.py — start_run(source), advance(run_id), drive(run_id, on_transition), run_state(run_id); resume-first, one committed apply_transition step per advance, zero carryover; RunNotFoundError, DriveLoopExhausted"
  - "cli.py — Typer app: run / resume; run id on stdout line 1, one 'PREV → NEXT' line per transition, summary block; exit 0 / 1 / 2 (D-05). __main__.py for `python -m dark_factory`"
  - "tests/conftest.py — advance_session_factory (repeatable Session factory in a rolled-back outer transaction) + fake_worker_registry (scripted FakeWorker registry builder)"
affects: [01-07, 01-08, 01-09, "Phase 2 WAITING_HUMAN / resume --answer", "Phase 3 config-driven pipeline", "Phase 4 spec loader", "Phase 10 github loader", "Phase 11 CI trigger exit codes"]

actuals:
  tokens: 14300
  tasks: 3
  commits: 3
  plan_head_before: cb6491133c5156a6301b9a405f56e5a9c024cb5e

tech-stack:
  added: []
  patterns:
    - "Resume-first advance(run_id): every call reconstructs RunState from Neon via load_run_state, runs exactly ONE apply_transition step, returns the new status — the happy path and the resume path are the same code, proven by drive() looping advance()"
    - "advance() reads with a session it closes, then calls the worker OUTSIDE any transaction, then mutates with a second fresh session — no transaction ever spans the worker call (the Phase 2 lease depends on this habit)"
    - "Dependency injection via keyword-only params with production defaults: advance/drive/start_run/run_state take session_factory / registry / pipeline so tests drive either terminal arm with no monkeypatching of production wiring; 'exactly one required argument, the run id' still holds"
    - "lifecycle.transition is typed against a structural Protocol (_RunStateView), not RunState, so the pure module imports nothing from dark_factory.persistence and contains no Session"
    - "The transition graph is enumerated explicitly (4 reachable edges) and every pair outside it raises IllegalTransitionError rather than defaulting to a status"
    - "drive() stop condition is the named constant STOP_STATUSES and the loop is bounded by _MAX_DRIVE_ITERATIONS (DriveLoopExhausted on exhaustion)"
    - "Loader dispatch is a {SourceKind: loader} mapping whose key set equals set(SourceKind) — a new kind without a loader fails a test, not a user"

key-files:
  created:
    - "src/dark_factory/input/resolver.py"
    - "src/dark_factory/input/loaders.py"
    - "src/dark_factory/workflows/pipeline.py"
    - "src/dark_factory/roles/registry.py"
    - "src/dark_factory/orchestrator/lifecycle.py"
    - "src/dark_factory/orchestrator/runner.py"
    - "src/dark_factory/cli.py"
    - "src/dark_factory/__main__.py"
    - "src/dark_factory/{orchestrator,workflows,roles,input}/__init__.py"
    - "tests/integration/test_walking_skeleton.py"
    - "tests/unit/test_lifecycle.py"
    - "tests/unit/test_resolver.py"
    - "tests/unit/test_loaders.py"
    - "tests/db/test_run_failure_path.py"
    - "tests/db/test_terminal_advance_noop.py"
    - "tests/integration/test_exit_codes.py"
    - "tests/integration/test_unsupported_source.py"
  modified:
    - "tests/conftest.py — added advance_session_factory + fake_worker_registry fixtures"

key-decisions:
  - "start_run(source: str) does classify -> load -> create_run and raises UnresolvableSourceError / SourceNotSupportedError before any write; the CLI's try block wraps start_run so exit 2 stays reserved for pre-persistence failures (resolves the PLAN's split wording between the runner and cli sections)"
  - "lifecycle.transition takes a structural Protocol, not RunState, so the pure module has no dark_factory.persistence import and no Session identifier (Task 1 acceptance criterion, literally)"
  - "advance/drive/start_run/run_state expose session_factory / registry / pipeline as keyword-only params with production defaults — the injection seam the plan's conftest fixture needs, without a second positional argument"
  - "role_executions.status uses plain strings RUNNING -> COMPLETED / FAILED; the CREATED->BA step inserts the attempt row as RUNNING and the BA-> terminal step updates it in place (one attempt row for the one-role path)"
  - "current_step is the pipeline ordinal of current_role (0 for BA); set on role entry, retained through COMPLETED/FAILED"
  - "runs.workflow is persisted as {\"roles\": [\"BA\"]} at create time; Phase 1 advance() still iterates the injected DEFAULT_PIPELINE — Phase 3 rebuilds the Pipeline from that snapshot with no orchestrator edit"
  - "Tasks 2 and 3 are coverage / contract lock-in over behaviour Task 1's tracer already implemented (the PLAN front-loads the full implementation into the tracer action text); the RED->GREEN commit split is test(01-06) then — where needed — feat(01-06), same shape as 01-05's regression-guard test"

patterns-established:
  - "The resume-first advance(run_id) entry point and the drive loop now exist; Plans 07-09 call drive() / advance() and assert against the CLI output contract rather than adding a new layer"

requirements-completed: [INTAKE-01, INTAKE-04, INTAKE-05, ORCH-01, ORCH-05, STATE-08, WORK-03, WORK-10]

coverage:
  - id: D1
    description: "`dark-factory run text:\"...\"` creates a durable run in PostgreSQL, drives CREATED -> BA -> COMPLETED via two committed advance steps, prints the run id on stdout line 1 then both transition lines, exits 0; events are exactly RUN_CREATED, ROLE_STARTED, ROLE_COMPLETED, RUN_COMPLETED; one BA attempt-1 role_executions row; a multi-byte body round-trips through runs.normalized_task"
    requirement: "INTAKE-01"
    verification:
      - kind: integration
        ref: "tests/integration/test_walking_skeleton.py (2 tests, real PostgreSQL 18.6)"
        status: pass
    human_judgment: false
  - id: D2
    description: "lifecycle.transition is a pure function of (state, signal, pipeline): every legal edge (CREATED+ENTER, role+ROLE_COMPLETED -> next role or COMPLETED, role+ROLE_FAILED -> FAILED) yields the documented tuple; every pair outside the graph raises IllegalTransitionError; no persistence import, no Session"
    requirement: "ORCH-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_lifecycle.py (13 tests, database-free)"
        status: pass
    human_judgment: false
  - id: D3
    description: "input.resolver.classify is pure prefix classification: correct (kind, remainder) for the three prefixes; empty / unknown / BOM / leading-whitespace raise UnresolvableSourceError; classify does no I/O (open, socket, session factory patched to raise) and creates no run (create_run patched to raise); no prefix is a proper prefix of another"
    requirement: "INTAKE-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_resolver.py (11 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "input.loaders.load dispatches through a {SourceKind: loader} mapping whose key set equals set(SourceKind); the text loader strips surrounding quotes/whitespace, derives a truncated title, and refuses an empty body; spec/github loaders raise SourceNotSupportedError naming Phase 4 / Phase 10"
    requirement: "INTAKE-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_loaders.py (9 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "advance(run_id) is resume-first: reconstructs RunState from Neon every call, executes exactly one committed apply_transition step, holds no carryover; the worker is obtained by registry lookup (no name conditional); advance takes exactly one required argument"
    requirement: "STATE-08"
    verification:
      - kind: integration
        ref: "tests/integration/test_walking_skeleton.py + tests/db/test_terminal_advance_noop.py + tests/db/test_run_failure_path.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_lifecycle_module_has_no_persistence_import_and_no_session"
        status: pass
    human_judgment: false
  - id: D6
    description: "A scripted FAILED WorkerResult drives the run to FAILED with current_role/current_step retained; RUN_CREATED, ROLE_STARTED, ROLE_FAILED, RUN_FAILED persisted in seq order; the one attempt row updated in place (no second attempt) with the failure detail in role_executions.error"
    requirement: "WORK-10"
    verification:
      - kind: integration
        ref: "tests/db/test_run_failure_path.py (6 tests, real PostgreSQL 18.6)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Exit codes across a real process boundary: 0 for COMPLETED, 1 for a persisted FAILED (driven by DARK_FACTORY_FAKE_SCRIPT, 'BA -> FAILED' on stdout, run id still on line 1), 2 for an unrecognised prefix / spec: / github: / empty text body / unknown resume id — with the runs row count unchanged for every exit-2 case"
    requirement: "ORCH-05"
    verification:
      - kind: integration
        ref: "tests/integration/test_exit_codes.py (3 tests) + tests/integration/test_unsupported_source.py (4 tests)"
        status: pass
    human_judgment: false
  - id: D8
    description: "advance on a terminal run performs zero writes and returns the same status: driving to COMPLETED and to FAILED, then two more advance calls leave the runs row, the role-execution rows and the run_events count byte-for-byte identical"
    requirement: "STATE-08"
    verification:
      - kind: integration
        ref: "tests/db/test_terminal_advance_noop.py (3 tests, real PostgreSQL 18.6)"
        status: pass
    human_judgment: false
  - id: D9
    description: "No worker-name branching: the runner obtains its worker via registry.get(node.worker); the existing WORK-03 source-tree guard (tests/unit/test_no_worker_name_leak.py) stays green across the new orchestrator/workflows/roles/input modules"
    requirement: "WORK-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-08
status: complete
---

# Phase 01 Plan 06: The End-to-End Tracer Summary

**`dark-factory run text:"..."` now drives a durable run `CREATED → BA → COMPLETED` in PostgreSQL through `FakeWorker` with zero external AI: a pure prefix resolver, a `{SourceKind: loader}` mapping, a hardcoded one-role pipeline iterated with no role count, a pure enumerated `transition()` graph, the resume-first `advance(run_id)` entry point and its `drive()` loop, and a Typer `run` / `resume` CLI with the D-05 0/1/2 exit-code contract — proven end to end against real PostgreSQL and locked by 38 unit + 9 db + 9 integration tests.**

## Contract record (Plans 07 / 08 / 09 assert against these)

### `orchestrator/runner.py`

```python
def start_run(
    source: str,
    *,
    session_factory: Callable[[], Session] = _default_session,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> UUID

def advance(
    run_id: UUID,
    *,
    session_factory: Callable[[], Session] = _default_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> RunStatus

def drive(
    run_id: UUID,
    on_transition: Callable[[RunStatus, RunStatus], None] | None = None,
    *,
    session_factory: Callable[[], Session] = _default_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> RunStatus

def run_state(
    run_id: UUID,
    *,
    session_factory: Callable[[], Session] = _default_session,
) -> RunState | None
```

* `advance` opens a session for `load_run_state` and closes it; returns `state.status` immediately (zero writes) when terminal; otherwise binds structlog contextvars (`run_id`, `role`, `attempt`), runs exactly one step, unbinds, returns the new status.
* **`CREATED → BA`** (`_enter_first_role`): `apply_transition(expected=CREATED, next=BA, next_current_role="BA", next_current_step=0, role_execution=RoleExecutionWrite(mode="insert", role="BA", worker="fake", status="RUNNING"), events=[ROLE_STARTED])`.
* **`BA → COMPLETED|FAILED`** (`_run_current_role`): `registry.get("fake").execute(context)` **outside any transaction** → `signal_from_result` → `transition` → `apply_transition(expected=BA, role_execution=RoleExecutionWrite(mode="update", id=latest.id, status="COMPLETED"|"FAILED", worker_session_id=result.worker_session_id, result=<dump>|None, error=None|<dump>), events=[ROLE_COMPLETED, RUN_COMPLETED] | [ROLE_FAILED, RUN_FAILED])`.
* `drive` loads the starting status once, then loops: stop when `status in STOP_STATUSES`; else `advance`, fire `on_transition(prev, new)` on a change; `DriveLoopExhausted` after `_MAX_DRIVE_ITERATIONS` (1000).
* Exceptions: `RunNotFoundError(LookupError)`, `DriveLoopExhausted(RuntimeError)`.

### Transition graph as implemented (`orchestrator/lifecycle.py`)

`transition(state, signal, pipeline) -> (next_status, next_current_role, next_current_step)`

| current status | signal | result |
|---|---|---|
| `CREATED` | `ENTER` | `(RunStatus(pipeline.nodes[0].name), pipeline.nodes[0].name, 0)` |
| role status (in pipeline) | `ROLE_COMPLETED`, not last node | `(RunStatus(next.name), next.name, index_of(next))` |
| role status (in pipeline) | `ROLE_COMPLETED`, last node | `(COMPLETED, current_role, current_step)` |
| role status (in pipeline) | `ROLE_FAILED` | `(FAILED, current_role, current_step)` |
| terminal status | any signal | `IllegalTransitionError` |
| anything else | anything else | `IllegalTransitionError` |

Phase 1 (`pipeline = ["BA"]`) reaches exactly: `CREATED --ENTER--> BA`, `BA --ROLE_COMPLETED--> COMPLETED`, `BA --ROLE_FAILED--> FAILED`.

### CLI output format (`cli.py`)

```
<run_id>                     # stdout line 1, immediately after create_run, before the loop
CREATED → BA                 # one line per transition, "PREV → NEXT" (U+2192)
BA → COMPLETED
                             # blank line
run <run_id>
  terminal state: COMPLETED
  last role:      BA
  attempt:        1
```

Exit: `0` when the terminal status is `COMPLETED`, `1` when `FAILED`, `2` for `UnresolvableSourceError` / `SourceNotSupportedError` / a non-UUID or unknown `resume` id (all raised before any `runs` row exists). `resume <id>` takes only the id (D-03) and runs the identical loop.

### `input/resolver.py` and `input/loaders.py`

* `SourceKind(StrEnum)` = `TEXT | SPEC | GITHUB`; `classify(raw) -> (SourceKind, remainder)`; `UnresolvableSourceError(ValueError)` for no match / empty.
* `load(kind, locator) -> NormalizedTask` via `_LOADERS: {SourceKind: Callable}` (key set `== set(SourceKind)`). Text loader: `body = locator.strip().strip('"')`, empty → `UnresolvableSourceError`, `title = body.splitlines()[0][:120]`, `source_kind="text"`, `source_ref=None`. `SourceNotSupportedError(NotImplementedError)` from the spec loader ("Phase 4") and github loader ("Phase 10").

### `workflows/pipeline.py` / `roles/registry.py`

`RoleNode(name, worker)`, `Pipeline(nodes: tuple[RoleNode, ...])` with `index_of`; `current_node(pipeline, current_role)` / `next_node(pipeline, current_role)`; `DEFAULT_PIPELINE = Pipeline((RoleNode("BA", "fake"),))`. `roles.registry.ba_role = Role(name="BA", worker="fake", description=...)`.

## Task Commits

1. **Task 1 (tracer):** `cd63c62` `feat(01-06)` — resolver, loaders, pipeline, ba_role, lifecycle.transition, runner (start_run / advance / drive / run_state), cli, __main__, conftest fixtures, `tests/integration/test_walking_skeleton.py`
2. **Task 2:** `784e395` `test(01-06)` — `tests/unit/test_lifecycle.py` + `test_resolver.py` + `test_loaders.py` (38 database-free tests)
3. **Task 3:** `7de973f` `test(01-06)` — `tests/db/test_run_failure_path.py` + `test_terminal_advance_noop.py`, `tests/integration/test_exit_codes.py` + `test_unsupported_source.py` (9 db + 7 integration tests)

**Plan metadata:** docs commit (this SUMMARY + STATE + ROADMAP + REQUIREMENTS).

`plan_head_before = cb6491133c5156a6301b9a405f56e5a9c024cb5e`; `git rev-list --count cb64911..HEAD` = 3 task commits.

## Tracer feedback gate

`workflow.human_verify_mode = end-of-phase` and the tracer `<verify>` carries only `<automated>` checks, so per execute-plan.md the gate re-ran the tracer verification rather than synthesising a checkpoint:

| Command | Result |
|---|---|
| `pytest -m integration -q tests/integration/test_walking_skeleton.py` | 2 passed |
| `mypy src/dark_factory` | Success: no issues found in 33 source files |

⚡ Tracer verified end-to-end — expansion tasks (2, 3) proceeded.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the plan-level `check tdd-red-evidence` verb gate is not enforced.

| Task | RED (`test(01-06)`) | GREEN (`feat(01-06)`) | Notes |
|------|---------------------|-----------------------|-------|
| 2 | `784e395` | — | Coverage / contract lock-in over the pure seams. The PLAN's Task 1 action text implements the full resolver / loader / transition behaviour (empty-body refusal, BOM rejection, illegal-pair raising, the whole graph), so these 38 tests were green at authoring — the same situation 01-05 documented for its `test_single_mutation_path.py` guard. No behaviour gap was found, so no `feat(01-06)` follow-up was needed. |
| 3 | `7de973f` | — | Same: the tracer's `_run_current_role` already wires the ROLE_FAILED / RUN_FAILED arm and `cli.py` already maps exit 0/1/2, so the db + integration tests lock the D-05 contract without a preceding gap. |

This is an honest deviation from a strict RED-first cycle: the plan structures Task 1 as a complete production tracer and Tasks 2–3 as its test coverage. Every test was run and observed green against real PostgreSQL 18.6 before commit.

## Verification Results

| Command | Result |
|---------|--------|
| `pytest -m unit -q tests/unit/test_lifecycle.py tests/unit/test_resolver.py tests/unit/test_loaders.py` | 38 passed (plan floor ≥ 20) |
| `pytest -m db -q tests/db/test_run_failure_path.py tests/db/test_terminal_advance_noop.py` | 9 passed (plan floor ≥ 8) |
| `pytest -m integration -q tests/integration/test_exit_codes.py tests/integration/test_unsupported_source.py` | 7 passed (plan floor ≥ 7) |
| `pytest -m integration -q tests/integration/test_walking_skeleton.py` | 2 passed |
| `pytest -m unit -q` (whole unit tier) | 152 passed, 43 deselected — no marker warnings |
| `pytest -q` (full suite) | see `## Full suite` below |
| `mypy src/dark_factory` (strict) | Success: no issues found in 33 source files |
| `ruff check .` | All checks passed |
| `ruff format --check src tests` | all files formatted |
| `python -m dark_factory --help` | exits 0, lists `run` and `resume` |

## Full suite

`bash run_tests.sh -q` (whole suite, real PostgreSQL 18.6 via `DARK_FACTORY_TEST_DATABASE_URL`): **211 passed in 417.44s**, exit 0. No failures, no errors, no marker warnings. (152 unit + 4 contract + db + integration; the +55 vs 01-05's 155-collected total is this plan's 38 unit + 9 db + 8 integration new tests.)

## Deviations from Plan

### 1. [Rule 3 - Blocking] `lifecycle.transition` typed against a Protocol, not `RunState`

- **Found during:** Task 1.
- **Issue:** The PLAN's artifact list types `transition(state: RunState, ...)`, but `RunState` lives in `dark_factory.persistence.repositories` and the same task's acceptance criterion requires `lifecycle.py` to "import nothing from `dark_factory.persistence` and contain no `Session`".
- **Fix:** Defined a structural `typing.Protocol` `_RunStateView` (`status`, `current_role`, `current_step`) in `lifecycle.py` and typed `transition` against it. `RunState` satisfies it structurally; the pure module has no persistence import. Proven by `test_lifecycle.py::test_lifecycle_module_has_no_persistence_import_and_no_session` (AST walk).
- **Files:** `src/dark_factory/orchestrator/lifecycle.py`, `tests/unit/test_lifecycle.py`.
- **Committed in:** `cd63c62`, `784e395`.

### 2. [Rule 3 - Blocking] `start_run(source: str)` owns classify + load, not the CLI

- **Found during:** Task 1.
- **Issue:** The PLAN's `runner.py` section says `start_run` performs "classify-then-load-then-`create_run`" while the `cli.py` section says the command "classifies and loads inside a try block, and ... then calls `start_run`" — the two cannot both be literal.
- **Fix:** `start_run(source: str)` does classify → load → `create_run` and raises `UnresolvableSourceError` / `SourceNotSupportedError`; `cli.run` wraps the single `start_run` call in the try block and maps either exception to exit 2. Exit 2 stays reserved for pre-persistence failures. `start_run` still exports the name the plan's artifact list requires.
- **Files:** `src/dark_factory/orchestrator/runner.py`, `src/dark_factory/cli.py`.
- **Committed in:** `cd63c62`.

### 3. [Rule 3 - Blocking] Injection seam: `session_factory` / `registry` / `pipeline` keyword params

- **Found during:** Task 1 (writing the conftest fixture the plan asks for).
- **Issue:** `Settings` has no `DARK_FACTORY_TEST_DATABASE_URL` fallback (contrary to a note in the execution prompt), so an in-process test cannot let `advance()` build its own engine, and `advance()` creating its own session would also block a scripted-worker test from reaching the drive loop "without touching production wiring".
- **Fix:** `advance` / `drive` / `start_run` / `run_state` take `session_factory` (and `registry` / `pipeline` where relevant) as keyword-only parameters with the production defaults (`_default_session` → the warmed engine; `default_registry`; `DEFAULT_PIPELINE`). `advance` still "accepts exactly one required argument, the run id". `tests/conftest.py` gains `advance_session_factory` (a repeatable `Session` factory inside a rolled-back outer transaction) and `fake_worker_registry` (a scripted-`FakeWorker` registry builder). Integration/subprocess tests instead set `DATABASE_URL` / `DATABASE_URL_DIRECT` from the `pg_url` fixture.
- **Files:** `src/dark_factory/orchestrator/runner.py`, `tests/conftest.py`, all Task 3 tests.
- **Committed in:** `cd63c62`, `7de973f`.

### 4. [Rule 3 - Tooling] `ruff format` run alongside `ruff check`

- **Found during:** every task's verification.
- **Issue:** `.claude/CLAUDE.md` mandates `ruff check` + `ruff format`; the plan `<verification>` lists only `ruff check .`. `ruff format` reflowed several new files.
- **Fix:** `uv run ruff format src tests` on the changed files — whitespace / line-wrap only, folded into the task commits. Same call the 01-02 / 01-03 / 01-04 / 01-05 executors made.
- **Files:** all new `src/` and `tests/` files this plan created.
- **Committed in:** `cd63c62`, `784e395`, `7de973f`.

---

**Total deviations:** 3 blocking (a Protocol to keep the pure module dependency-free; a `start_run` boundary decision resolving contradictory plan wording; a keyword-only injection seam) + 1 tooling. No scope creep — every file in `files_modified` was produced with the specified exports and behaviour; `spec:` and `github:` loaders are the only stubs and they raise a clean, phase-named error by design.

## Known Stubs

| File | Line | Stub | Intentional? | Resolved by |
|------|------|------|--------------|-------------|
| `src/dark_factory/input/loaders.py` | ~55 | `_load_spec` raises `SourceNotSupportedError("... until Phase 4")` | Yes — PLAN objective: "the only stubs are the `spec:` and `github:` loaders, which raise a clean unsupported-source error" (D-23) | Phase 4 (spec loader) |
| `src/dark_factory/input/loaders.py` | ~61 | `_load_github` raises `SourceNotSupportedError("... until Phase 10")` | Yes — same | Phase 10 (issue intake) |

Both are reachable extension points, not dead code: they classify successfully, raise a phase-named error, exit 2 with nothing persisted, and are covered by `test_loaders.py` + `test_unsupported_source.py`. Recorded in `.planning/WINDOWS.md` (entries 1–2, `kind: stub`).

## Threat surface / stub scan

- **T-01-02 (SQL injection via task text):** task text is only ever bound as a JSONB parameter through SQLAlchemy (`create_run` from 01-05); `input/loaders.py` builds a validated `NormalizedTask` and constructs no SQL; `classify` performs no I/O at all (proven by `test_resolver.py::test_classify_does_no_io`).
- **T-01-25 (path traversal via a source locator):** Phase 1 implements only the `text:` loader, which reads nothing; the `spec:` loader raises `SourceNotSupportedError` before touching a path.
- **T-01-06 (worker-name conditional in the runner):** the worker is obtained by `registry.get(node.worker)`; `tests/unit/test_no_worker_name_leak.py` stays green over the new modules.
- **T-01-05 (control chars forging transition lines):** transition lines are built from `RunStatus` enum members (`f"{previous.value} → {new.value}"`), never from task text.
- **T-01-26 (killed process leaves no run id):** the run id is echoed on stdout line 1 immediately after `start_run` returns and before `drive()` — asserted by the tracer test and every exit-code test that creates a run.
- **T-01-27 (exit 2 after a row exists):** exit 2 is raised only from the `start_run` classify/load block and the `resume` id checks, before any `runs` row; `test_unsupported_source.py` asserts the `runs` count is unchanged for every exit-2 path.
- **T-01-28 (spinning drive loop):** `drive` is bounded by `_MAX_DRIVE_ITERATIONS` and raises `DriveLoopExhausted`; `transition` raises `IllegalTransitionError` on any pair outside the graph.
- **Stubs:** `input/loaders.py` `_load_spec` / `_load_github` raise `SourceNotSupportedError` naming Phase 4 / Phase 10 respectively — intentional, plan-sanctioned, and covered by `test_loaders.py` + `test_unsupported_source.py`. No other stubs, placeholders, or skipped tests. No new network endpoints or auth paths.

## Next Phase Readiness

- **Ready for 01-07:** `advance` leaves a real committed intermediate state at `BA` (the `CREATED → BA` step inserts the `RUNNING` attempt row and commits before the worker runs); `drive` / `advance` / `run_state` take `session_factory`, so a subprocess-kill test and an in-process crash-injection test can both drive them. `__main__.py` exists for the fresh-process spawn.
- **Ready for 01-08:** `run_state(run_id)` already reads position from columns only; `dark-factory status` can wrap `load_run_state` / a read model without touching `runs.status` or the event log.
- **Ready for 01-09:** every JSONB payload the runner produces (`role_executions.result` / `error`, event payloads) flows through `apply_transition`'s single `redact()` call site; the SC5 e2e proof has a full run to grep.
- **Unchanged blockers:** the three research-flagged decisions (artifact durability → Phase 5, lease TTL → Phase 2, Copilot/Hermes flag matrix → Phase 8).

## Self-Check: PASSED

- All 16 source + test files listed in `key-files.created` verified present on disk.
- Commits `cd63c62`, `784e395`, `7de973f` verified in `git log` on `gsd/phase-01-walking-skeleton-one-durable-run`.
- Re-ran every plan `<verification>` command post-commit: full `pytest -q` 211 passed, `mypy src/dark_factory` clean (33 files), `ruff check .` clean, `python -m dark_factory --help` exits 0 listing `run` / `resume`.

---
*Phase: 01-walking-skeleton-one-durable-run*
*Completed: 2026-09-08*
