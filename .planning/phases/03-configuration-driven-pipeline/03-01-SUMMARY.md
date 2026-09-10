---
phase: 03-configuration-driven-pipeline
plan: 01
subsystem: infra
tags: [config, registry, pipeline, pydantic, actions, workers]

requires:
  - phase: 01-walking-skeleton-one-durable-run
    provides: WorkerRegistry name->factory map, Pipeline/RoleNode, RunStatus vocabulary, transition() pure function
  - phase: 02-pause-resume-lease
    provides: runs.workflow snapshot round-trip, DEFAULT_PIPELINE consumed by two db tests
provides:
  - "dark_factory.actions package — ActionRegistry (name->callable allowlist) + UnknownActionError + module-level default_registry"
  - "ActionContext — frozen extra=forbid pydantic v2 model, 8 fields, phase: Literal[before, after]"
  - "five MVP no-op built-in actions registered at import: prepare_role_context, ensure_clean_worktree, collect_diff, store_role_artifacts, collect_test_results"
  - "WorkerRegistry.__contains__ for invoke-free membership validation"
  - "claude-code / copilot / hermes registered as placeholder workers that raise NotImplementedError naming Phase 7 / 8"
  - "workflows.pipeline.pipeline_from_snapshot(snapshot) -> Pipeline, tolerant of legacy bare-string and new {name,worker} dict role shapes"
  - "DEFAULT_PIPELINE demoted to a documented test fixture (still importable, byte-identical)"
affects: [03-02 config loader validation, 03-03 orchestrator wiring, 03-04 acceptance gate]

actuals:
  tokens: 4400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "ActionRegistry is a verbatim clone of WorkerRegistry — every registry in the codebase is the same name->callable dict with a typed KeyError subclass and __contains__"
    - "placeholder worker: a properly-typed CodingWorker subclass whose entry points raise NotImplementedError via a NoReturn helper (mypy --strict clean)"
    - "pipeline_from_snapshot raises KeyError on a missing 'roles' key — no hardcoded fallback pipeline"

key-files:
  created:
    - src/dark_factory/actions/__init__.py
    - src/dark_factory/actions/registry.py
    - src/dark_factory/actions/context.py
    - src/dark_factory/actions/builtins.py
    - tests/unit/test_action_registry.py
    - tests/unit/test_worker_registry_names.py
    - tests/unit/test_pipeline_from_snapshot.py
  modified:
    - src/dark_factory/workers/registry.py
    - src/dark_factory/workflows/pipeline.py
    - tests/unit/test_lifecycle.py

key-decisions:
  - "ActionContext mirrors _build_context's run_id/role/worker/attempt/task/answer shape and adds phase + role_definition; frozen + extra=forbid like WorkerCapabilities/WorkerResult"
  - "Built-ins are callable no-ops, not raising stubs — SC2 needs the runner to actually invoke a configured hook; a raising stub would break every run that names one"
  - "_NotYetImplementedWorker is a real CodingWorker subclass (not the research sketch's execute=resume=capabilities=_fail class-scope bind) so it passes mypy --strict"
  - "DEFAULT_PIPELINE kept byte-identical and importable; only its docstring changed. The orchestrator parameter-default reference is 03-03's removal, not this plan's"
  - "pipeline_from_snapshot tolerates both role shapes so pre-Phase-3 runs.workflow snapshots ({'roles': ['BA']}) still build a valid Pipeline"

patterns-established:
  - "Leaf-package discipline: nothing under src/dark_factory/actions/ imports persistence / orchestrator / events / config"
  - "Config validation checks membership with `name in registry`, never registry.get(name) (get invokes the factory)"

requirements-completed: [CFG-04, WORK-02, ORCH-02]

