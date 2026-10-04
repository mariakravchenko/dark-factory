---
phase: 12-observability-audit-surface
plan: 04
subsystem: observability
tags: [events, audit-trail, qa-verdict, sqlalchemy, pytest]

# Dependency graph
requires:
  - phase: 12-observability-audit-surface
    provides: "12-01's EventType catalog, events/reader.py read_events, apply_transition single-write-path, and the gate_events accumulate-then-splice pattern this plan's qa_verdict_events mirrors"
  - phase: 12-observability-audit-surface
    provides: "12-03's redaction call-site discipline (unrelated to this plan's files, but the shared phase precedent for how a new runner.py call site is documented)"
provides:
  - "EventType.QA_FAILED / EventType.QA_PASSED (D-07) -- the final two catalog members; the catalog is now complete, every one of its 22 members written by shipped code"
  - "orchestrator/runner.py's qa_verdict_events accumulator: exactly one QA_FAILED (payload: role, criteria_failed) or QA_PASSED (payload: role) EventWrite per terminal-role verdict, spliced into all three signal arms (ROLE_COMPLETED, ROLE_FAILED, ROLE_BOUNCED) alongside -- never instead of -- the generic ROLE_COMPLETED"
  - "tests/db/test_qa_verdict_events.py: PASS/FAIL-under-cap/FAIL-at-cap/distinctness/late-failure-honesty cardinality proof against real PostgreSQL"
affects: [12-06-run-report]

# Actuals (#2632) -- pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 7454
  tasks: 2
  commits: 2

# Commit ledger (#3968) -- measured, not narrated.
plan_head_before: c6cf97064450a67c8e7dddfd0aa9bcc1c491791a

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "qa_verdict_events mirrors gate_events' accumulate-then-splice shape exactly: declared as an empty list beside gate_events, appended to inside the existing structural verdict.computed_status block (never a new predicate), spliced via .extend(qa_verdict_events) into all three signal arms, and reset to [] in the GitError catch that already resets gate_events -- a verdict the run never durably acted on leaves no event claiming it did"
    - "The QA-outcome and quality-gate signal families are proven non-inferable from each other in the same db-tier module: a FAIL verdict carries QA_FAILED with zero QUALITY_GATE_* events (GATE-01's short-circuit), while a PASS verdict can carry QA_PASSED alongside a QUALITY_GATE_FAILED from the independent command re-run"
    - "A db-tier scenario that needs to inspect a single bounce's event shape steps with advance() in a loop, never drive(): drive() runs to a STOP status, and an attempt-independent FAIL fixture (LazyFourRoleWorker's qa_files override) would otherwise keep bouncing until the configured cap is genuinely exhausted"

key-files:
  created:
    - tests/db/test_qa_verdict_events.py
  modified:
    - src/dark_factory/events/catalog.py
    - src/dark_factory/orchestrator/runner.py
    - tests/unit/test_domain_enums.py

key-decisions:
  - "The 'FAIL at the cap' scenario uses a zero iteration cap (qa_developer_max_iterations=0, the test_iteration_cap_exhaustion.py 'zero cap' shape), not the cap=1 bounce-then-exhaust shape the plan's read_first pointed at: a bounce-then-exhaust run legitimately carries two QA_FAILED events (one per failing attempt), which would make the plan's own 'QA_FAILED present exactly once' acceptance criterion false. The zero-cap shape has exactly one QA attempt, making 'exactly once' true by construction."
  - "The 'FAIL under the cap' scenario steps with advance() in a loop until the first ROLE_BOUNCED event lands, rather than driving to completion -- LazyFourRoleWorker's qa_files override is attempt-independent (every QA attempt fails identically), so drive() would keep bouncing until the cap is genuinely exhausted, which is a different (and already-covered) scenario."
  - "The late-failure honesty test monkeypatches orchestrator.runner.commit_run_artifacts to raise GitError directly, rather than trying to provoke a real git failure -- this isolates the proof to exactly the commit/push boundary the plan's threat register names, with no dependency on filesystem permissions or git state to simulate failure."

