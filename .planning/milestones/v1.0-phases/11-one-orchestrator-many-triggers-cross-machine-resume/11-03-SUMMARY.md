---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 03
subsystem: testing
tags: [subprocess-isolation, ast-guard, cross-machine, worktree, pytest-markers]

# Dependency graph
requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plan 11-01's tracer verification that the dispatch wiring is architecturally sound (this plan shares no files with 11-01/11-02; the depends_on edge is tracer ordering, not a file dependency)"
provides:
  - "tests/db/test_cross_machine_resume.py -- SC1/TRIG-04/HITL-06's two-real-subprocess proof, marked pytest.mark.db so it runs in CI, plus SC2's behavioural two-process-vs-single-process indistinguishability proof"
  - "tests/unit/test_trigger_carries_no_lifecycle_logic.py -- TRIG-01's structural guard: advance/drive defined in exactly one module, called only from the verified one-entry allowlist, never reached by the webhook package"
affects: [11-04, 11-05]

# Actuals (#2632)
actuals:
  tokens: 6560
  tasks: 2
  commits: 2
commits: 2
plan_head_before: 09a72e719a2c4ae38004aadc797a10ccd347ea8a

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deliberate pytest.mark.db (not integration) for a subprocess-spawning test, per 11-CONTEXT.md D-05/D-06 and 11-RESEARCH.md Pitfall 1 -- the differentiator is 'needs only PostgreSQL' vs 'needs live agent-CLI credentials', not 'spawns a subprocess'"
    - "remove_worktree(force=True) (not shutil.rmtree) to erase a worktree's local trace -- a bare rm -rf leaves git's own worktree registration behind (prunable), which then blocks the same-branch reconstruction the test is trying to prove"
    - "popen()/wait_for() to observe a rebuilt worktree mid-flight (armed with DARK_FACTORY_FAKE_SLEEP_MS) rather than after the resumed process exits -- a COMPLETED run's worktree is removed again unconditionally (D-04) before the process ever returns, so a post-exit filesystem check would always be false regardless of whether reconstruction happened"
    - "AST-walk structural guards (test_single_mutation_path.py's idiom) extended to a second invariant: advance/drive definition-count and call-site allowlist, verified against actual source rather than assumed from the plan's prose"

key-files:
  created:
    - tests/db/test_cross_machine_resume.py
    - tests/unit/test_trigger_carries_no_lifecycle_logic.py
  modified: []

key-decisions:
  - "The plan's own must_haves prohibition (must not prove 'a different machine' with anything less than two real OS processes) is honored literally: both Test 1's pause/resume proof and Test 2's two-process half use tests.support.subprocess_runner.spawn/popen, never advance()/drive() in-process, for the cross-machine claim itself"
  - "Task 2's _PERMITTED_CALL_SITES is the one-entry frozenset {\"cli.py\"}, not the plan's literally-stated two-entry {\"orchestrator/runner.py\", \"cli.py\"} -- verified against src/dark_factory/orchestrator/runner.py that advance and drive are siblings (each independently calls the private _advance_once; neither calls the other), and that advance has zero call sites anywhere in src/dark_factory/ today (exported for tests and any future single-step trigger, but no shipped trigger calls it directly). The anti-vacuity check for that test asserts only that the aggregate collected call list is non-empty, not that both names individually have a call site, since advance legitimately has none"
  - "Task 1's worktree-deletion step uses the production remove_worktree(config_root, run_id, force=True) helper instead of the plan's suggested plain shutil.rmtree -- verified empirically that a bare rm -rf on a git-worktree-created directory leaves git's administrative registration behind, and a same-repository reconstruction attempt then fails with 'already used by worktree at <stale-path>', which would fail the test for a git-locking reason unrelated to the actual SC1 claim"
  - "Task 1's 'the worktree exists again' assertion is made while the resumed process is still in flight (via popen + DARK_FACTORY_FAKE_SLEEP_MS + wait_for), not after it exits -- because orchestrator/runner.py's D-04 COMPLETED cleanup removes the worktree again, synchronously, before the resuming CLI process ever returns, so a post-exit check would be false regardless of whether reconstruction genuinely happened"

