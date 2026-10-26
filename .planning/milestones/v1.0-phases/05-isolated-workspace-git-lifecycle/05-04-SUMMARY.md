---
phase: 05-isolated-workspace-git-lifecycle
plan: 04
subsystem: git-lifecycle
tags: [git, write-scope, authorization, config-validation, phase-gate]
dependency-graph:
  requires:
    - "05-01: the git worktree spine (dark_factory.git package skeleton), run.base_branch/working_branch, ensure_worktree"
    - "05-02: dark_factory.git.lifecycle (assert_attached_head, wip_commit_if_dirty), the before-hook control-flow seam in _run_current_role"
    - "05-03: dark_factory.git.diff (commit_run_artifacts, push_working_branch, ARTIFACT_EXCLUDE_PATHSPEC), the validate-then-commit-then-push ordering in the ROLE_COMPLETED branch this plan extends"
  provides:
    - "dark_factory.git.scope: is_out_of_scope (fnmatch.fnmatchcase, D-14 zero-tolerance-by-construction), attempt_changed_paths (two git invocations, artifact-excluded), revert_paths (branches on HEAD membership), enforce_write_scope (collects all violations, reverts before raising WriteScopeViolation), validate_write_scope_patterns (fail-loud config-time validation)"
    - "config/loader.py: write_scope patterns validated per role while resolving the snapshot, raising ConfigError before create_run"
    - "orchestrator/runner.py: enforce_write_scope wired into the Signal.ROLE_COMPLETED branch, after the artifact validate/commit/push sequence and before transition() -- validate, then commit, then push, then enforce scope, then transition"
    - "real write_scope values on the two write-capable shipped roles (DEVELOPMENT: src/**, QA: tests/**); BA/ARCHITECTURE keep [] as the documented intended zero-tolerance value"
    - "tests/integration/test_phase5_acceptance.py: the Phase 5 gate tying all four success criteria and all four requirement ids to named, non-empty, non-skipping proofs"
  affects:
    - "Phase 5 is closed by this plan -- no further plans depend on this one within the phase; a later phase (6+) that adds tools/permissions work builds on write_scope as an established, enforced pattern rather than a snapshotted-but-inert config value"
tech-stack:
  added: []
  patterns:
    - "the matcher is a single expression with no branch on the empty-list case -- zero tolerance (D-14) falls out of `not any(...)` over an empty iterable for free; any future write_scope-shaped boundary in this codebase should copy this idiom rather than special-casing 'empty means unrestricted'"
    - "revert_paths branches on git cat-file -e HEAD:<path> before choosing restore vs rm+clean -- a single-mechanism revert silently leaves a newly-created violating file on disk; any future targeted-revert logic in this codebase should branch the same way"
    - "config-time validation of a boundary-defining string list (write_scope) follows the same fail-loud ConfigError convention as every other loader.py check -- reject at load time, never discover a malformed value at enforcement time"
key-files:
  created:
    - src/dark_factory/git/scope.py
    - tests/unit/test_write_scope.py
    - tests/integration/test_write_scope_enforcement.py
    - tests/integration/test_phase5_acceptance.py
    - .planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md
  modified:
    - src/dark_factory/git/__init__.py
    - src/dark_factory/config/loader.py
    - src/dark_factory/orchestrator/runner.py
    - .dark-factory/roles/DEVELOPMENT.yaml
    - .dark-factory/roles/QA.yaml
    - .dark-factory/roles/BA.yaml
    - .dark-factory/roles/ARCHITECTURE.yaml
    - tests/conftest.py
    - .planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md
key-decisions:
  - "is_out_of_scope's body is exactly `not any(fnmatch.fnmatchcase(path, pattern) for pattern in write_scope)` with no early-return branch for the empty-list case -- the intuitive `if not write_scope: return False` was deliberately never written, since it silently inverts D-14 and would grant write access to every read-only role."
  - "A write-scope violation clears artifact_writes (no ArtifactReference rows persisted) even though the artifact content itself is already durably committed on the working branch by the time the check runs -- mirrors the existing GitError branch's convention that a FAILED attempt records no artifacts rows, keeping the FAILED-attempt invariant uniform across all three failure paths in _run_current_role (schema violation, git commit/push failure, write-scope violation)."
  - "The revert mechanism branches on `git cat-file -e HEAD:<path>` (check=False) rather than attempting a single restore-or-clean call -- a tracked edit is restored via `git restore --source=HEAD --staged --worktree`, a new file is cleared from the index (if staged) then removed with `git clean --force`, each acting on exactly the one supplied path and nothing else."
  - "validate_write_scope_patterns defines 'malformed' as four concrete shapes (empty/whitespace, absolute, './'-prefixed, containing a '..' segment) rather than attempting to detect an fnmatch syntax error, since fnmatch.translate() has no such error class to validate against."
