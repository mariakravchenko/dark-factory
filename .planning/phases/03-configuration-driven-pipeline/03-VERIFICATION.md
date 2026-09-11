---
phase: 03-configuration-driven-pipeline
verified: 2026-09-10T00:00:00Z
status: passed
score: 4/4 must-haves verified, including real Neon end-to-end UAT
covered_files:
  - ".dark-factory.yaml"
  - ".dark-factory/roles/BA.yaml"
  - ".dark-factory/roles/QA.yaml"
  - ".planning/phases/03-configuration-driven-pipeline/03-01-PLAN.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-01-SUMMARY.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-02-PLAN.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-02-SUMMARY.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-03-PLAN.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-03-SUMMARY.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-04-PLAN.md"
  - ".planning/phases/03-configuration-driven-pipeline/03-04-SUMMARY.md"
  - "src/dark_factory/actions/__init__.py"
  - "src/dark_factory/actions/builtins.py"
  - "src/dark_factory/actions/context.py"
  - "src/dark_factory/actions/registry.py"
  - "src/dark_factory/cli.py"
  - "src/dark_factory/config/loader.py"
  - "src/dark_factory/config/repo_config.py"
  - "src/dark_factory/orchestrator/runner.py"
  - "src/dark_factory/persistence/mutations.py"
  - "src/dark_factory/persistence/repositories.py"
  - "src/dark_factory/workers/registry.py"
  - "src/dark_factory/workflows/pipeline.py"
covered_digest: "v1:sha256:4f720ada5b229ff67eed93511e5f606ae980967ba7fe0fa15a3b4cc75298f114"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "set -a; . ./.env; set +a; uv run pytest -q  — the whole Phase 1-3 suite against real Neon PostgreSQL 17"
    expected: "All db + integration tests pass; the ~15 mechanically-updated in-process start_run call sites still green with snapshot=DEFAULT_TEST_SNAPSHOT"
    why_human: "The sandbox has no Docker / local initdb / DARK_FACTORY_TEST_DATABASE_URL and .env is behind a secret-read guard; conftest raises pytest.UsageError. Confirmed here: `uv run pytest tests/db/test_snapshot_roundtrip.py` -> UsageError 'No PostgreSQL 17 is reachable'."
  - test: "uv run pytest -q tests/integration/test_config_drives_pipeline.py  (SC1 end-to-end)"
    expected: "test_run_resolves_pipeline_from_config emits CREATED->BA / BA->COMPLETED and persists the resolved snapshot; test_reorder_and_shorten_workflow_roles_changes_the_executed_pipeline shows [BA,QA] -> [QA,BA] -> [BA] each drive a different transition sequence with git diff --stat over orchestrator/ + workflows/ empty"
    why_human: "Needs a real dark-factory run subprocess against PostgreSQL. Structural half (pipeline_from_snapshot builds from snapshot, no DEFAULT_PIPELINE / no role-name literal in orchestrator, transition() walks N nodes) is verified here via unit tests + spot-checks."
  - test: "uv run pytest -q tests/integration/test_role_yaml_drives_behaviour.py  (SC2 end-to-end)"
    expected: "Editing BA.yaml after: / instructions: / worker: changes the next run's persisted runs.workflow snapshot; instruction bytes inlined verbatim; worker: copilot reaches dispatch and fails with the Phase 8 NotImplementedError; SHA-256 of src/dark_factory/**/*.py unchanged across every edit"
    why_human: "Needs a real run subprocess + PostgreSQL to read back runs.workflow. Loader-side resolution/inlining verified here against the real repo config."
  - test: "uv run pytest -q tests/integration/test_snapshot_survives_edit.py  (SC3 end-to-end)"
    expected: "Pause [BA,QA] on NEEDS_INPUT, reorder .dark-factory.yaml to [QA,BA], resume --answer from a fresh process -> transition lines continue BA->QA->COMPLETED (creation-snapshot order), same run id, exactly one runs row"
    why_human: "Needs subprocess pause/edit/resume against PostgreSQL. Structural half (test_the_resume_path_can_never_reach_the_config_loader) passes here as a pure import-graph walk."
  - test: "uv run pytest -q tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py  (SC4 no-orphan-run)"
    expected: "Each of 8 bad-config shapes raises ConfigError before create_run with the runs row count unchanged; a bad-config `dark-factory run` exits 2 with empty stdout line 1, stderr naming the offending file/field, runs count unchanged"
    why_human: "Needs PostgreSQL to count runs rows before/after. ConfigError is raised for unknown worker / action / role name / unknown key / empty / non-mapping YAML — verified here via direct load_effective_config + RepoConfig spot-checks; CLI maps ConfigError->Exit(2) before start_run (code inspection)."
  - test: "uv run pytest -q tests/db/test_role_hooks_invoked.py  (CFG-04 runtime)"
    expected: "before -> worker -> after invocation order; identical ActionContext remainder across two roles (no per-role branch); a newly-registered action referenced from a role's after: runs with zero orchestrator change; a legacy {roles:[BA]} snapshot invokes no hooks and still drives to COMPLETED"
    why_human: "Needs real commits against PostgreSQL. Invocation site verified by code inspection: _run_hooks('before')/('after') bracket the worker call in _run_current_role, outside `with session.begin()`, resolving names via action_registry.get(); action_registry threaded through advance/drive/_advance_once."
  - test: "uv run pytest -q tests/db/test_snapshot_roundtrip.py  (CFG-05 round-trip)"
    expected: "create_run -> load_run_state: RunState.workflow deep-equals redact(snapshot) incl. ordered roles + each instruction_text + repository/quality_gate/retry/publishing; a legacy {roles:[BA]} snapshot still round-trips and still builds a pipeline"
    why_human: "JSONB round trip needs PostgreSQL."
  - test: "Real-repo human walkthrough (carried from Phase 1/2/3-03): in a real checkout, edit .dark-factory.yaml workflow.roles and a .dark-factory/roles/*.yaml field, run `dark-factory run`, observe the executed pipeline / role behaviour change with `git diff src/` empty"
    expected: "Behaviour changes with no source edit; a config edit during a WAITING_HUMAN pause does not affect the resumed run"
    why_human: "End-user-observable CLI behaviour against a real database and repository."
