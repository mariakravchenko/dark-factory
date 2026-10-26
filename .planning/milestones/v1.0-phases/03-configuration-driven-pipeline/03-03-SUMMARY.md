---
phase: 03-configuration-driven-pipeline
plan: 03
subsystem: infra
tags: [config, pipeline, orchestrator, cli, snapshot, guard-tests]

requires:
  - phase: 03-configuration-driven-pipeline (03-01)
    provides: "pipeline_from_snapshot(snapshot) -> Pipeline (dict + legacy bare-string shapes); DEFAULT_PIPELINE demoted to a fixture"
  - phase: 03-configuration-driven-pipeline (03-02)
    provides: "load_effective_config(root, *, worker_registry, action_registry) -> snapshot dict; ConfigError(ValueError); config_root / config_root_factory conftest fixtures; the tracked .dark-factory.yaml + BA/QA role YAML"
  - phase: 01-walking-skeleton-one-durable-run
    provides: "start_run/advance/drive keyword-only injection seam; runs.workflow JSONB round-trip; RunStatus vocabulary; source-tree / import-graph guard-test idiom"
provides:
  - "cli.py::run() resolves load_effective_config(Path.cwd()) BEFORE start_run and maps ConfigError -> Exit(2); cli.py is the sole composition point importing dark_factory.config.loader"
  - "start_run(source, *, session_factory=new_session, snapshot: Mapping[str, Any]) -- snapshot is a REQUIRED keyword, no default; passes dict(snapshot) straight to create_run(workflow=...)"
  - "advance/drive/_advance_once take pipeline: Pipeline | None = None; _advance_once builds `pipeline = pipeline_from_snapshot(state.workflow)` right after load_run_state when none is injected"
  - "_workflow_snapshot and the DEFAULT_PIPELINE import/parameter-default are gone from orchestrator/runner.py"
  - "tests/support/config.py::DEFAULT_TEST_SNAPSHOT ({\"roles\": [\"BA\"]}) -- the shared snapshot ~15 Phase 1/2 in-process start_run call sites now pass"
  - "tests/support/subprocess_runner.py spawn()/popen() gain an optional cwd= kwarg (defaults to REPO_ROOT)"
  - "two architecture guards: tests/unit/test_no_role_name_literal.py (no RunStatus role literal in orchestrator/ + workflows/pipeline.py) and tests/unit/test_orchestrator_no_live_config_read.py (orchestrator/pipeline import closures exclude dark_factory.config.loader)"
  - "SC1 / SC4 proofs: tests/integration/test_config_drives_pipeline.py, tests/integration/test_config_error_exit_code.py, tests/db/test_bad_config_no_orphan_run.py"
affects: [03-04 acceptance gate + hook invocation in _run_current_role]

actuals:
  tokens: 14000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "The CLI is the composition root: it is the ONLY module that imports dark_factory.config.loader. The orchestrator rebuilds the pipeline from the persisted runs.workflow snapshot and never re-reads a config file (enforced by an import-graph guard)."
    - "start_run takes a required resolved snapshot -- no fabricated {\"roles\": [\"BA\"]} fallback. A run with no resolved config is a caller error, raised."
    - "_advance_once resolves `pipeline = pipeline_from_snapshot(state.workflow)` only when no explicit Pipeline is injected -- production path is snapshot-driven, tests keep the keyword-only injection seam."
    - "Role names are data from the snapshot, not code: an AST guard forbids any RunStatus role-name string literal under orchestrator/ or in workflows/pipeline.py."

key-files:
  created:
    - tests/support/config.py
    - tests/integration/test_config_drives_pipeline.py
    - tests/integration/test_config_error_exit_code.py
    - tests/db/test_bad_config_no_orphan_run.py
    - tests/unit/test_no_role_name_literal.py
    - tests/unit/test_orchestrator_no_live_config_read.py
  modified:
    - src/dark_factory/cli.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/persistence/mutations.py
    - src/dark_factory/persistence/repositories.py
    - tests/support/subprocess_runner.py
    - tests/db/test_resume_first_advance.py
    - tests/db/test_run_failure_path.py
    - tests/db/test_terminal_advance_noop.py
    - tests/db/test_status_from_columns.py
    - tests/db/test_transition_atomic.py
    - tests/db/test_lease_claim_atomic.py
    - tests/db/test_lease_lost_aborts_step.py
    - tests/db/test_pause_path_atomic.py
    - tests/db/test_pause_mechanism_generic.py
    - tests/db/test_state_event_pairing.py
    - tests/integration/test_heartbeat_slow_step.py
    - tests/integration/test_redaction_interactions.py
    - tests/integration/test_secret_redaction_e2e.py
    - tests/integration/test_single_owner_race.py

