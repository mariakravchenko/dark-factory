---
phase: 05-isolated-workspace-git-lifecycle
verified: 2026-09-15T00:00:00Z
status: human_needed
score: 3/4 truths verified
covered_files: [".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".gitignore", ".planning/REQUIREMENTS.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-01-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-01-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-02-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-02-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-03-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-03-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-04-PLAN.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-04-SUMMARY.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW-FIX.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-REVIEW.md", ".planning/phases/05-isolated-workspace-git-lifecycle/05-VALIDATION.md", "migrations/versions/0005_wip_commit_sha.py", "src/dark_factory/actions/builtins.py", "src/dark_factory/actions/context.py", "src/dark_factory/config/loader.py", "src/dark_factory/events/catalog.py", "src/dark_factory/events/redaction.py", "src/dark_factory/git/__init__.py", "src/dark_factory/git/client.py", "src/dark_factory/git/diff.py", "src/dark_factory/git/lifecycle.py", "src/dark_factory/git/scope.py", "src/dark_factory/git/worktree.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/persistence/models.py", "src/dark_factory/persistence/mutations.py", "src/dark_factory/persistence/repositories.py", "src/dark_factory/workers/fake.py"]
covered_digest: "v1:sha256:8ecbee740f006fa1ea998e2ca0c5a72f5891d27e97a0d6ec67da7bc46ad9b37b"
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:
  - truth: "SC4 — a role whose diff touches paths outside its configured write scope fails the role; the out-of-scope edit is reverted and the violation is logged"
    test: "Run `set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v` against a reachable PostgreSQL 17, then also add and run a regression case for a symlink-escape violation queued alongside an ordinary violation (CR-02's fix has zero test coverage at any tier)."
    expected: "All 6 scenarios in test_write_scope_enforcement.py pass (in-scope edit survives; tracked-edit violation restored from HEAD; new-file violation removed from disk+index; empty write_scope fails on any change; a later role isn't failed for an earlier role's legitimate edit; a role with both a valid artifact and a violation still fails while the artifact survives on the branch). A new symlink-escape-plus-ordinary-violation case proves CR-02's batch-collect-then-raise fix actually reverts every non-escaping violation rather than aborting the loop."
    why_human: "The enforcement/revert code path (src/dark_factory/git/scope.py) was the subject of two Critical code-review findings (CR-01: write-scope/PR-diff blind spot for tracked .dark-factory config; CR-02: revert_paths aborting mid-loop on a containment escape, leaving queued violations un-reverted). Both were fixed (commits 46adf4a, dd10f43), but neither fix — nor the pre-existing SC4 integration test itself — has ever been executed against a real PostgreSQL 17 in any sandbox for this phase. Presence, wiring, and a clean mypy/ruff/unit pass do not exercise the actual state-transition/cleanup invariant (does the revert really restore every queued file; does the role really fail). This sandbox has no reachable PostgreSQL 17 (confirmed live this session: pytest reports 'dark-factory test Postgres: NONE'), so it cannot be upgraded to VERIFIED without a human running it against a real database."
coincidental_reliance_items: []
human_verification:
  - test: "Run `set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v` against a reachable PostgreSQL 17"
    expected: "6/6 scenarios pass, proving SC4 (write-scope enforcement + targeted revert) end to end, including after the CR-01/CR-02/WR-01/WR-03 code-review fixes"
    why_human: "No PostgreSQL 17 is reachable in this verification sandbox; this is the one Phase 5 proof file that has never been executed against a real database at any point in the plan's history (05-04-SUMMARY.md: 'authored and self-consistency-checked but never executed'; 05-REVIEW-FIX.md WR-02: explicitly skipped for the same reason after the fixes landed)."
  - test: "Add and run a targeted regression test for CR-02: a violation set containing one path that resolves outside the worktree (e.g. a worker-created symlink) alongside one or more ordinary in-worktree violations, sorted so the escaping path is not last"
    expected: "Every non-escaping violation is reverted (tracked edits restored from HEAD, new files removed from disk and the index) and a single WriteScopeViolation is raised afterward naming the escaping path(s) — proving the batch-collect-then-raise fix, not just its absence of a regression"
    why_human: "grep across tests/ for 'symlink', '_resolve_in_worktree', and 'revert_paths' found zero references (confirmed this session) — this exact scenario, the one CR-02 was filed against, has no test at any tier (unit, db, or integration). The fix's correctness rests entirely on code review and manual reasoning, not an executed test."
  - test: "Re-run the full suite (`set -a; . ./.env; set +a; uv run pytest -q`) against a reachable PostgreSQL 17 once the two items above pass, and separately clean up the ~24 pre-existing leftover dark-factory/run-* worktrees/branches this checkout carries (per deferred-items.md), which predate this phase and are unrelated to its own deliverables"
    expected: "624+ passed, 0 failed, 0 skipped; `git worktree list --porcelain` names exactly one worktree and `git branch --list 'dark-factory/*'` is empty afterward"
    why_human: "Confirms the CR-01 pathspec narrowing (which affects both SC4's enforcement scan and SC2's artifact-commit/PR-diff exclusion) introduced no regression in the db/integration tiers that were last proven green before the fix landed, and restores the clean-checkout invariant Task 3 of 05-04 could not verify in-sandbox."
---

# Phase 5: Isolated Workspace & Git Lifecycle Verification Report

**Phase Goal:** Every run owns an explicit working branch and a clean worktree that all roles share, Dark Factory owns the git actions, and the run's artifacts travel with it to another machine.
**Verified:** 2026-09-15
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Phase 5 Success Criteria, verbatim)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | "A run creates a working branch from the configured base branch, named so it is unique to the run id, and every role executes against that same worktree." | ✓ VERIFIED | `src/dark_factory/git/worktree.py::ensure_worktree`/`working_branch_name`, `persistence/mutations.py::create_run` (writes `runs.base_branch`/`runs.working_branch` before any git command), `orchestrator/runner.py` unconditional `ensure_worktree` call. Unit: `tests/unit/test_git_worktree.py` (17 tests, fresh-run PASS this session) + `tests/unit/test_git_ownership_boundary.py` (3 tests, PASS). DB-tier: `tests/db/test_run_owns_a_worktree.py` (5 tests) — human-executed against real PostgreSQL 17 per 05-01-SUMMARY.md's coverage block ("40 db/integration tests... all green"), not independently re-run in this sandbox (no reachable DB here). |
| SC2 | "A process on a different machine, given only the run id and a fresh clone, has the run's artifact content available to rebuild context and continue." | ✓ VERIFIED | `src/dark_factory/git/diff.py::commit_run_artifacts` (force-add past `.gitignore`, pathspec-limited commit) + `push_working_branch` (D-16). Integration: `tests/integration/test_artifact_cross_clone.py` — human-executed, reported as part of 05-03-SUMMARY.md's "Round 3 (final)... 624 passed, 0 failed" full-suite gate. `commit_run_artifacts` itself is untouched by the later CR-01 pathspec fix (only the *exclusion* scope used by `collect_pr_diff`/`attempt_changed_paths` narrowed; the artifact commit still force-adds the whole `.dark-factory/runs/<run_id>` tree), so this evidence is not invalidated by the review fixes. |
| SC3 | "A role that finishes with uncommitted changes is recovered on next entry — changes WIP-committed to a persisted ref, worktree clean, nothing lost — and an entry on a detached HEAD fails the role with a persisted event instead of proceeding." | ✓ VERIFIED | Behavior-dependent (state-transition + cleanup invariant). `src/dark_factory/git/lifecycle.py::wip_commit_if_dirty`/`assert_attached_head`, `orchestrator/runner.py`'s before-hook `try/except DetachedHeadError` + head-SHA diff triggering `_persist_wip_commit`. Unit: `tests/unit/test_git_lifecycle.py` (9 tests, fresh PASS). DB/integration: `tests/db/test_wip_commit_recovery.py`, `tests/db/test_detached_head_fails_role.py`, `tests/integration/test_worktree_lifecycle.py` — human-executed with the exact named-test PASS transcript reproduced in 05-02-SUMMARY.md's "Test Execution Handoff" (8/8 named tests, then 604/604 full suite). This code path (`git/lifecycle.py`, the before-hook seam) is untouched by the later CR-01/CR-02/WR-01/WR-03 fixes. |
| SC4 | "A role whose diff touches paths outside its configured write scope (QA touching production code) fails the role; the out-of-scope edit is reverted and the violation is logged." | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Behavior-dependent (cleanup/revert invariant). `src/dark_factory/git/scope.py::enforce_write_scope`/`revert_paths`/`is_out_of_scope`, wired into `orchestrator/runner.py`'s `Signal.ROLE_COMPLETED` branch. Matcher unit tests pass (`tests/unit/test_write_scope.py`, 14 tests, fresh PASS). **But** `tests/integration/test_write_scope_enforcement.py` — the one file that proves the revert/fail behavior end to end — has never been executed against a real database, not before the code-review fixes (05-04-SUMMARY.md: status `unknown`, `human_judgment: true`) and not after them (05-REVIEW-FIX.md WR-02: explicitly skipped, "environment limitation"). This is exactly the code path two Critical findings (CR-01, CR-02) were filed and fixed against. Presence + wiring + a clean mypy/ruff/unit pass is insufficient evidence for a revert/cleanup invariant. Routed to Human Verification below. |