patterns-established:
  - "zero-tolerance-by-construction: a security-relevant matcher over an optionally-empty allowlist should express its default-deny case as a property of the boolean expression, not a branch that a later edit could silently flip."
  - "revert-by-HEAD-membership: any future targeted-revert-of-untrusted-changes logic in this codebase should probe HEAD membership per path before choosing its revert mechanism, exactly as dark_factory.git.scope.revert_paths does."
requirements-completed: [ROLE-05]
actuals:
  tokens: 17600
  tasks: 3
  commits: 3
  plan_head_before: "43cf8ca707c88dae76d04d34349200577e5d1b62"
coverage:
  - deliverable: "write_scope matcher (is_out_of_scope), config-time pattern validation (validate_write_scope_patterns), the containment guard, and the targeted revert (revert_paths, enforce_write_scope) in a new dark_factory.git.scope module"
    requirement: ROLE-05
    verification:
      - kind: unit
        ref: "tests/unit/test_write_scope.py"
        status: pass
    human_judgment: false
  - deliverable: "config/loader.py calls validate_write_scope_patterns per role while resolving the snapshot, raising ConfigError before create_run for a malformed pattern"
    requirement: ROLE-05
    verification:
      - kind: unit
        ref: "tests/unit/test_repo_config_schema.py"
        status: pass
      - kind: other
        ref: "uv run python -c one-liner asserting load_effective_config resolves DEVELOPMENT to ['src/**'], QA to ['tests/**'], BA/ARCHITECTURE to [] against this repo's own shipped .dark-factory/roles/*.yaml"
        status: pass
    human_judgment: false
  - deliverable: "DEVELOPMENT.yaml/QA.yaml ship real write_scope patterns (src/**, tests/**); BA.yaml/ARCHITECTURE.yaml keep [] with a comment naming it the intended zero-tolerance value, not a placeholder; tests/conftest.py's _write_config_tree mirrors the same four values"
    requirement: ROLE-05
    verification:
      - kind: other
        ref: "uv run python -c load_effective_config assertion (same command as above); grep -c 'PurePath'/'reset --hard' negative checks against scope.py"
        status: pass
    human_judgment: false
  - deliverable: "enforce_write_scope wired into orchestrator/runner.py's Signal.ROLE_COMPLETED branch, after the artifact validate/commit/push sequence and before transition() -- a violation downgrades the signal to ROLE_FAILED through the existing failure branch with no new event type or role-execution status"
    requirement: ROLE-05
    verification:
      - kind: integration
        ref: "tests/integration/test_write_scope_enforcement.py (6 scenarios: in-scope edit completes; tracked-edit violation restored from HEAD; new-file violation removed from disk and the index; empty write_scope fails on any change; a later role is not failed for an earlier role's legitimate edit; a role that ships a valid artifact and a violation in the same attempt still fails while the artifact survives on the branch)"
        status: unknown
    human_judgment: true
    rationale: "This sandbox has no reachable PostgreSQL 17 (confirmed this session: `uv run pytest -m db ...` raises pytest.UsageError -- Docker absent, no local initdb, DARK_FACTORY_TEST_DATABASE_URL unset), so the integration/db tiers cannot execute here. The test file was authored to full standard, mirrors the established db-tier idioms from tests/db/test_artifact_commit_per_role.py and tests/db/test_artifact_schema_violation_fails_role.py, was collected cleanly by pytest (`--collect-only`, 6 tests, zero fixture errors), and imports/compiles cleanly. This is the same recurring DB-reachability handoff pattern 05-02-SUMMARY.md and 05-03-SUMMARY.md already documented -- a human with real PostgreSQL 17 access must run it to convert this to a real PASS."
  - deliverable: "The Phase 5 acceptance gate (tests/integration/test_phase5_acceptance.py) maps all four ROADMAP Phase 5 success criteria and all four requirement ids (GIT-01, GIT-02, ART-04, ROLE-05) to named proof files, asserts each proof exists/is non-empty/contains a test, fails rather than skips on a gap, and drift-guards against 05-VALIDATION.md's Per-Task Verification Map"
    requirement: ROLE-05
    verification:
      - kind: other
        ref: "uv run python -c manually invoking every gate function (test_every_phase_5_success_criterion_is_mapped, test_every_phase_5_requirement_id_is_mapped, _assert_proofs_exist per criterion/requirement, test_no_mapped_proof_path_is_missing, test_validation_strategy_and_gate_cannot_drift) directly in this session, bypassing pytest's autouse _schema_at_head fixture -- which forces PostgreSQL-17 provisioning for ANY collected test carrying the integration marker, regardless of whether that specific test queries a database. All six checks passed."
        status: pass
      - kind: integration
        ref: "tests/integration/test_phase5_acceptance.py, run through pytest itself"
        status: unknown
    human_judgment: true
    rationale: "The gate's own logic does no database work -- it is pure filesystem/string assertions -- but this project's tests/conftest.py::_schema_at_head autouse session fixture provisions PostgreSQL for the whole session whenever any collected test carries the `integration` marker, which this file (correctly, matching test_phase4_acceptance.py's own marker) does. Confirmed this is a pre-existing, session-wide sandbox limitation, not specific to this file: `uv run pytest -q tests/integration/test_phase4_acceptance.py` (an already-merged, previously-verified-green gate from an earlier phase) fails identically in this same sandbox. The manual bypass above is a legitimate substitute proof of the gate's own logic; a human must still run it through real pytest for the canonical PASS."
  - deliverable: "05-VALIDATION.md closed out: every Per-Task Verification Map row carries real Task ID/Plan/Wave values (including fixing the GIT-01/GIT-02/ART-04 rows that earlier plans' summaries claimed were filled but were still showing placeholder Threat Ref/File-Exists values), every Wave 0 box ticked, all six sign-off items ticked, nyquist_compliant: true, status: validated, and an approval line naming the one item still pending human DB execution"
    requirement: ROLE-05
    verification:
      - kind: other
        ref: "grep -q 'nyquist_compliant: true' / grep -q 'status: validated' against 05-VALIDATION.md; grep -c TBD confirms zero TBD left in the Per-Task Verification Map"
        status: pass
    human_judgment: false
