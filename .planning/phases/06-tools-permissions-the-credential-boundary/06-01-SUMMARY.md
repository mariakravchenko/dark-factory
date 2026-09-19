---
phase: 06-tools-permissions-the-credential-boundary
plan: 01
subsystem: tools
tags: [capability-registry, deny-by-default, credential-boundary, tool-registry]

requires:
  - phase: 05-write-scope-enforcement
    provides: "enforce_write_scope path-containment discipline and the ROLE_FAILED/RUN_FAILED failure shape this plan's denial branch reuses"
  - phase: 01-walking-skeleton
    provides: "apply_transition single-mutation-path discipline (WR-01) and the events/catalog.py EventType vocabulary this plan extends"
provides:
  - "dark_factory.tools package: ToolError/CapabilityDeniedError/UnknownCapabilityError hierarchy"
  - "ToolRegistry.invoke() deny-by-default gate — the single enforcement point every future transport (MCP, shell) funnels through"
  - "Six registered capabilities: repo.read, repo.search, repo.write, repo.write_tests, artifacts.read, artifacts.write (shell.execute placeholder pending 06-02)"
  - "EventType.CAPABILITY_DENIED persisted alongside ROLE_FAILED/RUN_FAILED in the same apply_transition call"
  - "collect_role_artifacts reading through registry.invoke('artifacts.read', ...) as a real, unconditional production call site"
  - "load_effective_config rejecting an unregistered capability name at config-load time (ConfigError, no runs row)"
  - "QA.yaml grant expansion to repo.write_tests + shell.execute (D-16, ROADMAP SC1's 'writes tests and shells but cannot publish')"
  - "NATIVE_TOOL_CONTRACT — the D-02 typed per-worker native-tool translation table for Phase 7 adapters"
  - "Structural proof that a new capability is addable with zero role-executor/pipeline/lifecycle edits (TOOL-02, SC3)"
affects: [07-claude-code-worker-adapter, 08-copilot-hermes-adapters, 06-02-shell-execute-and-credential-boundary, 06-03-mcp-transport]

actuals:
  tokens: 24083
  tasks: 3
  commits: 4
  plan_head_before: 14ab97c7c52d87cab53b23725a62182033d3e745

tech-stack:
  added: []
  patterns:
    - "Registry-as-dict extension seam (ToolRegistry mirrors WorkerRegistry/ActionRegistry): register(name, fn) at import time, __contains__ for config-time membership validation, no public accessor returning a raw implementation"
    - "Deny-before-lookup ordering: invoke() checks grant membership before resolving the implementation, so a denied call has zero side effects regardless of registration state"
    - "Additive audit event: CAPABILITY_DENIED is prepended ahead of ROLE_FAILED/RUN_FAILED in the same apply_transition events list — never a replacement, so no observability consumer needs a new branch"
    - "Deny-by-default via .get(..., []) on a legacy snapshot's tools key — an absent/legacy grant list means nothing is granted, never everything"
    - "Design-contract-as-typed-data-with-a-completeness-guard: NATIVE_TOOL_CONTRACT is inert (no runtime consumer) but a unit test proves set(NATIVE_TOOL_CONTRACT) == default_registry.names(), so a future capability without a translation entry fails loudly instead of leaving a silent Phase 7 gap"

key-files:
  created:
    - src/dark_factory/tools/__init__.py
    - src/dark_factory/tools/registry.py
    - src/dark_factory/tools/native.py
    - tests/db/test_capability_denied_fails_role.py
    - tests/unit/test_tool_registry.py
    - tests/unit/test_tool_registry_extensibility.py
    - tests/unit/test_native_tool_contract.py
  modified:
    - src/dark_factory/artifacts/validation.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/events/catalog.py
    - src/dark_factory/config/loader.py
    - src/dark_factory/actions/builtins.py
    - .dark-factory/roles/QA.yaml
    - .dark-factory/roles/BA.yaml
    - .dark-factory/roles/ARCHITECTURE.yaml
    - .dark-factory/roles/DEVELOPMENT.yaml
    - tests/conftest.py
    - tests/db/test_artifact_commit_per_role.py
    - tests/db/test_artifact_handoff.py
    - tests/db/test_artifact_persistence.py
    - tests/db/test_artifact_schema_violation_fails_role.py
    - tests/db/test_four_role_pipeline.py
    - tests/integration/test_pr_diff_excludes_artifacts.py
    - tests/integration/test_role_yaml_drives_behaviour.py
    - tests/integration/test_write_scope_enforcement.py
    - tests/unit/test_artifact_paths.py
    - tests/unit/test_domain_enums.py
    - tests/unit/test_no_worker_name_leak.py