key-decisions:
  - "start_run's final signature: start_run(source, *, session_factory: SessionFactory = new_session, snapshot: Mapping[str, Any]) -- snapshot has NO default. from collections.abc import Mapping added; DEFAULT_PIPELINE dropped from the workflows.pipeline import, pipeline_from_snapshot added."
  - "_advance_once snapshot-to-pipeline line: `if pipeline is None: pipeline = pipeline_from_snapshot(state.workflow)` -- placed immediately after the load_run_state block and the `state is None` / STOP_STATUSES early returns, so a stopped/unknown run still short-circuits without building a pipeline."
  - "cli.run() does the ConfigError pre-check (`snapshot = load_effective_config(Path.cwd())`) AND adds ConfigError to the start_run except tuple for defence-in-depth; the pre-check is what guarantees 'no run id on stdout / no runs row'."
  - "test_pause_mechanism_generic.py's start_run(pipeline=_TWO_NODE_PIPELINE) became start_run(snapshot=_TWO_NODE_SNAPSHOT) -- a local 2-role dict snapshot; its advance() calls still inject _TWO_NODE_PIPELINE explicitly, so only runs.workflow changes."
  - "DEFAULT_TEST_SNAPSHOT is the legacy bare-string shape {\"roles\": [\"BA\"]} on purpose -- it exercises pipeline_from_snapshot's string tolerance and is byte-equivalent to the old DEFAULT_PIPELINE those tests relied on."

patterns-established:
  - "Composition-root rule made structural: tests/unit/test_orchestrator_no_live_config_read.py asserts the transitive dark_factory.* import closure of runner/answers/lifecycle/workflows.pipeline excludes dark_factory.config.loader, with a self-proving sanity test that dark_factory.cli's closure DOES include it."
  - "Role-name-as-data made structural: tests/unit/test_no_role_name_literal.py AST-scans for RunStatus role literals, docstrings exempted, with a self-proving 'ARCHITECTURE' sanity test."
  - "subprocess_runner spawn/popen cwd= lets a real dark-factory subprocess resolve config from a bespoke tmp .dark-factory/ tree."

requirements-completed: [ORCH-02, ORCH-03]

