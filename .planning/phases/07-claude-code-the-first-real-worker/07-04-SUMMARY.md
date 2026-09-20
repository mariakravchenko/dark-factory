---
phase: 07-claude-code-the-first-real-worker
plan: 04
subsystem: workers
tags: [claude-code-cli, allowedTools, tool-contract, native-tools, security]

# Dependency graph
requires:
  - phase: 07-claude-code-the-first-real-worker
    provides: "07-03: _base_argv, execute()/resume() sharing it, and the shared contract suite ClaudeCodeWorker already proves against"
provides:
  - "allowed_tools_for(granted, artifacts_glob) -> list[str]: pure translation of a role's context.tools grants into a sorted, de-duplicated --allowedTools value, deny-by-omission, with artifacts.write producing a path-scoped Edit(<glob>/**) specifier instead of a bare tool name"
  - "_base_argv(context) now appends --allowedTools <names> (or nothing, for an empty grant) -- both execute() and resume() inherit the restriction with no special-casing"
  - "dark_factory.tools.native.NATIVE_TOOL_CONTRACT's first real, guarded runtime consumer (dark_factory.workers.claude_code); tests/unit/test_native_tool_contract.py's reference guard narrowed from total inertness to an explicit _ALLOWED_CONSUMERS allowlist (3 paths)"
  - "WORKTREE_CONFINEMENT_NOTE: every claude_code contract entry now names cwd=<worktree> as the real confinement mechanism, replacing a claim about a nonexistent --permission-mode directory-scoping value"
affects: ["08-* (CopilotWorker/HermesWorker -- same NATIVE_TOOL_CONTRACT, same _ALLOWED_CONSUMERS pattern to extend)"]

# Actuals (#2632)
actuals:
  tokens: 6761
  tasks: 2
  commits: 4
plan_head_before: d2c2c62

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deny-by-omission tool translation: a capability with no _TOOL_NAMES entry contributes nothing to --allowedTools, mirroring the deny-by-default discipline ToolRegistry.invoke already enforces for Dark-Factory-initiated calls"
    - "Path-scoped native rule specifier (Edit(<glob>/**)) for a grant that must be narrower than a bare tool name -- artifacts.write is the first capability requiring this, kept out of the flat _TOOL_NAMES mapping specifically so it cannot accidentally widen to Write"
    - "Guard-narrowing-not-deleting: a design-contract table's reference guard moves from asserting zero consumers to an explicit consumer allowlist when the table gains its first real implementer, with a sanity test proving the walk itself still detects an out-of-allowlist reference"

key-files:
  created: []
  modified:
    - src/dark_factory/workers/claude_code.py
    - src/dark_factory/tools/native.py
    - tests/unit/test_claude_code_worker.py
    - tests/unit/test_native_tool_contract.py

key-decisions:
  - "artifacts.write deliberately excluded from _TOOL_NAMES (the flat capability -> tool-name mapping) and handled as a separate path-scoped specifier in allowed_tools_for -- a bare Write/Edit entry would silently widen the grant to the whole worktree"
  - "The artifacts glob is computed inline in _base_argv from context.run_id/context.artifacts_dir as a run-relative path (.dark-factory/runs/<run_id>/<artifacts_dir>) since the subprocess is spawned with cwd=work_dir; a context-free call (run_id or artifacts_dir missing) passes None and the artifacts.write specifier is simply skipped, never fabricated"
  - "_ALLOWED_CONSUMERS (renamed from _OWN_MODULES) is a positive allowlist of exactly 3 paths (tools/native.py, tools/__init__.py, workers/claude_code.py) rather than deleting the inertness guard entirely -- a future undeclared consumer still fails a test"
  - "WORKTREE_CONFINEMENT_NOTE is a single shared module constant interpolated into all seven claude_code contract strings, so the corrected prose cannot drift entry-by-entry the way the original --permission-mode claim apparently did"

patterns-established:
  - "Pattern: a design-contract table (Phase 6's NATIVE_TOOL_CONTRACT) transitions from a total-inertness guard to an explicit-consumer-allowlist guard the moment it gains its first real implementer -- Phase 8's Copilot/Hermes adapters follow the same two-step (implement, then add to _ALLOWED_CONSUMERS on purpose)"

