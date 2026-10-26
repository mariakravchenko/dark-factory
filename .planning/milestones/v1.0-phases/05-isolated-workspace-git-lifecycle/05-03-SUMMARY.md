---
phase: 05-isolated-workspace-git-lifecycle
plan: 03
subsystem: git-lifecycle
tags: [git, artifact-durability, worktree-cleanup, pr-diff, force-add, push]
dependency-graph:
  requires:
    - "05-01: the git worktree spine (dark_factory.git package skeleton), a per-run worktree checked out on its own working branch, base_branch/working_branch persisted on the run row"
    - "05-02: dark_factory.git.lifecycle (head_sha, assert_attached_head, dirty_paths, is_dirty, wip_commit_if_dirty), ensure_clean_worktree as the real git-only before-hook pattern, and the redaction fix that lets legitimate git SHAs survive under known git-object keys"
  provides:
    - "dark_factory.git.diff: commit_run_artifacts (force-add past .gitignore, pathspec-limited commit, empty-change-set/missing-directory no-ops) and push_working_branch (GIT_ASKPASS-only credential, bounded tenacity retry, no-op on missing token or missing origin)"
    - "run_git's env_extra escape hatch, layered on top of the general credential allowlist, used only by the push call"
    - "orchestrator/runner.py ROLE_COMPLETED wiring: validate, then commit_run_artifacts, then push_working_branch, then transition -- a commit/push failure folds into the existing ROLE_FAILED/RUN_FAILED shape with no new event type"
    - "_cleanup_run_worktree: recover-then-remove for COMPLETED runs only (wip_commit_if_dirty then non-forced remove_worktree; a GitError here is a logged warning, never a status downgrade); FAILED and WAITING_HUMAN both keep their worktree"
    - "actions.builtins.collect_diff as a real git+filesystem action: writes the three-dot merge-base PR diff to verification/<DIFF_PATCH_FILENAME> under the run root, excluding .dark-factory content, no-op when either branch name is None"
    - "tests/support/git_repo.py::run_artifact_text -- the read-through-the-branch helper for asserting artifact content once a COMPLETED run's worktree may already be removed"
  affects:
    - "05-04: PR creation can assume every completed role already has a durable, pushed artifact commit and a pre-written verification/diff.patch to attach; publish logic does not need to re-derive either"
tech-stack:
  added: []
  patterns:
    - "force-add is intentional and whole-run-tree: commit_run_artifacts stages the entire .dark-factory/runs/<run_id>/ path per invocation (not just the acting role's new files) so it can also carry verification/diff.patch; any test fixture that pre-writes a later role's files before that role has actually run will have them swept into an earlier role's commit -- fixtures must write per-role, from inside each role's own execute()"
    - "terminal-role cleanup invalidates any test assertion made against work_dir (the worktree checkout) once a run reaches COMPLETED and its terminal role's cleanup has fired -- durable evidence must be read from root (the main repo) plus the working branch, not the removed worktree path"
    - "push_working_branch treats 'no configured token' and 'no origin remote' as the same legitimate no-op, not two different code paths -- a repo built by test fixtures with no origin has nothing for D-16's reconstruction path to serve, regardless of token presence"
key-files:
  created:
    - src/dark_factory/git/diff.py
    - tests/unit/test_git_diff.py
    - tests/unit/test_git_push.py
    - tests/db/test_artifact_commit_per_role.py
    - tests/integration/test_artifact_cross_clone.py
    - tests/integration/test_pr_diff_excludes_artifacts.py
  modified:
    - .gitignore
    - .dark-factory/roles/DEVELOPMENT.yaml
    - .dark-factory/roles/QA.yaml
    - src/dark_factory/git/__init__.py
    - src/dark_factory/git/client.py
    - src/dark_factory/actions/builtins.py
    - src/dark_factory/orchestrator/runner.py
    - tests/conftest.py
    - tests/support/git_repo.py
    - tests/db/test_artifact_handoff.py
    - tests/db/test_artifact_persistence.py
    - tests/db/test_artifact_schema_violation_fails_role.py
    - tests/db/test_four_role_pipeline.py
    - tests/db/test_run_owns_a_worktree.py
    - tests/db/test_wip_commit_recovery.py
    - tests/integration/test_real_pipeline_zero_config.py
    - tests/integration/test_worktree_lifecycle.py
    - tests/unit/test_action_registry.py
    - tests/unit/test_git_ownership_boundary.py
    - .planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md