requirements-completed: [TRIG-01, TRIG-04, HITL-06]

coverage:
  - id: D1
    description: "SC1/TRIG-04/HITL-06: a run paused by one real dark-factory OS process, with its worktree and artifact tree deleted from disk, is finished to COMPLETED by a second, entirely separate OS process that shares only PostgreSQL -- same run, same attempt, no second role_executions row, no second runs row, worktree rebuilt from persisted base_branch/working_branch columns plus git"
    requirement: TRIG-04
    verification:
      - kind: integration
        ref: "tests/db/test_cross_machine_resume.py#test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over"
        status: pass
    human_judgment: false
  - id: D2
    description: "SC2 (behavioural half): a two-process run and a single-process in-process control run of the identical configuration reach the identical terminal status and the identical ordered run_events type sequence"
    requirement: TRIG-01
    verification:
      - kind: integration
        ref: "tests/db/test_cross_machine_resume.py#test_the_two_process_run_and_a_single_process_run_are_indistinguishable"
        status: pass
    human_judgment: false
  - id: D3
    description: "The D-06 proof is collected under the db marker (not integration), so ci.yml's db-tier selection genuinely runs it -- proven by a dedicated --collect-only check, per 11-RESEARCH.md Pitfall 1"
    requirement: TRIG-04
    verification:
      - kind: other
        ref: "uv run pytest -q -m db --collect-only tests/db/test_cross_machine_resume.py (2 tests collected)"
        status: pass
    human_judgment: false
  - id: D4
    description: "TRIG-01 (structural): advance and drive are defined in exactly one module and called only from the verified trigger allowlist; the webhook package never calls or imports either name; the guard cannot pass vacuously after a rename"
    requirement: TRIG-01
    verification:
      - kind: unit
        ref: "tests/unit/test_trigger_carries_no_lifecycle_logic.py#test_advance_and_drive_are_defined_in_exactly_one_module"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trigger_carries_no_lifecycle_logic.py#test_only_named_triggers_call_the_lifecycle_entry_points"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trigger_carries_no_lifecycle_logic.py#test_the_webhook_receiver_calls_neither"
        status: pass
    human_judgment: false
  - id: D5
    description: "No regression across the full unrestricted suite, and HITL-06's resume-lease assumption (a clean WAITING_HUMAN pause releases its lease normally through typer.Exit, no force_lease_expiry needed) held without correction"
    verification:
      - kind: integration
        ref: "uv run pytest -q (full suite, all tiers) -- 1181 passed, 1 failed, 2 skipped in 1:32:20"
        status: pass
    human_judgment: false
    rationale: "The single failure (tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder) is the exact pre-existing, unrelated failure 11-01-SUMMARY.md and 11-02-SUMMARY.md already documented and confirmed via git stash -- a real claude CLI on PATH in this sandbox returns a real COMPLETED result where the test expects a credential-gated FAILED. Not touched by this plan; carried forward as the same accepted baseline."

duration: ~20min task-commits + ~1h32m full-suite verification wait against real remote Neon PostgreSQL
completed: 2026-09-30
status: complete
---

# Phase 11 Plan 03: Cross-machine resume proof and the one-orchestrator structural guard Summary

**Two real `dark-factory` OS processes, sharing only PostgreSQL and with the run's worktree and artifact tree deleted between them, take a paused run to `COMPLETED` -- proved db-tier so it runs in CI -- alongside an AST guard pinning `advance`/`drive` to a single defining module and a verified one-entry call-site allowlist.**

## Performance

- **Duration:** ~20 min of task-commit work; the remainder of wall-clock time was the plan's own required full-suite verification against a real remote Neon PostgreSQL branch (1h32m20s).
- **Completed:** 2026-09-30
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments

