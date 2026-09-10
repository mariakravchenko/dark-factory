---
phase: 03-configuration-driven-pipeline
plan: 04
subsystem: infra
tags: [config, actions, hooks, orchestrator, snapshot, acceptance-gate, guard-tests]

requires:
  - phase: 03-configuration-driven-pipeline (03-01)
    provides: "ActionRegistry / UnknownActionError / ActionContext / default_registry with the five no-op built-ins; pipeline_from_snapshot"
  - phase: 03-configuration-driven-pipeline (03-02)
    provides: "load_effective_config -> effective-config snapshot dict (published key contract); config_root / config_root_factory / repo_config_snapshot conftest fixtures; tracked .dark-factory/ example set"
  - phase: 03-configuration-driven-pipeline (03-03)
    provides: "config-driven run creation; start_run requires a resolved snapshot; _advance_once builds pipeline via pipeline_from_snapshot(state.workflow); DEFAULT_TEST_SNAPSHOT; the no-role-literal / no-live-config-read guards; subprocess_runner cwd= seam"
  - phase: 01-walking-skeleton-one-durable-run
    provides: "advance/drive keyword-only injection seam; create_run -> load_run_state round-trip; redact() single call site; RunState.workflow JSONB column"
provides:
  - "orchestrator/runner.py::_run_current_role invokes every configured before action name (immediately ahead of the worker call) and every after name (immediately behind the lease-loss check) through action_registry.get(name)(ActionContext(...)) -- both OUTSIDE with session.begin(), with no branch on the role name (CFG-04 runtime)"
  - "orchestrator/runner.py::_role_definition(state, role) -> Mapping[str, Any] -- data lookup by role value in state.workflow['roles']; a legacy bare-string entry yields {'name': role, 'before': [], 'after': []} so the hook loops are a no-op for Phase 1/2 runs"
  - "advance / drive / _advance_once / _run_current_role gain a keyword-only action_registry: ActionRegistry = action_default_registry parameter (production default + test-injection seam), threaded exactly like registry: WorkerRegistry"
  - "tests/db/test_role_hooks_invoked.py -- before->worker->after ordering; identical ActionContext remainder across two roles; a newly-registered action usable from config with zero orchestrator change; legacy snapshot invokes no hooks (CFG-04)"
  - "tests/db/test_snapshot_roundtrip.py -- create_run -> load_run_state deep-equals redact(snapshot) incl. ordered roles + each instruction_text + repository/quality_gate/retry/publishing; a legacy {'roles': ['BA']} snapshot still round-trips and still builds a pipeline (CFG-05)"
  - "tests/integration/test_role_yaml_drives_behaviour.py -- editing BA.yaml after: / instructions: / worker: changes a fresh run's persisted snapshot with the src/dark_factory *.py digest unchanged; instruction bytes inlined verbatim; worker:copilot reaches dispatch and fails with the Phase 8 placeholder (CFG-02, CFG-03, SC2)"
  - "tests/integration/test_snapshot_survives_edit.py -- pause [BA,QA] on NEEDS_INPUT, reorder .dark-factory.yaml to [QA,BA], resume --answer from a fresh process -> transitions continue BA -> QA -> COMPLETED (creation-snapshot order), same run id, one runs row; plus an import-graph guard that the orchestrator / answer path cannot reach dark_factory.config.loader (CFG-05, SC3)"
  - "tests/integration/test_phase3_acceptance.py -- the Phase 3 acceptance gate: exact-set maps of SC1-SC4 and ORCH-02/ORCH-03/CFG-01..CFG-05/WORK-02 to present, non-empty, def-test_-carrying proof files; _VALIDATION_PROOF_FILES drift guard pinned to 03-VALIDATION.md; contains no opt-out call"
  - ".planning/phases/03-configuration-driven-pipeline/COVERAGE.md -- the single-line no-external-API declaration"
affects: [phase-04 (before/after hooks become real: prepare_role_context / store_role_artifacts), phase-05, phase-09]