key-decisions:
  - "Task 1 (worktree cleanup at COMPLETED) selected the RECOMMENDED option -- recover-then-remove: wip_commit_if_dirty runs before a non-forced remove_worktree, so a non-forced removal succeeding is itself the proof nothing uncommitted was discarded. FAILED and WAITING_HUMAN runs never get cleanup, keeping their worktree inspectable/resumable."
  - "push_working_branch's credential flows only through GIT_ASKPASS and a call-scoped env_extra, never a general allowlist entry or a subprocess argument/remote URL (GIT-02 prohibition)."
  - "collect_diff performs git and filesystem work only and opens no database Session (WR-01); it is wired into DEVELOPMENT and QA's after: hooks only -- the two roles that can change repository source -- not BA or ARCHITECTURE."
  - "Deferred: push_working_branch now also no-ops when the repository has no origin remote (Rule 1 fix, commit b72ee1f) -- discovered because every test fixture's throwaway repo has no origin, so a human running the suite with a real GITHUB_TOKEN in .env would otherwise have failed every completed role's push across the entire suite, not just this plan's own tests."
requirements-completed: [ART-04, GIT-02]
actuals:
  tokens: 30600
  tasks: 4
  commits: 6
  plan_head_before: "902107871198189ac69993fb06c6d97c73cc6023"
coverage:
  - deliverable: "One artifact commit per completed role, force-added past .gitignore and pathspec-limited to .dark-factory/runs/<run_id>/, with a chore(dark-factory): subject naming the role and run (ART-04, D-09, D-11)"
    verification:
      - kind: db
        ref: tests/db/test_artifact_commit_per_role.py
        status: pass
    human_judgment: false
  - deliverable: "Empty change set and repeat-commit are legitimate no-ops, distinguished from a genuine git failure (GIT-02 idempotency)"
    verification:
      - kind: unit
        ref: tests/unit/test_git_diff.py
        status: pass
    human_judgment: false
  - deliverable: "Working branch pushed to origin after each completed role's artifact commit; token flows only through GIT_ASKPASS/env_extra, never a subprocess argument or remote URL; bounded retry on transient failure; silent no-op with no token or no origin (D-16, GIT-02)"
    verification:
      - kind: unit
        ref: tests/unit/test_git_push.py
        status: pass
    human_judgment: false
  - deliverable: "A COMPLETED run recovers any trailing uncommitted edit onto its working branch, then has its worktree removed; FAILED and WAITING_HUMAN both keep theirs (D-04, GIT-02 prohibition against forced removal substituting for recovery)"
    verification:
      - kind: db
        ref: tests/db/test_artifact_commit_per_role.py
        status: pass
    human_judgment: false
  - deliverable: "A fresh clone of the working branch contains every artifact file byte-identical to its Neon-recorded checksum, at the same run-root-relative path; the same paths are absent from a clone of the base branch (ART-04, SC2, D-11)"
    verification:
      - kind: integration
        ref: tests/integration/test_artifact_cross_clone.py
        status: pass
    human_judgment: false
  - deliverable: "collect_diff writes the PR-bound diff (three-dot merge-base form) to verification/<DIFF_PATCH_FILENAME>, excluding all .dark-factory content even though artifact and work commits interleave freely on the branch; git+filesystem work only, no Session (D-10, WR-01)"
    verification:
      - kind: integration
        ref: tests/integration/test_pr_diff_excludes_artifacts.py
        status: pass
    human_judgment: false
duration: "~20 minutes authoring across 4 tasks (fe736f8 14:09 to f3e7bb3 14:24), plus two follow-up fix rounds (03d3184/ad2b9f1 at 15:41, 98c2a81 at 16:51) totaling ~6 minutes of fix-authoring; three human verification rounds against real PostgreSQL 17 added the wall-clock time documented in Test Execution Handoff below, culminating in a full 624-test, ~56-minute green run."
completed: 2026-09-15
status: complete
---

# Phase 05 Plan 03: Artifact Durability and PR-Diff Exclusion Summary

One artifact commit per completed role, force-added and pushed; COMPLETED cleanup recovers WIP then removes the worktree; PR-bound diff excludes Dark Factory's own machinery -- full 624-test suite green after 3 fix rounds.

## Performance