- `tests/db/test_cross_machine_resume.py` -- SC1/TRIG-04/HITL-06's proof: process A pauses a run on `NEEDS_INPUT`, its worktree and untracked artifact tree are deleted from disk via the production `remove_worktree` helper, and a genuinely separate process B (whose environment carries neither `DARK_FACTORY_FAKE_SCRIPT` nor `DARK_FACTORY_CRASH_AFTER`) resumes and finishes it to `COMPLETED` -- same run id, same `role_executions` row and `attempt`, no second `runs` row, worktree rebuilt and observed mid-flight (before the D-04 completion cleanup removes it again).
- The same module's second test proves SC2's behavioural half: a two-process run and an in-process single-process control run of the identical configuration reach the identical terminal status and identical ordered `run_events` type sequence.
- `tests/unit/test_trigger_carries_no_lifecycle_logic.py` -- TRIG-01's structural guard: `advance`/`drive` are defined in exactly one module (`orchestrator/runner.py`), called only from a verified one-entry allowlist (`cli.py`), and the webhook package never calls or imports either name -- restating `test_webhook_process_boundary.py`'s D-02 invariant from TRIG-01's own call-site angle.
- Both new modules are ruff-clean and mypy `--strict`-clean; `-m db --collect-only` confirms 2 tests are genuinely selected by the tier `ci.yml` will run (plan 11-04).
- Full unrestricted suite (`uv run pytest -q`) is green apart from the one pre-existing, unrelated, already-documented `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` failure.

## Task Commits

1. **Task 1: A run paused by one process is finished by another, with nothing carried over** - `c7b2de6` (test)
2. **Task 2: There is one orchestration implementation, and the guard says so** - `33ecbeb` (test)

## Files Created/Modified

- `tests/db/test_cross_machine_resume.py` -- the SC1 two-process proof and the SC2 behavioural-indistinguishability proof; `pytestmark = pytest.mark.db`.
- `tests/unit/test_trigger_carries_no_lifecycle_logic.py` -- the TRIG-01 AST structural guard; `pytestmark = pytest.mark.unit`.

## Decisions Made

See `key-decisions` in the frontmatter for full rationale on each of the four items below:

- The cross-machine claim is proved exclusively through `tests.support.subprocess_runner.spawn`/`popen`, never in-process `advance()`/`drive()` calls, per the plan's own zero-tolerance prohibition against simulating "a different machine."
- `_PERMITTED_CALL_SITES` is the one-entry `{"cli.py"}` the source tree actually contains, not the plan's literally-stated two-entry set -- `advance` and `drive` are siblings that both call the private `_advance_once`, and `advance` itself has zero call sites in the tree today.
- The worktree is erased via the production `remove_worktree(force=True)` helper rather than a bare `shutil.rmtree`, because a plain `rm -rf` leaves git's own worktree registration behind and breaks the reconstruction path the test is trying to prove.
- "The worktree exists again" is asserted while the resumed process is still in flight (via `popen` + `DARK_FACTORY_FAKE_SLEEP_MS` + `wait_for`), because the D-04 `COMPLETED` cleanup removes the worktree again synchronously before the process exits.

## Deviations from Plan

### Auto-fixed Issues

None found needing a fix during this session -- both target files (`tests/db/test_cross_machine_resume.py`, `tests/unit/test_trigger_carries_no_lifecycle_logic.py`) already existed on disk, complete and uncommitted, from a prior interrupted execution attempt against this same working tree. This session's work was: read both files in full against the plan's `must_haves`/`acceptance_criteria`/`<verify>` blocks, confirm they satisfy every stated criterion (including the three deviations each file's own docstring already documents and justifies -- see "Decisions Made" above, all three carried over unchanged from the prior attempt and independently re-verified here rather than re-authored), run every `<verify>` command fresh, and commit.

None of the three documented deviations required further action from this session; each was already resolved by judgment in the prior attempt's authoring and is recorded here as this plan's own decision record per the executor's Rule 1 (plan-internal inconsistency resolved by judgment, documented in the code's own docstring).

---

**Total deviations:** 0 new this session (3 pre-existing, already-documented deviations from the prior attempt, reviewed and confirmed correct, not modified).
**Impact on plan:** None -- the prior attempt's work matched the plan's intent in every case where it diverged from the plan's literal wording, and each divergence was independently re-verified against real source and a real PostgreSQL run before being accepted here.

## Issues Encountered

