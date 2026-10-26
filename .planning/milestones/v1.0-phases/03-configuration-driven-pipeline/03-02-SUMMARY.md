---
phase: 03-configuration-driven-pipeline
plan: 02
subsystem: infra
tags: [config, yaml, pydantic, pyyaml, snapshot, loader]

requires:
  - phase: 03-configuration-driven-pipeline (03-01)
    provides: "WorkerRegistry.__contains__ + ActionRegistry.__contains__ membership seams; the actions default_registry; pipeline_from_snapshot tolerating the widened snapshot shape"
  - phase: 01-walking-skeleton-one-durable-run
    provides: "RunStatus vocabulary (the legal workflow.roles set); frozen extra=forbid pydantic v2 boundary-model convention; input/ phase-named-error + mapping-dispatch precedent"
provides:
  - "config/repo_config.py — RepoConfig + WorkflowConfig / RepositoryConfig / QualityGateConfig / RetryConfig / PublishingConfig (frozen, extra=forbid, pydantic v2); the workflow.roles field_validator rejecting any non-RunStatus role value and naming the legal set"
  - "config/loader.py — ConfigError(ValueError), RolePermissions, RoleDefinition, _safe_load_mapping, load_effective_config(root, *, worker_registry, action_registry) -> one JSON-serialisable effective-config snapshot dict"
  - "the tracked example config set the project runs against: .dark-factory.yaml (workflow.roles [BA], worker fake), .dark-factory/roles/{BA,QA}.yaml, .dark-factory/instructions/{ba,qa}.md"
  - ".gitignore line .dark-factory/runs/ (config set stays tracked)"
  - "tests/conftest.py fixtures: config_root / config_root_factory (tmp_path .dark-factory/ builder, requestable workflow.roles order) + repo_config_snapshot (real repo-root snapshot)"
  - "pyyaml>=6,<7 runtime dep + types-PyYAML>=6,<7 dev stub"
affects: [03-03 orchestrator wiring, 03-04 acceptance gate]

actuals:
  tokens: 11000
  tasks: 2
  commits: 3

tech-stack:
  added: ["pyyaml>=6,<7", "types-PyYAML>=6,<7 (dev)"]
  patterns:
    - "Repo config is validated as if external: every model frozen + extra=forbid; a typo'd key is a load-time error, not a silently-dropped snapshot field"
    - "load_effective_config is a pure read that raises ConfigError — no Session, no runs row, no lock; an interrupted or parallel load leaves nothing partial"
    - "worker / before / after names from config validated by membership (name in registry), never registry.get(name) — no getattr / importlib surface"
    - "instruction path = (role_yaml.parent / rd.instructions).resolve(); must .is_file() AND be under root.resolve() (no .. escape); inlined text capped at 64 KiB"
    - "config/ is import-isolated from config/settings.py so a repo-config value can never enter Settings.known_secret_values()"

key-files:
  created:
    - src/dark_factory/config/repo_config.py
    - src/dark_factory/config/loader.py
    - .dark-factory.yaml
    - .dark-factory/roles/BA.yaml
    - .dark-factory/roles/QA.yaml
    - .dark-factory/instructions/ba.md
    - .dark-factory/instructions/qa.md
    - tests/unit/test_repo_config_schema.py
    - tests/unit/test_config_module_isolation.py
  modified:
    - pyproject.toml
    - uv.lock
    - .gitignore
    - tests/conftest.py

key-decisions:
  - "Task 1 (PyYAML legitimacy): APPROVED at 03-02 checkpoint 1 (blocking-human package-legitimacy gate). Proceeded with uv add pyyaml>=6,<7."
  - "Task 2 (snapshot storage + schema key names): recommended. Reuse the existing runs.workflow JSONB column — NO Alembic revision 0004, NO config_snapshot column, NO models.py / RunState / load_run_state change. RESEARCH key names verbatim. workflow.roles entries are RunStatus values (BA, ARCHITECTURE, ...), NOT human names — the example .dark-factory.yaml shows ARCHITECTURE-style values, intended."
  - "types-PyYAML added to the dev group: PyYAML 6.x ships no py.typed, so mypy --strict needs the typeshed stub (RESEARCH's 'inline type hints' claim was wrong). Runtime dep is pyyaml only."
  - "loader.py uses Path.is_relative_to(root) for the traversal check (Python 3.12) instead of a try/except relative_to."