actuals:
  tokens: 9400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "before/after hooks bracket the worker call exactly where it already sits in _run_current_role -- outside the one mutation transaction (T-03-12 / HITL-08): a slow hook can never hold a DB transaction across non-DB work"
    - "_role_definition is a lookup keyed on the role value, never a branch on which role it is; the no-role-literal AST guard (03-03) still passes"
    - "an UnknownActionError inside _run_current_role is a bug, not an input -- the loader validated every before/after name at run creation (03-02); the runner lets it propagate, never catches it"
    - "the Phase 3 acceptance gate is a SIBLING of test_phase2_acceptance.py (independently readable), asserting its own exact criteria/requirement key sets, never running the mapped proofs"

key-files:
  created:
    - tests/db/test_role_hooks_invoked.py
    - tests/db/test_snapshot_roundtrip.py
    - tests/integration/test_role_yaml_drives_behaviour.py
    - tests/integration/test_snapshot_survives_edit.py
    - tests/integration/test_phase3_acceptance.py
    - .planning/phases/03-configuration-driven-pipeline/COVERAGE.md
  modified:
    - src/dark_factory/orchestrator/runner.py

key-decisions:
  - "The before-loop sits immediately after `context = _build_context(...)` (ahead of the execute-vs-resume branch); the after-loop sits immediately after the `lease.lease_lost.is_set()` check and before `signal_from_result(result)`. A lost lease raises LeaseLost before the after-hooks run. Neither loop is inside `with session.begin()`; the existing apply_transition block is untouched."
  - "One nested helper `_run_hooks(hook_phase: Literal['before','after'])` closes over role_def / context / node / run_id / state / action_registry and is called twice -- keeps the ActionContext construction in one place and the Literal keeps mypy --strict happy on ActionContext.phase."
  - "_role_definition returns the raw snapshot dict for the Phase 3 shape and a synthesized `{'name': role, 'before': [], 'after': []}` for a legacy bare-string entry; a role not found raises LookupError (unreachable in practice -- current_node already validated the role against the same roles list)."
  - "test_phase3_acceptance.py SC4 maps test_role_hooks_invoked.py alongside the two bad-config proofs (per plan): the trio shows the creation-time / execution-time split -- unknown names fail validation at creation, valid names run at execution."
  - "COVERAGE.md already carried the exact plan-specified line as a stub; committed as-is (single line, verified with `test -s`)."

patterns-established:
  - "Hook invocation seam: `advance(..., action_registry=<ActionRegistry>)` mirrors `registry=<WorkerRegistry>` -- a fresh ActionRegistry with recording actions is how a test asserts 'the named callables ran, in order' while the built-ins stay no-ops."
  - "Role-YAML-drives-behaviour proof shape: rewrite one field of one role YAML in a tmp .dark-factory/ tree, run a fresh subprocess, assert runs.workflow reflects the edit, assert a SHA-256 digest of src/dark_factory/**/*.py is unchanged."

requirements-completed: [CFG-02, CFG-03, CFG-04, CFG-05]

