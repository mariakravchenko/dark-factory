---
phase: 05-isolated-workspace-git-lifecycle
plan: 01
subsystem: git-lifecycle
tags: [git, worktree, subprocess, orchestrator, GIT-01, GIT-02]

requires:
  - phase: 04-the-four-role-pipeline-artifact-handoffs
    provides: the four-role pipeline (BA/ARCHITECTURE/DEVELOPMENT/QA), the artifact-persistence contract (run_root, collect_role_artifacts), and RunState/ActionContext as the per-step value objects this plan extends
provides:
  - "dark_factory.git package: GitError hierarchy, run_git subprocess wrapper with an explicit env allowlist, and ensure_worktree/remove_worktree idempotent worktree lifecycle (D-01..D-04, D-15)"
  - "runs.base_branch / runs.working_branch persisted at create_run, before any git command runs"
  - "RunState / ActionContext carry the persisted git identifiers and the resolved worktree/run-root paths"
  - "orchestrator/runner.py calls ensure_worktree unconditionally on every role attempt; the run tree and role context resolve against the worktree, not the main checkout"
  - "every in-process advance()/drive() test call site drives against a real git-backed repo_root; the fail-loud contract for a non-git repo_root is proven by a named test"
  - "tests/support/git_repo.py: the throwaway real-git-repo fixture factory other Phase 5 plans build on"
affects: [05-02-wip-commit-recovery-detached-head, 05-03-artifact-durability-commit-mechanics, 05-04-write-scope-enforcement]

actuals:
  tokens: 32800
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "git subprocess wrapper with an explicit env allowlist (GIT_ENV_ALLOWLIST) mirroring tests/support/subprocess_runner.py's child_env discipline -- never os.environ.copy()"
    - "idempotent worktree creation: check the target's .git marker before any git call, mirroring artifacts/paths.py's compute-check-only-act-if-missing idiom"
    - "AST-walk ownership-boundary guards (test_git_ownership_boundary.py) mirroring test_single_mutation_path.py's technique for a second invariant (GIT-02)"

key-files:
  created:
    - src/dark_factory/git/__init__.py
    - src/dark_factory/git/client.py
    - src/dark_factory/git/worktree.py
    - tests/support/git_repo.py
    - tests/db/test_run_owns_a_worktree.py
    - tests/unit/test_git_worktree.py
    - tests/unit/test_git_ownership_boundary.py
  modified:
    - src/dark_factory/persistence/mutations.py
    - src/dark_factory/persistence/repositories.py
    - src/dark_factory/actions/context.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/workers/fake.py
    - tests/conftest.py
    - tests/support/config.py
    - "24 test files migrated onto a git-backed repo_root (see Deviations)"

key-decisions:
  - "GitCommandError's message now names the working directory (cwd=...) in addition to the subcommand/exit-code/stderr-first-line the plan specified, because some git failures (\"not a git repository\") never name a path in their own stderr -- discovered while writing the Task 2 regression guard."
  - "FakeWorker's true-default artifact synthesis computes the worktree-sibling root by inlining the sibling-path formula rather than importing dark_factory.git.worktree, to respect GIT-02's worker/git import boundary that Task 3's own guard enforces."

patterns-established:
  - "A test needing to pre-seed artifact content before drive() must pre-create the worktree via a direct ensure_worktree() call first (idempotent -- the runner's own call reuses it), never write into repo_root/run_root(root, run_id) directly, because the runner resolves the run tree inside the worktree."

requirements-completed: [GIT-01, GIT-02]