patterns-established:
  - "The .dark-factory.yaml / role-YAML key names are now a published contract (see below); 03-03 and 03-04 read them as settled."
  - "config_root_factory writes BOTH BA and QA role files regardless of the requested workflow.roles, so any permutation of [BA, QA] resolves for the 03-03 reorder proof."

requirements-completed: [CFG-01, CFG-02, CFG-03]

coverage:
  - id: D1
    description: ".dark-factory.yaml parses with yaml.safe_load into a frozen extra=forbid RepoConfig carrying version, repository.base_branch, workflow.roles, roles_dir, quality_gate.commands, retry.*_max_iterations, publishing.create_pr (CFG-01)"
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_repo_config_rejects_an_unknown_key"
        status: pass
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_valid_repo_config_round_trips_to_a_plain_dict"
        status: pass
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_loader_only_ever_calls_yaml_safe_load"
        status: pass
    human_judgment: false
  - id: D2
    description: "A non-RunStatus workflow.roles entry ('Architect', a typo, CREATED/COMPLETED) is a load-time validation error naming the legal set — not a bare ValueError deep in transition() (CFG-01, RESEARCH Pitfall 1)"
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_non_runstatus_role_name_is_rejected_naming_the_legal_set[Architect|bogus|CREATED|COMPLETED]"
        status: pass
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_empty_roles_list_is_rejected"
        status: pass
    human_judgment: false
  - id: D3
    description: "load_effective_config resolves each workflow.roles entry to <roles_dir>/<name>.yaml -> frozen RoleDefinition (name, worker, instructions, tools, permissions.write_scope, before, after, outputs, examples); reads the instruction Markdown UTF-8, asserts its resolved path is under the repo root and .is_file(), caps it at 64 KiB, inlines the text; returns one JSON-serialisable snapshot dict; opens no Session (CFG-02, CFG-03, CFG-05)"
    requirement: CFG-02
    verification:
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py::test_role_definition_rejects_an_unknown_key"
        status: pass
      - kind: other
        ref: "uv run python -c '...load_effective_config(repo_root); assert roles[0].name==BA, worker==fake, instruction_text non-empty, top-level keys present' -> prints ok"
        status: pass
      - kind: integration
        ref: "03-04 acceptance gate (test_snapshot_survives_edit / test_role_yaml_drives_behaviour) — not yet written"
        status: unknown
    human_judgment: true
    rationale: "The schema + one-shot resolution is proven by unit tests and the repo-root smoke check, but CFG-02/CFG-03's full contract ('editing .dark-factory/roles/*.yaml changes what executes', snapshot survives a .dark-factory.yaml edit on resume) is only closed once 03-03 wires the loader into start_run and 03-04's acceptance gate runs. CFG-02/CFG-03 are shared with 03-04 (its frontmatter requirements) and stay Pending in REQUIREMENTS.md until then."
  - id: D4
    description: "worker / before / after names in a role YAML are validated by membership on the 03-01 allowlist registries; an unregistered name raises ConfigError; name != workflow.roles entry raises ConfigError (CFG-02/CFG-03, threat T-03-02)"
    requirement: CFG-03
    verification:
      - kind: unit
        ref: "tests/unit/test_config_module_isolation.py (import-isolation guard, T-03-04) + test_repo_config_schema.py (yaml.safe_load-only AST guard, T-03-01)"
        status: pass
      - kind: integration
        ref: "03-03 test_bad_config_no_orphan_run.py (unknown worker/action -> ConfigError, no runs row) — not yet written"
        status: unknown
    human_judgment: true
    rationale: "The membership-validation branches exist and are unit-exercised through _safe_load_mapping and the schema tests, but the 'ConfigError at run creation, non-zero exit, no runs row' end-to-end proof belongs to 03-03/03-04 which have no SUMMARY yet."
  - id: D5
    description: "The repo ships a tracked, resolvable .dark-factory.yaml + BA/QA role YAML + instruction Markdown (workflow.roles [BA], worker fake); .dark-factory/runs/ is git-ignored; .dark-factory.yaml / roles/ / instructions/ stay tracked source"
    requirement: CFG-01
    verification:
      - kind: other
        ref: "grep -qx '.dark-factory/runs/' .gitignore && ! grep -Eq '^\\.dark-factory/?$|^\\.dark-factory\\.yaml$' .gitignore"
        status: pass
      - kind: other
        ref: "git ls-files .dark-factory.yaml .dark-factory/roles .dark-factory/instructions — all tracked"
        status: pass
    human_judgment: false
  - id: D6
    description: "config/repo_config.py and config/loader.py import nothing from config/settings.py and vice versa (RESEARCH Pitfall 6 — a repo-config field must never enter Settings.known_secret_values())"
    requirement: CFG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_config_module_isolation.py::test_repo_config_does_not_import_settings / test_loader_does_not_import_settings / test_settings_does_not_import_repo_config_or_loader / test_the_import_scan_actually_resolves_imports"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-09-10