duration: "~12 minutes of commit-to-commit authoring across 3 task commits (9d08b53 18:50:53 to 4a031b5 19:02:16, 2026-09-15), preceded by an extensive context-loading and source-reading pass (PLAN.md, PROJECT.md, STATE.md, config.json, 05-CONTEXT.md, 05-RESEARCH.md, 05-PATTERNS.md, 05-VALIDATION.md, 05-02/05-03-SUMMARY.md, and every read_first file named by all three tasks) not separately timed."
completed: 2026-09-15
status: complete
---

# Phase 5 Plan 4: Write-Scope Enforcement and the Phase 5 Acceptance Gate Summary

**write_scope enforcement via fnmatch.fnmatchcase with zero-tolerance-by-construction on the empty list, a HEAD-membership-branched targeted revert, and the Phase 5 acceptance gate tying all four success criteria and requirement ids to named proofs -- closing the phase.**

## Performance

- Duration: ~12 minutes of commit-to-commit authoring (see frontmatter `duration`)
- Started: 2026-09-15 (session start, exact wall-clock not separately tracked)
- Completed: 2026-09-15
- Tasks: 3/3
- Files modified: 14 (5 created, 9 modified)

## Accomplishments

- Built `dark_factory.git.scope`: `is_out_of_scope` (a single-expression matcher with no empty-list special case -- D-14's zero tolerance falls out of the expression itself), `attempt_changed_paths` (exactly two git invocations, artifact-excluded, sorted and de-duplicated), the `_resolve_in_worktree` containment guard (mirrors `artifacts/paths.py::resolve_under_run_root`'s T-04-01 pattern), `revert_paths` (branches on `git cat-file -e HEAD:<path>` before choosing `git restore --source=HEAD --staged --worktree` vs. `git rm --cached --force` + `git clean --force`), `enforce_write_scope` (collects every violation before reverting and raising), and `validate_write_scope_patterns` (four concrete malformed-pattern shapes: empty/whitespace, absolute, `./`-prefixed, containing a `..` segment).
- Wired `validate_write_scope_patterns` into `config/loader.py::load_effective_config`, raising `ConfigError` naming the role file and the offending pattern before any `runs` row is created.
- Shipped real `write_scope` values: `DEVELOPMENT.yaml` -> `["src/**"]`, `QA.yaml` -> `["tests/**"]`; `BA.yaml`/`ARCHITECTURE.yaml` keep `[]` with a comment stating it is the intended zero-tolerance value (D-14), not a placeholder. `tests/conftest.py`'s `_write_config_tree` mirrors all four values.
- Wired `enforce_write_scope` into `orchestrator/runner.py`'s `Signal.ROLE_COMPLETED` branch, immediately after the D-09/D-16 artifact validate/commit/push sequence and before `transition(...)` is computed -- a `WriteScopeViolation` downgrades the signal to `ROLE_FAILED` through the exact existing failure branch (no new event type, no new role-execution status) and clears `artifact_writes` for the same reason the `GitError` branch already does.
- Proved the matcher against exactly the two cases that distinguish a correct `fnmatch`-based implementation from the plausible-but-wrong `pathlib`-based one: deep nesting (3+ segments below the pattern root) and a decoy directory (the pattern root as a non-leading path segment) -- plus prefix-collision, multi-pattern disjunction, extension scoping, case sensitivity, and the empty-list zero-tolerance case (`tests/unit/test_write_scope.py`, 16 tests, all green in this session).
- Authored the SC4 integration proof (`tests/integration/test_write_scope_enforcement.py`, 6 scenarios) covering every behavior bullet the plan specified, including the two cases RESEARCH flagged as easy to get silently wrong (the tracked-edit revert verified against the HEAD blob via `git show`, not just re-reading the file; the new-file revert verified absent from both disk and `git ls-files --cached`).
- Built the Phase 5 acceptance gate (`tests/integration/test_phase5_acceptance.py`), a sibling of the Phase 3/4 gates, mapping all four ROADMAP success criteria and all four requirement ids to named, non-empty, test-containing proof files, failing rather than skipping on a gap, and drift-guarded against `05-VALIDATION.md`.
- Closed out `05-VALIDATION.md`: filled every Per-Task Verification Map row with real Task ID/Plan/Wave values (discovering and fixing that the GIT-01/GIT-02/ART-04 rows were still carrying `T-05-TBD` / `❌ W0` placeholders despite 05-02's and 05-03's own summaries claiming they were filled), ticked every Wave 0 box, ticked all six sign-off items, and set `nyquist_compliant: true` / `status: validated`.