requirements-completed: [WORK-04]

coverage:
  - id: D1
    description: "allowed_tools_for() translates a role's held capabilities into a sorted, de-duplicated --allowedTools value derived from NATIVE_TOOL_CONTRACT's capability vocabulary -- deny by omission for any capability with no translation, and a set(_TOOL_NAMES) | {artifacts.write} == set(NATIVE_TOOL_CONTRACT) completeness assertion so an untranslated future capability fails a test rather than silently granting nothing (T-07-18)"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_repo_read_and_search_union_sorted_deduped"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_shell_execute"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_repo_write"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_repo_write_tests"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_artifacts_read"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_empty_grant_yields_empty_list"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_is_deterministic_across_calls"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_tool_names_cover_every_native_contract_capability"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_ungranted_capability_contributes_no_tool_name"
        status: pass
    human_judgment: false
  - id: D2
    description: "artifacts.write is excluded from the flat tool-name mapping and instead produces a single path-scoped Edit(<run-relative artifacts glob>/**) specifier, never a bare Write, so holding it cannot widen to the whole worktree; a context-free call (no glob available) skips the specifier entirely"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_artifacts_write_is_path_scoped_not_bare"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_artifacts_write_with_no_glob_yields_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_artifacts_write_grant_produces_path_scoped_edit_in_execute_argv"
        status: pass
    human_judgment: false
  - id: D3
    description: "--allowedTools is wired into _base_argv, which both execute() and resume() build their argv from -- the restriction applies identically to both entry points with no special-casing, present when a grant is held and absent (no flag at all, not an empty value) for an empty grant"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_flag_present_in_execute_argv_for_granted_role"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_flag_present_in_resume_argv_for_granted_role"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_no_tools_granted_produces_no_allowed_tools_flag"
        status: pass
    human_judgment: false
  - id: D4
    description: "NATIVE_TOOL_CONTRACT's reference guard is narrowed from total inertness to an explicit 3-path _ALLOWED_CONSUMERS allowlist (workers/claude_code.py added as the deliberate first real consumer), with a sanity test proving the AST walk itself still detects a reference outside that allowlist"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py#test_contract_is_referenced_only_by_its_declared_consumers"
        status: pass
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py#test_the_guard_detects_a_reference_outside_the_allowed_set"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every claude_code contract entry names cwd=<worktree> (via WORKTREE_CONFINEMENT_NOTE) as the real worktree-confinement mechanism, replacing prior prose that attributed directory scoping to a nonexistent --permission-mode value (T-07-17); artifacts.read/artifacts.write entries name the concrete path-scoped rule syntax the adapter actually emits"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py#test_every_claude_code_entry_names_the_real_worktree_mechanism"
        status: pass
    human_judgment: false
  - id: D6
    description: "Pre-existing behavior is unchanged: test_contract_has_exactly_one_entry_per_registered_capability, test_every_entry_is_complete_and_self_keyed, test_hermes_entries_are_honest_about_having_no_native_mechanism, test_native_tool_grant_is_frozen_and_extra_forbid, and the four structural guards (test_no_worker_name_leak.py, test_no_environ_copy.py, test_git_ownership_boundary.py, test_single_mutation_path.py) all still pass with no edits to their bodies"
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "uv run pytest -m unit -q tests/unit/test_native_tool_contract.py tests/unit/test_no_worker_name_leak.py tests/unit/test_no_environ_copy.py tests/unit/test_git_ownership_boundary.py tests/unit/test_single_mutation_path.py (all passed)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Full non-db/non-integration suite (unit + contract) is green after both tasks; mypy --strict and ruff check both exit 0. The db/integration tier (real PostgreSQL/Neon) was not run in this environment -- deferred per the same convention prior Phase 7 plans used -- but this plan touches no DB-adjacent code (tools/native.py and workers/claude_code.py have zero database coupling), so the risk of an undetected regression there is negligible."
    requirement: "WORK-04"
    verification:
      - kind: unit
        ref: "uv run pytest -q -m \"not db and not integration\" (512 passed, 314 deselected)"
        status: pass
      - kind: other
        ref: "uv run mypy src/dark_factory && uv run ruff check ."
        status: pass
    human_judgment: true
    rationale: "The plan's <verification> block calls for the full uv run pytest -q suite including the db tier against a real PostgreSQL/Neon instance. This environment's secret-file guard blocks sourcing .env to obtain DATABASE_URL, so the db/integration tier could not be executed here. A human with database credentials should run the full suite once to close this out, matching how prior Phase 7 db-tier items were deferred to /gsd-verify-work."