coverage:
  - id: D1
    description: "_run_current_role invokes every configured before action name ahead of the worker call and every after name behind the lease-loss check, through action_registry.get(name)(ActionContext(...)), outside the mutation transaction, with no role-name branch; a newly-registered action is usable from config with zero orchestrator change (CFG-04 runtime)"
    requirement: CFG-04
    verification:
      - kind: unit
        ref: "grep: `action_registry.get(` present in _run_current_role; the two _run_hooks calls bracket the worker call, not the apply_transition block"
        status: pass
      - kind: unit
        ref: "uv run pytest -m unit tests/unit/test_single_mutation_path.py tests/unit/test_no_role_name_literal.py -> 4 passed (the new _role_definition / hook loop adds no lifecycle write and no role literal)"
        status: pass
      - kind: db
        ref: "tests/db/test_role_hooks_invoked.py::test_before_then_worker_then_after / test_two_roles_get_an_identical_context_remainder / test_a_newly_registered_action_runs / test_legacy_bare_string_snapshot_invokes_no_hooks"
        status: unknown
    human_judgment: true
    rationale: "The static half (invocation-site placement, no-role-literal guard, one-mutation-path guard, mypy --strict, ruff) is proven here. The db-tier behavioural proofs (ordering, identical ActionContext remainder, new-action-from-config) need a real PostgreSQL 17: the executor sandbox has no Docker, no local initdb, no DARK_FACTORY_TEST_DATABASE_URL, and .env is behind a secret-read guard. The module imports cleanly under `pytest --collect-only` (4 tests). Verifier must run it against the real Neon DB."
  - id: D2
    description: "Editing a .dark-factory/roles/*.yaml field (after / instructions / worker) changes a fresh run's persisted runs.workflow snapshot with no .py change under src/dark_factory; the instruction Markdown bytes are inlined verbatim into roles[i].instruction_text (CFG-02, CFG-03, SC2)"
    requirement: CFG-02
    verification:
      - kind: integration
        ref: "tests/integration/test_role_yaml_drives_behaviour.py::test_editing_the_after_list_changes_the_persisted_role_snapshot / test_editing_the_instructions_path_inlines_the_new_bytes_verbatim / test_editing_the_worker_changes_which_worker_the_run_dispatches"
        status: unknown
    human_judgment: true
    rationale: "Each case drives a real `python -m dark_factory run` subprocess against a tmp .dark-factory/ tree and a real PostgreSQL to read back runs.workflow -- not executable in the sandbox (no DB backend). The module imports cleanly under `pytest --collect-only` (3 tests). The loader-side inlining is already unit-proven in 03-02. Verifier must run this module against the real DB."
  - id: D3
    description: "The full effective-config snapshot survives a create_run -> load_run_state round trip: RunState.workflow deep-equals redact(snapshot) including the ordered roles list and each instruction_text; a legacy {'roles': ['BA']} snapshot still round-trips and still builds a working pipeline (CFG-05)"
    requirement: CFG-05
    verification:
      - kind: db
        ref: "tests/db/test_snapshot_roundtrip.py::test_full_effective_config_snapshot_roundtrips_deep_equal / test_legacy_bare_string_snapshot_roundtrips_and_still_builds_a_pipeline"
        status: unknown
    human_judgment: true
    rationale: "create_run + load_run_state both need a real PostgreSQL (JSONB round trip); not executable in the sandbox. The module imports cleanly under `pytest --collect-only` (2 tests). Verifier must run it against the real DB."
  - id: D4
    description: "A run paused on a NEEDS_INPUT script, whose .dark-factory.yaml workflow.roles is reordered during the pause, resumes from a brand-new process executing the run-creation snapshot role order (BA -> QA -> COMPLETED), not the edited [QA, BA] order; same run id, no new runs row; resume / drive call load_effective_config zero times (CFG-05, SC3)"
    requirement: CFG-05
    verification:
      - kind: integration
        ref: "tests/integration/test_snapshot_survives_edit.py::test_resume_follows_the_creation_snapshot_not_the_edited_file"
        status: unknown
      - kind: unit
        ref: "tests/integration/test_snapshot_survives_edit.py::test_the_resume_path_can_never_reach_the_config_loader (reuses tests.unit.test_orchestrator_no_live_config_read._transitive_closure / _loader_hits over dark_factory.orchestrator.runner + answers)"
        status: pass
    human_judgment: true
    rationale: "The import-graph half (no orchestrator/answers path can reach dark_factory.config.loader) is proven here -- it runs as a pure static walk. The end-to-end subprocess pause/edit/resume half needs a real PostgreSQL; not executable in the sandbox. Module imports cleanly under `pytest --collect-only` (2 tests). Verifier must run the subprocess proof against the real DB."
  - id: D5
    description: "The Phase 3 acceptance gate maps exactly SC1-SC4 and exactly ORCH-02/ORCH-03/CFG-01..CFG-05/WORK-02 to present, non-empty, def-test_-carrying proof files; _VALIDATION_PROOF_FILES is drift-guarded against 03-VALIDATION.md; the file contains no opt-out call (grep = 0). COVERAGE.md records the no-external-API declaration."
    requirement: CFG-04
    verification:
      - kind: other
        ref: "manual gate-logic check: all 13 mapped proof files exist + contain `def test_`; set(SUCCESS_CRITERIA)==_PHASE_3_CRITERIA; set(REQUIREMENTS)==_PHASE_3_REQUIREMENT_IDS; _VALIDATION_PROOF_FILES - _all_mapped_paths() == set()"
        status: pass
      - kind: other
        ref: "grep -c 'pytest\\.skip\\|skipif' tests/integration/test_phase3_acceptance.py -> 0; test -s .planning/phases/03-configuration-driven-pipeline/COVERAGE.md -> non-empty (1 line)"
        status: pass
      - kind: integration
        ref: "uv run pytest -q tests/integration/test_phase3_acceptance.py (16 tests)"
        status: unknown
    human_judgment: true
    rationale: "The gate logic is proven by a direct import-and-check of its own SUCCESS_CRITERIA / REQUIREMENTS / _VALIDATION_PROOF_FILES structures (all assertions pass) plus the grep and `test -s` guards. Running it *as pytest* triggers the autouse _schema_at_head PostgreSQL ladder because the module is integration-marked, so it was not executed in the sandbox. It collects cleanly (16 tests). Verifier runs it against the real DB."