requirements-completed: [OBS-02]

coverage:
  - id: D1
    description: "EventType has exactly 22 members and every one is written somewhere in shipped code -- no member is pre-declared for a future phase"
    requirement: OBS-02
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py#test_event_type_has_exactly_twenty_two_members_with_the_phase_two_five_six_nine_ten_and_twelve_types"
        status: pass
      - kind: other
        ref: "uv run python -c \"...[m.name for m in E if ('EventType.'+m.name) not in src]\" prints []"
        status: pass
    human_judgment: false
  - id: D2
    description: "QA_PASSED / QA_FAILED are each emitted from exactly one call site and spliced into all three signal arms (ROLE_COMPLETED, ROLE_FAILED, ROLE_BOUNCED), never replacing the generic ROLE_COMPLETED event (emission-site count unchanged at 2)"
    requirement: OBS-02
    verification:
      - kind: other
        ref: "uv run python -c \"...s.count('events.extend(qa_verdict_events)')\" prints 3; EventType.QA_PASSED/QA_FAILED counts print 1 1; EventType.ROLE_COMPLETED count unchanged at 2"
        status: pass
    human_judgment: false
  - id: D3
    description: "A PASS run leaves exactly one QA_PASSED / zero QA_FAILED; a FAIL-under-cap run leaves exactly one QA_FAILED / zero QA_PASSED alongside ROLE_BOUNCED with a non-empty criteria_failed naming the fixture's own failing criterion; a FAIL-at-cap run leaves exactly one QA_FAILED alongside ROLE_FAILED/RUN_FAILED"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_pass_verdict_emits_exactly_one_qa_passed_and_zero_qa_failed_in_order"
        status: pass
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_fail_under_cap_bounces_with_one_qa_failed_and_no_quality_gate_events"
        status: pass
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_fail_at_zero_cap_is_terminal_with_exactly_one_qa_failed"
        status: pass
    human_judgment: false
  - id: D4
    description: "QA_PASSED can coexist with QUALITY_GATE_FAILED in the same run, and a FAIL verdict emits zero QUALITY_GATE_* events of any kind -- the two signal families are non-inferable from each other"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_pass_verdict_coexists_with_quality_gate_failed"
        status: pass
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_fail_under_cap_bounces_with_one_qa_failed_and_no_quality_gate_events (converse assertion)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A commit/push failure after a verdict-bearing terminal role's apply_transition-eligible content leaves zero QA_PASSED/QA_FAILED events, alongside the zero artifacts rows the existing GitError catch already guarantees"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_commit_failure_after_verdict_leaves_zero_qa_verdict_events"
        status: pass
    human_judgment: false
  - id: D6
    description: "The production read_events(..., event_types=[...]) path agrees with the emission path on the same rows (not a hand-written query)"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py::test_fail_under_cap_bounces_with_one_qa_failed_and_no_quality_gate_events (read_events(run_id, event_types=[EventType.QA_FAILED], ...))"
        status: pass
    human_judgment: false
  - id: D7
    description: "The four pre-existing db-tier modules this plan's events touch (bounce, cap-exhaustion, artifact-created, schema-violation) pass unchanged -- the new events joined the stream, they did not displace anything"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_qa_bounce.py, tests/db/test_iteration_cap_exhaustion.py, tests/db/test_artifact_created_event.py, tests/db/test_artifact_schema_violation_fails_role.py (17 passed)"
        status: pass
    human_judgment: false

# Metrics
duration: ~2h (dominated by db/unit/integration verification against real PostgreSQL; two background pytest runs needed a re-run after the first was prematurely terminated by shell cleanup)
completed: 2026-10-04
status: complete
---

# Phase 12 Plan 4: QA-Verdict Audit Tie Summary

**`EventType.QA_FAILED` / `EventType.QA_PASSED` complete the 22-member event catalog, emitted from the existing structural `verdict.computed_status` block in `orchestrator/runner.py` and spliced into all three signal arms alongside the untouched `ROLE_COMPLETED` -- proven with exact event-cardinality assertions across PASS, FAIL-under-cap, FAIL-at-cap, PASS-with-gate-FAIL distinctness, and a late commit-failure scenario against real PostgreSQL.**