coverage:
  - id: D1
    description: "A run persists dark-factory/run-<run_id> on runs.working_branch and the snapshot's repository.base_branch on runs.base_branch, in the same transaction as the CREATED row, before any git command runs"
    requirement: GIT-01
    verification:
      - kind: db
        ref: "tests/db/test_run_owns_a_worktree.py::test_branch_columns_persisted_before_any_git_command"
        status: pass
    human_judgment: false
  - id: D2
    description: "A two-role run creates exactly one sibling git worktree checked out on its working branch; both roles execute inside it; the second role's entry reuses the worktree with no second git worktree add (unchanged branch HEAD SHA, unchanged worktree count)"
    requirement: GIT-01
    verification:
      - kind: db
        ref: "tests/db/test_run_owns_a_worktree.py::test_two_role_run_creates_and_reuses_one_worktree"
        status: pass
      - kind: unit
        ref: "tests/unit/test_git_worktree.py::test_ensure_worktree_second_call_reuses_without_a_second_worktree_add"
        status: pass
    human_judgment: false
  - id: D3
    description: "ensure_worktree reconstructs from origin when no local worktree exists but the branch has a pushed commit (D-15), and falls through to fresh -b creation when the branch exists nowhere"
    requirement: GIT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_git_worktree.py::test_ensure_worktree_reconstructs_from_origin_when_no_local_worktree_exists"
        status: pass
      - kind: unit
        ref: "tests/unit/test_git_worktree.py::test_ensure_worktree_falls_through_to_fresh_creation_when_branch_exists_nowhere"
        status: pass
    human_judgment: false
  - id: D4
    description: "ensure_worktree fails loudly (GitCommandError naming the branch, WorktreePathError naming the run id) on an invalid base branch or a missing persisted working_branch, leaving no directory behind"
    requirement: GIT-01
    verification:
      - kind: db
        ref: "tests/db/test_run_owns_a_worktree.py::test_ensure_worktree_invalid_base_branch_raises_git_command_error"
        status: pass
      - kind: unit
        ref: "tests/unit/test_git_worktree.py::test_ensure_worktree_invalid_base_branch_raises_and_leaves_no_directory"
        status: pass
    human_judgment: false
  - id: D5
    description: "src/dark_factory/git/client.py is the only module under src/dark_factory/ that invokes the git binary; no worker module imports dark_factory.git"
    requirement: GIT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_git_ownership_boundary.py::test_git_client_is_the_sole_git_invoker"
        status: pass
      - kind: unit
        ref: "tests/unit/test_git_ownership_boundary.py::test_no_worker_module_imports_the_git_package"
        status: pass
    human_judgment: false
  - id: D6
    description: "run_git builds its child environment from an explicit allowlist; DATABASE_URL/GITHUB_TOKEN set in the parent process never appear in git_env()"
    requirement: GIT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_git_worktree.py::test_git_env_contains_only_allowlisted_names_plus_identity"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every in-process advance()/drive() test call site in the whole suite drives against a real git-backed repo_root; driving against a non-git repo_root raises GitCommandError naming the path instead of silently degrading to the main checkout"
    requirement: GIT-01
    verification:
      - kind: db
        ref: "40 db/integration tests across the migrated files (test_lease_claim_atomic.py, test_lease_lost_aborts_step.py, test_pause_mechanism_generic.py, test_pause_path_atomic.py, test_resume_first_advance.py, test_role_hooks_invoked.py, test_run_failure_path.py, test_state_event_pairing.py, test_status_from_columns.py, test_terminal_advance_noop.py, test_transition_atomic.py, test_redaction_interactions.py, test_secret_redaction_e2e.py) plus the artifact-tier files (test_artifact_handoff.py, test_artifact_persistence.py, test_artifact_schema_violation_fails_role.py, test_four_role_pipeline.py) plus test_real_pipeline_zero_config.py -- all green"
        status: pass
      - kind: db
        ref: "tests/db/test_run_owns_a_worktree.py::test_advance_against_a_non_git_repo_root_raises_git_command_error"
        status: pass
    human_judgment: false

duration: 105min
completed: 2026-09-14
status: complete
---

# Phase 05 Plan 01: Isolated Workspace & Git Lifecycle -- The Worktree Spine Summary

**A run's working branch is persisted at creation and every role of that run executes inside one real, idempotently-reused `git worktree`, with the `git` binary reachable from exactly one module in the whole project.**

## Performance

- **Duration:** ~105min
- **Started:** 2026-09-14T11:30:00Z (approx.)
- **Completed:** 2026-09-14T13:15:00Z (approx.)
- **Tasks:** 3 completed
- **Files:** 35 changed (7 created, 28 modified)

## Accomplishments