coverage:
  - id: D1
    description: "cli.py::run() resolves the effective-config snapshot from Path.cwd() via load_effective_config and maps ConfigError -> exit 2 before printing the run id; cli.py is the only composition point importing the loader"
    requirement: ORCH-02
    verification:
      - kind: unit
        ref: "tests/unit/test_orchestrator_no_live_config_read.py::test_the_walk_resolves_imports_via_the_cli"
        status: pass
      - kind: integration
        ref: "tests/integration/test_config_drives_pipeline.py::test_run_resolves_pipeline_from_config"
        status: unknown
    human_judgment: true
    rationale: "The import-graph half is unit-proven; the end-to-end 'a real dark-factory run resolves .dark-factory.yaml and drives to COMPLETED, snapshot persisted' half needs a real PostgreSQL and was not executed here (no Docker / initdb / DATABASE_URL in the executor sandbox). The new integration module imports cleanly under pytest --collect-only. Verifier must run tests/integration/test_config_drives_pipeline.py against the real DB."
  - id: D2
    description: "start_run requires a resolved snapshot; _workflow_snapshot + the DEFAULT_PIPELINE parameter default are removed from runner.py; advance/drive/_advance_once build the pipeline from state.workflow via pipeline_from_snapshot"
    requirement: ORCH-02
    verification:
      - kind: other
        ref: "grep -c 'DEFAULT_PIPELINE\\|_workflow_snapshot' src/dark_factory/orchestrator/runner.py | grep -qx 0"
        status: pass
      - kind: other
        ref: "uv run mypy src/dark_factory -> Success (45 source files)"
        status: pass
      - kind: unit
        ref: "uv run pytest -m 'unit or contract' -q -> 242 passed"
        status: pass
      - kind: db
        ref: "tests/db/test_resume_first_advance.py + the ~15 updated in-process start_run call sites (Phase 1/2 db + integration suite)"
        status: unknown
    human_judgment: true
    rationale: "The removal + signature change are statically proven (grep gate, mypy --strict, ruff). The full Phase 1/2 db + integration suite with the mechanically-updated snapshot= call sites was not executed -- no PostgreSQL backend in the sandbox. All updated modules import cleanly (pytest --collect-only collects 417 tests, 0 errors). Verifier must run `set -a; . .env; set +a; uv run pytest -q`."
  - id: D3
    description: "SC1 / ORCH-03: reordering or shortening workflow.roles in .dark-factory.yaml changes the emitted transition sequence of a fresh run, with git diff --stat of src/dark_factory/orchestrator + src/dark_factory/workflows empty across the runs"
    requirement: ORCH-03
    verification:
      - kind: integration
        ref: "tests/integration/test_config_drives_pipeline.py::test_reorder_and_shorten_workflow_roles_changes_the_executed_pipeline"
        status: unknown
    human_judgment: true
    rationale: "Needs a real dark-factory run subprocess against PostgreSQL; not executed in the sandbox. Module imports cleanly (collect-only). The static half of ORCH-03 -- no role-name literal in orchestrator/ -- IS unit-proven (see D5). Verifier runs the integration module against the real DB."
  - id: D4
    description: "SC4 / CFG-01: an unknown role/worker/action name, a missing/oversized/escaping instruction file, or an empty / non-mapping .dark-factory.yaml makes `run` exit 2 with nothing on stdout line 1 and no runs row; ConfigError is raised in start_run before create_run"
    requirement: CFG-01
    verification:
      - kind: db
        ref: "tests/db/test_bad_config_no_orphan_run.py::test_bad_config_raises_before_create_run_and_writes_no_row (8 shapes)"
        status: unknown
      - kind: integration
        ref: "tests/integration/test_config_error_exit_code.py::test_bad_config_run_exits_2_with_no_run_id_and_no_row"
        status: unknown
    human_judgment: true
    rationale: "Both proofs need a real PostgreSQL to count runs rows before/after; not executed in the sandbox. Both modules import cleanly (collect-only; the db module parametrizes 8 bad-config shapes). CFG-01 is otherwise closed by 03-02; this plan contributes the run-creation-half proofs. Verifier runs both against the real DB."
  - id: D5
    description: "Two architecture guards: no RunStatus role-name literal in orchestrator/ or workflows/pipeline.py (AST); dark_factory.orchestrator.* transitively excludes dark_factory.config.loader (import graph)"
    requirement: ORCH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_no_role_name_literal.py::test_no_runstatus_role_name_literal_in_orchestrator_or_pipeline"
        status: pass
      - kind: unit
        ref: "tests/unit/test_no_role_name_literal.py::test_the_scan_would_catch_a_role_literal"
        status: pass
      - kind: unit
        ref: "tests/unit/test_orchestrator_no_live_config_read.py::test_resume_path_never_imports_the_config_loader[dark_factory.orchestrator.runner|answers|lifecycle & workflows.pipeline]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_orchestrator_no_live_config_read.py::test_the_walk_resolves_imports_via_the_cli"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-09-10
status: complete
---

# Phase 3 Plan 03: Config-driven run creation + the two architecture guards Summary

**`dark-factory run` now resolves its pipeline from `.dark-factory.yaml` in the cwd, persists that effective-config snapshot in `runs.workflow` at creation, and drives it via `pipeline_from_snapshot(state.workflow)`; `start_run` requires a resolved snapshot (no `DEFAULT_PIPELINE` fallback); a bad config exits 2 with no orphan run; and two guard tests lock the composition-root and role-names-are-data invariants.**

## Performance

- **Duration:** ~22 min
- **Tasks:** 3
- **Files modified:** 25 (6 created, 19 modified)
- **Commits:** 3 (measured: `git rev-list --count 5470bb7..HEAD` == 3)

_plan_head_before: 5470bb71694ce0f46fee92e7d80054716bf48768_

## Accomplishments