**Score:** 3/4 truths verified (1 present, behavior-unverified)

### Supporting Requirement-Level Findings

- **GIT-02 ownership boundary** (git binary reachable only from `dark_factory.git`): `tests/unit/test_git_ownership_boundary.py` — AST-walk guard, 3/3 PASS fresh this session.
- **Code-review fixes verified present in code** (all four commits confirmed on disk, not merely claimed in SUMMARY):
  - CR-01 (Critical): `ARTIFACT_EXCLUDE_PATHSPEC` narrowed from `:(exclude).dark-factory` to `:(exclude).dark-factory/runs` — confirmed at `src/dark_factory/git/diff.py`. Closes a write-scope/PR-diff blind spot for tracked `.dark-factory/roles/*.yaml` config.
  - CR-02 (Critical): `revert_paths` now collects containment escapes in a `try`/`except` per path instead of aborting the loop on the first one — confirmed at `src/dark_factory/git/scope.py`.
  - WR-01: unexpected `git rm --cached` failures now logged via structlog instead of silently swallowed — confirmed.
  - WR-03: `DEFAULT_WRITE_SCOPE` constant now the single source of the D-14 zero-tolerance default, consumed by both `config/loader.py` and `orchestrator/runner.py` — confirmed.
  - WR-02 (test-execution gap) legitimately skipped — it is an environment limitation (no reachable PostgreSQL 17), not a code defect the fixer could resolve; correctly not silently marked done.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/git/worktree.py` | `working_branch_name`/`worktree_path`/`ensure_worktree`/`remove_worktree` | ✓ VERIFIED | 156 lines, `ensure_worktree` present, unit-tested, wired into `runner.py` |
| `src/dark_factory/git/client.py` | `run_git` subprocess wrapper, explicit env allowlist | ✓ VERIFIED | 117 lines; `GIT_ENV_ALLOWLIST` excludes `DATABASE_URL`/`GITHUB_TOKEN`; no `environ.copy()`, no `shell=True` |
| `src/dark_factory/git/lifecycle.py` | WIP-commit recovery primitives | ✓ VERIFIED | 108 lines; `wip_commit_if_dirty`, `assert_attached_head` present, unit-tested |
| `src/dark_factory/git/diff.py` | Artifact commit, PR diff, push | ✓ VERIFIED | 322 lines; `commit_run_artifacts`, `collect_pr_diff`, `push_working_branch` present; `GIT_ASKPASS`-only credential confirmed (`grep -c 'DARK_FACTORY_GIT_PUSH_TOKEN' client.py` → 0, i.e. not in the general allowlist) |
| `src/dark_factory/git/scope.py` | Write-scope matcher, revert, enforcement | ✓ VERIFIED | 316 lines; `enforce_write_scope`, `revert_paths`, `is_out_of_scope` present, code-review-fixed, unit-tested for the matcher only (revert/enforce behavior not tested at any tier — see SC4 above) |
| `tests/support/git_repo.py` | Real-git-repo test fixture factory | ✓ VERIFIED | `make_git_repo`, `git_commit_all`, `read_committed`, `clone_repo`, `run_artifact_text` all present |
| `tests/integration/test_phase5_acceptance.py` | Phase gate mapping SC1-4 + all 4 requirement IDs to proofs | ✓ VERIFIED (structurally) | Collects cleanly (6 tests), maps SC1-4 verbatim against ROADMAP text, drift-guards against `05-VALIDATION.md`. Not run against a DB in this session (requires the same PostgreSQL fixture as the rest of the integration tier), but its own logic is pure filesystem/string assertion per its docstring. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `persistence/mutations.py::create_run` | `git/worktree.py::working_branch_name` | called inside the existing transaction, before any git command | ✓ WIRED | `grep -c 'working_branch_name' mutations.py` ≥ 1 |
| `orchestrator/runner.py::_run_current_role` | `git/worktree.py::ensure_worktree` | unconditional call before `build_role_context` | ✓ WIRED | confirmed at runner.py:726 |
| `orchestrator/runner.py` | `git/lifecycle.py::wip_commit_if_dirty` / `DetachedHeadError` | before-hook head-SHA diff + try/except | ✓ WIRED | confirmed at runner.py:71-74, 767-773 |
| `orchestrator/runner.py` (`Signal.ROLE_COMPLETED`) | `git/diff.py::commit_run_artifacts` → `push_working_branch` | validate → commit → push → enforce scope → transition ordering | ✓ WIRED | confirmed at runner.py:844-900 |
| `orchestrator/runner.py` (`Signal.ROLE_COMPLETED`) | `git/scope.py::enforce_write_scope` | after commit/push, before `transition()`; `WriteScopeViolation` → `ROLE_FAILED` | ✓ WIRED | confirmed at runner.py:868-900 |
| `orchestrator/runner.py` (`RunStatus.COMPLETED`) | `git/worktree.py::remove_worktree` via `_cleanup_run_worktree` | recover-then-remove, only for COMPLETED | ✓ WIRED | confirmed at runner.py:989 |
| `.dark-factory/roles/{BA,ARCHITECTURE,DEVELOPMENT,QA}.yaml` | `write_scope` enforcement | `DEVELOPMENT`→`["src/**"]`, `QA`→`["tests/**"]`, `BA`/`ARCHITECTURE`→`[]` (documented as intended zero-tolerance) | ✓ WIRED | confirmed via grep of all 4 role YAMLs |
| `config/loader.py::load_effective_config` | `git/scope.py::validate_write_scope_patterns` | fail-loud pattern validation before `create_run` | ✓ WIRED | confirmed at loader.py:146 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite (no DB dependency) | `uv run pytest -m unit -q` | 366 passed, 292 deselected, 13.02s | ✓ PASS |
| Strict typing | `uv run mypy src/dark_factory` | "Success: no issues found in 58 source files" | ✓ PASS |
| Lint | `uv run ruff check .` | "All checks passed!" | ✓ PASS |
| All Phase-5-relevant unit files together | `uv run pytest -m unit -q tests/unit/test_write_scope.py tests/unit/test_git_diff.py tests/unit/test_git_push.py tests/unit/test_git_lifecycle.py tests/unit/test_git_worktree.py tests/unit/test_git_ownership_boundary.py` | 59 passed, 12.42s | ✓ PASS |
| DB reachability (confirms the documented environment constraint is real, not fabricated) | `uv run pytest -m db tests/db/test_role_executions_wip_commit_sha_schema.py -q` | pytest banner: "dark-factory test Postgres: NONE — no reachable PostgreSQL 17" | ? SKIP (confirms constraint) |
| SC4 proof collection (existence, not execution) | `uv run pytest --collect-only -q tests/integration/test_write_scope_enforcement.py` | 6 tests collected, 0 errors | ✓ PASS (collection only) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| GIT-01 | 05-01, 05-02 | Each run has an explicit working branch from the configured base branch; all roles operate on the same run repository state | ✓ SATISFIED (code) | SC1 + SC3 evidence above. **Documentation gap:** REQUIREMENTS.md line 109 still shows `- [ ] GIT-01` and its traceability table (line 253) shows "Pending" while GIT-02/ART-04/ROLE-05 on adjacent lines are already marked Complete — stale tracker, not a code gap (see Anti-Patterns/Gaps note below). |
| GIT-02 | 05-01, 05-02, 05-03 | Dark Factory owns delivery actions; agents never own commit/push/PR policy | ✓ SATISFIED | Ownership-boundary AST guard passes; `GIT_ASKPASS`-only push credential; REQUIREMENTS.md already marks this Complete |
| ART-04 | 05-03 | Artifact content available to a resuming process on a different machine | ✓ SATISFIED | SC2 evidence above; REQUIREMENTS.md already marks this Complete |
| ROLE-05 | 05-04 | A role's write scope is enforced after execution using path rules from configuration | ⚠️ PRESENT, BEHAVIOR UNVERIFIED | Code/config/wiring complete and code-reviewed with 2 Critical fixes applied; the one proof that exercises it end-to-end has never run against a database. REQUIREMENTS.md already marks this Complete — premature given the unexecuted proof (see Gaps note). |

No orphaned requirements: REQUIREMENTS.md maps exactly GIT-01, GIT-02, ART-04, ROLE-05 to Phase 5, and all four appear in the four plans' `requirements:` frontmatter.

### Anti-Patterns Found

None (🛑 Blocker / ⚠️ Warning tier). No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any file touched by this phase (checked via full diff against the pre-phase commit `78f2180`). No empty-implementation or hardcoded-stub patterns found in the git package.

ℹ️ **Info:** This checkout carries ~24 pre-existing leftover `dark-factory/run-*` worktrees and branches (documented and explicitly not fixed in `deferred-items.md` as out-of-scope, predating this phase's own execution). Not a phase-5 defect, but worth a human cleanup pass (`git worktree prune` + branch review) before the next phase's own worktree-hygiene assertions run cleanly.

ℹ️ **Info:** REQUIREMENTS.md's per-requirement checklist/table shows GIT-01 as unmarked/"Pending" while its three sibling Phase-5 requirements (GIT-02, ART-04, ROLE-05) are already marked "Complete" — an internal inconsistency in the tracking document itself (all four requirements were worked in the same four plans of the same phase). This is a documentation bookkeeping issue, not a reflection of GIT-01's actual implementation state, which is independently verified above (SC1, SC3).

## Human Verification Required

### 1. Run the SC4 proof against a real database

**Test:** `set -a; . ./.env; set +a; uv run pytest tests/integration/test_write_scope_enforcement.py -v` against a reachable PostgreSQL 17.
**Expected:** All 6 scenarios pass (in-scope edit survives untouched; a tracked-edit violation is restored from HEAD; a new-file violation is removed from disk and the git index; an empty `write_scope` fails on any change at all; a later role is not penalized for an earlier role's legitimate in-scope edit; a role that both writes a valid artifact and commits a violation in the same attempt still fails while the artifact content survives on the branch).
**Why human:** No PostgreSQL 17 is reachable in this verification sandbox. This is the single Phase 5 proof file that has never been executed against a real database at any point in this phase's history — not when originally authored (05-04-SUMMARY.md), and not after the two Critical code-review fixes (CR-01, CR-02) that touch exactly this code path landed (05-REVIEW-FIX.md WR-02, explicitly skipped for the same reason).

### 2. Add and run a CR-02 regression test

**Test:** Construct a violation set containing one path that resolves outside the worktree (e.g., a worker-created symlink pointing outside the checkout) sorted alphabetically before one or more ordinary in-scope violations, and call `enforce_write_scope`/`revert_paths` against it.
**Expected:** Every non-escaping violation is still reverted (tracked edits restored from HEAD; new files removed from disk and the index), and exactly one `WriteScopeViolation` is raised afterward, naming the escaping path(s) — proving the batch-collect-then-raise fix actually works, not merely that it compiles.
**Why human:** `grep -rn "symlink|_resolve_in_worktree|revert_paths" tests/` returns zero hits for this exact scenario at any test tier (confirmed this session). CR-02's fix currently rests entirely on code review and manual reasoning; it has no executed regression coverage anywhere in the suite.

### 3. Re-run the full suite and confirm no regression from CR-01's pathspec narrowing

**Test:** `set -a; . ./.env; set +a; uv run pytest -q` against a reachable PostgreSQL 17, after items 1-2 above pass.
**Expected:** 624+ passed, 0 failed, 0 skipped (matching or exceeding 05-03-SUMMARY.md's last documented full-suite result). Also confirm `git worktree list --porcelain` names exactly one worktree and `git branch --list 'dark-factory/*'` is empty afterward (currently ~24 leftover from a pre-existing, unrelated accumulation — see `deferred-items.md`).
**Why human:** CR-01 narrowed `ARTIFACT_EXCLUDE_PATHSPEC`, the constant shared by SC2's PR-diff exclusion and SC4's write-scope change-scan. The fix's correctness for SC2 was cross-checked by hand against `test_pr_diff_excludes_artifacts.py`'s existing assertion text (per 05-REVIEW-FIX.md) rather than by re-running that test against a live database.

## Gaps Summary

No FAILED truths — every artifact this phase's plans promised exists, is substantive, and is wired into the runner exactly where the plans specified. The phase's own code review (05-REVIEW.md) found and the phase's own fix pass (05-REVIEW-FIX.md) resolved 4 of 5 in-scope findings (2 Critical, 2 Warning), all independently re-confirmed present in the current codebase during this verification. mypy, ruff, and the full 366-test unit suite are all green, run fresh in this session.

The one genuine gap is evidentiary, not architectural: **SC4 (write-scope enforcement)** — the phase's own headline "QA touching production code fails the role" guarantee — has never been proven against a real database, either in its original form or after the two Critical fixes (CR-01, CR-02) that were filed against precisely this code path. This is the same recurring DB-reachability constraint phases 1-4 documented (STATE.md: "real-Neon human check DEFERRED to /gsd-verify-work"), consistently reported rather than silently skipped by every plan in this phase, and is not a fabricated pass — SC1-SC3 have documented human-executed PASS transcripts with specific test names and wall-clock times; SC4 does not, and additionally has zero regression coverage for CR-02's specific fix at any tier. Routed to human verification per standard protocol rather than marked FAILED, since the code is present, wired, reviewed, and structurally sound — only the runtime proof is outstanding.

---

*Verified: 2026-09-15*
*Verifier: Claude (gsd-verifier)*