- Built the `dark_factory.git` package: a typed error hierarchy (`GitError`/`GitCommandError`/`DetachedHeadError`/`WorktreePathError`/`WriteScopeViolation`), `run_git` (an explicit-argument-list, explicit-env-allowlist subprocess wrapper), and `ensure_worktree`/`remove_worktree`/`working_branch_name`/`worktree_path` -- the whole D-01..D-04, D-15 worktree lifecycle.
- `create_run` now persists `runs.base_branch` / `runs.working_branch` in its existing transaction, before any git command runs -- the ROADMAP invariant "git effects are guarded by persisted identifiers before acting."
- `orchestrator/runner.py::_run_current_role` calls `ensure_worktree` unconditionally on every role attempt; the run tree and the role's `RoleContext` now resolve against the worktree, not the main checkout, making "every role operates on the same run repository state" literally true.
- Migrated every in-process `advance()`/`drive()` call site across the whole test suite (24 files, ~50 test functions) onto a real git-backed `repo_root`, and proved the fail-loud contract: driving against a non-git `repo_root` raises `GitCommandError` naming the path.
- Proved the GIT-02 ownership boundary with an AST guard mirroring `test_single_mutation_path.py`'s technique: `src/dark_factory/git/client.py` is the only module in the project that invokes the `git` binary, and no worker module imports `dark_factory.git`.

## Task Commits

1. **Task 1: End-to-end tracer -- a run creates its branch and worktree, and both its roles run inside it** - `6a5748a` (feat)
2. **Task 2: Migrate every in-process advance/drive call site onto a git-backed repository root** - `343f75b` (fix)
3. **Task 3: The GIT-01 unit proofs and the GIT-02 ownership boundary guard** - `f2f6412` (test)

## Files Created/Modified

- `src/dark_factory/git/__init__.py` -- the error hierarchy and public re-exports
- `src/dark_factory/git/client.py` -- `run_git`, `git_env`, `GIT_ENV_ALLOWLIST`, `GIT_IDENTITY_ENV`
- `src/dark_factory/git/worktree.py` -- `working_branch_name`, `worktree_path`, `ensure_worktree`, `remove_worktree`
- `tests/support/git_repo.py` -- `make_git_repo`, `git_commit_all`, `read_committed`, `clone_repo`
- `tests/db/test_run_owns_a_worktree.py` -- the SC1 tracer proof (5 tests)
- `tests/unit/test_git_worktree.py` -- the GIT-01 unit proofs (17 tests)
- `tests/unit/test_git_ownership_boundary.py` -- the GIT-02 AST guard (3 tests)
- `src/dark_factory/persistence/mutations.py` -- `create_run` persists the two branch columns
- `src/dark_factory/persistence/repositories.py` -- `RunState` gains `base_branch`/`working_branch`
- `src/dark_factory/actions/context.py` -- `ActionContext` gains `worktree`/`run_root`/`base_branch`/`working_branch`
- `src/dark_factory/orchestrator/runner.py` -- wires `ensure_worktree` into `_run_current_role`
- `src/dark_factory/workers/fake.py` -- true-default synthesis now targets the worktree-sibling root
- `tests/conftest.py` -- `_write_config_tree` git-initialises its tree; new `git_repo_root` fixture
- `tests/support/config.py` -- `DEFAULT_TEST_SNAPSHOT` carries `repository.base_branch`
- 24 test files across `tests/db/`, `tests/integration/`, `tests/unit/` -- migrated onto a git-backed `repo_root` (full list in the `343f75b` commit)

## Decisions Made

- **`GitCommandError` now names the working directory.** The plan's own spec for the message was "subcommand, exit code, first line of stderr." While writing Task 2's regression-guard test (`advance()` against a non-git `repo_root` must raise `GitCommandError` naming the path), git's own `fatal: not a git repository` stderr was found to never include a path. Added an optional `cwd` parameter to `GitCommandError` and threaded it through from `run_git`, so every `GitCommandError` names the directory git ran in -- a genuine diagnostic improvement, not a spec violation (the original three fields are all still present).
- **`FakeWorker`'s true-default synthesis mirrors the sibling-path formula rather than importing it.** `src/dark_factory/git/worktree.py::worktree_path` computes the identical deterministic path, but importing it into `workers/fake.py` would violate the GIT-02 ownership boundary Task 3's own guard enforces (no worker module may import `dark_factory.git`). The two-line formula is inlined with an explicit comment cross-referencing the source of truth.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `RunState` construction sites missing the new required `base_branch`/`working_branch` fields**
- **Found during:** Task 2's full-suite verification pass
- **Issue:** `tests/unit/test_context_builder.py::_state()` constructed `RunState` directly without the two new required fields Task 1 added, failing with a pydantic `ValidationError`.
- **Fix:** Added `base_branch="main"` and a deterministic `working_branch` to the helper.
- **Files modified:** `tests/unit/test_context_builder.py`
- **Verification:** `uv run pytest -m unit -q tests/unit/test_context_builder.py` (8 passed)
- **Commit:** `343f75b`