status: complete
---

# Phase 3 Plan 02: The .dark-factory.yaml schema and load_effective_config Summary

**Pydantic v2 `.dark-factory.yaml` / role-YAML schema plus `load_effective_config` — a pure `yaml.safe_load` read that resolves repo config + role YAML + instruction Markdown into one JSON-serialisable effective-config snapshot, raising `ConfigError` on any bad role/worker/action name, escaping/oversized instruction file, or unknown key; ships the tracked example config set the project runs against.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-10T18:54:04Z
- **Completed:** 2026-09-10T18:59:22Z
- **Tasks:** 2 executed (checkpoint Tasks 1 & 2 were pre-resolved by the human before this continuation agent ran)
- **Files modified:** 13 (9 created, 4 modified)

## Checkpoint Resolutions (recorded verbatim for 03-03 / 03-04)

**Task 1 — PyYAML legitimacy: APPROVED.** PyYAML dependency: human-approved at 03-02 checkpoint 1 (blocking-human package-legitimacy gate). PyYAML 6.x is the standard `import yaml` library (PyPI, ~19 years old, source github.com/yaml/pyyaml, MIT, no postinstall scripts; CLAUDE.md-pinned at 6.0.3). Added as `pyyaml>=6,<7` in Task 3.

**Task 2 — Snapshot storage + schema key names: `recommended`.**
- **(A) Snapshot storage:** reuse the existing `runs.workflow` JSONB column. NO Alembic revision, NO new `config_snapshot` column, NO `models.py` / `RunState` / `load_run_state` schema change. The column is already `redact()`-ed on write and loaded on every resume into `RunState.workflow`; its meaning widens from `{"roles": [...]}` to the full effective-config snapshot. 03-03 updates the `models.py::Run.workflow` / `repositories.py::load_run_state` docstrings when it wires the loader.
- **(B) Schema key names — the published contract:**
  - Top level: `version`, `repository.base_branch`, `workflow.roles`, `roles_dir` (default `.dark-factory/roles`), `quality_gate.commands`, `retry.qa_developer_max_iterations` / `retry.quality_gate_max_iterations`, `publishing.create_pr`.
  - Role YAML: `name`, `worker`, `instructions` (path relative to the role YAML's own directory), `tools`, `permissions.write_scope`, `before`, `after`, `outputs`, `examples`.
  - `workflow.roles` entries are **`RunStatus` values** (`BA`, `ARCHITECTURE`, `DEVELOPMENT`, `QA`, `VERIFYING`, `PUBLISHING`), NOT human names. The example `.dark-factory.yaml` ships `roles: [BA]`; a multi-role file would show `ARCHITECTURE`, not `Architect` — intended. This keeps `transition()` / `lifecycle.py` / `answers.py` untouched (`RunStatus(role_name)` works directly).

## Effective-config snapshot dict shape (persisted in `runs.workflow`)

```
{
  "version": <int>,
  "roles": [                              # ordered — pipeline_from_snapshot reads this
    {
      "name": "BA",
      "worker": "fake",
      "instructions_path": ".dark-factory/instructions/ba.md",   # str, relative to repo root
      "instruction_text": "<inlined UTF-8 contents, <= 64 KiB>",
      "tools": [...],
      "permissions": {"write_scope": [...]},                     # model_dump(mode="json")
      "before": [...], "after": [...],
      "outputs": [...], "examples": [...]
    }
  ],
  "repository":   {"base_branch": "main"},
  "quality_gate": {"commands": [...]},
  "retry":        {"qa_developer_max_iterations": 3, "quality_gate_max_iterations": 2},
  "publishing":   {"create_pr": true}
}
```

## Final `.dark-factory.yaml` key list

`version`, `repository:` (`base_branch`), `workflow:` (`roles`), `roles_dir`, `quality_gate:` (`commands`), `retry:` (`qa_developer_max_iterations`, `quality_gate_max_iterations`), `publishing:` (`create_pr`).

## Final role-YAML key list (`.dark-factory/roles/*.yaml`)

`name`, `worker`, `instructions`, `tools`, `permissions:` (`write_scope`), `before`, `after`, `outputs`, `examples`.

## Revision 0004

**Not created.** Task 2 chose `recommended` (reuse `runs.workflow`). No Alembic work in this plan; no schema change of any kind.

## Accomplishments

- `config/repo_config.py` — `RepoConfig` + five frozen `extra="forbid"` sub-models. `WorkflowConfig.roles` is `Field(min_length=1)` with a `@field_validator("roles") @classmethod` that rejects any entry not in `frozenset(RunStatus) - {CREATED, COMPLETED, WAITING_HUMAN, FAILED}` and names the sorted legal set in the message. Imports `RunStatus` only; nothing from `config/settings.py`.
- `config/loader.py` — `ConfigError(ValueError)` (docstring: raised in `start_run` before `create_run` -> CLI exit 2, no `runs` row); `RolePermissions`, `RoleDefinition` (all nine fields); `_MAX_INSTRUCTION_BYTES = 64 * 1024`; `_safe_load_mapping` (`yaml.safe_load` only, `yaml.YAMLError` -> `ConfigError`, non-`dict` -> `ConfigError`); `load_effective_config(root, *, worker_registry, action_registry) -> dict` doing the seven resolution steps, membership-validating worker + before/after names, resolving/bounding the instruction path under `root.resolve()`, and returning the snapshot via `model_dump(mode="json")` on every nested model. Opens no `Session`.
- Tracked example config set: `.dark-factory.yaml` (`workflow.roles: [BA]`, `worker: fake`), `.dark-factory/roles/{BA,QA}.yaml`, `.dark-factory/instructions/{ba,qa}.md`. QA is deliberately not in `workflow.roles` — it exists for the 03-03 reorder/shorten proof.
- `.gitignore` += `.dark-factory/runs/` (only that line; `.dark-factory.yaml` / `roles/` / `instructions/` stay tracked).
- `tests/conftest.py` — `config_root` / `config_root_factory` (tmp_path `.dark-factory/` builder, `roles` order requestable, writes both BA+QA role files) and `repo_config_snapshot` (loads the real repo-root config). Not wired into `advance()` / `start_run`.
- Two unit proof files: `test_repo_config_schema.py` (13 tests — `extra=forbid`, empty/scalar file rejection, empty roles list, non-`RunStatus` role rejection naming the set, `model_dump` round-trip, AST guard that the loader only ever calls `yaml.safe_load`) and `test_config_module_isolation.py` (4 tests — bidirectional `config/` <-> `settings.py` import isolation + self-proving sanity).

## Task Commits

1. **Task 3a: PyYAML dependency** — `ba77680` (chore) — `pyproject.toml` + `uv.lock`; `pyyaml>=6,<7` runtime + `types-PyYAML>=6,<7` dev.
2. **Task 3b: schema + loader** — `1d0d16d` (feat) — `config/repo_config.py`, `config/loader.py`, `test_repo_config_schema.py`, `test_config_module_isolation.py`.
3. **Task 4: example config set + fixtures** — `53281d0` (feat) — `.dark-factory.yaml`, `.dark-factory/roles/{BA,QA}.yaml`, `.dark-factory/instructions/{ba,qa}.md`, `.gitignore`, `tests/conftest.py`.

**Plan metadata:** _(this commit)_ (docs: complete plan)

_plan_head_before: 4ace11247e021ee44ded12d8fc3caf8a38a7cdc4_
_commits: 3 (measured: git rev-list --count 4ace112..HEAD)_

## Files Created/Modified

- `src/dark_factory/config/repo_config.py` — `RepoConfig` + `WorkflowConfig` / `RepositoryConfig` / `QualityGateConfig` / `RetryConfig` / `PublishingConfig`; the `workflow.roles` `field_validator`.
- `src/dark_factory/config/loader.py` — `ConfigError`, `RolePermissions`, `RoleDefinition`, `_safe_load_mapping`, `load_effective_config`.
- `.dark-factory.yaml` — the tracked repo config the project runs against.
- `.dark-factory/roles/BA.yaml`, `.dark-factory/roles/QA.yaml` — role definitions (worker `fake`).
- `.dark-factory/instructions/ba.md`, `.dark-factory/instructions/qa.md` — role instruction Markdown, inlined into the snapshot.
- `.gitignore` — `+ .dark-factory/runs/`.
- `tests/conftest.py` — `config_root` / `config_root_factory` / `repo_config_snapshot` fixtures.
- `tests/unit/test_repo_config_schema.py`, `tests/unit/test_config_module_isolation.py` — the two unit proofs.
- `pyproject.toml`, `uv.lock` — `pyyaml` + `types-PyYAML`.

## Decisions Made

- **`types-PyYAML` added to the dev group.** The plan and 03-RESEARCH both stated "PyYAML 6.x ships inline type hints — `types-PyYAML` is not required". `mypy --strict` disproved this (`Library stubs not installed for "yaml"`). Added `types-PyYAML>=6,<7` to `[dependency-groups].dev`; the runtime dependency is still `pyyaml` alone. See Deviations.
- **`Path.is_relative_to(root)` for the traversal guard** (Python 3.12), rather than a `try/except relative_to`. Same effect, less code.
- **`config_root_factory` always writes both BA and QA role files**, regardless of the requested `workflow.roles`, so 03-03's `[QA, BA]` reorder test and 03-04's shorten test both resolve without a bespoke tree.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `types-PyYAML` dev stub so `mypy --strict` stays clean**
- **Found during:** Task 3
- **Issue:** The plan's action text says "PyYAML 6.x ships inline type hints — `types-PyYAML` is not required for `mypy --strict`." It is not true for PyYAML 6.0.3: `uv run mypy src/dark_factory` failed with `src/dark_factory/config/loader.py: error: Library stubs not installed for "yaml" [import-untyped]`. The task's own `<verify>` block runs `mypy src/dark_factory` and fails on any `error:`.
- **Fix:** `uv add --dev "types-PyYAML>=6,<7"`. The runtime dependency list is unchanged (`pyyaml>=6,<7` only); the stub is dev-only, the canonical typeshed package, and was anticipated by name in the plan ("types-PyYAML is optional").
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Verification:** `uv run mypy src/dark_factory` -> `Success: no issues found in 45 source files`; `uv lock --check` -> exit 0.
- **Committed in:** `ba77680` (Task 3a commit)

**2. [Rule 3 - Blocking] Reworded the loader docstring so the `<verify>` YAML-safety grep passes**
- **Found during:** Task 3
- **Issue:** The plan's `<verify>` gate is `grep -v '^#' src/dark_factory/config/loader.py | grep -c 'yaml\.load(\|Loader=' | grep -qx 0`. The loader docstring originally contained the literal token `Loader=` (in prose explaining what is forbidden), so the grep counted 1 and the gate failed even though the code only ever calls `yaml.safe_load`.
- **Fix:** Reworded the docstring to "never the unsafe full loader nor an explicit unsafe loader argument" — no `yaml.load(` or `Loader=` literal anywhere in the file. The AST guard in `test_repo_config_schema.py` (checks actual `ast.Call` nodes, not text) independently confirms the code calls `yaml.safe_load` and never `yaml.load` / passes `Loader=`.
- **Files modified:** `src/dark_factory/config/loader.py`
- **Verification:** the grep now yields `0` (`GUARD PASS`); `test_loader_only_ever_calls_yaml_safe_load` passes.
- **Committed in:** `1d0d16d` (Task 3b commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking).
**Impact on plan:** No scope change. Both fixes keep the plan's own static-analysis / verify gates green; the schema, loader behaviour, and shipped contract match the plan and the Task 2 decision exactly.

## Issues Encountered

- **Full db/integration suite not executed.** Verification step 6 (`set -a; . ./.env; set +a; uv run pytest -q`) needs the Neon `DATABASE_URL` from `.env`; the executor sandbox's secret-read guard blocks reading `.env`, and there is no local Postgres / Docker / `DARK_FACTORY_TEST_DATABASE_URL`. Evidence the suite is unaffected: 228 unit tests pass (was 213; +15 new), 235 pass under `-m "unit or contract"`, all db/integration test modules import cleanly, `pytest --collect-only` collects 399 tests (was 384; +15) with zero errors, and this plan changes no code under `orchestrator/`, `persistence/`, `workflows/`, or `cli.py` — it only adds `config/`, example config data, two unit files, and three lazy conftest fixtures. This matches the Phase 1 / Phase 2 / 03-01 precedent of deferring the real-Neon run to `/gsd-verify-work`. Carried verification item for the verifier: run the full suite with the real `DATABASE_URL`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Ready for 03-03** (orchestrator wiring). `load_effective_config(Path.cwd(), worker_registry=..., action_registry=...)` is the call `start_run` makes before `create_run`; the returned dict goes straight to `create_run(workflow=snapshot)`. `ConfigError` is a `ValueError` subclass — add it to the `run` command's exit-2 guard. The snapshot's `roles` list is what `pipeline_from_snapshot` (03-01) already consumes. 03-03 also owns the `models.py::Run.workflow` / `repositories.py::load_run_state` docstring updates recording the column's widened meaning, and the two import-graph / no-role-literal guards.
- **Ready for 03-04** (acceptance gate). The `.dark-factory.yaml` / role-YAML key names above are the settled contract the 03-04 gate asserts against. `config_root_factory` supports a requestable `workflow.roles` order for the reorder/shorten proofs. CFG-02 / CFG-03 stay Pending in REQUIREMENTS.md until 03-04 closes them (they are in 03-04's frontmatter `requirements`).
- **Requirements:** CFG-01 marked complete (schema + the shipped tracked config set are wholly delivered here; not shared with a later plan). CFG-02 / CFG-03 contributed but left Pending — shared with 03-04.
- **No blockers.** One carried verification item: the full db/integration suite must be run against the real Neon database by `/gsd-verify-work`.

## Self-Check: PASSED

- All 9 created files present on disk (`config/repo_config.py`, `config/loader.py`, `.dark-factory.yaml`, `.dark-factory/roles/{BA,QA}.yaml`, `.dark-factory/instructions/{ba,qa}.md`, `test_repo_config_schema.py`, `test_config_module_isolation.py`).
- All 3 task commits present in history (`ba77680`, `1d0d16d`, `53281d0`); `git rev-list --count 4ace112..HEAD` == 3.
- `uv run pytest -m unit -q tests/unit/test_repo_config_schema.py tests/unit/test_config_module_isolation.py` — 15 passed.
- Full unit suite: 228 passed, 171 deselected. `-m "unit or contract"`: 235 passed.
- `grep -v '^#' src/dark_factory/config/loader.py | grep -c 'yaml\.load(\|Loader=' | grep -qx 0` — GUARD PASS.
- `uv run mypy src/dark_factory` — Success (45 source files). `uv run ruff check .` — All checks passed. `uv run ruff format --check src/dark_factory tests` — all formatted. `uv lock --check` — exit 0.
- `load_effective_config(Path('<repo root>'))` — resolves; `roles[0]` is `{name: BA, worker: fake}` with non-empty `instruction_text`; top-level keys `{version, roles, repository, quality_gate, retry, publishing}` present.
- `.gitignore` contains `.dark-factory/runs/` and no broader `.dark-factory` / `.dark-factory.yaml` ignore.
- Carried item (not a self-check failure): the db/integration suite was not *executed* — see "Issues Encountered".

---
*Phase: 03-configuration-driven-pipeline*
*Completed: 2026-09-10*