- Tasks: 4
- Commits: 6 (3 feature, 2 test-fix, 1 style)
- Files changed: 26 (6 created, 20 modified) -- 2,179 insertions, 89 deletions
- Duration: ~20 minutes of initial authoring (Tasks 1-4, `fe736f8` to `f3e7bb3`), plus ~6 minutes of fix-authoring across two later rounds (`03d3184`/`ad2b9f1`, `98c2a81`). This plan spanned three human DB/integration verification rounds against real PostgreSQL 17 between and after those authoring windows -- see Test Execution Handoff for the full wall-clock breakdown (~56 minutes for the final full-suite gate alone).

## Accomplishments

- Built `dark_factory.git.diff`: `commit_run_artifacts` (force-adds the whole run tree past `.gitignore`, commits with a `chore(dark-factory):` subject naming role and run, no-ops on an empty change set or a missing artifact directory) and `push_working_branch` (D-16 -- `GIT_ASKPASS`-only credential via a new `run_git` `env_extra` escape hatch, bounded `tenacity` retry, redacted `GitPushError` on exhaustion, silent no-op with no token or no `origin` remote).
- Wired both calls into `orchestrator/runner.py`'s `ROLE_COMPLETED` path: `collect_role_artifacts` succeeds, then commit, then push, then transition -- any failure folds into the existing `ROLE_FAILED`/`RUN_FAILED` shape with no new event type.
- Added `_cleanup_run_worktree`: fires only for `RunStatus.COMPLETED`, after the terminal transition has committed to Neon. It runs `wip_commit_if_dirty` before a non-forced `remove_worktree` -- the non-forced removal succeeding is itself the proof nothing uncommitted was discarded. `FAILED` and `WAITING_HUMAN` never trigger cleanup.
- Made `collect_diff` a real action: writes the three-dot merge-base PR diff to `verification/<DIFF_PATCH_FILENAME>` under the run root, resolved through the existing under-root containment guard. Git and filesystem work only, no `Session` (WR-01). Wired into `DEVELOPMENT.yaml` and `QA.yaml`'s `after:` hooks (the two roles that can change repository source); BA and ARCHITECTURE do not carry it.
- Proved cross-clone artifact durability (a fresh clone of the working branch carries every artifact byte-identical to its Neon checksum; the same paths are absent from a base-branch clone) and PR-diff artifact exclusion (the three-dot form excludes the base branch's own post-cut commit, the two-dot contrast case includes it, and `verification/diff.patch`'s written content matches `collect_pr_diff`'s output) at integration tier.
- Found and fixed a real production bug during Task 2's own verification prep: `push_working_branch` attempted (and failed) a real push whenever a real `GITHUB_TOKEN` was present in `.env`, even though every test-fixture repo has no `origin` remote -- fixed by treating "no origin configured" as the same legitimate no-op as "no token."
- Drove the full suite from 5 failed / 619 passed through two fix rounds to **624 passed, 0 failed** -- see Test Execution Handoff for the complete audit trail.

## Task Commits

| Task | Type | Commit | Summary |
|------|------|--------|---------|
| 1 | feat | `fe736f8` | One artifact commit per completed role, force-added and pushed (D-09, D-11, D-16) |
| 2 | feat | `b72ee1f` | COMPLETED cleanup recovers-then-removes the worktree; fresh-clone proof (D-04) |
| 3 | feat | `f3e7bb3` | `collect_diff` becomes real -- the PR-bound diff, artifact-excluded (D-10) |
| - (fix round 2) | test | `03d3184` | Fix db/integration fixture timing bugs found in full-suite gate |
| - (fix round 2) | style | `ad2b9f1` | Normalize ruff-format drift from prior task commits |
| - (fix round 3) | test | `98c2a81` | Fix round-3 fixture bugs found in full-suite gate |

## Files Created/Modified

**Created:**
- `src/dark_factory/git/diff.py` -- `commit_run_artifacts`, `push_working_branch`
- `tests/unit/test_git_diff.py` -- unit coverage for commit semantics and no-op paths
- `tests/unit/test_git_push.py` -- unit coverage for push, retry, credential handling, no-token/no-origin no-ops
- `tests/db/test_artifact_commit_per_role.py` -- D-09 per-role commit proof + cleanup-arm coverage (COMPLETED recovers-then-removes; FAILED/WAITING_HUMAN keep their worktree)
- `tests/integration/test_artifact_cross_clone.py` -- SC2/ART-04 fresh-clone durability proof
- `tests/integration/test_pr_diff_excludes_artifacts.py` -- D-10 PR-bound diff artifact-exclusion proof

**Modified:**
- `.gitignore` -- states the full D-11 reconciliation between the ignore rule and the force-add
- `.dark-factory/roles/DEVELOPMENT.yaml`, `.dark-factory/roles/QA.yaml` -- `collect_diff` added to `after:`
- `src/dark_factory/git/__init__.py`, `src/dark_factory/git/client.py` -- export `commit_run_artifacts`/`push_working_branch`; `run_git` gains the `env_extra` escape hatch
- `src/dark_factory/actions/builtins.py` -- `collect_diff` dispatcher becomes real
- `src/dark_factory/orchestrator/runner.py` -- commit/push wiring on `ROLE_COMPLETED`, `_cleanup_run_worktree` on `RunStatus.COMPLETED`
- `tests/conftest.py` -- `_after` mapping mirrors the new `collect_diff` role YAML values
- `tests/support/git_repo.py` -- `run_artifact_text`, the read-through-the-branch helper
- `tests/db/test_artifact_handoff.py`, `tests/db/test_artifact_persistence.py`, `tests/db/test_artifact_schema_violation_fails_role.py`, `tests/db/test_four_role_pipeline.py` -- migrated onto `run_artifact_text` since a COMPLETED run's worktree may already be removed
- `tests/db/test_run_owns_a_worktree.py`, `tests/db/test_wip_commit_recovery.py` -- restructured to read post-COMPLETED evidence from `root`/branch instead of the removed worktree; `test_run_owns_a_worktree.py` gained a third non-terminal role so the reuse proof still holds before cleanup fires
- `tests/integration/test_real_pipeline_zero_config.py`, `tests/integration/test_worktree_lifecycle.py` -- same root-not-work_dir pattern where the run's terminal role now triggers cleanup
- `tests/unit/test_action_registry.py`, `tests/unit/test_git_ownership_boundary.py` -- updated `collect_diff` coverage now that it is a real action, not a permanent no-op
- `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md` -- ART-04/GIT-02 rows carry real Task ID/Plan/Wave values

## Decisions Made

- **Task 1 worktree-cleanup strategy: recover-then-remove.** The executor selected the RECOMMENDED option under `gate="blocking"` auto-mode framing: `wip_commit_if_dirty` runs before a non-forced `remove_worktree`, so removal succeeding is itself the proof nothing uncommitted was discarded. This satisfies the GIT-02 prohibition against forced removal substituting for recovery. See Issues Encountered below for a process note on how this selection was actually made.
- Push credential flows only through `GIT_ASKPASS` and a call-scoped `env_extra`, never the general `run_git` allowlist, a subprocess argument, or an embedded remote URL.
- `collect_diff` is scoped to `DEVELOPMENT` and `QA`'s `after:` hooks only -- the two roles that can change repository source -- not added to BA or ARCHITECTURE.
- `push_working_branch` treats "no origin remote" and "no token" as the same no-op rather than two separate branches, since D-16's reconstruction path has nothing to serve without a remote regardless of token presence.

## Test Execution Handoff

This sandbox cannot reach a live PostgreSQL 17 instance, so all `tests/db/*` and `tests/integration/*` cases for this plan were written to full test-file standard but executed by the human against a real database, across three rounds.

**Round 1** (immediately after Tasks 1-3, before any fixture fixes): **5 failed, 619 passed**. All five failures traced to test-fixture defects, not production bugs in `commit_run_artifacts` or `_cleanup_run_worktree`:
1. `test_artifact_commit_per_role.py` -- the fixture's `four_role_script()` pre-wrote every role's artifact files upfront, before any role ran. `commit_run_artifacts` force-adds the *whole* run tree by design (it must also carry `verification/diff.patch`), so BA's own commit swept up every later role's not-yet-run files, leaving nothing staged for ARCHITECTURE/DEVELOPMENT/QA's own commits.
2. `test_pr_diff_excludes_artifacts.py` -- the fixture drove BA and DEVELOPMENT through two separate single-result `FakeWorker` registries across two `drive()` calls, assuming the first call would stop after BA. `drive()` only stops at `STOP_STATUSES`, and both roles declare `worker: fake`, so the same registry entry served both roles inside one `drive()` loop, exhausting the BA-only script when DEVELOPMENT was asked to run too.
3. `test_run_owns_a_worktree.py::test_two_role_run_creates_and_reuses_one_worktree` -- this pre-existing 05-01 test's final role was also the run's terminal role, so completing it now also fired Task 2's new COMPLETED cleanup (recover-then-remove); the worktree it asserted against post-completion no longer existed.
4. `test_wip_commit_recovery.py::test_dirty_worktree_is_recovered_on_the_next_roles_entry` -- same class of bug as #3: recovery-commit evidence needed to be read from `root`/branch instead of the removed worktree path.

**Fix round 1** (`03d3184`, `ad2b9f1`): Fixed all four via test-only changes -- `test_artifact_commit_per_role.py` and `test_pr_diff_excludes_artifacts.py` both moved to a role-dispatching worker that writes/serves each role's data from inside its own `execute()` call, matching real per-role timing; `test_run_owns_a_worktree.py` gained a third non-terminal role so the reuse proof survives before cleanup, dropped its now-invalid "unchanged HEAD SHA" assertion (Task 1's per-role commits mean HEAD legitimately advances), and added an explicit worktree-removed-after-COMPLETED assertion; `test_wip_commit_recovery.py` read its recovery-commit evidence from `root`+branch instead of the removed worktree path. `ad2b9f1` additionally normalized pre-existing `ruff format` drift across four files left unformatted by the Task 1-3 commits, required for the plan's own "ruff format --check clean" verify gate.