duration: 32min
completed: 2026-09-10
status: complete
---

# Phase 3 Plan 04: before/after hooks fire, role YAML drives behaviour, snapshot survives an edit, the acceptance gate Summary

**`_run_current_role` now invokes each role's configured `before` / `after` action names through the `ActionRegistry` around the worker call and outside the mutation transaction (CFG-04 runtime), with the four widening proofs -- role-YAML-drives-behaviour (SC2), the full-snapshot round trip (CFG-05), snapshot-survives-a-config-edit-during-a-pause (SC3), and the Phase 3 acceptance gate -- plus the `COVERAGE.md` no-external-API declaration. Phase 3 planning is closed.**

## Performance

- **Duration:** ~32 min
- **Tasks:** 3
- **Files modified:** 7 (6 created, 1 modified)
- **Commits:** 3 task commits (measured: `git rev-list --count 1b9612c..HEAD` == 3)

_plan_head_before: 1b9612c435af6417fc3e33d69a8d67ded760f340_

## Accomplishments

- **`orchestrator/runner.py` -- hook invocation.** New private `_role_definition(state, role) -> Mapping[str, Any]`: iterates `state.workflow["roles"]`, matching on the entry's `name` (dict shape) or the bare string itself (legacy shape); a legacy entry yields `{"name": role, "before": [], "after": []}`; a not-found role raises `LookupError` (unreachable -- `current_node` already validated it). In `_run_current_role`, a nested `_run_hooks(hook_phase: Literal["before", "after"])` closure builds a fresh `ActionContext(run_id, role=node.name, worker=node.worker, attempt=<from _build_context>, phase=hook_phase, task=<context task dict>, answer=state.pending_answer, role_definition=dict(role_def))` for each name in `role_def.get(hook_phase, [])` and calls `action_registry.get(name)(ctx)`. `_run_hooks("before")` fires right after `context = _build_context(...)`, ahead of the execute-vs-resume branch; `_run_hooks("after")` fires right after the `lease.lease_lost.is_set()` check, before `signal_from_result(result)`. Both are outside `with session.begin()`; the `apply_transition` block is byte-for-byte unchanged. No branch on `node.name` anywhere.
- **`action_registry` parameter** added keyword-only to `advance`, `drive`, `_advance_once`, `_run_current_role`, defaulting to `dark_factory.actions.default_registry` (imported as `action_default_registry` to avoid colliding with the worker `default_registry`), threaded through exactly the way `registry: WorkerRegistry` already is.
- **CFG-04 proof** (`tests/db/test_role_hooks_invoked.py`, `@pytest.mark.db`): a `_RecordingWorker` + recording actions on a fresh `ActionRegistry` prove `before -> worker -> after` order; a two-role snapshot naming the same action proves the non-role `ActionContext` remainder is identical across roles (no per-role branch); a brand-new `custom_hook` referenced from a role's `after` runs with zero runner change; a legacy `{"roles": ["BA"]}` snapshot invokes no hooks and still drives to COMPLETED.
- **CFG-05 round-trip** (`tests/db/test_snapshot_roundtrip.py`, `@pytest.mark.db`): `create_run(workflow=<real repo-root snapshot>)` -> `load_run_state` -> `RunState.workflow` deep-equals `redact(snapshot, known_secrets=fake_settings.known_secret_values())`, per-role `instruction_text` / `before` / `after` and the `repository` / `quality_gate` / `retry` / `publishing` blocks checked explicitly; a legacy bare-string snapshot round-trips and `pipeline_from_snapshot` still yields a 1-node `fake` pipeline.
- **SC2 role-YAML-drives-behaviour** (`tests/integration/test_role_yaml_drives_behaviour.py`, `@pytest.mark.integration`): rewrites only `BA.yaml` in a tmp `.dark-factory/` tree between subprocess runs -- an edited `after:` list, an edited `instructions:` path (new file bytes inlined verbatim into `roles[0]["instruction_text"]`), and `worker: copilot` (run created, `roles[0]["worker"] == "copilot"` persisted, dispatch then fails with the `NotImplementedError` naming Phase 8) -- with a SHA-256 digest of every `src/dark_factory/**/*.py` unchanged across all edits.
- **SC3 snapshot-survives-edit** (`tests/integration/test_snapshot_survives_edit.py`, `@pytest.mark.integration`): pause a `[BA, QA]` run `WAITING_HUMAN` on a `NEEDS_INPUT` script, rewrite `.dark-factory.yaml` to `[QA, BA]`, `resume <id> --answer` from a fresh process -> transition lines are `["BA -> QA", "QA -> COMPLETED"]` (the creation-snapshot order; the edited file would have produced the single `BA -> COMPLETED`), same run id, `runs` count grew by exactly one. A second test reuses `tests.unit.test_orchestrator_no_live_config_read._transitive_closure` / `_loader_hits` to assert `dark_factory.orchestrator.runner` and `.answers` cannot transitively import `dark_factory.config.loader`.
- **Phase 3 acceptance gate** (`tests/integration/test_phase3_acceptance.py`): a sibling of `test_phase2_acceptance.py`. `SUCCESS_CRITERIA` maps `SC1..SC4` (ROADMAP text) and `REQUIREMENTS` maps the eight ids (REQUIREMENTS.md text) to proof-file tuples; `_assert_proofs_exist` fails (never opts out) on a missing / empty / `def test_`-less proof; `test_every_phase_3_*_is_mapped` assert the exact key sets; `_VALIDATION_PROOF_FILES` (13 files) is drift-guarded against `03-VALIDATION.md`. `grep -c 'pytest\.skip\|skipif'` -> 0.
- **`COVERAGE.md`** written at `.planning/phases/03-configuration-driven-pipeline/COVERAGE.md` -- the single-line no-external-API declaration.