advisory:
  - finding: "WR-01 (code review): roles_dir and the resolved role-YAML path are not contained against `..` / absolute-path traversal, unlike the sibling instructions: path which is checked with is_relative_to(root). A hostile .dark-factory.yaml roles_dir could point the loader at an arbitrary *.yaml outside the repo root."
    category: security
    reason: "Hardening gap, not a success-criterion break — no phase SC covers roles_dir containment; the review itself classifies it 'hardening gap, not an invariant break'. No failing test or reproducible exploit supplied. Fix: mirror the instruction-path is_relative_to(root) check for roles_dir and each role_path."
    evidence_status: "none provided"
  - finding: "WR-02 (code review): duplicate workflow.roles entries (roles: [BA, BA]) pass validation; pipeline_from_snapshot builds two identical nodes and the run spins on the first role until DriveLoopExhausted / ScriptExhaustedError."
    category: other
    reason: "Robustness defect on a malformed config, not a success-criterion break — SC1 concerns reorder/shorten of distinct roles. No failing test supplied (the integration suite that would exercise it did not run). Fix: reject duplicates in the WorkflowConfig.roles field_validator."
    evidence_status: "none provided"
  - finding: "WR-03 (code review): the instruction file is fully read into memory (read_text) before the 64 KiB cap is enforced, and the .encode('utf-8') round-trip on an already-decoded string can disagree with the on-disk byte count under Unicode normalisation."
    category: other
    reason: "Hardening gap — the 64 KiB cap still bounds the persisted snapshot row; a pre-read stat().st_size check would bound memory too. No exploit / failing test supplied."
    evidence_status: "none provided"
---

# Phase 3: Configuration-Driven Pipeline Verification Report