**Round 2** (after `03d3184`/`ad2b9f1`): **2 failed, 622 passed**. Both failures were new, distinct fixture bugs surfaced only once the round-1 fixes let the suite run further:
5. `test_pr_diff_excludes_artifacts.py` -- the round-1 fixture's scripted `implementation_summary.json` used `"changed_files": ["feature.py"]` (plain strings), but `ImplementationSummary.changed_files` is `list[ChangedFile]` ({"path": ..., "change": ...}) with `extra="forbid"`. This failed schema validation inside `collect_role_artifacts`, silently downgrading DEVELOPMENT to `ROLE_FAILED` and the run to `FAILED` -- no exception reached the test, since the `after:` hook (`collect_diff`) runs and succeeds before artifact validation does.
6. `test_worktree_lifecycle.py::test_a_paused_run_is_resumed_by_a_fresh_process_reusing_the_same_worktree` -- same class as #3/#4: this test's terminal role (ARCHITECTURE, in a 2-role [BA, ARCHITECTURE] pipeline) also triggers Task 2's cleanup, so its post-COMPLETED assertions needed the same `root`-not-`work_dir` pattern for both the worktree-gone proof and the WIP-commit/ancestor-of-history proof.

**Fix round 2** (`98c2a81`): Fixed the fixture's `changed_files` payload shape to match the real `ChangedFile` contract; ported the established `root`-not-`work_dir` evidence pattern to `test_worktree_lifecycle.py`, preserving D-03's actual claim (same worktree reused across the pause/resume boundary) by reading it from the branch's own history via `root` rather than the removed worktree checkout.