coverage:
  - id: D1
    description: "ActionRegistry resolves a configured hook name to a callable, rejects an unknown name with UnknownActionError, and accepts a newly-registered action with zero change to any other module (CFG-04)"
    requirement: CFG-04
    verification:
      - kind: unit
        ref: "tests/unit/test_action_registry.py::test_builtin_action_resolves_to_a_callable_noop"
        status: pass
      - kind: unit
        ref: "tests/unit/test_action_registry.py::test_unknown_action_name_raises_and_is_not_a_member"
        status: pass
      - kind: unit
        ref: "tests/unit/test_action_registry.py::test_a_newly_registered_action_is_usable_with_no_core_change"
        status: pass
      - kind: unit
        ref: "tests/unit/test_action_registry.py::test_action_context_rejects_an_unknown_constructor_key"
        status: pass
      - kind: unit
        ref: "tests/unit/test_action_registry.py::test_action_context_is_immutable"
        status: pass
    human_judgment: false
  - id: D2
    description: "WorkerRegistry maps claude-code / copilot / hermes; membership works without invoking; a placeholder invocation raises NotImplementedError naming the phase (WORK-02)"
    requirement: WORK-02
    verification:
      - kind: unit
        ref: "tests/unit/test_worker_registry_names.py::test_all_placeholder_names_plus_fake_are_members"
        status: pass
      - kind: unit
        ref: "tests/unit/test_worker_registry_names.py::test_claude_code_placeholder_resolves_but_every_entry_point_names_phase_7"
        status: pass
      - kind: unit
        ref: "tests/unit/test_worker_registry_names.py::test_phase_8_placeholders_resolve_but_every_entry_point_names_phase_8"
        status: pass
      - kind: unit
        ref: "tests/unit/test_no_worker_name_leak.py::test_no_real_worker_runtime_name_leaks_into_the_core"
        status: pass
    human_judgment: false
  - id: D3
    description: "pipeline_from_snapshot builds an N-node Pipeline from both the new dict shape and the legacy bare-string shape; transition() walks it with no role-count assumption (ORCH-02)"
    requirement: ORCH-02
    verification:
      - kind: unit
        ref: "tests/unit/test_pipeline_from_snapshot.py::test_new_dict_shape_yields_ordered_nodes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_pipeline_from_snapshot.py::test_legacy_bare_string_shape_defaults_worker_to_fake"
        status: pass
      - kind: unit
        ref: "tests/unit/test_pipeline_from_snapshot.py::test_missing_roles_key_raises_key_error"
        status: pass
      - kind: unit
        ref: "tests/unit/test_pipeline_from_snapshot.py::test_three_node_snapshot_drives_a_full_transition_walk"
        status: pass
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_snapshot_built_pipeline_walks_identically_to_a_hand_built_one"
        status: pass
    human_judgment: false
  - id: D4
    description: "DEFAULT_PIPELINE stays importable for the Phase 1 / Phase 2 db tests but is documented as a fixture only"
    verification:
      - kind: unit
        ref: "python -c 'import tests.db.test_lease_lost_aborts_step, tests.db.test_pause_mechanism_generic' (clean import)"
        status: pass
      - kind: other
        ref: "pytest --collect-only -q (384 tests collected, 0 errors)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full existing Phase 1 + Phase 2 db/integration suite stays green (nothing in orchestrator/, cli.py, persistence/ changed)"
    verification:
      - kind: other
        ref: "set -a; . .env; uv run pytest -q — the whole suite"
        status: unknown
    human_judgment: true
    rationale: "The db/integration tests need the Neon DATABASE_URL from .env, which the executor sandbox's secret-read guard blocks, and no local Postgres backend is available. All 213 unit tests pass, all 51 db/integration test modules import cleanly, full collection (384 tests) succeeds, and the change set is purely additive leaf code with zero edits to orchestrator/ / persistence/ / cli.py — but the db suite was not executed. Verifier must run the full suite with the real DATABASE_URL."

duration: 9min
completed: 2026-09-10
status: complete
---

# Phase 3 Plan 01: Registries and the pipeline builder Summary

**A leaf `actions/` package (ActionRegistry + ActionContext + five no-op built-ins), `WorkerRegistry.__contains__` with claude-code/copilot/hermes phase-named placeholders, and `pipeline_from_snapshot` — the three seams 03-02 and 03-03 hang the rest of Phase 3 on, with no orchestrator wiring yet.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-10T16:03:12Z
- **Completed:** 2026-09-10T16:12:29Z
- **Tasks:** 3
- **Files modified:** 10 (7 created, 3 modified)

## Accomplishments