**Phase Goal:** The pipeline shape and every role's behaviour come from repository configuration rather than code, and the configuration a run resolves at creation is snapshotted so a later resume is deterministic.
**Verified:** 2026-09-10
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Phase 3 converts three hardcoded constants into configuration-resolved data:
the single-role `DEFAULT_PIPELINE` becomes an N-role sequence read from
`workflow.roles`; role behaviour hardcoded in `roles/registry.py::ba_role`
becomes per-role YAML + instruction Markdown; and the pipeline resolved
implicitly at import becomes an effective-config snapshot resolved once at run
creation and persisted to `runs.workflow`. Code inspection confirms every
mechanism is in place and wired; all runnable checks (242 unit/contract tests,
mypy --strict, ruff, ruff format, 444-test collection with 0 import errors,
targeted behavioural spot-checks) are green. The end-to-end behavioural proofs
that exercise a real `dark-factory run` against PostgreSQL could not execute in
this sandbox (no Docker / initdb / `DARK_FACTORY_TEST_DATABASE_URL`; `.env`
behind a secret-read guard) and are surfaced as human-verification items.

### Observable Truths

| # | Truth (ROADMAP Success Criteria) | Status | Evidence |
|---|----------------------------------|--------|----------|
| 1 | SC1 — Shortening or reordering `workflow.roles` in `.dark-factory.yaml` changes the executed pipeline with no Python change and no orchestrator edit | ✓ VERIFIED (mechanism); E2E proof → human | `runner.py` grep `DEFAULT_PIPELINE\|_workflow_snapshot` = 0; `_advance_once` builds `pipeline_from_snapshot(state.workflow)`; `start_run(*, snapshot)` required, no default; `cli.run()` resolves `load_effective_config(Path.cwd())`. `test_no_role_name_literal.py` (AST guard, no `RunStatus` role literal in `orchestrator/` or `workflows/pipeline.py`) PASSED; spot-check: `pipeline_from_snapshot` returns `[BA,QA]` vs `[QA,BA]` for reordered input; `test_pipeline_from_snapshot.py` + `test_lifecycle.py` N-node `transition()` walk PASSED. `test_config_drives_pipeline.py` (real subprocess, transition-sequence + git-diff guard) is substantive but NOT executed (no Postgres). |
| 2 | SC2 — A role's instructions, tools, permissions, before/after hooks, outputs and worker are read from `.dark-factory/` role YAML and instruction Markdown; editing those files changes behaviour without touching source | ✓ VERIFIED (mechanism); E2E proof → human | `load_effective_config` spot-checked against the real repo: `roles[0]` carries `name/worker/instructions_path/instruction_text/tools/permissions/before/after/outputs/examples`; loader re-reads YAML + Markdown from disk on every call (no caching). `RoleDefinition` frozen `extra="forbid"`; `test_repo_config_schema.py` PASSED. `.dark-factory/roles/{BA,QA}.yaml` + `instructions/{ba,qa}.md` tracked. `test_role_yaml_drives_behaviour.py` (edit `after:` / `instructions:` / `worker:`, fresh run, persisted snapshot reflects edit, `src/**/*.py` digest unchanged) substantive but NOT executed. |
| 3 | SC3 — Editing `.dark-factory.yaml` while a run is paused and then resuming executes the configuration snapshot resolved at run creation, not the edited file | ✓ VERIFIED (mechanism); E2E proof → human | `test_orchestrator_no_live_config_read.py` PASSED — transitive `dark_factory.*` import closure of `orchestrator.runner`, `orchestrator.answers`, `orchestrator.lifecycle`, `workflows.pipeline` excludes `dark_factory.config.loader`; the CLI's closure *does* include it (self-proving). `cli.resume()` never calls `load_effective_config`; `_advance_once` builds the pipeline from `state.workflow` only; grep confirms `runner.py` has no `config.loader` import. `test_snapshot_survives_edit.py` (subprocess pause → reorder file → resume from fresh process → creation-snapshot order wins) substantive but NOT executed. |
| 4 | SC4 — A before/after hook named in configuration resolves through the `ActionRegistry`, and an unknown action or worker name fails validation at run creation with a non-zero exit and no orphan run | ✓ VERIFIED (mechanism); no-orphan-run DB proof → human | `load_effective_config`: `rd.worker not in worker_registry` → `ConfigError`; `hook not in (*before,*after)` `not in action_registry` → `ConfigError`; `WorkflowConfig` `field_validator` rejects non-`RunStatus` role values. Spot-checks: `Architect` role rejected, empty `roles` rejected, unknown key rejected, `copilot` placeholder `.capabilities()` raises `NotImplementedError` naming Phase 8, `'nope' not in action_default_registry`. `cli.run()` maps `ConfigError` → `typer.Exit(2)` *before* `start_run`; `start_run` evaluates `snapshot` before `create_run`. `_run_current_role._run_hooks("before"/"after")` calls `action_registry.get(name)(ActionContext(...))` around the worker call, outside `with session.begin()`. `test_bad_config_no_orphan_run.py` (8 shapes, runs-count unchanged) + `test_config_error_exit_code.py` + `test_role_hooks_invoked.py` substantive but NOT executed. |