key-decisions:
  - "artifacts.write gets a real registered implementation but no orchestrator-owned production caller this plan — its genuine call path is the MCP transport landing in plan 06-03; store_role_artifacts stays a permanent no-op because a role-configurable after: hook is opt-in and a permission check a role's config can omit is not deny-by-default (planner override of the 06-CONTEXT.md note)"
  - "shell.execute is registered in Task 2 with a NotImplementedError placeholder body (naming plan 06-02) purely so the shipped QA/DEVELOPMENT role YAMLs validate at config-load time; its real body lands with build_worker_env in 06-02"
  - "QA's tools: grant expands to include repo.write_tests + shell.execute while repo.write stays absent — the literal 'writes tests and shells but cannot publish' half of ROADMAP SC1 (D-16), resolving 06-RESEARCH Open Question 1"
  - "[Rule 3 - blocking issue] test_no_worker_name_leak.py's pre-existing WORK-03 guard forbade the strings claude/copilot/hermes outside workers/ and config/, but D-02 requires tools/native.py to name them as NATIVE_TOOL_CONTRACT keys. Added a narrowly-scoped single-file exemption (_EXEMPT_FILES = {tools/native.py}) rather than widening the guard's exempted directory scope — the file holds data about a worker (translation-table keys), identical in kind to config/'s already-exempt YAML worker: values, never a per-worker branch in orchestrator core, which is what the guard actually protects against"

patterns-established:
  - "pattern: capability-gated production read — a function that used to call an I/O primitive directly (read_artifact_text) is migrated to call it through registry.invoke(role, capability, granted, ...) instead, with the primitive's body unchanged and the permission check added purely at the call boundary"
  - "pattern: config-time capability validation mirrors worker/action validation exactly — an unregistered name in a role's tools: list raises ConfigError before any runs row exists, using Container[str] membership on the tool registry the same way worker_registry and action_registry are already validated"

requirements-completed: [TOOL-01, TOOL-02, TOOL-03]

