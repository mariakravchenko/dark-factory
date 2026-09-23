---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 04
subsystem: orchestrator
tags: [gap-closure, write-scope, authorization, security]

requires:
  - src/dark_factory/git/scope.py::enforce_write_scope
  - src/dark_factory/git/scope.py::WriteScopeViolation
  - src/dark_factory/domain/signal.py::Signal
provides:
  - "enforce_write_scope guard widened to cover Signal.ROLE_BOUNCED"
  - "tests/unit/test_write_scope_guard_covers_bounce.py (structural regression guard)"
  - "tests/db/test_write_scope_enforced_on_bounce.py (behavioural regression proof)"
affects:
  - src/dark_factory/orchestrator/runner.py

actuals:
  tokens: 5720
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "AST structural regression guard over runner.py, mirroring test_no_role_name_literal.py's idiom, used where a db-tier behavioural proof cannot run in every environment"
    - "sentinel_writes / out_of_scope_writes as deliberate opposites on the same test fixture -- one targets the gitignored run tree to stay invisible to enforcement, the other targets a tracked-visible path to trigger it"

key-files:
  created:
    - tests/unit/test_write_scope_guard_covers_bounce.py
    - tests/db/test_write_scope_enforced_on_bounce.py
  modified:
    - src/dark_factory/orchestrator/runner.py
    - tests/support/fake_artifacts.py

key-decisions:
  - "Widened the enforce_write_scope guard to `signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED)` rather than adding a second, parallel enforcement call for ROLE_BOUNCED -- one call site, one code path, matches the existing GitError/ArtifactError sibling checks."
  - "The WriteScopeViolation handler clears counter_increments and bounce_reason (mirroring the GitError block) but deliberately does NOT clear gate_events, since commit_run_artifacts has already succeeded and durably committed the gate artifact by the time this check runs -- unlike the GitError branch, where the carrying commit never landed."
  - "AttemptAwareFourRoleWorker's new out_of_scope_writes/worktree_root keywords are additive and default to None, so every existing db test (test_qa_bounce.py, test_iteration_cap_exhaustion.py) is unaffected; a misconfigured fixture (out_of_scope_writes without worktree_root) raises ValueError at construction rather than silently planting nothing."

patterns-established:
  - "A source-structural AST guard is the correct instrument for pinning an authorization boundary when the behavioural proof is db-tier and cannot run in every sandbox -- fast, always-runnable, and fails loudly if the call site the behavioural test relies on ever moves or duplicates."

requirements-completed: [LOOP-02, LOOP-03, LOOP-04]

coverage:
  - id: cov-1
    description: "The ROLE-05 write-scope guard is enforced for both Signal.ROLE_COMPLETED and Signal.ROLE_BOUNCED, and a violation on a would-be-bounced attempt clears counter_increments/bounce_reason while leaving gate_events untouched"
    requirement: LOOP-03
    verification:
      - kind: unit
        ref: tests/unit/test_write_scope_guard_covers_bounce.py
        status: pass
    human_judgment: false
  - id: cov-2
    description: "A real four-role drive() run in which QA writes outside its declared write_scope on an attempt that would otherwise bounce ends FAILED with the file reverted, zero ROLE_BOUNCED events, both counters untouched, and no phantom second attempt row"
    requirement: LOOP-03
    verification:
      - kind: db
        ref: tests/db/test_write_scope_enforced_on_bounce.py::test_a_bounce_is_write_scope_enforced_exactly_like_a_completion
        status: unrun
    human_judgment: true
    rationale: "This db-tier test requires a real reachable PostgreSQL 17, which this sandbox does not have (no Docker, no local initdb, no DARK_FACTORY_TEST_DATABASE_URL). Collection is clean (1 test collected; whole db tier collects 1005 tests / 0 errors). Recorded under Manual-Only Verification in 09-04-PLAN.md with exact rerun instructions."

duration: ~35min
completed: 2026-09-23
status: complete
---

# Phase 9 Plan 04: Widen the ROLE-05 write-scope guard to cover a bounced attempt, closing an authorization bypass on the Phase 9 bounce edge Summary

Widened `enforce_write_scope` to run on `Signal.ROLE_BOUNCED` as well as `Signal.ROLE_COMPLETED` -- the write-scope authorization boundary written in Phase 5, before `ROLE_BOUNCED` existed, was silently skipped on every bounced terminal-role attempt, letting an out-of-scope write survive uncaught into the next role's WIP-recovery commit.

## Performance

- **Duration:** ~35min
- **Started:** 2026-09-23T11:08:46Z
- **Completed:** 2026-09-23T11:25:27Z (approx)
- **Tasks:** 2/2
- **Files modified:** 4 (1 modified production file, 1 modified test fixture, 2 new test modules)

## Accomplishments