## Performance

- **Duration:** ~2h (verification-dominated: five pytest invocations against real PostgreSQL, totaling roughly 24 minutes of actual test execution, plus a full unfiltered unit-tier sweep of ~9 minutes)
- **Started:** 2026-10-04T05:21:15Z (Task 1 commit)
- **Completed:** 2026-10-04T07:22:45Z
- **Tasks:** 2/2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- `EventType` now has exactly 22 members, every one written by shipped code: `QA_FAILED`/`QA_PASSED` complete the set PROJECT.md declared, closing the Phase 12 observability catalog.
- `orchestrator/runner.py`'s `qa_verdict_events` accumulator emits exactly one `QA_FAILED` (payload: `role`, `criteria_failed` -- the failing criterion ids only, never free-text descriptions) or `QA_PASSED` (payload: `role`) event from the existing structural verdict block, spliced into `ROLE_COMPLETED`, `ROLE_FAILED`, and `ROLE_BOUNCED` alongside the generic `ROLE_COMPLETED` the worker earned -- no existing consumer of that event needs a new branch.
- A commit/push failure (`GitError`) voids the verdict event the same way it already voids `gate_events` -- a verdict the run never durably acted on leaves no event claiming it did.
- `tests/db/test_qa_verdict_events.py` (5 tests, new) proves exact event cardinality against real PostgreSQL across PASS, FAIL-under-cap (with a non-empty `criteria_failed` matching the fixture's own failing criterion), FAIL-at-a-zero-cap, PASS-coexists-with-`QUALITY_GATE_FAILED` distinctness, and the late-failure honesty scenario -- one assertion reads through the production `read_events(..., event_types=[...])` path.
- The four pre-existing db-tier modules this plan's events touch (`test_qa_bounce.py`, `test_iteration_cap_exhaustion.py`, `test_artifact_created_event.py`, `test_artifact_schema_violation_fails_role.py`) pass unchanged (17 passed) -- the new events joined the stream without displacing anything.
- `tests/integration/test_events_cli.py` (11 tests) confirms the new types render through the `dark-factory events` command and its `--type` filter with zero code change, as the plan claimed.

## Task Commits

Each task was committed atomically:

1. **Task 1: The verdict becomes an event, alongside the role event and never instead of it** - `24d503e` (feat)
2. **Task 2: Cardinality and distinctness, proven across PASS, FAIL-under-cap and FAIL-at-cap** - `5a1cadd` (test)

**Plan metadata:** (this commit, below)

## Files Created/Modified

- `src/dark_factory/events/catalog.py` - `QA_FAILED`/`QA_PASSED` added as the 21st/22nd members; module docstring updated to state the catalog is now complete and names the `QA_*`/`QUALITY_GATE_*` distinction D-07 locks.
- `src/dark_factory/orchestrator/runner.py` - `qa_verdict_events: list[EventWrite] = []` declared beside `gate_events`; appended to inside the existing `verdict.computed_status` FAIL/PASS arms; `.extend(qa_verdict_events)` spliced into all three signal-dispatch arms; reset to `[]` in the `GitError` catch (not the `WriteScopeViolation` catch, which deliberately leaves `gate_events` alone for the same reason).
- `tests/unit/test_domain_enums.py` - the single literal `EventType` member-count assertion bumped 20 -> 22; the Phase 12 member set widened to `{"ARTIFACT_CREATED", "QA_FAILED", "QA_PASSED"}`.
- `tests/db/test_qa_verdict_events.py` *(new)* - 5 db-tier tests proving exact cardinality, non-inferability, and late-failure honesty.

## Decisions Made

- The "FAIL at the cap" scenario uses a zero iteration cap rather than the plan's literal cap=1 bounce-then-exhaust configuration device: a bounce-then-exhaust run genuinely carries two `QA_FAILED` events (one per failing attempt), which would make "exactly one `QA_FAILED`" false. The zero-cap shape (one QA attempt, immediately terminal) is the one configuration that makes the plan's own acceptance criterion true by construction.
- The "FAIL under the cap" scenario steps with `advance()` in a loop until the first `ROLE_BOUNCED` event lands, rather than `drive()`-ing to completion, because `LazyFourRoleWorker`'s `qa_files` override is attempt-independent -- every QA attempt fails identically, so `drive()` would keep bouncing until the cap is genuinely exhausted (a different, already-covered scenario).
- The late-failure honesty test monkeypatches `orchestrator.runner.commit_run_artifacts` directly to raise `GitError`, isolating the proof to exactly the commit/push boundary the plan's threat register names, with no dependency on simulating a real git failure.

## Deviations from Plan

None - plan executed exactly as written for Task 1. Task 2's scenario-configuration choices (documented above under Decisions Made) are implementation discretion within the plan's stated acceptance criteria, not deviations from them -- each choice makes the plan's own literal assertion ("exactly once") true rather than working around it.

## Issues Encountered

- **Background-process termination during verification (tooling, not code):** the first attempt to run `tests/db/test_qa_verdict_events.py` against real PostgreSQL was silently killed when its backgrounding shell was cleaned up, producing an empty `[killed]` result with no test output. Re-run synchronously with an explicit long timeout; all 5 tests passed in 265s. No code changes resulted from this -- it was purely a session/tooling artifact, logged here so a future executor recognizes the symptom (an empty `[killed]` background-task output) rather than mistaking it for a real failure.
- **Full `pytest -m db -q` (the whole database tier) was not run exhaustively this session** -- only the new module plus the four pre-existing modules this plan's events directly touch were run against real PostgreSQL (22 passed total). Logged to `.planning/WINDOWS.md` (entry #20) per the broken-windows ledger. The full tier has historically taken 20 minutes to 4+ hours in this project (see STATE.md's Phase 11 entries); the targeted subset is the set the plan's own threat register and task `<verify>` blocks name as load-bearing for this change.
- **Pre-existing, out-of-scope failure (already logged, phase 12, WINDOWS.md entry #18):** `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this sandbox because a live `ANTHROPIC_API_KEY`/`claude` CLI is present, so the live adapter completes instead of the test's expected credential-absent `FAILED`. Confirmed present again this session (819 passed / 1 failed / 1 skipped out of the full unit tier) -- unrelated to this plan's files, not touched.
- **Pre-existing, out-of-scope `mypy`/`ruff format` findings (already logged in prior phase-12 SUMMARYs):** `mypy src/dark_factory` reports 2 `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` (optional `mcp` extra not installed); `ruff format --check .` reports 19 pre-existing unformatted files, none of which this plan touches. Confirmed: all four files this plan created/modified pass `ruff format --check` cleanly in isolation.

All plan-scoped verification passed: Task 1's and Task 2's own `<verify>`/`<acceptance_criteria>` commands, the targeted db-tier modules (22 passed), the full unit tier (819 passed, 1 pre-existing unrelated failure, 1 skipped), the integration events-CLI suite (11 passed), `ruff check .` (clean), and `ruff format --check` on every file this plan touched (clean).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The `EventType` catalog is now complete at 22 members, every one written by shipped code -- no member is pre-declared for a future phase. Plan 12-06 (run report) can treat the catalog as a closed, stable surface.
- The QA-verdict and quality-gate signal families are proven non-inferable from each other in the same db-tier module, giving a future report-generation plan a tested basis for distinguishing "did the work meet acceptance criteria" from "did the independent re-run pass."
- No blockers for 12-06.

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-04*

## Self-Check: PASSED

- FOUND: src/dark_factory/events/catalog.py
- FOUND: src/dark_factory/orchestrator/runner.py
- FOUND: tests/unit/test_domain_enums.py
- FOUND: tests/db/test_qa_verdict_events.py
- FOUND: commit 24d503e
- FOUND: commit 5a1cadd