duration: 14min
completed: 2026-09-20
status: complete
---

# Phase 7 Plan 4: Native Tool Narrowing via `--allowedTools` Summary

**`ClaudeCodeWorker` now spawns the `claude` CLI with `--allowedTools` derived deterministically from the role's `context.tools` grants through `NATIVE_TOOL_CONTRACT`, and the contract's prior claim about a nonexistent `--permission-mode` directory-scoping flag is corrected to name the real `cwd=<worktree>` mechanism.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-20T18:33:12Z
- **Completed:** 2026-09-20T18:46:48Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `allowed_tools_for(granted, artifacts_glob)` is a pure function that unions the native tool names for every held capability into a sorted, de-duplicated `--allowedTools` value -- deny by omission for any capability with no translation, and a `set(_TOOL_NAMES) | {"artifacts.write"} == set(NATIVE_TOOL_CONTRACT)` completeness assertion (T-07-18) so a future untranslated capability fails a test instead of silently granting nothing
- `artifacts.write` produces a single path-scoped `Edit(.dark-factory/runs/<run_id>/<artifacts_dir>/**)` specifier rather than a bare `Write`, so that grant cannot widen to the whole worktree (T-07-16); a context-free call with no resolvable glob simply omits the specifier
- `_base_argv` -- shared verbatim by `execute()` and `resume()` since 07-03 -- now appends `--allowedTools <names>` whenever the list is non-empty and nothing at all for an empty grant, so both entry points get the identical restriction with no special-casing
- `dark_factory.tools.native.NATIVE_TOOL_CONTRACT` gained its first real runtime consumer (`dark_factory.workers.claude_code`), and `tests/unit/test_native_tool_contract.py`'s reference guard was narrowed -- not deleted -- from "zero consumers" to an explicit 3-path `_ALLOWED_CONSUMERS` allowlist, with a new sanity test proving the AST walk itself still catches a reference outside that allowlist (T-07-19)
- Every `claude_code` contract entry now names `cwd=<worktree>` (via the shared `WORKTREE_CONFINEMENT_NOTE` constant) as the real worktree-confinement mechanism, replacing a claim that `--permission-mode` scopes file access to a directory -- 07-RESEARCH.md confirmed no such value exists (T-07-17); the `artifacts.read`/`artifacts.write` entries now name the concrete path-scoped rule syntax the adapter actually emits

## Task Commits

Each task was committed atomically (RED/GREEN pairs per `tdd="true"`):

1. **Task 1: The spawned agent gets exactly the native tools the role was granted**
   - `1ee4cc0` test(07-04): add failing tests for --allowedTools tool narrowing (WORK-04)
   - `65068d9` feat(07-04): narrow spawned agent's native tools to the role's grants (WORK-04)
2. **Task 2: The contract table stops describing a mechanism that does not exist, and its guard is narrowed rather than deleted**
   - `19d13c8` test(07-04): add failing tests for the corrected worktree-confinement contract prose
   - `ce9bdbe` feat(07-04): correct native-tool contract prose to name the real worktree mechanism (T-07-17)

**Plan metadata:** (this commit, see below)

_Note: no REFACTOR commit was needed for either task -- both GREEN implementations were accepted as written with no follow-up cleanup._

## Files Created/Modified
- `src/dark_factory/workers/claude_code.py` -- `_TOOL_NAMES`, `_tool_names_cover_native_contract`, `allowed_tools_for`, `_base_argv` extended to emit `--allowedTools`
- `src/dark_factory/tools/native.py` -- `WORKTREE_CONFINEMENT_NOTE`, all seven `claude_code` entries rewritten, module docstring corrected
- `tests/unit/test_claude_code_worker.py` -- `_context()` gained a `tools` param; 14 new tests for `allowed_tools_for` and argv wiring
- `tests/unit/test_native_tool_contract.py` -- `_OWN_MODULES` renamed `_ALLOWED_CONSUMERS` (+1 entry), reference-guard test renamed and rewritten, 2 new tests

