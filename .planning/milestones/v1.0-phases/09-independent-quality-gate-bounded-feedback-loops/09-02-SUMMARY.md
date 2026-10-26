---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 02
subsystem: orchestrator
tags: [bounded-feedback-loop, bounce, lifecycle-transition, iteration-cap, run-events, LOOP-02, LOOP-03, LOOP-04]

requires:
  - phase: 09-independent-quality-gate-bounded-feedback-loops
    provides: [quality_gate.py, the verdict-read/gate-execution block in runner.py, plan 09-01's EventType.QUALITY_GATE_* trio and its pre-answered EventType-naming decision]
provides:
  - "Signal.ROLE_BOUNCED and previous_node -- the pure, structural backwards-transition primitive lifecycle.transition() maps to the pipeline's preceding node"
  - "EventType.ROLE_BOUNCED -- the fourth Phase 9 event, reported instead of the ROLE_FAILED/RUN_FAILED run-is-dead pair when a rejection is still under its iteration cap"
  - "_bounce_or_fail -- the shared runner.py helper implementing D-04/D-06's cap-then-choose-signal rule for both the QA-verdict and quality-gate FAIL edges"
  - "AttemptAwareFourRoleWorker -- the attempt-aware test fixture that makes multi-attempt bounce scenarios expressible against a real drive() run"
  - "db-tier proof of both bounce edges (test_qa_bounce.py) and both exhaustion paths plus idempotent re-drive (test_iteration_cap_exhaustion.py)"
affects: [09-03-feedback-delivery, 12-observability-audit-history]

actuals:
  tokens: 18466
  tasks: 4
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Cap-then-choose-signal helper (_bounce_or_fail): one small pure function shared by both feedback edges so the QA-verdict and quality-gate FAIL paths cannot drift on D-04/D-06's rule"
    - "A bounced attempt's role_executions.status stays COMPLETED (worker genuinely completed; only run-level routing differs), with the bounce recorded via a dedicated EventType member rather than the status column -- mirrors CAPABILITY_DENIED's precedent"
    - "Structural bounce-target computation (previous_node, mirroring next_node) keeps the role-name-literal guard green and generalizes past the current 4-role config"
    - "Gitignored-path test fixture writes (AttemptAwareFourRoleWorker's sentinel_writes) to stay invisible to write-scope enforcement's untracked-file scan, rather than a write_scope config workaround"

key-files:
  created:
    - tests/db/test_qa_bounce.py
    - tests/db/test_iteration_cap_exhaustion.py
  modified:
    - src/dark_factory/domain/signal.py
    - src/dark_factory/orchestrator/lifecycle.py
    - src/dark_factory/workflows/pipeline.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/events/catalog.py
    - tests/unit/test_lifecycle.py
    - tests/unit/test_domain_enums.py
    - tests/support/fake_artifacts.py
    - tests/db/test_quality_gate_gates_the_run.py
    - tests/db/test_artifact_schema_violation_fails_role.py
    - tests/db/test_context_builder_retry_isolation.py

key-decisions:
  - "Task 1's checkpoint (role_executions.status + EventType shape for a bounced attempt) was pre-answered by the user before dispatch: Option B1 -- COMPLETED status with the bounce recorded in `result`, plus one new EventType.ROLE_BOUNCED member. The plan's own recommended option and the shape Task 2's action text already assumed."
  - "The bounce/fail decision is factored into one module-level helper (_bounce_or_fail) rather than duplicated inline at the QA-verdict and gate-FAIL call sites, so D-04/D-06's rule cannot drift between the two edges."
  - "A gate-FAIL sentinel fixture write goes under the gitignored .dark-factory/runs/ prefix, not the bare worktree root -- avoids tripping enforce_write_scope's zero-tolerance empty write_scope in these db-test fixtures, discovered while designing Task 3's gate-bounce scenario."

patterns-established:
  - "Cap-then-choose-signal is checked BEFORE the signal is picked (LOOP-03's literal wording), never after, and the increment rides the same apply_transition call as every other field -- no new lock site for a counter column."

requirements-completed: [LOOP-02, LOOP-03, LOOP-04]

coverage:
  - id: D1
    description: "transition() computes a backwards move to the pipeline's preceding node from a ROLE_BOUNCED signal, rejects it from the first node with IllegalTransitionError, and TERMINAL_STATUSES/WAITING_HUMAN reject it on the existing guards before the new arm is reached"
    requirement: "LOOP-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_legal_transitions_produce_documented_next_state"
        status: pass
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_illegal_pairs_raise"
        status: pass
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_previous_node_returns_none_for_the_first_node"
        status: pass
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_previous_node_returns_the_preceding_node_mid_pipeline"
        status: pass
    human_judgment: false
  - id: D2
    description: "signal_from_result never returns Signal.ROLE_BOUNCED for any WorkerResultStatus -- the bounce is orchestrator-computed, never worker-reported"
    requirement: "LOOP-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py::test_signal_from_result_maps_worker_result_status"
        status: pass
    human_judgment: false
  - id: D3
    description: "The iteration counter is read off RunState and compared to its configured cap BEFORE the signal is chosen -- under cap yields Signal.ROLE_BOUNCED, at or over cap yields Signal.ROLE_FAILED (D-04, D-06); a cap of 0 needs no special case"
    requirement: "LOOP-03"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py::test_qa_fail_then_pass_bounces_once_and_completes"
        status: not_run
      - kind: db
        ref: "tests/db/test_iteration_cap_exhaustion.py::test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce"
        status: not_run
    human_judgment: true
    rationale: "This sandbox has no reachable PostgreSQL 17 -- no Docker, no local initdb/pg_ctl, and no DARK_FACTORY_TEST_DATABASE_URL, the same pre-existing constraint every prior db-tier plan in this project (Phases 6/7/8, plan 09-01) has documented. Both files collect cleanly (6 tests, zero import/collection errors, confirmed this session) but were not executed here. Re-run once a real PostgreSQL 17 is available: `uv run pytest -m db -q tests/db/test_qa_bounce.py tests/db/test_iteration_cap_exhaustion.py`."
  - id: D4
    description: "A QA-verdict FAIL increments only Run.qa_developer_iterations and a quality-gate FAIL increments only Run.quality_gate_iterations; neither counter is ever folded into the other (D-06)"
    requirement: "LOOP-03"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py::test_qa_fail_then_pass_bounces_once_and_completes"
        status: not_run
      - kind: db
        ref: "tests/db/test_qa_bounce.py::test_gate_fail_then_pass_bounces_once_and_completes"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Collection-verified clean."
  - id: D5
    description: "The increment is applied through apply_transition's existing counter_increments parameter under its with_for_update row lock and expected_owner_token fence -- no new lock site anywhere outside persistence/mutations.py"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "grep -rn 'with_for_update|pg_advisory' src/dark_factory/ excluding persistence/mutations.py and persistence/repositories.py -- zero matches"
        status: pass
    human_judgment: false
  - id: D6
    description: "When the failing role is the pipeline's first node there is no earlier role to bounce to -- the runner chooses Signal.ROLE_FAILED with reason no_earlier_role_to_bounce_to, and lifecycle.transition() independently raises IllegalTransitionError for a ROLE_BOUNCED signal in that position (LOOP-04 adjacency)"
    requirement: "LOOP-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_lifecycle.py::test_illegal_pairs_raise[first-node-bounce case]"
        status: pass
      - kind: db
        ref: "tests/db/test_artifact_schema_violation_fails_role.py::test_qa_verdict_fail_with_no_earlier_role_fails_the_run"
        status: not_run
    human_judgment: true
    rationale: "The unit-tier proof (transition() rejecting a first-node bounce) is fully verified. The db-tier proof (a single-role [QA] pipeline's runner-level routing) needs the same missing Postgres as D3; collection-verified clean."
  - id: D7
    description: "With retry.qa_developer_max_iterations set to 0 the first QA FAIL transitions the run straight to FAILED with the exhaustion reason -- zero bounces, no zero-value special case"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_iteration_cap_exhaustion.py::test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Satisfied by construction in _bounce_or_fail (0 < 0 is already false, no branch needed) and collection-verified."
  - id: D8
    description: "The two feedback edges are evaluated in a fixed total order within one attempt -- the verdict is folded first and a FAIL verdict short-circuits the gate -- so exactly one counter can ever be touched per attempt"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py (both scenarios assert the untouched counter stays 0)"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Satisfied by construction (plan 09-01's existing if/else already short-circuits; this plan added no new gate/verdict branch)."
  - id: D9
    description: "Re-driving an already-FAILED exhausted run writes no further run_events rows and no further counter increments, via the existing STOP_STATUSES early return in _advance_once"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_iteration_cap_exhaustion.py::test_redriving_an_exhausted_run_is_a_no_op"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Collection-verified clean."
  - id: D10
    description: "On a gate FAIL under cap the run's current_role moves back to the pipeline node immediately before the terminal role, and the next advance() inserts a fresh role_executions row with attempt = previous + 1 for that role (D-05)"
    requirement: "LOOP-02"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py::test_gate_fail_then_pass_bounces_once_and_completes"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. D-05 needed zero new production code (09-RESEARCH.md); this scenario exercises the existing _enter_role/_advance_once dispatch for real."
  - id: D11
    description: "On exhaustion the run reaches RunStatus.FAILED with a RUN_FAILED event whose payload names the exhausted counter, its value and its configured cap, and every prior attempt is still present as its own role_executions row"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_iteration_cap_exhaustion.py::test_qa_cap_exhausted_ends_the_run_failed_with_every_attempt_persisted"
        status: not_run
      - kind: db
        ref: "tests/db/test_iteration_cap_exhaustion.py::test_gate_cap_exhausted_ends_the_run_failed_with_every_attempt_persisted"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Collection-verified clean."
  - id: D12
    description: "MUST NOT discard, overwrite or reuse an earlier attempt's role_executions row when a bounce re-enters an earlier role -- every attempt remains independently queryable"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py (both scenarios assert 2+2 independently-attempted role_executions rows, 4 distinct ids)"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Satisfied by construction (D-05 reuses the existing _enter_role attempt-increment machinery, unmodified)."
  - id: D13
    description: "MUST NOT report a bounce through the ROLE_FAILED / RUN_FAILED event pair -- those mean the run is dead"
    requirement: "LOOP-04"
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py (both scenarios assert zero RUN_FAILED events)"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D3. Collection-verified clean."

duration: ~50min
completed: 2026-09-23
status: complete
---

# Phase 9 Plan 02: Bounded Feedback Loops Summary

**A QA-verdict FAIL and a quality-gate FAIL each route through a new `Signal.ROLE_BOUNCED` that sends the run back to the Developer with a fresh attempt row when the relevant iteration counter is still under its configured cap, and terminally to `FAILED` with a machine-readable exhaustion reason once it isn't -- turning plan 09-01's two unconditional terminal rejections into the phase's headline bounded feedback loop.**

## Performance
- **Duration:** ~50min
- **Started:** 2026-09-23T05:47:00Z (approximate)
- **Completed:** 2026-09-23T06:11:00Z
- **Tasks:** 4 (1 pre-answered checkpoint, 3 auto/tdd)
- **Files modified:** 13 (2 created, 11 modified)

## Accomplishments
- `workflows/pipeline.py` gains `previous_node`, an exact structural mirror of `next_node`, keeping the role-name-literal guard green and the bounce target computed from the pipeline, never a literal.
- `domain/signal.py` gains `Signal.ROLE_BOUNCED`, deliberately excluded from `signal_from_result`'s result-status mapping -- a bounce is orchestrator-computed, never a worker's own reported status.
- `orchestrator/lifecycle.py`'s `transition()` gains the `ROLE_BOUNCED` arm: computes the backwards move via `previous_node`, raises `IllegalTransitionError` with no earlier role, and is rejected from `TERMINAL_STATUSES`/`WAITING_HUMAN` by the existing guards before the new arm is ever reached.
- `events/catalog.py` gains `EventType.ROLE_BOUNCED` (16 members total), reported instead of `ROLE_FAILED`/`RUN_FAILED` when a rejection is still under cap.
- `orchestrator/runner.py`'s `_bounce_or_fail` helper implements D-04/D-06's cap-then-choose-signal rule once, shared by both the QA-verdict-FAIL and quality-gate-FAIL branches, so the two edges cannot drift. Wired into the existing gate block: the cap is checked before the signal is picked (LOOP-03), the counter increment rides the existing `apply_transition` call (no new lock site), and a new `ROLE_BOUNCED` dispatch arm keeps `role_executions.status = "COMPLETED"` (load-bearing for plan 09-03's feedback delivery) while writing a dedicated audit event instead of the run-is-dead pair.
- `tests/support/fake_artifacts.py`'s new `AttemptAwareFourRoleWorker` makes "QA fails on attempt 1, passes on attempt 2" and "the gate fails until the Developer's next attempt creates a sentinel" expressible against a real `drive()` run, for the first time in this project.
- `tests/db/test_qa_bounce.py` and `tests/db/test_iteration_cap_exhaustion.py`: 6 new db-tier scenarios proving both bounce edges, both exhaustion paths, the zero-cap terminal edge, and re-drive idempotency -- written and collection-verified (see Coverage).

## Task Commits
1. **Task 1: A run can move backwards -- the pure bounce transition** - `3185dc2` (feat)
2. **Task 2: A rejection now loops instead of killing the run -- cap check, bounce, counter** - `fa4f26e` (feat)
3. **Task 3: Prove the loop and its ceiling against real runs** - `fef4650` (test)

## Files Created/Modified
- `src/dark_factory/workflows/pipeline.py` - new `previous_node` function, mirroring `next_node`
- `src/dark_factory/domain/signal.py` - new `Signal.ROLE_BOUNCED` member, excluded from the result-status mapping
- `src/dark_factory/orchestrator/lifecycle.py` - new `ROLE_BOUNCED` transition arm; module docstring's legal graph extended
- `src/dark_factory/events/catalog.py` - new `EventType.ROLE_BOUNCED` member (16 total)
- `src/dark_factory/orchestrator/runner.py` - `_bounce_or_fail` helper, `_EXHAUSTION_REASON_TO_COUNTER` map, hoisted retry-cap reads, the two decision points rewired, new `ROLE_BOUNCED` dispatch arm, `RUN_FAILED` payload extended with exhaustion facts, `counter_increments` passed into `apply_transition`
- `tests/unit/test_lifecycle.py` - `ROLE_BOUNCED` legal/illegal parametrized cases, direct `previous_node` tests
- `tests/unit/test_domain_enums.py` - `EventType` count 15->16, `Signal` membership set updated to include `ROLE_BOUNCED`
- `tests/support/fake_artifacts.py` - new `AttemptAwareFourRoleWorker` class
- `tests/db/test_qa_bounce.py` (new) - both bounce edges proved end to end
- `tests/db/test_iteration_cap_exhaustion.py` (new) - both exhaustion paths, the zero-cap edge, re-drive idempotency
- `tests/db/test_quality_gate_gates_the_run.py` - two plan 09-01 scenarios' default retry caps overridden to 0 to preserve their original single-attempt semantics under the new bounce logic; exhaustion-reason string assertions updated
- `tests/db/test_artifact_schema_violation_fails_role.py` - one stale plan 09-01 scenario (single-role `[QA]` pipeline, schema-valid FAIL verdict) updated: now correctly fails via `no_earlier_role_to_bounce_to` instead of asserting the pre-Phase-9 `COMPLETED` outcome
- `tests/db/test_context_builder_retry_isolation.py` - docstring points to the new real bounce proof; assertions unchanged

## Decisions Made
- Task 1's `checkpoint:decision` was pre-answered by the user before dispatch: **Option B1** -- a bounced attempt keeps `role_executions.status = "COMPLETED"` (bounce recorded in `result`) plus one new `EventType.ROLE_BOUNCED` member. The plan's own recommended option and the shape Task 2's `<action>` text already assumed (`re_status = _ROLE_COMPLETED`). Logged here, not re-asked.
- The bounce/fail decision is factored into one shared module-level helper (`_bounce_or_fail`) rather than duplicated inline at the two call sites, so D-04/D-06's rule cannot drift between the QA-verdict and quality-gate edges.
- A gate-bounce test fixture's sentinel file write goes under the gitignored `.dark-factory/runs/` prefix rather than the bare worktree root -- discovered while designing Task 3's gate-FAIL-then-PASS scenario that a write_scope-zero-tolerance role's own `enforce_write_scope` check would otherwise revert an untracked worktree-root file before the gate ever re-checks it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Two plan 09-01 db tests' default retry caps would now bounce instead of terminally failing on their scripted repeated rejection**
- **Found during:** Task 2, while reasoning through `tests/db/test_quality_gate_gates_the_run.py`'s existing scenarios against the new bounce logic.
- **Issue:** `test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary` and `test_a_failing_verdict_short_circuits_the_gate_entirely` both drive a `LazyFourRoleWorker` that repeats the same FAIL content on every attempt, and both used `config_root_factory`'s default retry caps (3, 2). Under the new `_bounce_or_fail` logic, `0 < 2`/`0 < 3` is true, so the very first rejection would now bounce instead of failing immediately, and the tests' `qa_execution.error.get("error")` assertions (`"quality_gate_fail"` / `"qa_verdict_fail"`) would no longer match the *final* attempt's error once it eventually exhausted after several bounces.
- **Fix:** Extended `_write_four_role_tree`'s config-tree helper to accept `qa_developer_max_iterations`/`quality_gate_max_iterations` overrides (the same build-then-overwrite idiom the file already used for `quality_gate.commands`), set the relevant cap to 0 in each of the two scenarios to preserve their original single-attempt intent, and updated the two error-string assertions to the exhaustion reason `_bounce_or_fail` now produces even at cap 0 (`"quality_gate_max_iterations_exhausted"` / `"qa_developer_max_iterations_exhausted"`, since `0 < 0` is already false and the helper never distinguishes "always was over cap" from "exhausted after bounces").
- **Files modified:** `tests/db/test_quality_gate_gates_the_run.py`
- **Commit:** `fa4f26e`

**2. [Rule 1 - Bug] A stale plan 09-01 (Phase 4-era) db test asserted `RunStatus.COMPLETED` for a schema-valid FAIL verdict on a single-role `[QA]` pipeline**
- **Found during:** Task 2, while auditing every existing db-tier test that reaches the terminal-role gate block for the new bounce logic's effect.
- **Issue:** `test_qa_verdict_fail_advances_the_run_exactly_like_pass` (its own docstring: "Phase 4 does not branch the transition on verdict content") predates plan 09-01's own verdict-gate wiring and was never updated when that wiring landed -- the module's own docstring incorrectly claimed every scenario in the file "ends FAILED via a schema violation raised before that new logic is ever reached", but this one scenario's `verdict.json` is schema-*valid* (an internally consistent FAIL), so it genuinely reaches the terminal-role gate block and was already silently broken by plan 09-01 alone, before this plan's own change. Left uncaught because plan 09-01's db-tier suite was never executed in that plan's sandbox (same missing-Postgres constraint this plan also carries).
- **Fix:** Renamed to `test_qa_verdict_fail_with_no_earlier_role_fails_the_run`, updated the module docstring to record the correction, and rewrote the assertions: the run now ends `FAILED` with `error.get("error") == "no_earlier_role_to_bounce_to"` (this module's single-role `[QA]` pipeline makes QA both the terminal *and* the first role, so `previous_node` returns `None` -- LOOP-04's adjacency case, not a bounce), asserting `ROLE_FAILED`/`RUN_FAILED` present and `ROLE_BOUNCED` absent.
- **Files modified:** `tests/db/test_artifact_schema_violation_fails_role.py`
- **Commit:** `fa4f26e`

### None beyond the above
Every other part of the plan (the `previous_node`/`ROLE_BOUNCED` primitives, the `_bounce_or_fail` helper's shape, the dispatch-arm wiring, the `AttemptAwareFourRoleWorker` fixture, the two new db-tier test modules) was implemented exactly as specified.

## Issues Encountered

**db-tier execution deferred (not a failure):** This sandbox has no reachable PostgreSQL 17 -- no Docker, no local `initdb`/`pg_ctl`, and no `DARK_FACTORY_TEST_DATABASE_URL` -- the same pre-existing, documented constraint every prior db-tier plan in this project (Phases 6, 7, 8, plan 09-01) has carried. All touched db-tier modules (`test_qa_bounce.py`, `test_iteration_cap_exhaustion.py`, `test_quality_gate_gates_the_run.py`, `test_artifact_schema_violation_fails_role.py`, `test_context_builder_retry_isolation.py`) collect cleanly (17+6 = 23 items across the touched files, zero import/collection errors, confirmed this session via `pytest -m db --collect-only`) but were not executed here. See the `coverage` entries above for the honest `human_judgment: true` accounting.

**Fully executed and green this session:** `pytest -m "unit or contract" -q` (650 passed, 1 skipped, 325 deselected, confirmed twice -- once before and once after Task 3's changes) and `mypy src/dark_factory` / `ruff check .` (both clean; mypy's two `mcp.server` import-not-found errors in `tools/mcp_transport.py` are pre-existing and unrelated to this plan, confirmed via `git stash`).

## User Setup Required

A reachable PostgreSQL 17 instance is required to execute this plan's db-tier scenarios. Once available, re-run:

```bash
uv run pytest -m db -q tests/db/test_qa_bounce.py tests/db/test_iteration_cap_exhaustion.py
```

Expected: 6 passed, 0 skipped. Also re-run the full db tier to confirm no regression on the pre-existing suite (per the plan's own `<verification>` section), and the two 09-01 modules this plan's Task 2 fixed:

```bash
uv run pytest -m db -q
```

## Next Phase Readiness

Plan 09-03 (feedback delivery) can proceed: a bounced attempt's `role_executions.status` stays `"COMPLETED"` (Option B1's load-bearing choice), so `context/builder.py`'s `_latest_completed_execution` filter already sees it -- plan 09-03's job is resolving `verdict.json`/`quality_gate.json` into the bounced attempt's next `RoleContext`, not changing anything this plan shipped. No other Phase 9 plan depends on anything this plan did not ship.

## Self-Check: PASSED

- FOUND: `src/dark_factory/workflows/pipeline.py` (`previous_node`)
- FOUND: `src/dark_factory/domain/signal.py` (`ROLE_BOUNCED`)
- FOUND: `src/dark_factory/orchestrator/lifecycle.py` (`ROLE_BOUNCED` arm)
- FOUND: `src/dark_factory/events/catalog.py` (`ROLE_BOUNCED` member)
- FOUND: `src/dark_factory/orchestrator/runner.py` (`_bounce_or_fail`)
- FOUND: `tests/support/fake_artifacts.py` (`AttemptAwareFourRoleWorker`)
- FOUND: `tests/db/test_qa_bounce.py`
- FOUND: `tests/db/test_iteration_cap_exhaustion.py`
- FOUND commit: `3185dc2` (Task 1)
- FOUND commit: `fa4f26e` (Task 2)
- FOUND commit: `fef4650` (Task 3)
