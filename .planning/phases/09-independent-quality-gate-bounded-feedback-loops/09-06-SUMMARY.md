---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 06
subsystem: testing
tags: [ast-guard, tdd, test-fixture, worktree, feedback-loops, gap-closure]

requires:
  - phase: 09-independent-quality-gate-bounded-feedback-loops
    provides: "09-03's LOOP-01/LOOP-02 feedback-delivery db-tier proofs and the AttemptAwareFourRoleWorker fixture"
provides:
  - "A corrected _CapturingWorker._record_and_maybe_rebuild that derives the run's worktree via ensure_worktree(base_branch, working_branch) from the freshly loaded RunState, exactly as _advance_once does, instead of resolving artifacts against the config repo root"
  - "A new DB-free AST guard (tests/unit/test_role_context_rebuild_uses_the_worktree.py) that fails the moment the rebuild's context root is ever again something other than the ensure_worktree-derived value"
affects: [09-verify-work, future-uat-gap-closure-plans]

actuals:
  tokens: 2400
  tasks: 1
  commits: 2
  plan_head_before: 8776a951903add709521392bc932e14712d943f8

tech-stack:
  added: []
  patterns:
    - "DB-free AST structural guard over a db-tier test fixture, mirroring tests/unit/test_write_scope_guard_covers_bounce.py's idiom (ast.parse + ast.walk helpers, pytestmark = pytest.mark.unit, one guard-on-the-guard test asserting exactly one call site)"

key-files:
  created:
    - tests/unit/test_role_context_rebuild_uses_the_worktree.py
  modified:
    - tests/db/test_feedback_reaches_developer.py

key-decisions:
  - "Chose route 2 (derive the worktree inside the rebuild hook via ensure_worktree) over route 1 (hand the constructor an already-computed worktree path) — it extends the D-07 durability proof to cover path resolution itself, mirrors _advance_once line for line, and does not leave a repo_root-named parameter holding a worktree path"
  - "No runtime assertion added comparing the derived worktree to the stored root — worktree_path is pure path arithmetic that can never make them equal, so such a check would be dead weight; the new AST guard is the real regression pin"

patterns-established:
  - "A db-tier test fixture that reconstructs run state for a durability proof must derive filesystem roots (worktree) from persisted state columns, never from an out-of-band-computed path captured at construction time — this is now enforced by a DB-free structural guard, not left to db-tier execution alone"

requirements-completed: [LOOP-01, LOOP-02]

coverage:
  - id: D1
    description: "_CapturingWorker._record_and_maybe_rebuild derives the worktree via ensure_worktree(base_branch, working_branch) from the freshly loaded RunState and passes it as build_role_context's root argument"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "AC1 one-liner: ast.parse(...) build_role_context call site's args[1] unparses to 'work_dir' (was 'self._repo_root')"
        status: pass
      - kind: unit
        ref: "AC2 one-liner: ensure_worktree present in _record_and_maybe_rebuild's call set (was absent)"
        status: pass
      - kind: unit
        ref: "AC3 one-liner: ensure_worktree's two keyword values both qualified by fresh_state"
        status: pass
      - kind: unit
        ref: "tests/unit/test_role_context_rebuild_uses_the_worktree.py::test_the_rebuild_derives_the_worktree_with_ensure_worktree"
        status: pass
      - kind: unit
        ref: "tests/unit/test_role_context_rebuild_uses_the_worktree.py::test_the_rebuild_never_resolves_the_context_against_the_stored_root"
        status: pass
    human_judgment: false
  - id: D2
    description: "Guard-on-the-guard: exactly one build_role_context call site exists in the edited module"
    verification:
      - kind: unit
        ref: "tests/unit/test_role_context_rebuild_uses_the_worktree.py::test_exactly_one_build_role_context_call_site_in_the_module"
        status: pass
    human_judgment: false
  - id: D3
    description: "No production file changed; both _CapturingWorker construction sites and __init__ byte-identical to pre-task form"
    verification:
      - kind: other
        ref: "git diff --name-only shows no src/ path; git diff of test_feedback_reaches_developer.py shows only _record_and_maybe_rebuild body + docstring changed"
        status: pass
    human_judgment: false
  - id: D4
    description: "LOOP-01/LOOP-02 end-to-end feedback-delivery proofs against a real PostgreSQL 17 (test_qa_fail_delivers_structured_issues_to_developer_attempt_2, test_gate_fail_delivers_real_command_output_to_developer_attempt_2 both passing 2/2, 0 skipped)"
    requirement: "LOOP-01, LOOP-02"
    verification: []
    human_judgment: true
    rationale: "This sandbox has no reachable PostgreSQL 17 (no Docker, no local initdb/pg_ctl, no DARK_FACTORY_TEST_DATABASE_URL) — the db tier raises pytest.UsageError on collection-run. The fix is reasoned correct (mirrors the runner's own passing code path) and structurally pinned by D1/D2 above, but the actual db-tier green run is recorded under Manual-Only Verification and requires a human with real PostgreSQL 17 to execute the documented command."

duration: 20min
completed: 2026-09-26
status: complete
---

# Phase 09 Plan 06: Gap Closure — Feedback-Delivery Test Fixture Summary

**Fixed `_CapturingWorker`'s attempt-2 rebuild to derive the run's worktree via `ensure_worktree` from the freshly loaded `RunState`, instead of resolving artifacts against the config repo root — closing G-09-6/G-09-7 by correcting the sole wrong argument in a test fixture, with zero production code touched, plus a new DB-free AST guard pinning the fix against regression.**

