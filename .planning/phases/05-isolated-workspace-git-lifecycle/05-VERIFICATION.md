---
phase: 05-isolated-workspace-git-lifecycle
verified: 2026-09-16T18:20:00Z
status: passed
score: 4/4 truths verified
covered_files: [".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".gitignore", ".planning/REQUIREMENTS.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-01-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-01-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-02-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-02-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-03-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-03-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-04-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-04-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-05-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-05-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-06-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-06-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW-FIX.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-UAT.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md", ".planning/phases/05-isolated-workspace-git-lifecycle/deferred-items.md", "migrations/versions/0005_wip_commit_sha.py", "src/dark_factory/actions/builtins.py", "src/dark_factory/actions/context.py", "src/dark_factory/config/loader.py", "src/dark_factory/events/catalog.py", "src/dark_factory/events/redaction.py", "src/dark_factory/git/__init__.py", "src/dark_factory/git/client.py", "src/dark_factory/git/diff.py", "src/dark_factory/git/lifecycle.py", "src/dark_factory/git/scope.py", "src/dark_factory/git/worktree.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/persistence/models.py", "src/dark_factory/persistence/mutations.py", "src/dark_factory/persistence/repositories.py", "src/dark_factory/workers/fake.py", "tests/integration/test_phase5_acceptance.py", "tests/integration/test_write_scope_enforcement.py", "tests/unit/test_write_scope_revert.py"]
covered_digest: "v1:sha256:3acba3c57ce121ce52a6bf6b6b2c7967a5149840fb0334870b1803905ce8b3b4"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 3/4
  gaps_closed:
    - "SC4 / ROLE-05 — write-scope enforcement's revert/fail behavior, previously PRESENT_BEHAVIOR_UNVERIFIED (never executed against a real database), is now behaviorally proven: 6/6 tests/integration/test_write_scope_enforcement.py scenarios independently re-run against a real PostgreSQL 17 in this verification session, all passing (G-05-1)."
    - "CR-02 (revert_paths' escape-ordering fix) previously had zero executed regression coverage at any tier; tests/unit/test_write_scope_revert.py now exists with 7 DB-free unit tests, independently re-run in this session, all passing (G-05-2)."
  gaps_remaining: []
  regressions: []
coincidental_reliance_items: []
---

# Phase 5: Isolated Workspace & Git Lifecycle Verification Report

**Phase Goal:** Every run owns an explicit working branch and a clean worktree that all roles share, Dark Factory owns the git actions, and the run's artifacts travel with it to another machine.
**Verified:** 2026-09-16
**Status:** passed
**Re-verification:** Yes — after gap closure (05-05, 05-06, closing G-05-1 and G-05-2 from 05-UAT.md)

## Goal Achievement

### Observable Truths (ROADMAP Phase 5 Success Criteria, verbatim)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | "A run creates a working branch from the configured base branch, named so it is unique to the run id, and every role executes against that same worktree." | ✓ VERIFIED | Unchanged since prior verification round (no `src/` changes in this session's two gap-closure plans, confirmed via `git log --stat` on `05-05`/`05-06` commits). `src/dark_factory/git/worktree.py::ensure_worktree`/`working_branch_name`, `persistence/mutations.py::create_run`, `orchestrator/runner.py`'s unconditional `ensure_worktree` call, all re-confirmed present in this session's reads. |
| SC2 | "A process on a different machine, given only the run id and a fresh clone, has the run's artifact content available to rebuild context and continue." | ✓ VERIFIED | Unchanged since prior round. `src/dark_factory/git/diff.py::commit_run_artifacts`/`push_working_branch` untouched by this session's changes. |
| SC3 | "A role that finishes with uncommitted changes is recovered on next entry ... and an entry on a detached HEAD fails the role with a persisted event instead of proceeding." | ✓ VERIFIED | Unchanged since prior round; `git/lifecycle.py` untouched by this session's changes. Previously human-executed with a named-test PASS transcript (05-02-SUMMARY.md). |
| SC4 | "A role whose diff touches paths outside its configured write scope (QA touching production code) fails the role; the out-of-scope edit is reverted and the violation is logged." | ✓ VERIFIED (upgraded from ⚠️ PRESENT_BEHAVIOR_UNVERIFIED) | Behavior-dependent (cleanup/revert invariant). **Independently re-run in this verification session** (not taken from SUMMARY claims): `set -a; . ./.env; set +a; uv run pytest -q tests/integration/test_write_scope_enforcement.py -v` against the externally-supplied PostgreSQL 17 → **6 passed in 119.84s**, zero skipped. `test_an_in_scope_edit_completes_with_no_revert` (the previously-failing scenario, G-05-1) now reads the in-scope edit through `read_committed(root, working_branch_name(run_id), "src/app.py")` and separately asserts `not work_dir.exists()` — read and confirmed at `tests/integration/test_write_scope_enforcement.py:283-317`. CR-02's escape-ordering fix (G-05-2), previously with zero test coverage at any tier, is now proven at the unit tier: `uv run pytest -m unit -q tests/unit/test_write_scope_revert.py` → **7 passed in 2.60s**, no database. Read the full file (268 lines) — all 6 revert-level cases (escape-first, escape-last, escape-only, multiple-escapes, escape-never-acted-upon, single-raise-naming) plus 1 `enforce_write_scope`-level ordering proof are present and match their described intent, not stubs. Production code (`src/dark_factory/git/scope.py::revert_paths`/`enforce_write_scope`) read directly and confirmed to match the CR-02 fix description (per-path `try`/`except` collecting escapes, single raise after the loop, lines 214-247). |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Gap Closure Verification (G-05-1, G-05-2)

Both gaps from `05-UAT.md` were independently re-verified in this session by directly executing the test commands the gap-closure plans claimed to satisfy — not by trusting 05-05-SUMMARY.md / 05-06-SUMMARY.md's reported pass counts:

| Gap | Claim | Independently re-run | Result |
|-----|-------|----------------------|--------|
| G-05-1 | All 6 SC4 scenarios pass against real PostgreSQL 17 | `uv run pytest -q tests/integration/test_write_scope_enforcement.py -v` | **6 passed in 119.84s** — matches claim |
| G-05-2 | CR-02 regression suite (7 tests) passes, no database | `uv run pytest -m unit -q tests/unit/test_write_scope_revert.py` | **7 passed in 2.60s** — matches claim |
| Both | Phase 5 acceptance gate green with the new proof registered under SC4/ROLE-05 | `uv run pytest -q tests/integration/test_phase5_acceptance.py -v` | **12 passed in 3.19s** — matches claim |
| Both | Zero production source changes | `git log --stat` on `d494c33`, `0017004`, `1c8296e`, `26d5ec5` | Confirmed: only `tests/*.py` and `05-VALIDATION.md` touched; zero `src/` diffs |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/integration/test_write_scope_enforcement.py` | `test_an_in_scope_edit_completes_with_no_revert` reads via `read_committed`/`working_branch_name`, asserts `work_dir` gone | ✓ VERIFIED | Confirmed at lines 283-317; `read_committed` import added at line 56; all 6 scenarios pass live |
| `tests/unit/test_write_scope_revert.py` | CR-02 regression suite: escape-ordering, boundary neighbours, enforce-level ordering proof | ✓ VERIFIED | New file, 268 lines, 7 tests, unit-marked (`pytestmark = pytest.mark.unit`), imports `revert_paths`/`enforce_write_scope` directly (no DB import, no `drive()` call — confirmed by read), all 7 pass live |
| `tests/integration/test_phase5_acceptance.py` | SC4/ROLE-05 tuples and `_VALIDATION_PROOF_FILES` extended with the new proof | ✓ VERIFIED | `grep -c 'tests/unit/test_write_scope_revert.py'` = 3 (SC4 tuple, ROLE-05 tuple, `_VALIDATION_PROOF_FILES`); gate passes 12/12 live |
| `.planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md` | New proof row under ROLE-05 | ✓ VERIFIED | Row present at line 49, marked "✅ green (05-06, 7 passed, no database)" |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `test_an_in_scope_edit_completes_with_no_revert` | `tests.support.git_repo.read_committed` | `read_committed(root, working_branch_name(run_id), "src/app.py")` | ✓ WIRED | Confirmed at line 311; import at line 56 |
| `_cleanup_run_worktree` (runner.py) | `wip_commit_if_dirty` → `remove_worktree` (D-04) | committed to working branch before worktree removal | ✓ WIRED | `grep -c 'remove_worktree' runner.py` ≥ 1; behavior directly proven by the passing scenario (in-scope content survives on branch, worktree gone) |
| `tests/unit/test_write_scope_revert.py` | `dark_factory.git.scope.revert_paths` / `enforce_write_scope` | direct import, no DB, no orchestrator | ✓ WIRED | Confirmed at line 44; first direct import of the revert path anywhere in the suite |
| `enforce_write_scope`'s `sorted(...)` | escape-first ordering in production | `test_enforce_write_scope_produces_the_escape_first_ordering_itself` | ✓ WIRED | Confirmed at scope.py:268 (`sorted(path for path in changed if is_out_of_scope(...))`), exercised end-to-end by the 7th unit test, passing |

### Behavioral Spot-Checks (independently executed this session)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC4 full proof file, real PostgreSQL 17 | `uv run pytest -q tests/integration/test_write_scope_enforcement.py -v` | 6 passed in 119.84s, 0 failed, 0 skipped | ✓ PASS |
| CR-02 regression suite, no database | `uv run pytest -m unit -q tests/unit/test_write_scope_revert.py` | 7 passed in 2.60s | ✓ PASS |
| Phase 5 acceptance gate, real PostgreSQL 17 | `uv run pytest -q tests/integration/test_phase5_acceptance.py -v` | 12 passed in 3.19s | ✓ PASS |
| Debt-marker scan on all files touched by 05-05/05-06 | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across the 4 changed files | 0 matches | ✓ PASS |
| Production-code diff scope | `git log --stat` on the 4 gap-closure commits | Only `tests/*.py` + `05-VALIDATION.md`; zero `src/` changes | ✓ PASS |
| Full regression suite (started, background) | `uv run pytest -q` (all tiers, real PostgreSQL 17) | Still running at time of report (>4 min elapsed, remote-DB round-trip bound); not required for the phase-goal truths above, which were each independently proven via targeted runs | ? SKIP (supplementary, not load-bearing for this verdict — UAT test 3 was explicitly "blocked pending 1-2" and is not one of the two gaps this round closes) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| GIT-01 | 05-01, 05-02 | Each run has an explicit working branch from the configured base branch; all roles operate on the same run repository state | ✓ SATISFIED | SC1/SC3 evidence above. REQUIREMENTS.md now correctly shows `- [x] GIT-01` and "Complete" in the traceability table (the stale-tracker issue the prior verification flagged was independently fixed by commit `ad53108`, confirmed via `git log`). |
| GIT-02 | 05-01, 05-02, 05-03 | Dark Factory owns delivery actions; agents never own commit/push/PR policy | ✓ SATISFIED | Unchanged; `GIT_ENV_ALLOWLIST` re-confirmed to exclude `DATABASE_URL`/`GITHUB_TOKEN` |
| ART-04 | 05-03 | Artifact content available to a resuming process on a different machine | ✓ SATISFIED | SC2 evidence above; unchanged |
| ROLE-05 | 05-04, 05-05, 05-06 | A role's write scope is enforced after execution using path rules from configuration | ✓ SATISFIED | SC4 evidence above — now behaviorally proven, not just present/wired. REQUIREMENTS.md marks Complete; this verification now independently substantiates that mark rather than finding it premature. |

No orphaned requirements: REQUIREMENTS.md maps exactly GIT-01, GIT-02, ART-04, ROLE-05 to Phase 5, and all four appear across the six plans' `requirements:` frontmatter (05-01/05-02: GIT-01, GIT-02; 05-03: ART-04, GIT-02; 05-04/05-05/05-06: ROLE-05).

### Anti-Patterns Found

None (🛑 Blocker tier). No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any file touched by the two gap-closure plans (`tests/integration/test_write_scope_enforcement.py`, `tests/unit/test_write_scope_revert.py`, `tests/integration/test_phase5_acceptance.py`, `05-VALIDATION.md`).

⚠️ **Warning (non-blocking, new this session's re-review — 05-REVIEW.md):**
- **WR-04**: `enforce_write_scope`'s call site in `orchestrator/runner.py:889-903` catches only `WriteScopeViolation`, not the broader `GitError` its sibling commit/push call site catches immediately above it. An unrelated `GitCommandError` during revert (e.g. permission error, corrupted index) would propagate uncaught out of `drive()`/`advance()` instead of cleanly failing the role. This code was authored in 05-04 (not touched by 05-05/05-06); a real, reachable gap but not a regression from this session's work, and not one of the two truths (SC1-4) this phase promises.
- **WR-05**: an escape-triggered `WriteScopeViolation` (raised by `revert_paths`) loses the role/attempt/write-scope context that a non-escape violation's message carries, because `revert_paths`'s own raise reaches the caller before `enforce_write_scope`'s own final raise is ever hit. Intentional-but-uncompensated-for side effect of the CR-02 fix, documented in `test_write_scope_revert.py`'s own docstring. Same code path as WR-04, same disposition.

ℹ️ **Info:**
- **IN-02**: WR-01's "unexpected `git rm --cached` failure" structlog warning branch (added in an earlier 05-04 fix round) still has zero test coverage after this session's additions — neither `test_write_scope_revert.py` nor `test_write_scope_enforcement.py` constructs a scenario where `git rm --cached` fails for a reason other than "not staged." Diagnostic-only branch (doesn't change control flow); low priority.
- `05-VALIDATION.md` line 48 (the Task 2/05-04 row for `test_write_scope_enforcement.py`) still reads "⬜ pending — DB-reachability handoff" even though this session independently confirmed that file now passes 6/6 against a real database. This row was in scope for 05-04, not for 05-05/05-06 (05-05's plan did not include a `05-VALIDATION.md` update in its `files_modified`), so it is a pre-existing documentation-drift artifact, not something either gap-closure plan promised to fix. Does not affect the goal-achievement verdict; worth a follow-up doc touch-up.
- This checkout still carries pre-existing leftover git state (31 worktrees, 34 `dark-factory/*` branches vs. the expected 1/0) — documented and explicitly out-of-scope in `deferred-items.md`, predates this phase's own execution, unrelated to G-05-1/G-05-2.

## Human Verification Required

None. Both gaps from `05-UAT.md` (G-05-1, G-05-2) are closed with independently-executed, passing behavioral evidence gathered in this verification session (not taken from SUMMARY.md claims). All four ROADMAP Phase 5 Success Criteria are now VERIFIED, including SC4, which was the sole PRESENT_BEHAVIOR_UNVERIFIED item in the prior verification round.

## Gaps Summary

No gaps. Both UAT-identified gaps are closed:

- **G-05-1** (SC4 in-scope-edit scenario, minor severity): closed by 05-05. The test's post-condition now reads the in-scope edit off the run's working branch (`read_committed`) instead of the worktree filesystem D-04 deletes on COMPLETED, and adds a companion assertion that the worktree is gone. Independently re-run: 6/6 SC4 scenarios pass against real PostgreSQL 17. Zero production changes — confirmed this was a test-defect fix, not a product bug, consistent with the root-cause diagnosis in `.planning/debug/in-scope-edit-missing-after-completed.md`.
- **G-05-2** (CR-02 regression coverage, major severity): closed by 05-06. `tests/unit/test_write_scope_revert.py` now directly exercises `revert_paths`/`enforce_write_scope`'s escape-ordering fix at the unit tier with no database dependency. Independently re-run: 7/7 tests pass. Registered under both SC4 and ROLE-05 in the acceptance gate and in `05-VALIDATION.md`. Zero production changes.

Two new non-blocking Warning-tier findings (WR-04, WR-05) surfaced during this session's re-review of the production code these gaps' tests now exercise more thoroughly — both concern `git/scope.py`/`orchestrator/runner.py` code authored in 05-04 (not touched by 05-05/05-06), are real and reachable but do not contradict any of the four ROADMAP truths this phase promises, and are recorded above for a future hardening pass rather than blocking this phase's goal achievement.

---

*Verified: 2026-09-16*
*Verifier: Claude (gsd-verifier)*