## Task Commits

| Task | Type | Commit | Summary |
|------|------|--------|---------|
| 1 | feat | `9d08b53` | The matcher, the targeted revert, and fail-loud pattern validation (`dark_factory.git.scope`, `config/loader.py`, the four shipped role YAMLs, `tests/conftest.py`) |
| 2 | feat | `70c386c` | Enforcement wired into the role step (`orchestrator/runner.py`) with both violation shapes proven end to end (`tests/integration/test_write_scope_enforcement.py`) |
| 3 | test | `4a031b5` | The matcher unit suite and the Phase 5 acceptance gate (`tests/unit/test_write_scope.py`, `tests/integration/test_phase5_acceptance.py`, `05-VALIDATION.md` close-out, `deferred-items.md`) |

## Files Created/Modified

**Created:**
- `src/dark_factory/git/scope.py` -- the write-scope matcher, containment guard, targeted revert, enforcement entry point, and config-time pattern validation
- `tests/unit/test_write_scope.py` -- the matcher proof (16 tests)
- `tests/integration/test_write_scope_enforcement.py` -- the SC4 proof (6 scenarios, authored to full standard, not executed in this sandbox -- see Test Execution Handoff)
- `tests/integration/test_phase5_acceptance.py` -- the Phase 5 acceptance gate
- `.planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md` -- logs a pre-existing, out-of-scope leftover git-worktree/branch accumulation in this checkout