## Performance
- **Duration:** ~20min
- **Started:** 2026-09-26T05:52:10Z (session start recorded in STATE.md)
- **Completed:** 2026-09-26T06:04:18Z
- **Tasks:** 1 completed (TDD: RED → GREEN, no REFACTOR needed)
- **Files modified:** 2

## Accomplishments
- Root-caused defect corrected: `_record_and_maybe_rebuild` now calls `ensure_worktree(self._repo_root, self._run_id, base_branch=fresh_state.base_branch, working_branch=fresh_state.working_branch)` and passes the returned `work_dir` — not `self._repo_root` — as `build_role_context`'s root argument, mirroring `_advance_once` (runner.py:854-866) line for line.
- New DB-free AST guard module (`tests/unit/test_role_context_rebuild_uses_the_worktree.py`, 3 tests) restores a fast, always-runnable detection signal for a class of defect that previously required a real PostgreSQL 17 to surface, and went unnoticed for a whole phase.
- Both `_CapturingWorker` construction sites and its `__init__` are byte-identical to their pre-task form — `repo_root` still genuinely holds a repo root everywhere it appears.
- Zero production files changed, confirmed by `git diff --name-only` showing no `src/` path.

## Task Commits
Each task was committed atomically (TDD: RED → GREEN, REFACTOR not needed — implementation was already minimal and clean per `ruff`/`mypy`):
1. **Task 1 RED: add failing test for rebuild deriving worktree via ensure_worktree** - `da0147f` (test)
2. **Task 1 GREEN: rebuild derives worktree via ensure_worktree, not repo root** - `8df8f06` (feat)

## Files Created/Modified
- `tests/unit/test_role_context_rebuild_uses_the_worktree.py` — new DB-free AST guard: three helpers (`_calls_named`, `_find_function`, `_ensure_worktree_bound_name`) plus three tests proving `_record_and_maybe_rebuild` calls `ensure_worktree`, that `build_role_context`'s root argument is the `ensure_worktree`-derived local (never `self._repo_root`), and a guard-on-the-guard asserting exactly one `build_role_context` call site.
- `tests/db/test_feedback_reaches_developer.py` — `_record_and_maybe_rebuild` now derives `work_dir` via `ensure_worktree` from `fresh_state.base_branch`/`fresh_state.working_branch` and passes it to `build_role_context`; module docstring extended to record the derivation and cite G-09-6/G-09-7 plus the debug session, so a future edit does not mistake it for redundant ceremony.

## Decisions Made
- **Route 2 chosen over route 1** (see plan's `<action>` block, reproduced in key-decisions above): derive the worktree inside the rebuild hook rather than threading an already-computed path into the constructor. This extends the D-07 durability proof to cover path resolution itself, mirrors production code for readability, and avoids ever making a parameter named `repo_root` hold a worktree path.
- **No defensive runtime assertion added** comparing the derived worktree to the stored repo root — `worktree_path` is pure arithmetic that structurally can never make the two equal, so such a check would be dead weight rather than a live guard. The new AST guard is the actual regression pin.

## Deviations from Plan

None - plan executed exactly as written. The single task's RED/GREEN/REFACTOR cycle produced exactly the two anchor commits the plan's TDD behavior block specified (test 3, the guard-on-the-guard, stayed green throughout as designed); no REFACTOR commit was needed since the GREEN implementation was already clean under `ruff check`, `ruff format --check`, and `mypy --strict`.

## TDD Gate Compliance

- RED commit present: `da0147f test(09-06): add failing test for rebuild deriving worktree via ensure_worktree` — verified 2 genuine RED failures (tests 1 and 2) plus 1 green guard-on-the-guard (test 3) before the fix.
- GREEN commit present: `8df8f06 feat(09-06): rebuild derives worktree via ensure_worktree, not repo root` — verified all 3 tests pass after the fix.
- REFACTOR: not needed (no commit) — implementation was minimal (2 lines argument change + a new call) and already clean under all linters/type-checkers.
- No fail-fast violations: no unexpected GREEN in RED phase, no INVALID_RED (both RED failures were genuine `AssertionError`s on the intended assertions, not collection/fixture errors).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Manual-Only Verification (recorded, not claimed)

This sandbox has no reachable PostgreSQL 17. The db-tier proof that both LOOP-01 and LOOP-02 now actually pass end to end against a real database is **not performed here** — only the fix's structural correctness is proved here (AST guard + acceptance-criteria one-liners + clean collection with zero errors). Per the plan's own Manual-Only Verification table, a human with PostgreSQL 17 reachable must run:

```
uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -m db -q tests/db/test_feedback_reaches_developer.py
```

and confirm **2 passed, 0 skipped, 0 failed**, specifically that `test_qa_fail_delivers_structured_issues_to_developer_attempt_2` and `test_gate_fail_delivers_real_command_output_to_developer_attempt_2` both pass with no `MissingArtifactContentError`. Neither G-09-6 nor G-09-7 should be marked verified until that command has actually been executed. This is the same pre-existing constraint carried through Phases 6-9 (see plan's `<manual_only_verification>` and `.planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md`).

## Next Phase Readiness

This is the last plan in Phase 09 (plans 01-06 all now have SUMMARYs). Phase complete, ready for next step — `/gsd-verify-work` should be run to independently confirm this plan's structural fix and, when PostgreSQL 17 is reachable, execute the Manual-Only Verification command above before Phase 09 is considered fully closed end-to-end.

No blockers.

---
*Phase: 09-independent-quality-gate-bounded-feedback-loops*
*Completed: 2026-09-26*

## Self-Check: PASSED

- FOUND: tests/unit/test_role_context_rebuild_uses_the_worktree.py
- FOUND: .planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-06-SUMMARY.md
- FOUND: commit da0147f (test(09-06))
- FOUND: commit 8df8f06 (feat(09-06))
