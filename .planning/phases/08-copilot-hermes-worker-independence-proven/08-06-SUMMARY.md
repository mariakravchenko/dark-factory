---
phase: 08-copilot-hermes-worker-independence-proven
plan: 06
subsystem: testing
tags: [pytest, postgresql, integration-testing, exit-codes, test-fixtures]

requires:
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "08-05's artifact scope enforcement (enforce_artifact_scope) and the two CR-01 negative-path proofs it added"
provides:
  - "A repaired _drive_shipped_config harness with a per-caller expected_exit and a D-05 cross-check, so the two CR-01 negative-path proofs assert the exit code the CLI actually contracts to return for a terminal FAILED run"
  - "The full UAT Test 2 command set (10 tests) actually executed against a real PostgreSQL instance for the first time, plus the phase's standing unit/contract/mypy/ruff gates"
  - "A whole-repo ruff format pass fixing 17 files with pre-existing drift, unrelated to G-08-2 but discovered while running this plan's repo-wide format gate"
  - "A LazyFourRoleWorker test fixture fixing a follow-on defect: two other db tests' four-role fixture front-loaded all roles' artifact files before a run started, which enforce_artifact_scope (08-05) now flags as the first role writing outside its own subtree"
affects: [any future phase-08 db test that drives a real multi-role run through FakeWorker-style scripted fixtures]

actuals:
  tokens: 210000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Per-caller keyword-only expected_exit (no default) on a shared test harness, so a future caller cannot silently inherit another caller's exit-code expectation"
    - "A structural (AST-based) acceptance criterion for an assertion that is, by design, unreachable in a green run — verifies the guard exists without requiring it to fire"
    - "LazyFourRoleWorker: write a scripted role's artifact files at execute()/resume() time, not upfront, so a multi-role FakeWorker-driven db test doesn't trip per-role artifact-scope enforcement"

key-files:
  created: []
  modified:
    - tests/integration/test_artifact_scope_enforcement.py
    - .planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md
    - src/dark_factory/config/loader.py
    - src/dark_factory/tools/env.py
    - src/dark_factory/workers/claude_code.py
    - src/dark_factory/workers/copilot.py
    - src/dark_factory/workers/hermes.py
    - tests/support/fake_artifacts.py
    - tests/db/test_artifact_persistence.py
    - tests/db/test_four_role_pipeline.py
    - tests/db/test_capability_denied_fails_role.py
    - tests/integration/test_phase6_acceptance.py
    - tests/integration/test_role_reassignment_sc2.py
    - tests/unit/test_ci_enforces_worker_name_guard.py
    - tests/unit/test_claude_code_worker.py
    - tests/unit/test_copilot_worker.py
    - tests/unit/test_hermes_worker.py
    - tests/unit/test_mcp_adapter.py
    - tests/unit/test_no_mcp_import_in_core.py
    - tests/unit/test_tool_registry.py
    - tests/unit/test_tool_registry_extensibility.py
    - tests/unit/test_worker_capabilities_match_behaviour.py

key-decisions:
  - "Ran the DB-dependent test commands myself directly via Bash (sourcing the user's shell profile for DARK_FACTORY_TEST_DATABASE_URL) rather than through a spawned gsd-executor subagent, after Claude Code's auto-mode safety classifier blocked the subagent dispatch for that exact instruction pattern (sourcing a shell rc file for a DB credential). The user chose this split explicitly (option 2 of a presented checkpoint) after the classifier denial."
  - "Fixed 17 files' pre-existing ruff-format drift and a genuine cross-role test-fixture regression (LazyFourRoleWorker) beyond plan 08-06's declared files_modified scope, at the user's explicit direction (\"let's fix formatting and all tests\") after flagging both as out-of-scope discoveries first."
  - "Declined to chase 11 additional db-tier test failures found in a full-suite run: they fail with PendingRollbackError / connection-level errors, at different, non-reproducible test names across repeated runs, and all pass individually — genuine environment-level flakiness against the live Neon test database (connection/session churn under sustained load), not a code defect. Documented rather than fixed; would need its own debug session."