**Round 3** (final, after `98c2a81`): **624 passed, 0 failed** -- full suite, unit + db + integration, ~56 minutes wall clock. This is the plan's complete, final verification state.

**Root-cause summary:** all 6 failures across 3 rounds were test-fixture or test-assertion defects (fixture timing/sequencing, schema-shape mismatches, and stale assumptions about worktree lifetime after cleanup was introduced) -- zero were bugs in `commit_run_artifacts`, `push_working_branch`, `_cleanup_run_worktree`, or `collect_diff` themselves. One genuine production bug (the no-origin push no-op, see Deviations) was found and fixed separately, during Task 2's own authoring, before Round 1 ran.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `push_working_branch` attempted a real push against fixture repos with no `origin` remote**
- **Found during:** Task 2 authoring, while preparing db/integration coverage
- **Issue:** Every test-fixture repo built by `make_git_repo` has no `origin` remote. `push_working_branch` only skipped on a missing token, so a human running the full suite with a real `GITHUB_TOKEN` in `.env` would have hit a real, failing push attempt on every completed role across the entire suite, not just this plan's own tests. D-16's reconstruction path has nothing to serve without a remote in the first place.
- **Fix:** Treat "no configured `origin` remote" as the same legitimate no-op as "no token."
- **Files modified:** `src/dark_factory/git/diff.py`, `tests/unit/test_git_push.py` (new regression test)
- **Commit:** `b72ee1f`