- **Both target test files already existed, untracked, on disk at session start.** `git status` showed `tests/db/test_cross_machine_resume.py` and `tests/unit/test_trigger_carries_no_lifecycle_logic.py` as untracked (file mtimes predating this session), with no `11-03-SUMMARY.md` present -- consistent with a prior execution attempt against this same working tree that completed implementation but was interrupted before verification/commit (the wave-2 sibling plans 11-02/11-04/11-05 and this plan's own long full-suite verification wall-clock make an interruption plausible). Rather than re-authoring from the plan text, this session read both files in full, cross-checked every line against the plan's `must_haves`, `acceptance_criteria`, and `<verify>`/`<verification>` blocks, and found full compliance -- then ran every verification command fresh (not trusted from before) before committing.
- **The HITL-06 lease-release assumption held without correction.** The plan's own `<flagged_assumptions>` section named "the lease is released cleanly by process A" as an assumption to verify, with an explicit fallback (`force_lease_expiry`) if wrong. `test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over` resumes process B with no `force_lease_expiry` call and passes -- confirming a `WAITING_HUMAN` pause exits cleanly through `typer.Exit(code=0)`, `run_lease.__exit__` runs, and the lease is released normally. No defect found; no follow-up needed.
- **Artifact-tree deletion was a no-op for this one-role pipeline.** Per the plan's own `<output>` request: `run_root(config_root, run_id)` (the path the test also asserts absent) was never populated in the first place, because this architecture nests the real run tree *inside* the worktree (`run_root(work_dir, run_id)`), never directly under `config_root`. The assertion is honest but not load-bearing for this one-role `[BA]` pipeline. A multi-role pipeline that writes artifacts via `store_role_artifacts` before pausing would populate the in-worktree tree, which Phase 3's deletion (`remove_worktree`) already covers as part of the worktree itself -- no additional deletion step would be needed, since the artifact tree lives inside the worktree directory this test already erases.
- **Full-suite run_events sequence (SC2 proof).** Both the two-process run and the single-process control run produced the same ordered type sequence for a one-role `[BA]` pipeline pausing once and resuming once: `RUN_CREATED, ROLE_STARTED, QUESTION_CREATED, RUN_PAUSED, HUMAN_ANSWER_RECEIVED, RUN_RESUMED, ROLE_COMPLETED, RUN_COMPLETED` (confirmed by both tests passing with `control_events == two_process_events`).
- **Measured wall-clock cost.** The db-tier target module (`tests/db/test_cross_machine_resume.py`, 2 tests, 4 spawned real subprocesses total across both tests) took 138.08s against the real remote Neon test branch -- the figure plan 11-04's CI timeout calibration should consume. The full unrestricted suite (`uv run pytest -q`, all tiers, 1184 test items) took 1h32m20s (5540.35s) against the same remote branch.

## User Setup Required

None -- no new credential or configuration surface. `DARK_FACTORY_TEST_DATABASE_URL` (set by the coordinator during plan 11-01) remained sufficient for this plan's db-tier and full-suite verification.

## Next Phase Readiness

- Plan 11-04 (CI tier enablement) can now flip `ci.yml`'s test-selection line to include the `db` marker with confidence: this plan's `--collect-only` check confirms `tests/db/test_cross_machine_resume.py` is genuinely selected, and its own measured wall-clock cost (138s for this module alone; 1h32m for the full unrestricted suite) is the concrete input plan 11-04's own Pitfall-2 timeout calibration needs -- note the full-suite figure includes `integration`-tier tests that `ci.yml`'s `db`-tier selection will not run in CI, so CI's actual added cost from this plan's two tests is closer to the 138s module-level figure than the full-suite figure.
- Plan 11-05 (deployer-facing documentation) is unaffected by this plan's scope (no dispatch/`resume.yml`-facing content here).
- No blockers. The one full-suite failure is the same pre-existing, unrelated, sandbox-specific issue carried since plan 11-01; no phase-11 action item follows from it.

## Self-Check: PASSED

Both claimed files (`tests/db/test_cross_machine_resume.py`, `tests/unit/test_trigger_carries_no_lifecycle_logic.py`) found on disk with the expected content; both claimed commits (`c7b2de6`, `33ecbeb`) found in git history via `git log --oneline --all`.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-09-30*