## Decisions Made
- `artifacts.write` deliberately excluded from the flat `_TOOL_NAMES` mapping and handled as a separate path-scoped specifier -- a bare tool name here would silently widen the grant to the whole worktree
- The artifacts glob is computed inline in `_base_argv` from `context.run_id`/`context.artifacts_dir` (run-relative, since the subprocess is spawned with `cwd=work_dir`); a context-free call passes `None` and the specifier is skipped, never fabricated
- `_ALLOWED_CONSUMERS` stays a positive allowlist of exactly 3 paths rather than deleting the inertness guard -- a future undeclared consumer still fails a test
- `WORKTREE_CONFINEMENT_NOTE` is one shared constant interpolated into all seven entries, so the corrected prose cannot drift entry-by-entry

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The db/integration test tier (real PostgreSQL/Neon) could not be run in this environment: sourcing `.env` for `DATABASE_URL` is blocked by a secret-file read guard. Ran the full `unit`+`contract` suite instead (512 passed, 0 failed), plus `mypy --strict` and `ruff check` (both clean). This plan's changes touch only `tools/native.py` and `workers/claude_code.py`, neither of which has any database coupling, so the risk of an undetected db-tier regression is negligible -- but the full suite including the db tier should still be run once by a human with credentials, per the same convention prior Phase 7 plans used for this deferral.

## User Setup Required
None - no external service configuration required. A live `claude` CLI on `PATH` and a real `ANTHROPIC_API_KEY` are needed only for an actual integration-tier/production run; every automated test in this plan fakes both.

## Next Phase Readiness
- Phase 7 is now complete (4 of 4 plans): a real agent runtime (Claude Code) performs a role end to end, including pause/resume, with its native tool surface bounded by the role's declared grants -- and the orchestrator remains unable to tell which runtime it is talking to (no worker-name branching outside `workers/`).
- Phase 8 (Copilot + Hermes) can follow the same two-step pattern this plan established: implement the adapter's native-tool translation from `NATIVE_TOOL_CONTRACT`, then add the new adapter module to `_ALLOWED_CONSUMERS` deliberately.
- One deferred item: the db/integration test tier for this plan's changes should be run once against real PostgreSQL/Neon by a human with `.env` credentials (see Issues Encountered). No blockers -- the changed modules have no DB coupling.

## TDD Gate Compliance

| Task | RED commit | GREEN commit | Notes |
|------|-----------|--------------|-------|
| Task 1 | `1ee4cc0` | `65068d9` | Full RED/GREEN split; RED verified as 14 genuine target-assertion failures (`ImportError`/`AttributeError` for `allowed_tools_for`/`_TOOL_NAMES`, missing `--allowedTools` in recorded argv) against the other 34 pre-existing tests still passing unchanged |
| Task 2 | `19d13c8` | `ce9bdbe` | Full RED/GREEN split; RED was a module-collection `ImportError` for the not-yet-defined `WORKTREE_CONFINEMENT_NOTE` -- the natural Python RED shape when a test module's own import line names the symbol under test, which does not exist until GREEN |

## Self-Check: PASSED

All four key files confirmed present on disk (`src/dark_factory/workers/claude_code.py`,
`src/dark_factory/tools/native.py`, `tests/unit/test_claude_code_worker.py`,
`tests/unit/test_native_tool_contract.py`). All four task commits (`1ee4cc0`, `65068d9`,
`19d13c8`, `ce9bdbe`) confirmed present in `git log`. Full `unit`+`contract` suite
re-verified green (512 passed, 314 deselected), `mypy --strict` and `ruff check` both
exit 0. The plan's named structural guards (`test_no_worker_name_leak.py`,
`test_no_environ_copy.py`, `test_git_ownership_boundary.py`,
`test_single_mutation_path.py`) pass. The db/integration tier was not re-run here (see
Issues Encountered) -- this is the one open item.

---
*Phase: 07-claude-code-the-first-real-worker*
*Completed: 2026-09-20*