**2. [Rule 1 - Bug] Every in-process `advance()`/`drive()` test call site needed a git-backed `repo_root`**
- **Found during:** Task 2 (the task's own explicit purpose)
- **Issue:** `ensure_worktree` is now an unconditional call inside `_run_current_role`; any test driving a run in-process without an explicit `repo_root` defaults to `Path.cwd()`, which for the test process is this worktree's own checkout -- risking a real `git worktree add` against the developer's own tree.
- **Fix:** Threaded `repo_root=git_repo_root` (a new function-scoped fixture) or an existing `config_root_factory` tree through 20 files; added `repository.base_branch` to three inline snapshot dicts that lacked it.
- **Files modified:** 20 files under `tests/db/` and `tests/integration/` (full list in `343f75b`).
- **Verification:** 40 tests run in a single combined session, all passing; `git worktree list --porcelain` / `git branch --list 'dark-factory/*'` / `.dark-factory/runs/` all clean afterward.
- **Commit:** `343f75b`

**3. [Rule 1 - Bug] Test-side artifact pre-writes targeted the main checkout, not the worktree**
- **Found during:** Task 2, running `tests/db/test_artifact_handoff.py`
- **Issue:** Four db-tier tests write scripted artifact content to `run_root(root, run_id)` *before* calling `drive()`, so the worker's reported `WorkerResult.artifacts` point at already-written files. Since the orchestrator now resolves the run tree inside the worktree (a sibling of `root`), these pre-written files landed in the wrong location, and BA failed the D-09 schema-validation gate with `MissingArtifactContentError`.
- **Fix:** Each affected test now pre-creates the worktree via a direct `ensure_worktree(root, run_id, base_branch="main", working_branch=working_branch_name(run_id))` call (idempotent -- the runner's own call inside `drive()` reuses it) and writes into `run_root(work_dir, run_id)` instead.
- **Files modified:** `tests/db/test_artifact_handoff.py`, `tests/db/test_artifact_persistence.py`, `tests/db/test_artifact_schema_violation_fails_role.py`, `tests/db/test_four_role_pipeline.py`
- **Verification:** All 4 files' tests green (verified individually and as part of the combined 40-test run).
- **Commit:** `343f75b`

**4. [Rule 1 - Bug] `FakeWorker`'s true-default artifact synthesis wrote to the wrong root**
- **Found during:** Task 2, running `tests/integration/test_real_pipeline_zero_config.py`
- **Issue:** `FakeWorker`'s unscripted-default synthesis path computed its write root as `run_root(Path.cwd(), run_id)`. Once GIT-01 relocated the actual run tree to the worktree (a sibling of `Path.cwd()`), this pre-existing computation became wrong for any CLI-driven run using the true default -- a real, general production bug exposed (not caused in the sense of new code, but newly triggered) by this task's wiring change.
- **Fix:** `_default_script` now computes the identical worktree-sibling path the orchestrator resolves, inlined rather than imported (see Decisions Made) so the GIT-02 ownership boundary holds.
- **Files modified:** `src/dark_factory/workers/fake.py`; `tests/unit/test_fake_worker_synthesis.py` updated to read artifact content back through the same formula (via `dark_factory.git.worktree.worktree_path`, permitted in test code).
- **Verification:** `tests/unit/test_fake_worker_synthesis.py` (11 passed); `tests/integration/test_real_pipeline_zero_config.py` (1 passed).
- **Commit:** `343f75b`

**5. [Rule 1 - Bug] `tests/integration/test_real_pipeline_zero_config.py` drove the CLI against this repository's own checkout**
- **Found during:** Task 2's explicit action item
- **Issue:** The test set `cwd` to this project's own root so the shipped `.dark-factory.yaml` would be exercised. Once `ensure_worktree` fires unconditionally, this would create a real sibling worktree and a `dark-factory/run-<id>` branch next to the developer's own checkout.
- **Fix:** The test now copies the shipped config set (`.dark-factory.yaml`, `.dark-factory/roles/`, `.dark-factory/instructions/`) into a throwaway `tmp_path` git repository and drives the CLI there instead, with the module docstring recording why.
- **Files modified:** `tests/integration/test_real_pipeline_zero_config.py`
- **Verification:** 1 test passed; the repository's own checkout confirmed free of stray worktrees/branches after the run.
- **Commit:** `343f75b`

**6. [Rule 1 - Bug] `_VOLATILE_COLUMNS` in `test_resume_first_advance.py` needed `working_branch`**
- **Found during:** Task 2 (part of the same repo_root migration pass, discovered by inspection before the full-suite run)
- **Issue:** This test compares `runs` column values field-by-field between two independently-driven runs, excluding only genuinely per-run-unique columns (`id`, `created_at`, `updated_at`). `working_branch` embeds the run's own UUID (`dark-factory/run-<run_id>`) and is exactly as run-specific as `id`, so the comparison would now fail on every run.
- **Fix:** Added `"working_branch"` to `_VOLATILE_COLUMNS`.
- **Files modified:** `tests/db/test_resume_first_advance.py`
- **Verification:** 2 tests passed.
- **Commit:** `343f75b`

**7. [Rule 1 - Bug] `test_as_text_renders_one_line_per_field_including_the_branch_fields` asserted the stale null-marker expectation**
- **Found during:** Task 2's file-by-file review of `test_status_from_columns.py`
- **Issue:** This pre-Phase-5 test asserted `base_branch`/`working_branch` render as `NULL_MARKER`, documenting "shown even though null until Phase 5." Since Phase 5 now populates both columns on every run, the assertion was stale.
- **Fix:** Updated to assert the real values (`"main"` and the deterministic `working_branch_name(run_id)`).
- **Files modified:** `tests/db/test_status_from_columns.py`
- **Verification:** 9 tests passed (this file's full suite).
- **Commit:** `343f75b`

**Total deviations:** 7 auto-fixed (all Rule 1 -- bugs directly exposed by this task's own wiring change). **Impact:** All fixes are test-tier or a single narrowly-scoped production fix (`workers/fake.py`); no architectural change; no scope creep beyond making the plan's own stated behavior actually work end to end.

## Threat Flags

None -- the threat register's mitigations (T-05-01 argument-list invocation, T-05-04 env-allowlist, T-05-09 derived-path-only, T-05-10 timeout, T-05-11 pinned identity) are all implemented and unit-tested as specified in `<threat_model>`; no new surface was introduced beyond what the plan's own threat register already covers.

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

Plan 05-01 is complete: the worktree spine is proven end-to-end (branch persisted before any git command, worktree created once and reused, run tree and role context resolve inside it), the git subprocess ownership boundary is guarded by an AST test, and the whole test suite (318 unit + every db/integration test that drives a run in-process) is green against the new git-backed reality.

Ready for **05-02** (WIP-commit recovery, detached-HEAD failure, the `ensure_clean_worktree` action becoming real) and **05-03** (artifact-content durability commits, the PR-bound diff), both of which build directly on `dark_factory.git.worktree`'s `ensure_worktree`/`remove_worktree` and the persisted `base_branch`/`working_branch` columns this plan shipped.

No blockers.

## Self-Check: PASSED

All 7 created files verified present on disk (`src/dark_factory/git/__init__.py`, `client.py`, `worktree.py`, `tests/support/git_repo.py`, `tests/db/test_run_owns_a_worktree.py`, `tests/unit/test_git_worktree.py`, `tests/unit/test_git_ownership_boundary.py`, this SUMMARY.md). All 3 task commit hashes (`6a5748a`, `343f75b`, `f2f6412`) verified present in `git log --oneline --all`.

---
*Phase: 05-isolated-workspace-git-lifecycle*
*Completed: 2026-09-14*