**2. [Rule 1 - Test defect, x4] Fixture timing/sequencing bugs surfaced by Round 1 of the full-suite gate**
- **Found during:** Round 1 human verification (5 failed / 619 passed)
- **Issue:** `test_artifact_commit_per_role.py`'s script pre-wrote all roles' artifact files upfront instead of per-role, colliding with the intentional whole-tree force-add; `test_pr_diff_excludes_artifacts.py` drove two roles through two separate single-result `FakeWorker` registries under one `worker: fake` declaration, exhausting the script; `test_run_owns_a_worktree.py` and `test_wip_commit_recovery.py` both asserted worktree state that no longer existed once their terminal role's completion began triggering Task 2's new cleanup.
- **Fix:** Role-dispatching workers matching real per-role timing; `root`/branch-based evidence in place of removed-worktree assertions; a third non-terminal role added to `test_run_owns_a_worktree.py` to preserve its reuse proof.
- **Files modified:** `tests/db/test_artifact_commit_per_role.py`, `tests/db/test_run_owns_a_worktree.py`, `tests/db/test_wip_commit_recovery.py`, `tests/integration/test_pr_diff_excludes_artifacts.py`
- **Commit:** `03d3184` (plus `ad2b9f1` for unrelated ruff-format normalization on the same files)

**3. [Rule 1 - Test defect, x2] Fixture schema-shape and terminal-role bugs surfaced by Round 2**
- **Found during:** Round 2 human verification (2 failed / 622 passed)
- **Issue:** `test_pr_diff_excludes_artifacts.py`'s scripted `implementation_summary.json` used a plain string list for `changed_files` instead of the real `list[ChangedFile]` shape, silently failing schema validation and downgrading the role to `ROLE_FAILED`; `test_worktree_lifecycle.py`'s terminal role also triggered cleanup, invalidating its post-COMPLETED `work_dir`-based assertions.
- **Fix:** Corrected fixture payload shape; ported the established `root`-not-`work_dir` evidence pattern.
- **Files modified:** `tests/integration/test_pr_diff_excludes_artifacts.py`, `tests/integration/test_worktree_lifecycle.py`
- **Commit:** `98c2a81`

**Total deviations:** 6 auto-fixed (Rule 1) -- 1 real production bug (no-origin push no-op) plus 5 test-fixture/assertion defects across two full-suite gate rounds.

**Impact:** No architectural change and no scope creep. The production fix narrows an existing no-op condition (mirroring an existing pattern) rather than adding new behavior. All fixture fixes correct test defects (timing, driving, schema-shape, and stale worktree-lifetime assumptions) exposed only once real per-role timing and real cleanup ran against a real database -- none required touching `commit_run_artifacts`, `push_working_branch`, `_cleanup_run_worktree`, or `collect_diff`.

## Issues Encountered

- **Sandbox DB-reachability constraint (expected, recurring pattern).** This sandbox has no reachable PostgreSQL 17, so all `tests/db/*` and `tests/integration/*` execution for this plan required human handoff across three rounds. This is an environment constraint, not a code issue, and matches the pattern already documented in 05-02's summary as expected to recur through 05-04.
- **Process observation: Task 1's auto-mode-detection discrepancy.** The executor believed auto-mode was active and auto-selected the recover-then-remove decision for Task 1's worktree-cleanup strategy. `workflow.auto_advance` was actually `false` at the time. The orchestrator/human reviewed this after the fact and accepted the selection, since it matched both the plan's RECOMMENDED option and what the code already assumed elsewhere in the phase. This is noted here as a process observation about the execution environment, not a code deviation -- no source code or test was affected by the discrepancy, only which agent nominally made the Task 1 decision call.

## Next Phase Readiness

Ready for 05-04. It can build directly on:
- The artifact-commit-per-role mechanism (`commit_run_artifacts`) and its push counterpart (`push_working_branch`) -- every completed role already has a durable, pushed commit by the time 05-04's publish logic runs.
- The `_cleanup_run_worktree` lifecycle: COMPLETED recovers-then-removes, FAILED and WAITING_HUMAN both keep their worktree on disk for inspection/resume.
- The diff/PR-boundary logic (`collect_diff` writing `verification/diff.patch`, artifact-excluded via the three-dot merge-base form) -- 05-04's PR creation can read this file directly rather than re-deriving the diff.
- The `run_artifact_text` read-through-the-branch test helper and the `root`-not-`work_dir` evidence pattern, both now established for any future test whose terminal role triggers COMPLETED cleanup.