## `_run_current_role` hook-invocation shape (for phase-04)

```
node = current_node(pipeline, state.current_role)
worker = registry.get(node.worker)
context = _build_context(run_id, state, node)
role_def = _role_definition(state, node.name)          # data lookup, no role branch
_run_hooks("before")                                   # action_registry.get(name)(ActionContext(phase="before", ...))
result = worker.resume(...) | worker.execute(...)      # unchanged
if lease.lease_lost.is_set(): raise LeaseLost(...)     # unchanged
_run_hooks("after")                                    # action_registry.get(name)(ActionContext(phase="after", ...))
signal = signal_from_result(result)                    # unchanged
... apply_transition block ...                         # unchanged, inside `with session.begin()`
```

`_role_definition` legacy fallback: a bare-string `roles` entry (`"BA"`) resolves to `{"name": "BA", "before": [], "after": []}`, so `_run_hooks` iterates nothing -- every Phase 1 / Phase 2 in-process test that passes `DEFAULT_TEST_SNAPSHOT` is unaffected.

## Acceptance-gate maps

**Criterion -> proof:**
- SC1 -> `test_config_drives_pipeline.py`, `test_no_role_name_literal.py`
- SC2 -> `test_role_yaml_drives_behaviour.py`, `test_snapshot_roundtrip.py`
- SC3 -> `test_snapshot_survives_edit.py`, `test_orchestrator_no_live_config_read.py`
- SC4 -> `test_bad_config_no_orphan_run.py`, `test_config_error_exit_code.py`, `test_role_hooks_invoked.py`