- `dark_factory.actions` package: `ActionRegistry` (a verbatim clone of `WorkerRegistry` — `register` / `get` raising `UnknownActionError` / `__contains__`), module-level `default_registry`, frozen `extra="forbid"` `ActionContext` with fields `run_id, role, worker, attempt, phase, task, answer, role_definition` (`phase: Literal["before", "after"]`), and five callable-no-op built-ins registered at import.
- `WorkerRegistry.__contains__` for invoke-free membership validation; `claude-code` (Phase 7), `copilot` (Phase 8), `hermes` (Phase 8) registered as `_NotYetImplementedWorker` placeholders whose `execute` / `resume` / `capabilities` each raise `NotImplementedError` naming the phase.
- `workflows.pipeline.pipeline_from_snapshot(snapshot) -> Pipeline` — builds an N-node pipeline from `snapshot["roles"]`, accepting both the legacy list-of-strings and the new list-of-`{name,worker}`-dicts; raises `KeyError` when `"roles"` is absent (no hardcoded fallback). `DEFAULT_PIPELINE` kept byte-identical and importable, docstring demoted to "test fixture only".
- Four unit proof files: `test_action_registry.py`, `test_worker_registry_names.py`, `test_pipeline_from_snapshot.py`, plus an added N-node snapshot-walk case in `test_lifecycle.py`.
- All pre-existing guards stay green: `test_no_worker_name_leak` (the three literals stay confined to `workers/`), `test_single_mutation_path` (the new `actions/` package writes no lifecycle state), `test_status_import_graph`.

## Task Commits

1. **Task 1: actions package — ActionRegistry, ActionContext, five no-op built-ins** — `6186d45` (feat)
2. **Task 2: WorkerRegistry.__contains__ + claude-code/copilot/hermes placeholders** — `c881205` (feat)
3. **Task 3: pipeline_from_snapshot builder; demote DEFAULT_PIPELINE to a fixture** — `91fce63` (feat)

**Plan metadata:** _(this commit)_ (docs: complete plan)

_plan_head_before: 404f8c3718da406b90bfb8a36139816d608364b2_

## Files Created/Modified

- `src/dark_factory/actions/registry.py` — `ActionRegistry`, `UnknownActionError`, `default_registry`
- `src/dark_factory/actions/context.py` — frozen `ActionContext` boundary model
- `src/dark_factory/actions/builtins.py` — five `(ActionContext) -> None` no-op built-ins
- `src/dark_factory/actions/__init__.py` — registers the five built-ins into `default_registry` at import; re-exports the package surface
- `src/dark_factory/workers/registry.py` — added `__contains__`, `_NotYetImplementedWorker`, three placeholder registrations; module docstring updated
- `src/dark_factory/workflows/pipeline.py` — added `pipeline_from_snapshot` + `__all__` entry; `DEFAULT_PIPELINE` docstring demoted; module docstring rewritten
- `tests/unit/test_action_registry.py` — get / contains / unknown / new-action / frozen-forbid ActionContext
- `tests/unit/test_worker_registry_names.py` — membership without invoking; phase-named `NotImplementedError` on invocation
- `tests/unit/test_pipeline_from_snapshot.py` — new dict shape, legacy string shape, empty list, missing key, three-node `transition()` walk
- `tests/unit/test_lifecycle.py` — added a parametrized snapshot-built N-node walk case

## Decisions Made