- **`cli.py::run()`** adds `from pathlib import Path` + `from dark_factory.config.loader import ConfigError, load_effective_config`, resolves `snapshot = load_effective_config(Path.cwd())` and maps `ConfigError -> typer.Exit(2)` *before* `typer.echo(str(run_id))`, then calls `start_run(source, snapshot=snapshot)` (with `ConfigError` also in the exit-2 except tuple for defence). `resume()` untouched -- it never resolves config.
- **`orchestrator/runner.py`**: `_workflow_snapshot` deleted; `DEFAULT_PIPELINE` dropped from the `workflows.pipeline` import and from the `start_run` / `advance` / `drive` parameter defaults; `pipeline_from_snapshot` + `from collections.abc import Mapping` added. Final signature: `start_run(source, *, session_factory: SessionFactory = new_session, snapshot: Mapping[str, Any])`. `advance` / `drive` / `_advance_once` now take `pipeline: Pipeline | None = None`; `_advance_once` runs `if pipeline is None: pipeline = pipeline_from_snapshot(state.workflow)` right after the `load_run_state` / `state is None` / `STOP_STATUSES` block. Module + `advance` docstrings record the snapshot-is-the-only-config-source contract.
- **`persistence/mutations.py` + `repositories.py`**: docstring-only -- `create_run.workflow` and `RunState.workflow` / `load_run_state` now document the column's widened dual role (pipeline shape + full effective-config snapshot) and that resume never re-reads a config file.
- **`tests/support/config.py`** (new): `DEFAULT_TEST_SNAPSHOT: dict[str, object] = {"roles": ["BA"]}` with `__all__`.
- **`tests/support/subprocess_runner.py`**: `spawn()` / `popen()` gain `cwd: str | Path | None = None` (defaults to `REPO_ROOT`).
- **~15 in-process `start_run(` call sites** under `tests/db/` and `tests/integration/` now pass `snapshot=DEFAULT_TEST_SNAPSHOT` (mechanical); `test_pause_mechanism_generic.py` swapped its `pipeline=_TWO_NODE_PIPELINE` arg for a local `snapshot=_TWO_NODE_SNAPSHOT`.
- **SC1** (`tests/integration/test_config_drives_pipeline.py`): the tracer (`[BA]` config -> `CREATED → BA` / `BA → COMPLETED`, snapshot persisted with a non-empty `instruction_text`) plus the reorder/shorten proof (`[BA,QA]` -> `[QA,BA]` -> `[BA]`, executed sequence changes; git-diff / SHA-256 companion guard shows no source file changed).
- **SC4** (`tests/db/test_bad_config_no_orphan_run.py` -- 8 bad-config shapes; `tests/integration/test_config_error_exit_code.py` -- a real subprocess): `ConfigError` before `create_run`, exit 2, empty stdout line 1, unchanged `runs` count.
- **Guards** (`tests/unit/test_no_role_name_literal.py`, `tests/unit/test_orchestrator_no_live_config_read.py`): both pass, each with a self-proving sanity test (`test_the_scan_would_catch_a_role_literal`, `test_the_walk_resolves_imports_via_the_cli`).

## Task Commits

1. **Task 1: resolve pipeline from config snapshot at run creation** -- `6f0d633` (feat)
2. **Task 2: SC1 -- reorder/shorten workflow.roles changes the executed pipeline** -- `db3c414` (test)
3. **Task 3: SC4 bad-config exit 2 / no orphan run + two architecture guards** -- `37bfdb8` (test)

**Plan metadata:** _(next commit)_ (docs: complete plan)

## Files Created/Modified

See `key-files` frontmatter. Load-bearing:
- `src/dark_factory/cli.py` -- config pre-check in `run()`; the sole loader import point.
- `src/dark_factory/orchestrator/runner.py` -- required `snapshot`, `DEFAULT_PIPELINE`/`_workflow_snapshot` removed, `pipeline_from_snapshot(state.workflow)` on the resume path.
- `tests/support/config.py`, `tests/support/subprocess_runner.py` -- the shared snapshot + `cwd=` seam.
- `tests/unit/test_no_role_name_literal.py`, `tests/unit/test_orchestrator_no_live_config_read.py` -- the two guards.

## Decisions Made