**Requirement -> proof:**
- ORCH-02 -> `test_config_drives_pipeline.py`, `test_pipeline_from_snapshot.py`
- ORCH-03 -> `test_config_drives_pipeline.py`, `test_no_role_name_literal.py`
- CFG-01 -> `test_repo_config_schema.py`, `test_config_error_exit_code.py`
- CFG-02 -> `test_role_yaml_drives_behaviour.py`
- CFG-03 -> `test_role_yaml_drives_behaviour.py`, `test_repo_config_schema.py`
- CFG-04 -> `test_action_registry.py`, `test_role_hooks_invoked.py`
- CFG-05 -> `test_snapshot_roundtrip.py`, `test_snapshot_survives_edit.py`
- WORK-02 -> `test_worker_registry_names.py`

## Task Commits

1. **Task 1: invoke before/after actions via ActionRegistry around the worker call** -- `a4fe72e` (feat)
2. **Task 2: SC2 role-YAML-drives-behaviour, snapshot round-trip, SC3 survives-edit** -- `8a4cca8` (test)
3. **Task 3: Phase 3 acceptance gate + COVERAGE.md no-external-API declaration** -- `7da8d17` (test)

**Plan metadata:** _(next commit)_ (docs: complete plan)

## Files Created/Modified

See `key-files` frontmatter. Load-bearing:
- `src/dark_factory/orchestrator/runner.py` -- `_role_definition`, the `_run_hooks` before/after loops, the `action_registry` parameter on `advance` / `drive` / `_advance_once` / `_run_current_role`.
- `tests/db/test_role_hooks_invoked.py`, `tests/db/test_snapshot_roundtrip.py` -- CFG-04 / CFG-05 db proofs.
- `tests/integration/test_role_yaml_drives_behaviour.py`, `tests/integration/test_snapshot_survives_edit.py` -- SC2 / SC3 integration proofs.
- `tests/integration/test_phase3_acceptance.py` -- the Phase 3 acceptance gate.
- `.planning/phases/03-configuration-driven-pipeline/COVERAGE.md` -- the no-external-API declaration.

## Decisions Made

See `key-decisions` frontmatter. In brief: the before-loop sits ahead of the execute-vs-resume branch and the after-loop behind the lease-loss check, both outside the transaction; a lost lease raises `LeaseLost` before the after-hooks; one `_run_hooks(Literal["before","after"])` closure keeps `ActionContext` construction in one place and mypy-strict on `phase`; `_role_definition` synthesizes an empty-hook dict for the legacy shape; the acceptance gate maps `test_role_hooks_invoked.py` to SC4 per the plan (creation-time vs execution-time split); `COVERAGE.md` already held the exact plan line as a stub and was committed as-is.

## Deviations from Plan

None - plan executed exactly as written. Task 1's `action` text prescribed threading `action_registry` through `advance` / `drive` / `_advance_once` / `_run_current_role` and the before/after loops around the worker call; done exactly. Task 2's three modules and Task 3's gate + `COVERAGE.md` match the plan's `<files>` and `<action>` verbatim.