- Closed gap CR-01 (09-VERIFICATION.md failed truth #22): the `enforce_write_scope` ROLE-05 boundary now runs for both `Signal.ROLE_COMPLETED` and `Signal.ROLE_BOUNCED`, the two signals under which an attempt's worktree changes are retained rather than the run ending outright.
- The `WriteScopeViolation` handler now clears `counter_increments` and `bounce_reason` when it downgrades a would-be bounce to `ROLE_FAILED`, so a violation can never silently spend the operator's configured retry budget on a loop iteration that never happened. `gate_events` is deliberately left untouched, since the gate's own audit events are already durably committed by the time this check runs.
- Rewrote the stale ROLE-05 comment paragraph above the guard, which claimed enforcement was conditional on `ROLE_COMPLETED` alone.
- Added a fast, environment-independent AST structural regression guard (`tests/unit/test_write_scope_guard_covers_bounce.py`) pinning the guard's shape, so this boundary cannot silently narrow again the way it did between Phase 5 and Phase 9.
- Added a db-tier behavioural regression proof (`tests/db/test_write_scope_enforced_on_bounce.py`) that drives a real four-role run in which QA writes outside its declared `write_scope` on an attempt that would otherwise bounce, and asserts the run ends FAILED with the file reverted, zero `ROLE_BOUNCED` events, both counters untouched, and no phantom second attempt row.
- Added additive `out_of_scope_writes`/`worktree_root` constructor keywords to `AttemptAwareFourRoleWorker` (`tests/support/fake_artifacts.py`), the deliberate opposite of the existing `sentinel_writes` hook: it plants a tracked-visible worktree write specifically *in order to* trigger `enforce_write_scope`, rather than one that stays invisible to it.

## Task Commits

1. `932a278` — test(09-04): add failing test for write-scope guard covering bounce (TDD RED)
2. `d276985` — feat(09-04): widen write-scope guard to cover a bounced attempt (TDD GREEN)
3. `3655448` — test(09-04): prove a bounce cannot launder an out-of-scope write

No REFACTOR commit was needed -- the GREEN implementation required no cleanup pass.

## Files Created/Modified

- `src/dark_factory/orchestrator/runner.py` (modified) -- the `enforce_write_scope` guard expression, two new assignments (`counter_increments = {}`, `bounce_reason = None`) inside the existing `except WriteScopeViolation` handler, and the rewritten ROLE-05 comment paragraph.
- `tests/unit/test_write_scope_guard_covers_bounce.py` (new) -- AST structural regression guard: exactly one `enforce_write_scope`-guarding `if`/`try` pair exists, its guard names both `ROLE_COMPLETED` and `ROLE_BOUNCED`, its handler assigns `signal`/`outcome`/`artifact_writes`/`counter_increments`/`bounce_reason`, and does not assign `gate_events`.
- `tests/support/fake_artifacts.py` (modified) -- `AttemptAwareFourRoleWorker.__init__` gains `out_of_scope_writes`/`worktree_root` (both additive, default `None`); `_record` gains the enforcement-visible worktree write branch; class docstring gains the `sentinel_writes`-vs-`out_of_scope_writes` contrast paragraph.
- `tests/db/test_write_scope_enforced_on_bounce.py` (new) -- one db-tier `drive()` scenario plus local copies of `_write_four_role_tree`/`_registry`/`real_session_factory`/`cleanup_runs`/`_events`/`_role_executions`, following `tests/db/test_qa_bounce.py`'s per-module-copy convention.

## Decisions Made

- One widened guard condition (`signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED)`) rather than a second, parallel `enforce_write_scope` call site for the bounce case -- keeps one code path and one exception-handling block, matching how the sibling `GitError`/`ArtifactError` checks are already structured.
- `gate_events` is explicitly NOT cleared in the widened handler, diverging deliberately from the `GitError` block it otherwise mirrors -- because by the time write-scope enforcement runs, `commit_run_artifacts` has already succeeded and the gate artifact (`verification/quality_gate.json`) is durably committed, so its `QUALITY_GATE_*` events remain true statements that must still be emitted on the `ROLE_FAILED` path.
- `AttemptAwareFourRoleWorker`'s new keywords are additive and default to `None`/raise-on-misuse, not a breaking signature change -- zero existing db test (`test_qa_bounce.py`, `test_iteration_cap_exhaustion.py`) changes behaviour.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `pytest -m "unit or contract"` full suite run took ~4m20s per invocation (671 tests against no live database), run twice (once after Task 1's GREEN, once after Task 2) and both times returned clean with no timeouts requiring retry.

## User Setup Required

None -- no external services, no new dependency, no config change.

## Manual-Only Verification (recorded, not a gap)

`tests/db/test_write_scope_enforced_on_bounce.py::test_a_bounce_is_write_scope_enforced_exactly_like_a_completion` requires a reachable PostgreSQL 17, which this sandbox lacks (no Docker, no local `initdb`, no `DARK_FACTORY_TEST_DATABASE_URL`). Confirmed collection-clean: `pytest -m db -q --collect-only tests/db/test_write_scope_enforced_on_bounce.py` collects exactly 1 test with 0 errors, and `pytest -m db -q --collect-only` (whole tier) collects 1005 tests with 0 errors (up from before this plan). Attempting to run it produces the exact, expected `pytest.UsageError: No PostgreSQL 17 is reachable` message documented in Phases 6, 7, and 8 -- not a regression. Rerun instructions and the full list of Phase 9 db-tier proofs to re-verify together are recorded in `09-04-PLAN.md`'s Manual-Only Verification table.

## Next Phase Readiness

Gap CR-01 is closed. Sibling gap-closure plan `09-05` (CR-02, touching `src/dark_factory/orchestrator/quality_gate.py` and `tests/unit/test_quality_gate.py`) has not yet run -- it is still pending and is expected to execute next, with no file overlap against this plan's changes.

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 4 task/plan commit hashes (932a278, d276985, 3655448, b84685c) confirmed present in git log.