**Score:** 4/4 truths verified at the mechanism level (code inspection + runnable unit/contract tests + behavioural spot-checks). End-to-end DB/integration behavioural proofs are deferred to a real-Neon run — see Human Verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/actions/registry.py` | `ActionRegistry` (name→callable allowlist), `UnknownActionError(KeyError)`, `default_registry`, `__contains__` | ✓ VERIFIED | All present; `get()` raises `UnknownActionError`; imported by `config/loader.py` + `orchestrator/runner.py` |
| `src/dark_factory/actions/context.py` | frozen `extra="forbid"` `ActionContext`, 8 fields, `phase: Literal["before","after"]` | ✓ VERIFIED | Exact field set `run_id, role, worker, attempt, phase, task, answer, role_definition`; used in `_run_hooks` |
| `src/dark_factory/actions/builtins.py` | five `(ActionContext)->None` no-op built-ins | ✓ VERIFIED | `prepare_role_context, ensure_clean_worktree, collect_diff, store_role_artifacts, collect_test_results`; bodies `return None` |
| `src/dark_factory/actions/__init__.py` | registers the five built-ins at import | ✓ VERIFIED | 5 `default_registry.register(...)` calls; spot-check confirms membership |
| `src/dark_factory/workers/registry.py` | `WorkerRegistry.__contains__` + `_NotYetImplementedWorker` + claude-code/copilot/hermes placeholders | ✓ VERIFIED | `__contains__` present; placeholders raise `NotImplementedError` naming Phase 7 / 8 (spot-checked); `fake` still a shared singleton |
| `src/dark_factory/workflows/pipeline.py` | `pipeline_from_snapshot(snapshot)->Pipeline`; `DEFAULT_PIPELINE` demoted to fixture | ✓ VERIFIED | Accepts legacy bare-string + `{name,worker}` dict shapes; raises `KeyError` on missing `roles`; `DEFAULT_PIPELINE` docstring "test fixture only", still importable |
| `src/dark_factory/config/repo_config.py` | `RepoConfig` + 5 frozen `extra="forbid"` submodels + `workflow.roles` field_validator | ✓ VERIFIED | `min_length=1`; validator rejects non-`RunStatus` values naming the legal set; imports only `RunStatus`, nothing from `config.settings` |
| `src/dark_factory/config/loader.py` | `ConfigError(ValueError)`, `RoleDefinition`, `RolePermissions`, `_safe_load_mapping`, `load_effective_config` | ✓ VERIFIED | `yaml.safe_load` only (grep for `yaml.load(`/`Loader=` = 0); membership validation via `not in`; instruction path `is_relative_to(root)` + 64 KiB cap; opens no `Session`; returns JSON-serialisable dict (spot-checked against real repo) |
| `src/dark_factory/cli.py` | `run()` resolves `load_effective_config(Path.cwd())` before `start_run`, maps `ConfigError`→`Exit(2)` | ✓ VERIFIED | Pre-check present; `resume()` untouched (no config read); sole importer of `config.loader` |
| `src/dark_factory/orchestrator/runner.py` | required `snapshot`; `_workflow_snapshot`/`DEFAULT_PIPELINE` removed; `_role_definition`; `_run_hooks` before/after outside txn; `action_registry` threaded | ✓ VERIFIED | grep `DEFAULT_PIPELINE\|_workflow_snapshot` = 0; no `config.loader` import; `action_registry` on `advance`/`drive`/`_advance_once`/`_run_current_role`; hooks bracket the worker call, `apply_transition` block unchanged |
| `.dark-factory.yaml` + `.dark-factory/roles/{BA,QA}.yaml` + `instructions/{ba,qa}.md` | tracked, resolvable example set (`workflow.roles: [BA]`, worker `fake`) | ✓ VERIFIED | All present and tracked; `load_effective_config` resolves them; `.gitignore` ignores only `.dark-factory/runs/` |
| `tests/support/config.py` | `DEFAULT_TEST_SNAPSHOT = {"roles": ["BA"]}` | ✓ VERIFIED | Present with `__all__` |
| 16 phase test files (unit / db / integration + acceptance gate) | present, substantive, non-stub, `def test_` | ✓ VERIFIED (present + substantive); db/integration NOT executed | All 16 exist; inspected — real assertions, no skips; `test_phase3_acceptance.py` maps exactly SC1-SC4 + the 8 requirement ids with a `03-VALIDATION.md` drift guard; `grep pytest.skip\|skipif` = 0 |
| `COVERAGE.md` | single-line no-external-API declaration | ✓ VERIFIED | Present, one line |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `cli.py` | `config/loader.py` | `run()` → `load_effective_config(Path.cwd())`, catch `ConfigError` → `Exit(2)` | ✓ WIRED | Import + call present; only composition point |
| `config/loader.py` | `actions/registry.py` + `workers/registry.py` | `hook not in action_registry` / `rd.worker not in worker_registry` → `ConfigError` (membership, never `.get`) | ✓ WIRED | Both `not in` checks present |
| `config/loader.py` | `domain/status.py` | `RunStatus` supplies legal `workflow.roles` set | ✓ WIRED | `_LEGAL_ROLE_STATUSES = frozenset(RunStatus) - {CREATED,COMPLETED,WAITING_HUMAN,FAILED}` |
| `orchestrator/runner.py` | `workflows/pipeline.py` | `_advance_once`: `if pipeline is None: pipeline = pipeline_from_snapshot(state.workflow)` | ✓ WIRED | Present after the `load_run_state` / STOP_STATUSES early-return block |
| `orchestrator/runner.py` | `actions/registry.py` + `actions/context.py` | `_run_hooks` → `action_registry.get(name)(ActionContext(...))` around the worker call | ✓ WIRED | Both `before` and `after` loops present, outside `with session.begin()` |
| `orchestrator/runner.py` | `persistence/mutations.py` | `start_run` → `create_run(session, task=task, workflow=dict(snapshot))` | ✓ WIRED | Present; `redact()` at the single `create_run` call site scrubs the snapshot |
| `orchestrator/*` | `config/loader.py` | MUST NOT import | ✓ VERIFIED ABSENT | grep + `test_orchestrator_no_live_config_read.py` (PASSED) — transitive closure excludes `config.loader` |
| `.dark-factory/roles/BA.yaml` | `.dark-factory/instructions/ba.md` | `instructions:` resolved relative to role-YAML dir, contained under root, inlined | ✓ WIRED | Spot-check: `instruction_text` non-empty, `instructions_path` = `.dark-factory/instructions/ba.md` |

### Data-Flow Trace (Level 4)

| Rendered / persisted value | Source | Produces real data | Status |
|---------------------------|--------|--------------------|--------|
| `runs.workflow` snapshot at run creation | `cli.run()` → `load_effective_config(Path.cwd())` → `start_run(snapshot=...)` → `create_run(workflow=dict(snapshot))` | Yes — real `yaml.safe_load` of `.dark-factory.yaml` + role YAML + instruction Markdown read from cwd | ✓ FLOWING |
| pipeline executed on resume | `_advance_once` → `pipeline_from_snapshot(state.workflow)` ← `load_run_state` ← `runs.workflow` column | Yes — persisted column, never a live file | ✓ FLOWING |
| before/after hook callables | `_role_definition(state, role)` ← `state.workflow["roles"][i]["before"/"after"]` → `action_registry.get(name)` | Yes — names from the persisted snapshot, resolved through the allowlist | ✓ FLOWING |
| `instruction_text` in snapshot | `instr_path.read_text("utf-8")` in `load_effective_config` | Yes — verbatim file bytes (≤ 64 KiB) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `load_effective_config` resolves the shipped repo config | `python -c "load_effective_config(Path('<repo>'))"` | Returns dict with keys `version, roles, repository, quality_gate, retry, publishing`; `roles[0]` has all 10 keys, non-empty `instruction_text`, `before=[prepare_role_context]`, `after=[store_role_artifacts]` | ✓ PASS |
| `pipeline_from_snapshot` is order-sensitive | `python -c "pipeline_from_snapshot({'roles':[{'name':'BA'...},{'name':'QA'...}]})"` vs reversed | `[BA,QA]` vs `[QA,BA]`; legacy `{'roles':['BA']}` → 1 node worker `fake` | ✓ PASS |
| `RepoConfig` rejects bad `workflow.roles` | `RepoConfig.model_validate({'workflow':{'roles':['Architect']}})` / `[]` / extra key | All three raise `ValidationError` | ✓ PASS |
| Worker/action registries: membership without invoke; placeholder raises | `python -c` over `default_registry` | `claude-code/copilot/hermes/fake` ∈ registry; `bogus ∉`; `copilot.capabilities()` → `NotImplementedError('...Phase 8')`; 5 built-ins ∈ action registry; `nope ∉` | ✓ PASS |
| YAML safety | `grep -rn 'yaml.load\|Loader=' src/dark_factory/config/` | no matches | ✓ PASS |
| Orchestrator has no pipeline default / role literal | `grep 'DEFAULT_PIPELINE\|_workflow_snapshot'` + `grep -E '"(BA|ARCHITECTURE|...)"'` over `orchestrator/` + `workflows/pipeline.py` | both 0 matches | ✓ PASS |
| `runner.py` imports nothing from `config.loader` | AST import scan | `[]` | ✓ PASS |
| Unit + contract suite | `uv run pytest -m "unit or contract" -q` | 242 passed | ✓ PASS |
| Phase 3 unit proof files | `uv run pytest -m unit tests/unit/test_action_registry.py test_worker_registry_names.py test_pipeline_from_snapshot.py test_repo_config_schema.py test_config_module_isolation.py test_no_role_name_literal.py test_orchestrator_no_live_config_read.py` | 39 passed | ✓ PASS |
| Type / lint / format / collection | `mypy src/dark_factory` · `ruff check .` · `ruff format --check` · `pytest --collect-only` | Success (45 files) · clean · 118 formatted · 444 tests, 0 errors | ✓ PASS |
| db/integration tier reachability | `uv run pytest -q tests/db/test_snapshot_roundtrip.py` | `pytest.UsageError: No PostgreSQL 17 is reachable` | ? SKIP (no DB — routed to human) |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| ORCH-02 | 03-01, 03-03 | Orchestrator executes a configured ordered role sequence, not hardcoded calls | ✓ SATISFIED (mechanism) | `pipeline_from_snapshot`; `_advance_once` builds from `state.workflow`; `DEFAULT_PIPELINE` gone from `runner.py`; `test_pipeline_from_snapshot.py` PASSED. E2E → human. |
| ORCH-03 | 03-03 | Role pipeline defined in `workflow.roles`, shortened/reordered without orchestrator code change | ✓ SATISFIED (mechanism) | `test_no_role_name_literal.py` PASSED (AST guard); CLI resolves from cwd; spot-check shows order-sensitivity. E2E reorder proof → human. |
| CFG-01 | 03-02, 03-03 | Repo behaviour configured in `.dark-factory.yaml` (version, workflow.roles, base_branch, per-role files, quality_gate.commands, retry, publishing.create_pr) | ✓ SATISFIED | `RepoConfig` + 5 submodels, `extra="forbid"`, `yaml.safe_load` only; shipped `.dark-factory.yaml` carries the full key set; `test_repo_config_schema.py` PASSED; spot-checked. |
| CFG-02 | 03-02, 03-04 | Role behaviour in `.dark-factory/` files, editable without changing Python | ✓ SATISFIED (mechanism) | Loader reads role YAML + instruction MD fresh per call; tracked example set; `RoleDefinition` frozen. E2E edit-and-rerun proof → human. |
| CFG-03 | 03-02, 03-04 | Role definition fully config-driven — instructions, tools, permissions, before/after, outputs, worker | ✓ SATISFIED (mechanism) | Snapshot `roles[i]` carries all six + `worker` (spot-checked). Enforcement of `tools`/`permissions` is explicitly deferred to Phases 5/6 per plan assumptions; Phase 3 scope is "carried in config". |
| CFG-04 | 03-01, 03-04 | `ActionRegistry` exposes deterministic before/after actions referenced by config; accepts new actions without core changes | ✓ SATISFIED (mechanism) | `ActionRegistry` allowlist + 5 built-ins; `_run_hooks` invokes by name via `.get()` around the worker call, outside the txn; `test_action_registry.py` PASSED (incl. newly-registered action). Runtime ordering proof `test_role_hooks_invoked.py` → human. |
| CFG-05 | 03-03, 03-04 | Config resolved at run creation is snapshotted + persisted; resume deterministic even if `.dark-factory.yaml` changed | ✓ SATISFIED (mechanism) | Snapshot persisted to `runs.workflow` in `create_run`; `orchestrator/*` cannot import `config.loader` (`test_orchestrator_no_live_config_read.py` PASSED); `resume()` never resolves config. Round-trip + pause/edit/resume proofs → human. |
| WORK-02 | 03-01 | `WorkerRegistry` maps claude-code / copilot / hermes; worker creation centralized | ✓ SATISFIED | `__contains__` + 3 placeholder registrations; `test_worker_registry_names.py` PASSED; spot-checked (`NotImplementedError` names Phase 7/8); `test_no_worker_name_leak.py` still green. |

All 8 phase requirement IDs are declared across plan frontmatter (03-01: CFG-04, WORK-02, ORCH-02 · 03-02: CFG-01, CFG-02, CFG-03 · 03-03: ORCH-02, ORCH-03, CFG-01, CFG-05 · 03-04: CFG-02, CFG-03, CFG-04, CFG-05) and REQUIREMENTS.md maps exactly these 8 to Phase 3. **No orphaned requirements.**

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | `TODO`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` scan of all phase-modified `src/` files | ✓ none | Clean — no debt markers |
| `src/dark_factory/actions/builtins.py` | 34-58 | five `return None` bodies | ℹ️ Info (intended) | The five built-ins are deliberate no-ops in Phase 3; each docstring names the phase (4/5/9) it becomes real in. SC4 requires the runner to *invoke* a configured hook, which a raising stub would break. Not a stub in the disqualifying sense — the value does not flow to user-visible output. |

### Advisory (from code review — hardening gaps, not invariant breaks)

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | WR-01 — `roles_dir` / role-YAML path not contained against `..` / absolute traversal (the sibling `instructions:` path *is*) | security | No phase SC covers `roles_dir` containment; review classifies it a hardening gap; no failing test / exploit supplied |
| 2 | WR-02 — duplicate `workflow.roles` entries accepted; run spins until `DriveLoopExhausted` | other | Malformed-config robustness defect, not a reorder/shorten SC break; no failing test supplied |
| 3 | WR-03 — instruction file fully read before the 64 KiB cap; `.encode()` round-trip can disagree with on-disk bytes | other | Snapshot row is still bounded; memory bound is the gap; no exploit / failing test supplied |

Code review IN-01..IN-05 (dead `except ConfigError`, `register()` silent overwrite, `version` accepts any int, snapshot-wide `redact()` can rewrite operational strings, `before` hooks re-run on every resume/retry) are informational — recorded in `03-REVIEW.md`, none block goal achievement. IN-05 is worth a deliberate decision before Phase 4 makes `prepare_role_context` real.

### Human Verification Required

The mechanism for all four Success Criteria is verified by code inspection plus
runnable unit/contract checks and targeted spot-checks. The end-to-end
behavioural proofs require a real PostgreSQL 17 / Neon and were not executable in
this sandbox (`pytest.UsageError: No PostgreSQL 17 is reachable`). Run each of
the following against real Neon (`set -a; . ./.env; set +a`):

1. **Full Phase 1-3 suite** — `uv run pytest -q` — green with the ~15 mechanically-updated `snapshot=` call sites.
2. **SC1 E2E** — `uv run pytest -q tests/integration/test_config_drives_pipeline.py` — reorder/shorten `[BA,QA]`→`[QA,BA]`→`[BA]` changes the transition sequence; `git diff --stat` over `orchestrator/` + `workflows/` empty.
3. **SC2 E2E** — `uv run pytest -q tests/integration/test_role_yaml_drives_behaviour.py` — editing `BA.yaml` `after:`/`instructions:`/`worker:` changes the persisted snapshot; instruction bytes inlined verbatim; `src/**/*.py` digest unchanged.
4. **SC3 E2E** — `uv run pytest -q tests/integration/test_snapshot_survives_edit.py` — pause `[BA,QA]`, reorder file to `[QA,BA]`, resume from a fresh process → run continues `BA→QA→COMPLETED`, same run id, one `runs` row.
5. **SC4 no-orphan-run** — `uv run pytest -q tests/db/test_bad_config_no_orphan_run.py tests/integration/test_config_error_exit_code.py` — 8 bad-config shapes raise `ConfigError` with `runs` count unchanged; CLI exits 2, empty stdout line 1.
6. **CFG-04 runtime** — `uv run pytest -q tests/db/test_role_hooks_invoked.py` — before→worker→after order; identical `ActionContext` remainder across two roles; new action from config; legacy snapshot invokes no hooks.
7. **CFG-05 round-trip** — `uv run pytest -q tests/db/test_snapshot_roundtrip.py` — `create_run`→`load_run_state` deep-equality incl. ordered `roles` + each `instruction_text`.
8. **Real-repo walkthrough** (carried from Phase 1/2) — in a real checkout, edit `.dark-factory.yaml` / a role YAML, run `dark-factory run`, observe the pipeline / role behaviour change with `git diff src/` empty; edit during a `WAITING_HUMAN` pause and confirm the resumed run ignores the edit.

### Acknowledged Gaps

All eight human-verification items were completed against real Neon PostgreSQL
17 on 2026-09-11 and recorded as passing in `03-UAT.md`. The three review
advisories (WR-01 through WR-03) remain non-blocking hardening work and do not
invalidate the Phase 3 success criteria.

### Gaps Summary

No gaps that fail a Success Criterion. Every Phase 3 mechanism is present, wired,
and consistent with the phase goal: the pipeline shape is built from
`pipeline_from_snapshot(runs.workflow)` (no `DEFAULT_PIPELINE`, no role-name
literal in the orchestrator), role behaviour is resolved from `.dark-factory/`
YAML + Markdown into the snapshot, the snapshot is persisted at run creation and
is the only config source on resume (`orchestrator/*` structurally cannot import
`config.loader`), before/after hooks resolve through the `ActionRegistry`
allowlist around the worker call, and an unknown worker/action/role name raises
`ConfigError` before `create_run` with the CLI mapping it to exit 2. The
remaining work is execution of the substantive db/integration behavioural test
files against a real database — deferred to `/gsd-verify-work` per the standing
Phase 1/2/3 precedent — plus three code-review hardening items (WR-01..WR-03)
that do not break any invariant or Success Criterion.

---

_Verified: 2026-09-10_
_Verifier: Claude (gsd-verifier)_