## Issues Encountered

- **db / integration tiers not executed.** The `db` and `integration` tiers need a real PostgreSQL 17: the executor sandbox has no Docker, no local `initdb`, no `DARK_FACTORY_TEST_DATABASE_URL`, and `.env` is behind a secret-read guard (`conftest._select_rung()` -> `"none"` -> `pytest.UsageError`). This matches the Phase 1 / 02 / 03-01 / 03-02 / 03-03 precedent of deferring the real-DB run to `/gsd-verify-work`. Note the Phase 3 acceptance gate itself needs no DB, but running it *as pytest* trips the autouse `_schema_at_head` provisioning ladder because the module is `integration`-marked -- so its logic was verified by importing the module and checking its `SUCCESS_CRITERIA` / `REQUIREMENTS` / `_VALIDATION_PROOF_FILES` structures directly instead.
- **Evidence the change set is sound:**
  - `uv run pytest -m "unit or contract" -q` -> **242 passed** (unchanged from the 03-03 baseline -- the runner change adds no unit regressions).
  - `uv run pytest -m unit tests/unit/test_single_mutation_path.py tests/unit/test_no_role_name_literal.py tests/unit/test_orchestrator_no_live_config_read.py` -> **9 passed** (the hook loop constructs no lifecycle row and no role literal; the resume path still excludes the loader).
  - `uv run mypy src/dark_factory` -> **Success (45 source files)**.
  - `uv run ruff check .` -> **All checks passed**; `uv run ruff format --check .` -> **125 files already formatted**.
  - `uv run pytest --collect-only -q` -> **444 tests, 0 errors** (was 417; +27 = the 4+2+3+2+16 new test functions; every new db/integration module imports cleanly).
  - `grep -c 'pytest\.skip\|skipif' tests/integration/test_phase3_acceptance.py` -> **0**.
  - manual gate-logic check: all 13 mapped proof files exist and contain `def test_`; both exact-set assertions hold; `_VALIDATION_PROOF_FILES - _all_mapped_paths()` is empty.
- **Carried verification items for `/gsd-verify-work`** (run with the real `DATABASE_URL` / `.env` sourced):
  1. `set -a; . ./.env; set +a; uv run pytest -q` -- the whole Phase 1-3 suite green, zero skips added.
  2. `uv run pytest -q tests/db/test_role_hooks_invoked.py` -- CFG-04 hook ordering + new-action-from-config.
  3. `uv run pytest -q tests/db/test_snapshot_roundtrip.py` -- CFG-05 full-snapshot round trip.
  4. `uv run pytest -q tests/integration/test_role_yaml_drives_behaviour.py` -- SC2.
  5. `uv run pytest -q tests/integration/test_snapshot_survives_edit.py` -- SC3.
  6. `uv run pytest -q tests/integration/test_phase3_acceptance.py` -- the acceptance gate (16 tests).
  7. The real-Neon human walkthrough carried from Phase 1 / Phase 2 / 03-03 (edit `.dark-factory.yaml` / a role YAML in a real checkout, observe behaviour change with `git diff src/` empty).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 3 planning is closed** -- all four plans executed. `_run_current_role` now has a working before/after hook seam; phase-04 makes `prepare_role_context` / `store_role_artifacts` real (they are still no-ops), and the `ActionContext` already carries `run_id` / `role` / `worker` / `attempt` / `task` / `answer` / `role_definition` for them to consume.
- **Requirements:** CFG-02, CFG-03, CFG-04, CFG-05 completed here (the shared-ID gate the earlier plans deferred now closes). ORCH-02 / ORCH-03 (03-03), CFG-01 (03-02), WORK-02 (03-01) already complete.
- **No blockers.** Carried verification items listed above are the standard real-DB deferral.

## Self-Check: PASSED

---
*Phase: 03-configuration-driven-pipeline*
*Completed: 2026-09-10*