See `key-decisions` frontmatter. In brief: `snapshot` is a required kw with no fallback; the `pipeline_from_snapshot` call sits after the early-return block in `_advance_once`; the CLI does both an explicit pre-check and a belt-and-braces `ConfigError` catch; `DEFAULT_TEST_SNAPSHOT` is deliberately the legacy bare-string shape.

## Deviations from Plan

None - plan executed exactly as written. The mechanical `snapshot=` edits were applied to precisely the call sites the plan's `<files>` list named, plus the one `pipeline=`-carrying call site in `test_pause_mechanism_generic.py` that the plan's action text called out for conversion.

## Issues Encountered

- **db / integration suites not executed.** The `db` and `integration` tiers need a real PostgreSQL 17: the executor sandbox has no Docker, no local `initdb`, no `DATABASE_URL` / `DARK_FACTORY_TEST_DATABASE_URL`, and `.env` is behind a secret-read guard. This matches the Phase 1 / 03-01 / 03-02 precedent of deferring the real-DB run to `/gsd-verify-work`. Evidence the change set is sound: `uv run pytest -m "unit or contract" -q` -> 242 passed (was 235; +7 new guard tests); `uv run mypy src/dark_factory` -> Success; `uv run ruff check .` + `ruff format --check` -> clean; `uv run pytest --collect-only -q` -> 417 tests, 0 errors (every new + edited db/integration module imports cleanly); `grep -c 'DEFAULT_PIPELINE\|_workflow_snapshot' src/dark_factory/orchestrator/runner.py` -> 0.
- **Carried verification items for `/gsd-verify-work`:**
  1. `set -a; . .env; set +a; uv run pytest -q` -- the whole suite green with the updated `start_run` call sites.
  2. `uv run pytest -m integration -q tests/integration/test_config_drives_pipeline.py` -- SC1 (tracer + reorder/shorten).
  3. `uv run pytest -q tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py` -- SC4.
  4. The real-Neon human walkthrough already carried from Phase 1 / Phase 2.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Ready for 03-04** (acceptance gate + hooks). `_run_current_role(run_id, state, pipeline, registry, session_factory, lease)` keeps its Phase 1 shape -- 03-04 adds the `action_registry` parameter and the before/after hook invocation there. `_advance_once` already hands `_run_current_role` a `Pipeline` (narrowed from `Pipeline | None`). The persisted snapshot carries `before` / `after` / `tools` / `permissions` per role for 03-04 to consume.
- **Requirements:** ORCH-02 and ORCH-03 completed here (owned solely by this plan). CFG-01 was closed by 03-02; CFG-05 stays Pending -- shared with 03-04 (its frontmatter). CFG-02 / CFG-03 also remain Pending for 03-04. Mirrors the shared-ID gate 03-01 / 03-02 used.
- **No blockers.** Carried verification items listed above.

## Self-Check: PASSED

- All 6 created files present on disk (`tests/support/config.py`, `tests/integration/test_config_drives_pipeline.py`, `tests/integration/test_config_error_exit_code.py`, `tests/db/test_bad_config_no_orphan_run.py`, `tests/unit/test_no_role_name_literal.py`, `tests/unit/test_orchestrator_no_live_config_read.py`).
- All 3 task commits present in history: `6f0d633`, `db3c414`, `37bfdb8`; `git rev-list --count 5470bb7..HEAD` == 3.
- `uv run pytest -m unit -q tests/unit/test_no_role_name_literal.py tests/unit/test_orchestrator_no_live_config_read.py` -> 7 passed.
- Full `-m "unit or contract"` -> 242 passed, 175 deselected.
- `grep -c 'DEFAULT_PIPELINE\|_workflow_snapshot' src/dark_factory/orchestrator/runner.py` -> 0.
- `uv run mypy src/dark_factory` -> Success (45 source files). `uv run ruff check .` -> All checks passed. `uv run ruff format --check src/dark_factory tests` -> 113 files already formatted.
- `uv run pytest --collect-only -q` -> 417 tests collected, 0 errors.
- Carried item (not a self-check failure): the db / integration tiers were not *executed* -- no PostgreSQL backend in the sandbox. See "Issues Encountered".

---
*Phase: 03-configuration-driven-pipeline*
*Completed: 2026-09-10*