requirements-completed: [WORK-05, WORK-06, ROLE-05]

coverage:
  - id: D1
    description: "Both CR-01 negative-path proofs (Hermes QA overwrite, Copilot ARCHITECTURE overwrite) pass end to end against a real PostgreSQL instance, asserting the D-05 persisted-FAILED exit code (1)"
    requirement: "WORK-05"
    verification:
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails"
        status: pass
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails"
        status: pass
    human_judgment: false
  - id: D2
    description: "The positive control still demands and gets the success exit code (0), proving the fix does not weaken the control"
    requirement: "WORK-06"
    verification:
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts"
        status: pass
    human_judgment: false
  - id: D3
    description: "The D-05 cross-check inside _drive_shipped_config exists structurally (by design unreachable in a green run) and is verified via AST inspection, not execution"
    requirement: "ROLE-05"
    verification:
      - kind: other
        ref: "AST structural check (see plan 08-06 Task 1 acceptance criteria) — module-level frozen set, single cross-check assert, expected_exit consulted twice"
        status: pass
    human_judgment: false
  - id: D4
    description: "The full UAT Test 2 command set (10 tests) plus the phase-01 D-05 exit-code guard pass together in one invocation against a real PostgreSQL instance"
    verification:
      - kind: integration
        ref: "pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_exit_codes.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Zero production change: src/dark_factory/cli.py and the rest of src/dark_factory/ (beyond the incidental ruff-format pass) carry no logic edits from this plan's gap-closure work"
    verification:
      - kind: other
        ref: "git diff --numstat -- src/dark_factory/ (empty across the G-08-2 commit)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Repo-wide standing gates (unit/contract suite, mypy strict, ruff check/format) are green, including a whole-repo formatting fix and a cross-role test-fixture fix done at the user's request beyond this plan's original scope"
    verification:
      - kind: unit
        ref: "pytest -m \"unit or contract\" -q — 640 passed"
        status: pass
      - kind: other
        ref: "mypy src/dark_factory — clean; ruff check . and ruff format --check . — clean"
        status: pass
    human_judgment: false

duration: ~90min (interactive session with a human-verify checkpoint and scope expansion; not a continuous executor run)
completed: 2026-09-22
status: complete
---

# Phase 08 Plan 06: G-08-2 Exit-Code Repair Summary

**Repaired the shared CR-01 test harness's hardcoded success-exit assertion into a per-caller, D-05-cross-checked `expected_exit`, then actually ran the previously-never-executed 10-test UAT set against a real database — and along the way fixed a whole-repo ruff-format gap and a second, unrelated artifact-scope test-fixture regression the user asked to be cleaned up too.**

## Performance