coverage:
  - id: D1
    description: "ToolRegistry.invoke() denies a capability not in the role's granted list before the implementation is looked up or called, raising CapabilityDeniedError naming role + capability + granted set"
    requirement: "TOOL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_registry.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "A granted-but-unregistered capability name raises UnknownCapabilityError, never CapabilityDeniedError or KeyError; an empty granted list denies every registered capability; grant-list order/duplicates never change the outcome; no prefix or wildcard matching"
    requirement: "TOOL-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_registry.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "A denied capability invocation fails the role attempt end-to-end and persists to Neon: FAILED role_executions row, and run_events containing CAPABILITY_DENIED (payload exactly {role, capability, reason}) followed by ROLE_FAILED followed by RUN_FAILED, with zero artifacts rows for that attempt — the SC1 tracer proof"
    requirement: "TOOL-01"
    verification:
      - kind: integration
        ref: "tests/db/test_capability_denied_fails_role.py"
        status: pass
    human_judgment: true
    rationale: "Db-tier verification required sourcing .env, which this session's secret-read-guard blocks; user ran the full suite and confirmed 694 passed / 3 pre-existing unrelated failures (this test included in the passing set)."
  - id: D4
    description: "A run whose roles grant artifacts.read/artifacts.write completes exactly as before this plan's migration — the four-role pipeline still reaches COMPLETED with the same artifact rows (behaviour-preservation proof for the eleven-file tools: [] migration, A-06-02)"
    requirement: "TOOL-03"
    verification:
      - kind: integration
        ref: "tests/db/test_capability_denied_fails_role.py (companion grant-present COMPLETED test) and the full migrated db/integration suite"
        status: pass
    human_judgment: true
    rationale: "Db-tier verification required sourcing .env, which this session's secret-read-guard blocks; user ran the full suite and confirmed 694 passed / 3 pre-existing unrelated failures (this test included in the passing set)."
  - id: D5
    description: "collect_role_artifacts reads every declared output through tool_registry.invoke(role, 'artifacts.read', granted, ...) instead of calling read_artifact_text directly — a real, unconditional, every-role-execution production call site"
    requirement: "TOOL-03"
    verification:
      - kind: unit
        ref: "grep -c 'artifacts.read' src/dark_factory/artifacts/validation.py (acceptance criterion, prints >=1) plus tests/unit/test_tool_registry.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "The shipped per-role grants match ROADMAP SC1 verbatim: BA/ARCHITECTURE denied repo.write and repo.write_tests; DEVELOPMENT granted repo.write; QA granted repo.write_tests + shell.execute and denied repo.write — proven by driving load_effective_config against the shipped .dark-factory/roles/*.yaml, not a hard-coded copy"
    requirement: "TOOL-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_registry.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "A role YAML naming a capability the tool registry does not contain is rejected by load_effective_config with a typed ConfigError before any runs row exists, matching the existing worker/action/write_scope fail-loud-at-config-load convention"
    requirement: "TOOL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_registry.py"
        status: pass
    human_judgment: false
  - id: D8
    description: "A capability registered on a ToolRegistry after import time (a synthetic test.echo name appearing nowhere under src/) is invokable by a granted role and denied to an ungranted one, with orchestrator/runner.py, workflows/pipeline.py and orchestrator/lifecycle.py byte-identical before and after — zero role-executor edits (TOOL-02, SC3)"
    requirement: "TOOL-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_registry_extensibility.py"
        status: pass
    human_judgment: false
  - id: D9
    description: "A one-role run whose config grants the synthetic capability reaches COMPLETED end-to-end through the real driver and load_effective_config with an injected fresh registry"
    requirement: "TOOL-02"
    verification:
      - kind: integration
        ref: "tests/unit/test_tool_registry_extensibility.py (db-tier arm)"
        status: pass
    human_judgment: true
    rationale: "Db-tier verification required sourcing .env, which this session's secret-read-guard blocks; user ran the full suite and confirmed 694 passed / 3 pre-existing unrelated failures (this test included in the passing set)."
  - id: D10
    description: "NATIVE_TOOL_CONTRACT has exactly one entry per registered capability (set(NATIVE_TOOL_CONTRACT) == default_registry.names()), every entry names concrete claude_code/copilot/hermes translation values plus a non-empty absent_behaviour, hermes states honestly that no per-tool native restriction flag is documented, and the table is structurally inert (no module outside tools/native.py and tools/__init__.py imports it)"
    requirement: "TOOL-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py"
        status: pass
    human_judgment: false
  - id: D11
    description: "ToolRegistry.invoke() opens no database Session and constructs no lifecycle ORM row (WR-01 discipline extends cleanly to the new tools/ package)"
    requirement: "TOOL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_single_mutation_path.py"
        status: pass
    human_judgment: false
  - id: D12
    description: "Static gates clean: mypy --strict over src/dark_factory and ruff check ."
    requirement: "TOOL-01"
    verification:
      - kind: unit
        ref: "uv run mypy src/dark_factory (61 source files, clean); uv run ruff check . (clean)"
        status: pass
    human_judgment: false

duration: "13min task-commit span (10:17-10:30, 2026-09-18) + ~57min db-tier full-suite verification run by the user (694 passed / 3 pre-existing failures)"
completed: 2026-09-19
status: complete
---

# Phase 06 Plan 01: Per-role capability enforcement with an auditable deny-by-default gate Summary

**`ToolRegistry.invoke()` now checks every capability call against the invoking role's persisted `tools:` grant before any implementation runs, failing the role attempt and writing a `CAPABILITY_DENIED` event to Neon alongside `ROLE_FAILED`/`RUN_FAILED` when the grant is absent.**

## Performance
- **Duration:** 13min task-commit span (2026-09-18 10:17-10:30) for the three implementation tasks; db-tier full-suite verification (694 passed, 3 pre-existing unrelated failures) ran separately by the user and took ~57min wall clock
- **Started:** 2026-09-18T10:17:12+03:00 (first task commit)
- **Completed:** 2026-09-19 (close-out)
- **Tasks:** 3
- **Files modified:** 28 (7 created, 21 modified)

## Accomplishments
- Built the `dark_factory.tools` package from scratch: an error hierarchy (`ToolError`, `CapabilityDeniedError`, `UnknownCapabilityError`) and `ToolRegistry` mirroring the existing `WorkerRegistry`/`ActionRegistry` extension idiom, with `invoke()` as the single enforcement point — deny-check strictly before implementation lookup, so a denied call has zero side effects.
- Registered six of the seven planned capabilities (`repo.read`, `repo.search`, `repo.write`, `repo.write_tests`, `artifacts.read`, `artifacts.write`), each path-taking implementation resolving through the same containment guard `resolve_under_run_root` already enforces; `shell.execute` is a `NotImplementedError` placeholder pending plan 06-02's `build_worker_env`.
- Migrated `collect_role_artifacts` off a direct `read_artifact_text` call onto `tool_registry.invoke(role, "artifacts.read", granted, ...)` — a real, unconditional, every-role-execution production call site — and threaded `tool_registry` through `drive → advance → _advance_once → _run_current_role`.
- Added `EventType.CAPABILITY_DENIED`, emitted ahead of `ROLE_FAILED`/`RUN_FAILED` in the same `apply_transition` call, with a payload narrowed to exactly `{role, capability, reason}`.
- Expanded QA's shipped grants to `repo.write_tests` + `shell.execute` (still denying `repo.write`) — the literal "writes tests and shells but cannot publish" half of ROADMAP SC1 — and made `load_effective_config` reject any role YAML naming an unregistered capability before a `runs` row exists.
- Migrated all thirteen `tools: []` occurrences across eleven test files onto real per-role grant sets matching the shipped role YAMLs, keeping the whole suite behaviour-preserving.
- Proved TOOL-02/SC3 structurally: a synthetic capability registered post-import is grantable and deniable with `orchestrator/runner.py`, `workflows/pipeline.py`, and `orchestrator/lifecycle.py` byte-identical before and after, plus an end-to-end run reaching `COMPLETED` with the new grant.
- Delivered the D-02 `NATIVE_TOOL_CONTRACT` — a typed, completeness-guarded table mapping each registered capability to its Claude Code/Copilot/Hermes native-tool translation, for Phase 7 to implement against without re-deriving the mapping.

## Task Commits
1. **Task 1 [BLOCKING]: End-to-end capability denial tracer** - `5f1c196` (feat) — `dark_factory.tools` package, `ToolRegistry.invoke()`, `CAPABILITY_DENIED` event, `collect_role_artifacts` migration, runner threading, eleven-file `tools:` migration, `test_capability_denied_fails_role.py`
2. **Task 2: Remaining capabilities, QA grant expansion, config validation** - `3118f37` (feat) — `repo.*` implementations, `shell.execute` placeholder, QA.yaml D-16 expansion, `load_effective_config` capability validation, `test_tool_registry.py`
3. **Task 3: TOOL-02 extensibility proof and D-02 native-tool contract** - `96a7913` (feat) — `tools/native.py`, `NATIVE_TOOL_CONTRACT`, `test_native_tool_contract.py`, `test_tool_registry_extensibility.py`

**Plan metadata:** (recorded after this SUMMARY's own commit)

## Files Created/Modified

**Created:**
- `src/dark_factory/tools/__init__.py` — error hierarchy + public re-exports
- `src/dark_factory/tools/registry.py` — `ToolRegistry`, `invoke()`, all six/seven capability implementations, `default_registry`
- `src/dark_factory/tools/native.py` — `NativeToolGrant` + `NATIVE_TOOL_CONTRACT` (D-02 contract)
- `tests/db/test_capability_denied_fails_role.py` — the SC1 tracer proof (denial + grant-present companion)
- `tests/unit/test_tool_registry.py` — SC1 grant/deny matrix + TOOL-02 edge probes
- `tests/unit/test_tool_registry_extensibility.py` — synthetic-capability zero-edit proof
- `tests/unit/test_native_tool_contract.py` — completeness + inertness guard

**Modified:**
- `src/dark_factory/artifacts/validation.py` — `collect_role_artifacts` gains `granted`/`tool_registry` params, reads via `invoke`
- `src/dark_factory/orchestrator/runner.py` — `tool_registry` threaded through `drive`/`advance`/`_advance_once`/`_run_current_role`; `CapabilityDeniedError` catch ahead of `ArtifactError`; `CAPABILITY_DENIED` event emission
- `src/dark_factory/events/catalog.py` — `CAPABILITY_DENIED` member
- `src/dark_factory/config/loader.py` — `tool_registry` param, unregistered-capability `ConfigError`
- `src/dark_factory/actions/builtins.py` — docstring update recording where the artifact grant is actually enforced
- `.dark-factory/roles/QA.yaml` — D-16 grant expansion
- `.dark-factory/roles/BA.yaml`, `ARCHITECTURE.yaml`, `DEVELOPMENT.yaml` — stale "not enforced" comment corrected
- `tests/conftest.py` + 10 db/integration test files — thirteen `tools: []` occurrences migrated to real grant sets
- `tests/unit/test_no_worker_name_leak.py` — single-file exemption for `tools/native.py` (deviation, see below)

## Decisions Made
- `artifacts.write` gets a real registered implementation but no orchestrator-owned production caller this plan — its genuine call path is the MCP transport landing in plan 06-03. `store_role_artifacts` stays a permanent no-op because a role-configurable `after:` hook is opt-in, and a permission check a role's own config can switch off is not deny-by-default. This resolves 06-RESEARCH.md Open Question 2 per the plan's own `<planner_override>`.
- `shell.execute` is registered in Task 2 with a `NotImplementedError` placeholder body purely so the shipped QA/DEVELOPMENT role YAMLs validate at config-load time; the real body lands with `build_worker_env` in plan 06-02.
- QA's `tools:` grant expands to `repo.write_tests` + `shell.execute` while `repo.write` stays absent, resolving 06-RESEARCH.md Open Question 1 and making ROADMAP SC1's "QA writes tests and shells but cannot publish" literally true against the shipped config.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Pre-existing worker-name-leak guard blocked D-02's required native-tool contract**
- **Found during:** Task 3
- **Issue:** `tests/unit/test_no_worker_name_leak.py`'s pre-existing WORK-03 guard forbids the literal strings `claude`, `copilot`, `hermes` anywhere under `src/dark_factory/` outside the already-exempt `workers/` and `config/` directories. D-02 requires `tools/native.py` to name exactly those three runtimes as `NATIVE_TOOL_CONTRACT` dictionary keys (`claude_code`, `copilot`, `hermes` fields on `NativeToolGrant`), which the guard would otherwise fail.
- **Fix:** Added a narrowly-scoped single-file exemption (`_EXEMPT_FILES = {_SRC_ROOT / "tools" / "native.py"}`) to the guard's scanner, rather than widening its exempted directory scope. The rationale recorded in the guard's own comment: `tools/native.py` holds data *about* a worker (translation-table keys), identical in kind to `config/`'s already-exempt YAML `worker: fake` values — never a per-worker `if worker == "claude"` branch in orchestrator core, which is what the guard actually protects against (and what the project's CLAUDE.md "Role != Worker" constraint forbids).
- **Files modified:** `tests/unit/test_no_worker_name_leak.py`
- **Commit:** `96a7913`

No other deviations. Tasks 1 and 2 executed exactly as planned, with the eleven-file `tools: []` test migration (A-06-02) executed at the scope and grant sets the plan specified.

## Issues Encountered

**3 pre-existing, unrelated test failures** (confirmed present in the baseline BEFORE this plan's work at 662 passed/3 failed, and unchanged after this plan's work at 694 passed/3 failed — the +32 passing tests are this plan's new/migrated tests; the 3 failures did not change):
- `tests/db/test_artifact_commit_per_role.py::test_one_artifact_commit_per_role_force_added_and_source_edits_survive` — `AssertionError: assert 'source_edit.txt' in []`
- `tests/db/test_artifact_commit_per_role.py::test_completed_run_with_a_trailing_edit_gets_a_recovery_commit_then_loses_its_worktree` — `AssertionError: assert <RunStatus.FAILED> is <RunStatus.COMPLETED>`
- `tests/integration/test_pr_diff_excludes_artifacts.py::test_pr_diff_excludes_dark_factory_and_ignores_the_base_branchs_own_post_cut_commit` — `AssertionError: assert <RunStatus.FAILED> is <RunStatus.DEVELOPMENT>`

These are phase-4 git-worktree/artifact-commit mechanics, unrelated to this plan's tool-registry/capability-enforcement work — out of scope, not caused by this plan, left unresolved for a future phase/fix to address.

**Db-tier verification constraint:** this session's secret-read-guard hook blocks the executor from sourcing `.env`, so all db-tier test confirmation for this plan (the SC1 tracer, the grant-present companion, the extensibility end-to-end arm, and the full 694-test suite) was performed by the user directly in their own terminal rather than by the executor. See the `coverage` block above for which deliverables this affects (all marked `human_judgment: true` with this rationale).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
Plan 06-02 (shell-execute + credential boundary / `build_worker_env`) can now register `shell.execute`'s real implementation over the `ToolRegistry.register` seam this plan built, replacing the `NotImplementedError` placeholder. Plan 06-03 (MCP transport) has its genuine `artifacts.write` call site waiting — the capability is registered but uncalled by production code until the MCP server construction lands. Phase 7's Claude Code adapter has `NATIVE_TOOL_CONTRACT` as a concrete, guarded table to implement `--allowedTools`/`--permission-mode` translation against, rather than re-deriving the mapping from `.claude/CLAUDE.md` prose.

---
*Phase: 06-tools-permissions-the-credential-boundary*
*Completed: 2026-09-19*

## Self-Check: PASSED