**Modified:**
- `src/dark_factory/git/__init__.py` -- exports the new `scope` module surface; updated the `WriteScopeViolation` docstring entry now that it is actually raised
- `src/dark_factory/config/loader.py` -- calls `validate_write_scope_patterns` per role; `RolePermissions`'s docstring updated to reflect enforcement is now real, not deferred
- `src/dark_factory/orchestrator/runner.py` -- `enforce_write_scope` wired into `_run_current_role`'s `Signal.ROLE_COMPLETED` branch; docstring extended with the ROLE-05/D-12/D-13/D-14 paragraph
- `.dark-factory/roles/DEVELOPMENT.yaml`, `.dark-factory/roles/QA.yaml` -- real `write_scope` patterns, updated comments
- `.dark-factory/roles/BA.yaml`, `.dark-factory/roles/ARCHITECTURE.yaml` -- comment added stating `[]` is the intended zero-tolerance value, not a placeholder
- `tests/conftest.py` -- `_write_config_tree` writes the same four `write_scope` values as the shipped role YAMLs
- `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md` -- closed out per Task 3 (see Accomplishments)

## Decisions Made

- **`is_out_of_scope`'s body is exactly one expression with no empty-list branch.** D-14's zero tolerance is a property of `not any(...)` over an empty iterable, not a special case -- deliberately, so there is no line a future edit could flip to silently grant write access to a read-only role.
- **The revert mechanism branches on HEAD membership** (`git cat-file -e HEAD:<path>`, `check=False`) rather than attempting one universal revert call -- research proved a single-mechanism revert leaves a newly-created violating file on disk (and possibly staged) while appearing to succeed.
- **A write-scope violation clears `artifact_writes`**, matching the existing `GitError` branch's convention, even though the artifact content is already durably committed on the working branch by the time the check runs -- keeps the "a FAILED attempt records no `artifacts` rows" invariant uniform across all three failure paths in `_run_current_role`.
- **Malformed `write_scope` pattern is defined as four concrete shapes** (empty/whitespace, absolute, `./`-prefixed, `..`-segment) rather than an attempt to detect an `fnmatch` syntax error, since none exists to detect.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Documentation defect] 05-VALIDATION.md's GIT-01/GIT-02/ART-04 rows were not actually filled despite 05-02's and 05-03's own summaries claiming they were**
- **Found during:** Task 3, closing out `05-VALIDATION.md`
- **Issue:** `05-02-SUMMARY.md` states "`.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md` -- Per-Task Verification Map filled in for GIT-01/GIT-02 rows" and `05-03-SUMMARY.md` states "ART-04/GIT-02 rows carry real Task ID/Plan/Wave values", but reading the actual file at the start of this plan showed the GIT-01 rows still carrying `T-05-TBD / —` and `❌ W0`, and the GIT-02 row likewise -- only the ART-04 row had a real Threat Ref and a ✅ File Exists mark.
- **Fix:** Filled the Threat Ref (`T-05-09` for GIT-01, drawn from `05-01-PLAN.md`'s own threat register; `T-05-01` for GIT-02, drawn from the same source), File Exists, and Status columns for all four pre-existing rows, in addition to the two new ROLE-05 rows this plan adds.
- **Files modified:** `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md`
- **Commit:** `4a031b5`

**Total deviations:** 1 auto-fixed (Rule 1 -- documentation defect, not a code bug).

**Impact:** No code change; no architectural change. A trailing documentation-accuracy gap from two earlier plans was closed as part of this plan's own Task 3 action item ("confirm every earlier row was filled by plans 05-02 and 05-03 and fill any that was missed").

## Issues Encountered

- **This sandbox has no reachable PostgreSQL 17** (confirmed directly this session: `uv run pytest -m db tests/db/test_role_executions_wip_commit_sha_schema.py` raises `pytest.UsageError` -- Docker absent, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset). This is the exact recurring pattern `05-02-SUMMARY.md` and `05-03-SUMMARY.md` already documented and flagged as "expected to recur through 05-04." `tests/integration/test_write_scope_enforcement.py` (the SC4 proof) and `tests/integration/test_phase5_acceptance.py` (the acceptance gate, whose own logic is pure-filesystem but which still triggers `tests/conftest.py::_schema_at_head`'s session-wide autouse provisioning because it carries the `integration` marker) could therefore not be run through `pytest` in this sandbox. Both files were authored to full standard, collected cleanly by `pytest --collect-only` with zero fixture errors, and (for the acceptance gate) had every one of their assertion functions manually invoked directly in Python to confirm the gate's own logic is correct, bypassing only the DB-provisioning fixture. A human with real PostgreSQL 17 access must run both to convert these from "authored and self-consistency-checked" to a canonical pytest PASS -- see `05-VALIDATION.md`'s Per-Task Verification Map and Approval line, and the `coverage` block above.
- **Pre-existing repo hygiene gap, out of scope, logged and not fixed.** This checkout's own `git worktree list`/`git branch --list 'dark-factory/*'` show 24 more worktrees and branches than the clean-checkout invariant Task 3's `<verify>` block expects, dating back (by commit content) to an earlier phase and unrelated to this plan's own execution (which created no worktrees or branches in this sandbox). See `.planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md` for the full account and the recommended human follow-up (`git worktree prune` + a review pass over the 24 branches).

## User Setup Required

None for this plan's own deliverables. Outstanding from Issues Encountered above: a human with real PostgreSQL 17 access should run `set -a; . ./.env; set +a; uv run pytest -q` (the full suite) to convert `tests/integration/test_write_scope_enforcement.py` and `tests/integration/test_phase5_acceptance.py` from authored-and-collected to a canonical green, and should separately review/prune the pre-existing leftover worktrees and branches logged in `deferred-items.md`.

## Carried Assumptions (outlive this phase)

Restated here, per this plan's own Task 3 action item, so the next planner inherits them rather than rediscovering them:

- **A-05-03 (still UNRESOLVED).** Cross-machine transport (SSH, rsync, actual "another machine" orchestration) remains Phase 11's concern. This phase only established that a fresh `git clone` + checkout of the working branch has the artifact content available -- it does not perform the cross-machine hop itself.
- **A-05-01.** A role YAML that omits `ensure_clean_worktree` from its `before:` list forgoes WIP-commit recovery and detached-HEAD protection entirely for that role -- the action is real-but-opt-in (registry-dispatched), not an unconditional `runner.py` call, deliberately, per D-06's literal wording. Every currently-shipped role lists it; a future role YAML that forgets to is a silent regression, not a loud one.
- **A-05-10.** The PR-bound diff `collect_diff` writes (`verification/diff.patch`) is a commit-range diff (`base...working`), so at the moment a role's `after:` hook runs, that role's own still-uncommitted edits are not yet in it -- they join on the next role's entry (WIP recovery) or the terminal role's `COMPLETED` cleanup pass. The diff is complete only once a run finishes, which is exactly when Phase 9's quality gate and Phase 10's publisher read it.
- **A-05-16.** The crash-mid-revert path -- a process killed partway through `revert_paths` iterating multiple violating paths -- is reasoned about (the next entry's recovery pass commits whatever remains, so nothing is destroyed, and the attempt re-runs against a clean tree) but not directly exercised by a test in this phase.

## Next Phase Readiness

**Phase 5 is complete, ready for the next step.** All four Phase 5 success criteria (SC1-SC4) and all four requirement ids (GIT-01, GIT-02, ART-04, ROLE-05) are now tied to named, non-empty, non-skipping proofs by `tests/integration/test_phase5_acceptance.py`. `05-VALIDATION.md` is closed out: `nyquist_compliant: true`, `status: validated`, every Per-Task row filled, every Wave 0 box ticked, all six sign-off items ticked. One integration-tier proof (`test_write_scope_enforcement.py`) and the acceptance gate itself still need a human's real-PostgreSQL-17 `pytest` run to convert from "authored and self-consistency-checked" to a canonical green -- see Issues Encountered and User Setup Required above.

Phase 5 leaves a fully enforced `write_scope` boundary (ROLE-05), a durable per-role artifact commit/push mechanism (ART-04), an artifact-excluded PR-bound diff, WIP-commit crash recovery and detached-HEAD hard-stop (GIT-01), and a git ownership boundary confined entirely to `dark_factory.git` (GIT-02) for Phase 6 (Tools, Permissions & the Credential Boundary) to build on.

*Phase: 05-isolated-workspace-git-lifecycle*
*Completed: 2026-09-15*

## Self-Check: PASSED

All created files found on disk; all three task commit hashes (`9d08b53`, `70c386c`, `4a031b5`) found in `git log --oneline --all`.