- **Built-ins are callable no-ops, not raising stubs.** SC2 requires the runner to actually invoke a configured hook; a raising stub would fail every run that names one. Each built-in's docstring names the phase it becomes real in (4 / 5 / 5 / 4 / 9).
- **`_NotYetImplementedWorker` is a real `CodingWorker` subclass.** The research sketch's `execute = resume = capabilities = _fail` class-scope bind (with `_fail(self, *_args, **_kwargs) -> object`) fails `mypy --strict` on override-incompatibility — see Deviations.
- **`DEFAULT_PIPELINE` untouched except its docstring.** It is still a parameter default in `orchestrator/runner.py` (lines 160/199/446); removing that reference is 03-03's job. This plan changes no code under `orchestrator/`, `cli.py`, or `persistence/`.
- **`pipeline_from_snapshot` accepts both role shapes** so existing `runs.workflow` snapshots (`{"roles": ["BA"]}`) keep building a valid `Pipeline` with no back-fill.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `_NotYetImplementedWorker` shape changed to pass `mypy --strict`**
- **Found during:** Task 2
- **Issue:** The plan's action text (from 03-RESEARCH Pattern 7) prescribes `_fail(self, *_args: object, **_kwargs: object) -> object` with `execute = resume = capabilities = _fail` bound at class scope. Under `mypy --strict` — which the task's own `<verify>` block runs and fails on any `error:` — that binding is an incompatible override of `CodingWorker.execute` / `.resume` / `.capabilities` (return type `object` is not assignable to `WorkerResult` / `WorkerCapabilities`).
- **Fix:** Implemented `_NotYetImplementedWorker` as a proper `CodingWorker` subclass with correctly-typed `execute` / `resume` / `capabilities` methods that delegate to a private `_fail(self) -> NoReturn` helper which raises `NotImplementedError(f"{name} worker adapter lands in Phase {phase}")`. The observable contract is identical: name resolves, construction is cheap, every entry point raises `NotImplementedError` naming the phase.
- **Files modified:** `src/dark_factory/workers/registry.py`
- **Verification:** `tests/unit/test_worker_registry_names.py` (membership + phase-named raise on all three entry points), `uv run mypy src/dark_factory` (Success), `uv run ruff check .` (clean).
- **Committed in:** `c881205` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** No scope change. The placeholder's external behavior matches the plan's acceptance criteria exactly; only its internal typing was adjusted to satisfy the plan's own static-analysis gate.

## Issues Encountered

- **Full db/integration suite not executed in the executor sandbox.** Plan verification step 4 (`set -a; . .env; uv run pytest -q`) needs the Neon `DATABASE_URL` from `.env`; the executor's secret-read guard blocks reading `.env`, and the sandbox has no Docker / local `initdb` / `DARK_FACTORY_TEST_DATABASE_URL`. Mitigation and evidence that the suite is unaffected: all 213 unit tests pass (including every source-tree guard), all 51 db/integration test modules import cleanly, `pytest --collect-only` collects all 384 tests with zero errors, and the change set is purely additive leaf code with no edits under `orchestrator/`, `persistence/`, or `cli.py`. This matches the Phase 1 / Phase 2 precedent of deferring the real-Neon run to `/gsd-verify-work`. Coverage deliverable D5 is flagged `human_judgment: true` for the verifier to run the full suite against the real database.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Ready for 03-02** (config loader). `name in dark_factory.actions.default_registry` and `name in dark_factory.workers.registry.default_registry` are the membership seams the loader uses for hook / worker validation; `ActionContext` is the boundary model the loader's snapshot feeds.
- **Ready for 03-03** (orchestrator wiring). `pipeline_from_snapshot(state.workflow)` is the builder `advance()` / `drive()` / `_advance_once` will call in place of the `DEFAULT_PIPELINE` parameter default; `ActionContext` + `default_registry.get(name)` is the before/after hook invocation seam for `_run_current_role`.
- **No blockers.** One carried verification item: the full db/integration suite must be run against the real Neon database by `/gsd-verify-work`.

## Self-Check: PASSED

- All 7 created files present on disk.
- All 3 task commits present in history (`6186d45`, `c881205`, `91fce63`).
- Targeted unit verification: `test_action_registry.py`, `test_worker_registry_names.py`, `test_pipeline_from_snapshot.py`, `test_lifecycle.py`, `test_no_worker_name_leak.py`, `test_single_mutation_path.py` — 44 passed.
- Full unit suite: 213 passed, 171 deselected.
- `uv run mypy src/dark_factory` — Success (43 source files).
- `uv run ruff check .` — All checks passed. `ruff format --check` — all files already formatted.
- All 51 db/integration test modules import cleanly; `pytest --collect-only` — 384 tests, 0 errors.
- Carried item (not a self-check failure): the db/integration suite was not *executed* — see "Issues Encountered" / coverage D5.

---
*Phase: 03-configuration-driven-pipeline*
*Completed: 2026-09-10*
