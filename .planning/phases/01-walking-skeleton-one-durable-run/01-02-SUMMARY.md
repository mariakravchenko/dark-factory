---
phase: 01-walking-skeleton-one-durable-run
plan: 02
subsystem: domain
tags: [pydantic-v2, strenum, abc, worker-contract, registry, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: "uv-managed dark_factory package, pinned pydantic 2.x, pytest markers unit/db/integration/contract, ruff + mypy --strict config"
provides:
  - "domain/status.py — RunStatus StrEnum (all 10 STATE-07 values); TERMINAL_STATUSES and STOP_STATUSES as distinct module-level frozenset constants (D-06/D-08)"
  - "domain/signal.py — Signal StrEnum (ENTER, ROLE_COMPLETED, ROLE_FAILED, ROLE_NEEDS_INPUT) + signal_from_result(result) -> Signal, a pure map over result.status only (ORCH-05)"
  - "domain/task.py — NormalizedTask (frozen, extra=forbid): source_kind, source_ref, title, body, metadata (INTAKE-05)"
  - "domain/worker.py — WorkerResultStatus (COMPLETED|NEEDS_INPUT|FAILED); ArtifactRef; WorkerCapabilities (frozen); WorkerResult (frozen, extra=forbid) with the WORK-08 field set plus optional error; model_validator rejects question-less NEEDS_INPUT"
  - "events/catalog.py — EventType StrEnum with the six Phase-1 members (D-22)"
  - "workers/base.py — CodingWorker ABC: execute(context), resume(context, previous, answer), capabilities()"
  - "workers/fake.py — FakeWorker (shipped code) + ScriptExhaustedError; script resolves explicit arg -> DARK_FACTORY_FAKE_SCRIPT JSON -> D-10 default"
  - "workers/registry.py — UnknownWorkerError, WorkerRegistry name->factory map, module-level default_registry with 'fake' bound"
  - "tests/contract/test_coding_worker_contract.py — shared CodingWorker contract suite parametrized over WORKER_FACTORIES ([FakeWorker] now, real adapters in Phases 7-8)"
  - "two abstraction guards: no claude/copilot/hermes name outside workers/+config/; no wholesale os.environ copy anywhere under src/dark_factory/"
affects: [01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09, "Phase 7 ClaudeCodeWorker", "Phase 8 Copilot/Hermes adapters"]

actuals:
  tokens: 7300
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "Closed StrEnum sets defined once, in full, from Phase 1: RunStatus carries all ten STATE-07 values though only four are reachable (avoids ALTER TYPE / CHECK churn later, RESEARCH Pitfall 6)"
    - "Boundary models are frozen pydantic v2 with extra=forbid: a WorkerResult the orchestrator cannot mutate cannot become a back-channel for a transition (ORCH-05 enforced structurally)"
    - "Stop-condition sets are named constants (TERMINAL_STATUSES vs STOP_STATUSES): Phase 2 adds WAITING_HUMAN to STOP_STATUSES only, by editing one line"
    - "Worker as a port: CodingWorker ABC + WorkerRegistry name->factory lookup; the core reads only WorkerResult / WorkerCapabilities fields, never a worker name"
    - "Abstraction invariants asserted as pytest tests (not shell greps) so failures name the offending file:line"

key-files:
  created:
    - "src/dark_factory/domain/__init__.py, src/dark_factory/domain/status.py, src/dark_factory/domain/signal.py, src/dark_factory/domain/task.py, src/dark_factory/domain/worker.py"
    - "src/dark_factory/events/__init__.py, src/dark_factory/events/catalog.py"
    - "src/dark_factory/workers/__init__.py, src/dark_factory/workers/base.py, src/dark_factory/workers/fake.py, src/dark_factory/workers/registry.py"
    - "tests/unit/test_domain_enums.py, tests/unit/test_domain_models.py, tests/unit/test_workers.py, tests/unit/test_no_worker_name_leak.py, tests/unit/test_no_environ_copy.py"
    - "tests/contract/__init__.py, tests/contract/test_coding_worker_contract.py"
  modified: []

key-decisions:
  - "WorkerResultStatus lives in domain/worker.py and was created in Task 1 (not Task 2) because domain/signal.py's signal_from_result needs it — Task 2 then extended the same file with ArtifactRef / WorkerCapabilities / WorkerResult"
  - "WorkerResult carries an 8th field `error: str | None = None` in addition to the 7 canonical WORK-08 fields, per the plan action text and D-10's FAILED arm; the WORK-08 set proper is status, summary, questions, artifacts, changed_files, worker_session_id, metadata"
  - "Added tests/unit/test_workers.py (not in the plan's file list) to hold the FakeWorker / registry / ABC-enforcement assertions the plan's acceptance criteria require but assign no file for"
  - "signal_from_result annotates its param as WorkerResult via a TYPE_CHECKING import; runtime mapping is keyed on WorkerResultStatus so only .status is ever read"

patterns-established:
  - "Define-the-contracts plan: this is the only Phase 1 plan that introduces new type definitions; downstream plans import them rather than exploring the codebase"
  - "RED commit is test-only and fails on ModuleNotFoundError / assertion; GREEN commit adds the implementation — two commits per TDD task"

requirements-completed: [STATE-07, WORK-01, WORK-03, WORK-08, WORK-10]

coverage:
  - id: D1
    description: "RunStatus StrEnum with all ten STATE-07 values; TERMINAL_STATUSES and STOP_STATUSES as separate named frozenset constants"
    requirement: "STATE-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py#test_run_status_has_exactly_ten_members / #test_terminal_statuses_is_completed_and_failed / #test_stop_statuses_equals_terminal_statuses_but_is_a_distinct_name"
        status: pass
    human_judgment: false
  - id: D2
    description: "Signal StrEnum + signal_from_result maps WorkerResultStatus -> Signal reading only result.status (ORCH-05)"
    requirement: "WORK-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py#test_signal_from_result_maps_worker_result_status / #test_signal_from_result_reads_only_the_status_field"
        status: pass
    human_judgment: false
  - id: D3
    description: "NormalizedTask frozen boundary model (source_kind, source_ref, title, body, metadata); multi-byte body survives a JSON round trip"
    requirement: "WORK-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_models.py#test_normalized_task_exposes_the_expected_field_names / #test_normalized_task_multibyte_body_survives_json_round_trip"
        status: pass
    human_judgment: false
  - id: D4
    description: "WorkerResult contract: WORK-08 field set + error; frozen; extra=forbid; question-less NEEDS_INPUT rejected; list defaults never None; order survives round trip"
    requirement: "WORK-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_models.py#test_worker_result_defaults_are_empty_lists_never_none / #test_worker_result_rejects_unknown_field / #test_worker_result_is_frozen / #test_worker_result_needs_input_with_empty_questions_is_rejected / #test_worker_result_changed_files_order_survives_round_trip"
        status: pass
    human_judgment: false
  - id: D5
    description: "CodingWorker ABC enforces execute / resume / capabilities — omitting any raises TypeError at construction"
    requirement: "WORK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_workers.py#test_coding_worker_subclass_missing_methods_cannot_be_instantiated"
        status: pass
    human_judgment: false
  - id: D6
    description: "FakeWorker returns a scripted WorkerResult sequence in declaration order with no external AI call; empty/spent script raises ScriptExhaustedError; DARK_FACTORY_FAKE_SCRIPT drives the failure arm across a process boundary"
    requirement: "WORK-10"
    verification:
      - kind: unit
        ref: "tests/unit/test_workers.py#test_fake_worker_returns_scripted_results_in_declaration_order / #test_fake_worker_empty_script_raises_script_exhausted / #test_fake_worker_reads_script_from_env / #test_fake_worker_explicit_empty_script_beats_env"
        status: pass
    human_judgment: false
  - id: D7
    description: "WorkerRegistry resolves workers by name through a factory map (fresh instance per get); unknown name raises UnknownWorkerError; module-level default_registry has 'fake' bound"
    requirement: "WORK-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_workers.py#test_worker_registry_get_returns_a_fresh_instance / #test_worker_registry_unknown_name_raises / #test_default_registry_has_fake_bound"
        status: pass
    human_judgment: false
  - id: D8
    description: "Shared CodingWorker contract suite runs green over [FakeWorker] and is written to accept real adapters unchanged in Phases 7-8"
    requirement: "WORK-01"
    verification:
      - kind: integration
        ref: "tests/contract/test_coding_worker_contract.py (uv run pytest -m contract -q => 4 passed)"
        status: pass
    human_judgment: false
  - id: D9
    description: "Abstraction guards: no claude/copilot/hermes name outside workers/+config/ (T-01-06); no wholesale os.environ copy under src/dark_factory/ (T-01-07)"
    requirement: "WORK-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py#test_no_real_worker_runtime_name_leaks_into_the_core / tests/unit/test_no_environ_copy.py#test_no_module_copies_the_process_environment_wholesale"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-08
status: complete
---

# Phase 01 Plan 02: Domain and Worker Contracts Summary

**The closed RunStatus/Signal/EventType StrEnums, the frozen NormalizedTask and WorkerResult pydantic v2 boundary models, and the CodingWorker ABC + WorkerRegistry + scripted FakeWorker — with two abstraction guards, all delivered RED→GREEN.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-08T07:51:00Z
- **Completed:** 2026-09-08
- **Tasks:** 3 (all `tdd="true"`, each RED→GREEN)
- **Files created:** 19 (5 empty package markers; 14 with content)

## Accomplishments

- `RunStatus` defines all ten STATE-07 values in one `enum.StrEnum` with `.value == .name`; `TERMINAL_STATUSES` and `STOP_STATUSES` are distinct module-level `frozenset` constants so Phase 2 adds `WAITING_HUMAN` to the drive loop's stop condition by editing one line (D-06).
- `WorkerResult` is a frozen, `extra="forbid"` pydantic v2 model carrying the WORK-08 field set — `status, summary, questions, artifacts, changed_files, worker_session_id, metadata` — plus an optional `error`; a `@model_validator(mode="after")` rejects `NEEDS_INPUT` with an empty `questions` list; `questions`/`artifacts`/`changed_files` default to `[]`, never `None`.
- `CodingWorker` is an `abc.ABC` with three `@abstractmethod`s (`execute`, `resume`, `capabilities`); a subclass omitting any raises `TypeError` at construction. `FakeWorker` implements it as shipped `src/` code, returning a scripted `WorkerResult` sequence in declaration order and raising `ScriptExhaustedError` when the script is empty or spent.
- `WorkerRegistry` is a name→factory dict lookup with a module-level `default_registry` binding `"fake"`; `get` yields a fresh instance and raises `UnknownWorkerError` for an unknown name — no conditional on a worker's name anywhere in the core.
- The shared `tests/contract/` suite runs green over `[FakeWorker]` and is parametrized so Phases 7-8 append real adapters unchanged. Both abstraction guards pass: no `claude`/`copilot`/`hermes` string outside `workers/`+`config/`, and no wholesale `os.environ` copy under `src/dark_factory/`.

## Contract record (Plans 04/05 + Phases 7-8 are written against these)

**`WorkerResult` fields** (`src/dark_factory/domain/worker.py`, frozen, `extra="forbid"`):

| Field | Type | Default |
|-------|------|---------|
| `status` | `WorkerResultStatus` | required |
| `summary` | `str` | `""` |
| `questions` | `list[str]` | `[]` (`default_factory=list`) |
| `artifacts` | `list[ArtifactRef]` | `[]` (`default_factory=list`) |
| `changed_files` | `list[str]` | `[]` (`default_factory=list`) |
| `worker_session_id` | `str \| None` | `None` |
| `metadata` | `dict[str, Any]` | `{}` (`default_factory=dict`) |
| `error` | `str \| None` | `None` |

Validator: `status is NEEDS_INPUT and not questions` → `ValueError` (surfaced as `ValidationError` naming `questions`).

**`WorkerResultStatus`** = `COMPLETED | NEEDS_INPUT | FAILED` (StrEnum, value == name).

**`WorkerCapabilities`** (frozen, `extra="forbid"`): `native_resume=False`, `session_id=False`, `structured_output=True`, `non_interactive=True`, `emits_changed_files=False`, `max_prompt_bytes: int | None = None`.

**`ArtifactRef`** (`extra="forbid"`, not frozen): `type: str`, `path: str`, `checksum: str | None = None`.

**`CodingWorker` method signatures** (`src/dark_factory/workers/base.py`):

```python
class CodingWorker(ABC):
    @abstractmethod
    def execute(self, context: object) -> WorkerResult: ...
    @abstractmethod
    def resume(self, context: object, previous: WorkerResult, answer: str | None) -> WorkerResult: ...
    @abstractmethod
    def capabilities(self) -> WorkerCapabilities: ...
```

**`FakeWorker.__init__(self, script: Sequence[WorkerResult] | None = None)`** — script resolution order: explicit `script` (empty list honoured) → `DARK_FACTORY_FAKE_SCRIPT` JSON array (each element `WorkerResult.model_validate`) → D-10 default (one `COMPLETED` result, `worker_session_id=f"fake-{uuid4()}"`). `resume()` delegates to `execute()`. `capabilities()` → `WorkerCapabilities(native_resume=False, session_id=True, structured_output=True, non_interactive=True)`.

**`WorkerRegistry`**: `register(name: str, factory: Callable[[], CodingWorker]) -> None`, `get(name: str) -> CodingWorker` (calls factory; raises `UnknownWorkerError(name)`). Module-level `default_registry` with `"fake"` bound at import.

**`RunStatus`** = `CREATED, BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING, COMPLETED, WAITING_HUMAN, FAILED`. `TERMINAL_STATUSES = STOP_STATUSES = frozenset({COMPLETED, FAILED})` (distinct objects).
**`Signal`** = `ENTER, ROLE_COMPLETED, ROLE_FAILED, ROLE_NEEDS_INPUT`; `signal_from_result` maps `COMPLETED→ROLE_COMPLETED`, `FAILED→ROLE_FAILED`, `NEEDS_INPUT→ROLE_NEEDS_INPUT`.
**`EventType`** = `RUN_CREATED, ROLE_STARTED, ROLE_COMPLETED, ROLE_FAILED, RUN_COMPLETED, RUN_FAILED`.

## Task Commits

1. **Task 1: RunStatus, Signal and the event catalog** — RED `9a152c9` (test), GREEN `1a380af` (feat)
2. **Task 2: NormalizedTask and the WorkerResult contract** — RED `28aefe5` (test), GREEN `aee632c` (feat)
3. **Task 3: CodingWorker port, WorkerRegistry, FakeWorker, and the two guards** — RED `15b7a92` (test), GREEN `48684c1` (feat)

**Plan metadata:** docs commit (see final commit)

## TDD Gate Compliance

| Task | RED (`test(01-02)`) | GREEN (`feat(01-02)`) | REFACTOR | Status |
|------|---------------------|-----------------------|----------|--------|
| 1 | `9a152c9` | `1a380af` | — | Pass |
| 2 | `28aefe5` | `aee632c` | — | Pass |
| 3 | `15b7a92` | `48684c1` | — | Pass |

Each RED commit failed on `ModuleNotFoundError` at the time it was made (the target module did not yet exist). No gate violations. `workflow.tdd_mode` is `false` in config, so the plan-level RED-evidence verb gate is not enforced; the RED→GREEN discipline was followed per the execution prompt.

## Files Created/Modified

- `src/dark_factory/domain/status.py` — `RunStatus` StrEnum (10 values) + `TERMINAL_STATUSES` / `STOP_STATUSES` frozensets
- `src/dark_factory/domain/signal.py` — `Signal` StrEnum + `signal_from_result` pure mapping
- `src/dark_factory/domain/task.py` — `NormalizedTask` frozen boundary model
- `src/dark_factory/domain/worker.py` — `WorkerResultStatus`, `ArtifactRef`, `WorkerCapabilities`, `WorkerResult`
- `src/dark_factory/events/catalog.py` — `EventType` StrEnum (6 Phase-1 members)
- `src/dark_factory/workers/base.py` — `CodingWorker` ABC
- `src/dark_factory/workers/fake.py` — `FakeWorker`, `ScriptExhaustedError`
- `src/dark_factory/workers/registry.py` — `UnknownWorkerError`, `WorkerRegistry`, `default_registry`
- `src/dark_factory/domain/__init__.py`, `src/dark_factory/events/__init__.py`, `src/dark_factory/workers/__init__.py` — empty package markers
- `tests/unit/test_domain_enums.py`, `tests/unit/test_domain_models.py`, `tests/unit/test_workers.py` — unit coverage
- `tests/unit/test_no_worker_name_leak.py`, `tests/unit/test_no_environ_copy.py` — abstraction guards
- `tests/contract/__init__.py`, `tests/contract/test_coding_worker_contract.py` — shared contract suite

## Decisions Made

- **`WorkerResultStatus` created in Task 1, not Task 2.** `domain/signal.py`'s `signal_from_result` needs it, and Task 1 owns `signal.py`. Task 2 extended the same `domain/worker.py` file with `ArtifactRef` / `WorkerCapabilities` / `WorkerResult`. See Deviations.
- **`WorkerResult` has 8 fields, not 7.** The 7 canonical WORK-08 fields plus optional `error: str | None = None`, per the plan's Task 2 action text ("plus an optional `error` for the failure arm") and D-10's scripted-FAILED path.
- **Added `tests/unit/test_workers.py`.** The plan's Task 3 acceptance criteria list FakeWorker/registry/ABC assertions but assign no file for them (only the contract suite and the two guards). See Deviations.
- **`ruff format` applied** in addition to `ruff check` (CLAUDE.md mandates both). Reformatted `domain/status.py` (committed clean in Task 1, whitespace-only touch-up folded into Task 3 GREEN) and three Task 3 test files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `WorkerResultStatus` moved into Task 1's scope**
- **Found during:** Task 1 (signal vocabulary)
- **Issue:** `domain/signal.py` — a Task 1 file — defines `signal_from_result`, whose behavior and acceptance criteria are expressed in terms of `WorkerResultStatus`. The plan creates `domain/worker.py` in Task 2, so Task 1's tests could not pass.
- **Fix:** Created `src/dark_factory/domain/worker.py` in Task 1 containing only the `WorkerResultStatus` StrEnum. Task 2 extended the same file with `ArtifactRef`, `WorkerCapabilities` and `WorkerResult` (an edit, not a create). `signal.py` imports `WorkerResultStatus` at runtime and `WorkerResult` under `TYPE_CHECKING` only.
- **Files modified:** `src/dark_factory/domain/worker.py` (Task 1 + Task 2)
- **Verification:** `pytest -m unit` green after Task 1; `mypy src/dark_factory/domain` green after Task 2 completes `WorkerResult`.
- **Committed in:** `1a380af` (Task 1 GREEN), `aee632c` (Task 2 GREEN)

**2. [Rule 2 - Missing test file] Added `tests/unit/test_workers.py`**
- **Found during:** Task 3
- **Issue:** Task 3's acceptance criteria require assertions for ABC enforcement (`TypeError`), scripted order, `ScriptExhaustedError`, `DARK_FACTORY_FAKE_SCRIPT` resolution, and `WorkerRegistry` fresh-instance / `UnknownWorkerError` behavior. The plan's `<files>` list names only the contract suite and the two guard tests — no home for these.
- **Fix:** Created `tests/unit/test_workers.py` (marked `unit`, 11 tests) covering every listed criterion. The `contract` suite stays focused on the parametrized shared contract.
- **Files modified:** `tests/unit/test_workers.py` (new)
- **Verification:** `pytest -m unit -q` → 44 passed; the specific tests referenced in coverage D5-D7.
- **Committed in:** `15b7a92` (RED), `48684c1` (GREEN)

**3. [Rule 3 - Tooling] `ruff format` run alongside `ruff check`**
- **Found during:** Task 3 verification
- **Issue:** Plan `<verification>` lists `ruff check .` only; CLAUDE.md mandates `ruff check` + `ruff format`. `ruff format --check` reported 4 files needing reformat.
- **Fix:** Ran `uv run ruff format src tests`. Whitespace/line-wrap only, no logic change. One file (`domain/status.py`) had already been committed in Task 1; its formatting touch-up was folded into the Task 3 GREEN commit.
- **Files modified:** `src/dark_factory/domain/status.py`, `tests/unit/test_no_environ_copy.py`, `tests/unit/test_no_worker_name_leak.py`, `tests/unit/test_workers.py`
- **Verification:** `ruff check .` and `ruff format --check src tests` both clean; all tests still green.
- **Committed in:** `48684c1` (Task 3 GREEN)

---

**Total deviations:** 3 (1 blocking reorder, 1 missing-test-file addition, 1 tooling). No scope creep — every file in the plan's `<files>` list was produced; the additions are a co-located enum and one test file the acceptance criteria implied.
**Impact on plan:** None substantive. All five plan-level success criteria met; all four `<verification>` commands pass.

## Verification Results

| Command | Result |
|---------|--------|
| `uv run pytest -m unit -q` | 44 passed, 5 deselected — no marker warnings |
| `uv run pytest -m contract -q` | 4 passed |
| `uv run mypy src/dark_factory` | Success: no issues found in 12 source files (strict) |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check src tests` | 25 files already formatted |

## Issues Encountered

- **Task 1 / Task 2 import coupling.** `signal.py` (Task 1) forward-references `WorkerResult` (Task 2). Resolved by keeping the reference under `TYPE_CHECKING` and creating `WorkerResultStatus` early (Deviation 1). Between the Task 1 GREEN and Task 2 GREEN commits, `mypy src/dark_factory/domain` would have reported one `attr-defined` error; it is green from `aee632c` onward. Task 1's own `<verify>` (pytest only) was green throughout.

## User Setup Required

None - no external service configuration required. This plan is pure in-memory Python: no database, no `.env`, no network.

## Next Phase Readiness

- **Ready:** every contract the tracer (Plan 05) and expansion plans need is importable and unit-tested — `RunStatus` + stop-condition sets, `Signal` + `signal_from_result`, `NormalizedTask`, the full `WorkerResult` contract, `EventType`, `CodingWorker`, `WorkerRegistry` / `default_registry`, `FakeWorker`.
- **For Phases 7-8:** append `ClaudeCodeWorker` / `CopilotWorker` / `HermesWorker` factories to `WORKER_FACTORIES` in `tests/contract/test_coding_worker_contract.py` — the suite runs against them with no other change.
- **Guards active:** any later code that leaks a runtime name outside `workers/`+`config/`, or copies `os.environ` wholesale, fails `pytest -m unit`.
- **Unchanged blockers:** the three research-flagged decisions (artifact-content durability → Phase 5, lease TTL → Phase 2, Copilot/Hermes flag matrix → Phase 8) are untouched by this plan.

## Self-Check: PASSED

All 15 content files verified present on disk; all 7 commits (`9a152c9`, `1a380af`, `28aefe5`, `aee632c`, `15b7a92`, `48684c1`, `95de4fa`) verified in `git log`.

---
*Phase: 01-walking-skeleton-one-durable-run*
*Completed: 2026-09-08*