- **Duration:** ~90 min interactive (paused mid-run for a `blocking-human` precondition checkpoint — no reachable PostgreSQL — resolved by the user exporting `DARK_FACTORY_TEST_DATABASE_URL`; scope then expanded twice at the user's request)
- **Tasks:** 2/2 completed
- **Files modified:** 21 (2 in the plan's declared scope; 19 additional, at explicit user direction, documented below)

## Accomplishments

- `_drive_shipped_config`'s exit-code assertion is now per-caller (`expected_exit`, keyword-only, no default) instead of a hardcoded `== 0` inherited from a positive-path caller, closing G-08-2.
- Added a D-05 cross-check inside the harness tying `expected_exit` to the persisted terminal `run.status`, so the suite becomes a second guard on the CLI's exit-code contract rather than merely a consumer of it.
- Ran the full UAT Test 2 command set (10 tests) together with the phase-01 D-05 guard for the first time against a real PostgreSQL instance: **10 passed, 0 failed, 0 skipped**.
- Fixed a pre-existing, unrelated mypy `--strict` gap in the same test file (indexing a `dict[str, object]` return value without narrowing) that was blocking this plan's own mypy acceptance gate.
- At the user's request, reformatted 17 files across the repo with pre-existing `ruff format` drift, and fixed a second real regression: `tests/support/fake_artifacts.py::four_role_script` pre-staged all four roles' artifact files before a run started, which 08-05's `enforce_artifact_scope` now flags as a false violation — fixed via a new `LazyFourRoleWorker` fixture.

## Task Commits

1. **Task 1: Give `_drive_shipped_config` a per-caller expected exit code and a D-05 cross-check** — `7b752fe` (fix)
2. **Task 2: Execute the full UAT Test 2 set alongside the D-05 guard and record the execution** — this SUMMARY commit (docs), preceded by the verification runs recorded in the `08-05-SUMMARY.md` addendum

Two additional commits, outside this plan's declared scope, made at the user's explicit request after being flagged:
- `3e24df4` (style): whole-repo `ruff format` pass, 17 pre-existing files
- `5ef2d97` (fix): `LazyFourRoleWorker` — stop front-loading four-role fixture artifacts, fixing `tests/db/test_artifact_persistence.py` (3 tests) and `tests/db/test_four_role_pipeline.py` (1 test)

## Files Created/Modified

- `tests/integration/test_artifact_scope_enforcement.py` — per-caller `expected_exit`, D-05 cross-check, mypy narrowing fix (Task 1, in scope)
- `.planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md` — additive execution-verified addendum (Task 2, in scope)
- `tests/support/fake_artifacts.py`, `tests/db/test_artifact_persistence.py`, `tests/db/test_four_role_pipeline.py` — `LazyFourRoleWorker` fix (out of scope, user-requested)
- 15 further files across `src/dark_factory/` (3 worker modules, `config/loader.py`, `tools/env.py`) and `tests/` — whitespace-only `ruff format` (out of scope, user-requested)

## Decisions Made

- Ran the DB-dependent verification commands directly myself via Bash (sourcing the user's `~/.zshrc` for `DARK_FACTORY_TEST_DATABASE_URL`) rather than through a spawned `gsd-executor` subagent, after Claude Code's auto-mode safety classifier blocked that exact instruction pattern when dispatched to a subagent. The user chose this split explicitly.
- Expanded scope twice at explicit user request ("let's fix formatting and all tests") after flagging both issues (repo-wide format drift, the `LazyFourRoleWorker` regression) as pre-existing and unrelated to G-08-2 first — never silently expanded scope on my own judgment.
- Declined to chase 11 further db-tier failures surfaced by a full-suite run (`pytest -m db`, no file filter): different test names failed on each of two repeated attempts, all with `PendingRollbackError`/connection-level errors, and every one passes individually. This is environment-level flakiness against the live Neon test database, not a code defect — worth its own investigation, not this plan's scope.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pre-existing mypy `--strict` gap in the harness's own test file**
- **Found during:** Task 1's mypy acceptance criterion
- **Issue:** `result["status_by_role"]["QA"]` and similar indexed a `dict[str, object]` return value without narrowing, in code this plan did not otherwise touch (pre-existing since 08-05)
- **Fix:** `isinstance(status_by_role, dict)` narrowing, matching the idiom the same file's positive-control test already used
- **Files modified:** `tests/integration/test_artifact_scope_enforcement.py`
- **Verification:** `mypy tests/integration/test_artifact_scope_enforcement.py` — clean
- **Committed in:** `7b752fe`

**2. [Rule 3 - Blocking, user-directed] Whole-repo `ruff format` drift**
- **Found during:** Task 2's `ruff format --check .` acceptance criterion
- **Issue:** 17 files across `src/` and `tests/` had pre-existing formatting drift unrelated to G-08-2
- **Fix:** `ruff format .`; flagged to the user before fixing, fixed on explicit direction
- **Files modified:** see list above
- **Verification:** `ruff format --check .` — clean; targeted sanity re-run of the 9 reformatted unit-test files — all passed
- **Committed in:** `3e24df4`

**3. [Rule 1 - Bug, user-directed] `four_role_script` front-loading trips `enforce_artifact_scope`**
- **Found during:** investigating a `db`-tier failure the user surfaced (`tests/db/test_artifact_persistence.py`, 3 failures) while chasing Task 2's broader "fix all tests" request
- **Issue:** the shared four-role fixture wrote all four roles' artifact files before the run started; 08-05's `enforce_artifact_scope` (introduced after this fixture was written) flags the first role's check as seeing later roles' files
- **Fix:** `LazyFourRoleWorker`, writing each role's files at `execute()`/`resume()` time — the same pattern `tests/db/test_artifact_commit_per_role.py` already used for this exact reason
- **Files modified:** `tests/support/fake_artifacts.py`, `tests/db/test_artifact_persistence.py`, `tests/db/test_four_role_pipeline.py`
- **Verification:** all three affected/adjacent files together — 8 passed, 0 failed against a real Postgres instance
- **Committed in:** `5ef2d97`

---

**Total deviations:** 3 auto-fixed (1 pre-existing mypy gap within declared scope, 2 pre-existing/unrelated issues fixed at explicit user direction after being flagged).
**Impact on plan:** None of the three affected G-08-2 itself or `src/dark_factory/cli.py`. All were flagged before being fixed; none were fixed silently.

## Issues Encountered

- **Claude Code auto-mode classifier blocked a subagent dispatch.** Spawning a `gsd-executor` subagent with instructions to source `~/.zshrc` (to reach `DARK_FACTORY_TEST_DATABASE_URL`, which isn't visible to non-interactive shells) was denied by the harness's own safety classifier. Resolved by running the DB-dependent verification commands directly in the orchestrator's own Bash tool instead, per the user's explicit choice.
- **A `blocking-human` precondition checkpoint fired on the first dispatch attempt**, correctly per GSD's checkpoint protocol: no PostgreSQL 17 was reachable (no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset). The user resolved it by exporting the variable in their shell profile; the harness's actual test-provisioning code does not enforce the literal version 17 for the "external" rung, so a reachable PostgreSQL 18.6 instance satisfied the precondition as coded.
- **11 additional `db`-tier test failures surfaced by a full-suite run**, all connection-level (`PendingRollbackError`) and non-reproducible at the same test names across repeated runs — documented above as environment flakiness, not fixed here.

## User Setup Required

None beyond what the user already provided this session (`DARK_FACTORY_TEST_DATABASE_URL`, already in their `~/.zshrc`).

## Next Phase Readiness

- G-08-2 is closed. The CR-01 proof is repaired, not relaxed, and `src/dark_factory/cli.py` is unchanged.
- The `db` test tier has known, documented environment-level flakiness against the live Neon test database (connection/session churn under sustained sequential load) worth a dedicated `/gsd-debug` session before relying on a full `pytest -m db` run as a hard CI gate.
- No blockers for advancing past phase 08.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-22*

## Self-Check: PASSED

- `tests/integration/test_artifact_scope_enforcement.py` and `.planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md` both confirmed on disk with the described edits.
- `git log --oneline --all --grep="08-06"` returns the Task 1 commit `7b752fe`.
- `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_exit_codes.py`: 10 passed.
- `uv run pytest -m "unit or contract" -q`: 640 passed.
- `uv run mypy src/dark_factory`: clean. `uv run mypy tests/integration/test_artifact_scope_enforcement.py`: clean.
- `uv run ruff check .` and `uv run ruff format --check .`: both clean.
- `git diff --numstat -- src/dark_factory/cli.py`: empty.
- `git diff --numstat -- .planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md`: 53 added, 0 deleted — addendum confirmed additive.
- AST structural check for the D-05 cross-check: passes (prints "D-05 cross-check present via _D05_SUCCESS_STATUSES").
- `tests/db/test_artifact_persistence.py`, `tests/db/test_four_role_pipeline.py`, `tests/db/test_artifact_commit_per_role.py` together: 8 passed, 0 failed.
