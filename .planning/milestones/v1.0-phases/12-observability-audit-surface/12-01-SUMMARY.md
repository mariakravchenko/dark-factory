---
phase: 12-observability-audit-surface
plan: 01
subsystem: observability
tags: [events, audit-trail, rich, typer, redaction, sqlalchemy]

# Dependency graph
requires:
  - phase: 10-one-orchestrator-many-triggers
    provides: the persistence/mutations.py apply_transition single-write-path, the EventType catalog, read_status/observability.status as the sibling pattern
provides:
  - "EventType.ARTIFACT_CREATED (D-06), emitted once per artifact write inside the existing apply_transition call"
  - "dark_factory.events.reader.read_events — the one new module permitted to query run_events for a read path"
  - "dark_factory.observability.render.render_events_text / DEFAULT_RENDER_WIDTH — pure DTO rendering, events-free"
  - "dark_factory.domain.views.EventRow — frozen DTO sibling of RunView"
  - "dark-factory events <run-id> Typer command — the first new CLI surface since status"
  - "Two architectural guards: a package-wide observability events-free sweep, and a generalized read-command AST guard over every @app.command()"
affects: [12-02-events-filters-and-json, 12-03-runs-and-artifacts-commands, 12-04-qa-verdict-events, 12-06-run-report]

# Actuals (#2632)
actuals:
  tokens: 11200
  tasks: 3
  commits: 3

# Commit ledger (#3968) — measured, not narrated.
plan_head_before: d12c5ff5b91151cfba4161af6818035b92de8bbc

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "events/reader.py as a sibling of observability/status.py (not a member of the observability package) — keeps the status read path's events-free closure trivially provable while still letting a read path legitimately query run_events"
    - "Package-wide transitive-import-closure sweep (glob + reuse of test_status_import_graph.py's walker) instead of a single hand-named root module, so sibling modules added in later plans are covered on arrival with no edit"
    - "rich.console.Console.print(..., markup=False, soft_wrap=True) for parseable, never-wrapped, never-markup-interpreted CLI line output"
    - "Build-the-event-list-once-after-every-clearing-arm pattern for a derived EventWrite list (artifact_events), mirroring the existing gate_events accumulate-then-splice shape"

key-files:
  created:
    - src/dark_factory/events/reader.py
    - src/dark_factory/observability/render.py
    - tests/db/test_artifact_created_event.py
    - tests/integration/test_events_cli.py
    - tests/integration/test_cli_commands_are_reads.py
    - tests/unit/test_observability_import_graph.py
  modified:
    - src/dark_factory/events/catalog.py
    - src/dark_factory/domain/views.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/cli.py
    - tests/unit/test_domain_enums.py

key-decisions:
  - "events/reader.py is a sibling of observability/status.py, not a member of the observability package -- the one new module permitted to query run_events, keeping the status read path's events-free closure trivially provable"
  - "ARTIFACT_CREATED events are built once from the final artifact_writes value, after every arm that can clear it to [] has already run, then spliced into ROLE_COMPLETED/ROLE_BOUNCED only -- a late write-scope failure after collect_role_artifacts succeeded leaves zero artifacts rows and zero ARTIFACT_CREATED events (ART-04 honesty)"
  - "render_events_text prints each EventRow.as_line with markup=False and soft_wrap=True so payload content (e.g. a list-shaped value) is never misread as rich markup and a line is never wrapped -- one line per event holds for any configured width"

patterns-established:
  - "Pattern: a read-model module that touches run_events lives beside observability/, not inside it -- the package boundary is the architectural claim, enforced by a package-wide import-closure sweep rather than a single named root"
  - "Pattern: every @app.command() body in cli.py is swept for a RunStatus comparison by one generalized AST guard, non-vacuity proven by a baseline command-name superset check plus a self-detection counterexample"

requirements-completed: []  # OBS-02, OBS-03, TRIG-02 all declared by later plans in this phase too (12-02/12-03) -- requirements.ready-ids reported 0/3 ready; none marked complete here.

coverage:
  - id: D1
    description: "EventType.ARTIFACT_CREATED is emitted by orchestrator/runner.py, once per artifact write, in the same apply_transition call that inserts the matching artifacts row"
    requirement: OBS-02
    verification:
      - kind: db
        ref: "tests/db/test_artifact_created_event.py#test_artifact_created_events_exactly_match_artifact_rows_and_render"
        status: pass
      - kind: db
        ref: "tests/db/test_artifact_created_event.py#test_role_failing_after_collect_role_artifacts_succeeded_leaves_zero_artifacts_and_events"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two events written by the same apply_transition call share one created_at value and are ordered deterministically and distinctly by seq"
    requirement: OBS-03
    verification:
      - kind: db
        ref: "tests/db/test_artifact_created_event.py#test_two_events_from_one_apply_transition_share_created_at_distinct_seq"
        status: pass
    human_judgment: false
  - id: D3
    description: "dark-factory events <run-id> prints one redacted line per event in seq order, exits 0 for an existing run (including a short/empty-ish list) and 2 for an unknown or malformed id"
    requirement: TRIG-02
    verification:
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_events_for_a_completed_run_names_role_and_run_lifecycle_in_order"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_unknown_run_id_exits_2_with_empty_stdout"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_malformed_run_id_exits_2_with_empty_stdout"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_events_for_a_run_parked_mid_flight_exits_0_with_a_short_event_list"
        status: pass
    human_judgment: false
  - id: D4
    description: "src/dark_factory/observability/ is proven events-free package-wide (not just the single status.py module); events/reader.py is confirmed to live outside the swept package"
    verification:
      - kind: unit
        ref: "tests/unit/test_observability_import_graph.py#test_every_observability_module_is_swept_and_none_reaches_events"
        status: pass
      - kind: unit
        ref: "tests/unit/test_observability_import_graph.py#test_events_reader_is_outside_the_swept_package"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every @app.command() body in cli.py is guarded against a RunStatus comparison, non-vacuously"
    verification:
      - kind: integration
        ref: "tests/integration/test_cli_commands_are_reads.py#test_every_command_body_avoids_a_run_status_comparison"
        status: pass
      - kind: integration
        ref: "tests/integration/test_cli_commands_are_reads.py#test_the_guard_detects_its_own_subject"
        status: pass
    human_judgment: false

# Metrics
duration: 40min
completed: 2026-10-03
status: complete
---

# Phase 12 Plan 1: End-to-End Artifact-Write Audit Tie Summary

**`EventType.ARTIFACT_CREATED` emitted from `orchestrator/runner.py`, read back by a new `events/reader.py`, rendered redacted via `observability/render.py`, and surfaced through the new `dark-factory events <run-id>` Typer command — proven end to end against real PostgreSQL.**

## Performance

- **Duration:** 40 min
- **Started:** 2026-10-03T10:09:39Z
- **Completed:** 2026-10-03T10:49:15Z
- **Tasks:** 3
- **Files modified:** 11 (6 created, 5 modified)

## Accomplishments

- `EventType.ARTIFACT_CREATED` is the twentieth member of the catalog, emitted exactly once per artifact a role attempt actually wrote, riding the same `apply_transition` call that inserts the `artifacts` row.
- `dark_factory.events.reader.read_events` — a sibling of `observability/status.py`, the one new module permitted to query `run_events`, never ordering by `created_at`.
- `dark_factory.observability.render.render_events_text` — pure, I/O-free rendering of already-read `EventRow` DTOs, events-free by construction.
- `dark-factory events <run-id>` — a real Typer command, proven through a real subprocess: happy path, unknown-id exit 2, malformed-id exit 2, and a mid-flight-parked run exiting 0 with a short event list.
- Two architectural guards: a package-wide `observability/` events-free import sweep (replacing the single-module root with a directory glob so later sibling modules are covered with no edit), and a generalized AST guard over every `@app.command()` body in `cli.py`.
- ART-04 transparency proven adversarially: a role whose `collect_role_artifacts` call succeeded but was later discovered to carry an out-of-scope write leaves zero `artifacts` rows and zero `ARTIFACT_CREATED` events — a durability claim is never made for content that was never actually recorded as durable.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end "an artifact write shows up in the audit trail" — one path only** - `d46e1af` (feat)
2. **Task 2: The Typer wiring and the exit-code contract, proven as a real subprocess** - `26cd573` (test)
3. **Task 3: The architectural boundary becomes a package-wide sweep, not a single-module check** - `59b9fad` (test)

## Files Created/Modified

- `src/dark_factory/events/catalog.py` - `ARTIFACT_CREATED` added, docstring narrative updated to name only QA_FAILED/QA_PASSED as still pending
- `src/dark_factory/domain/views.py` - `EventRow` frozen DTO + `as_line()` renderer, sibling of `RunView`
- `src/dark_factory/events/reader.py` *(new)* - `read_events(run_id, *, event_types, session_factory)`, the one module permitted to query `run_events` for a read path
- `src/dark_factory/observability/render.py` *(new)* - `DEFAULT_RENDER_WIDTH`, `render_events_text` — pure rendering, no I/O, no `dark_factory.events` import
- `src/dark_factory/orchestrator/runner.py` - `artifact_events` built once from the final `artifact_writes`, spliced into the `ROLE_COMPLETED`/`ROLE_BOUNCED` arms
- `src/dark_factory/cli.py` - `_redactor()`/`_parse_run_id()` factored out of `status`; new `events` command
- `tests/db/test_artifact_created_event.py` *(new)* - exact artifact/event parity, same-transaction adjacency, ART-04 honesty on a late failure
- `tests/integration/test_events_cli.py` *(new)* - the CLI exit-code contract via a real subprocess
- `tests/integration/test_cli_commands_are_reads.py` *(new)* - generalized read-command AST guard
- `tests/unit/test_observability_import_graph.py` *(new)* - package-wide events-free sweep
- `tests/unit/test_domain_enums.py` - `EventType` cardinality bumped 19 → 20 (deviation, see below)

## Decisions Made

- `events/reader.py` lives beside `observability/`, not inside it, so the status read path's events-free closure stays trivially provable while a read path can still legitimately query `run_events`.
- `artifact_events` is computed once, after every arm that can clear `artifact_writes` to `[]` has already run, and spliced only into `ROLE_COMPLETED`/`ROLE_BOUNCED` — never `ROLE_FAILED`/`ROLE_NEEDS_INPUT`, where `artifact_writes` is already empty and an empty splice would be dead code.
- `render_events_text` prints with `markup=False, soft_wrap=True` so a payload containing a list-shaped value is never misread as rich markup and no line is ever wrapped — "one line per event" holds for any width.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bumped `EventType` cardinality test from nineteen to twenty members**
- **Found during:** Task 3 (verification step of the full enum-cardinality assertion the task's own `<verify>` command runs)
- **Issue:** `tests/unit/test_domain_enums.py` asserted a literal nineteen-member count and Phase 2/5/6/9/10 member sets; Task 1 added the twentieth member (`ARTIFACT_CREATED`), which this plan's own Task 3 acceptance criteria require the test to assert (`EventType` member count is now `20`).
- **Fix:** Renamed the test to `test_event_type_has_exactly_twenty_members_with_the_phase_two_five_six_nine_ten_and_twelve_types`, bumped the literal count to `20`, and added the Phase 12 member set `{"ARTIFACT_CREATED"}` alongside the existing per-phase sets, following the same pattern every earlier phase's addition used.
- **Files modified:** `tests/unit/test_domain_enums.py`
- **Verification:** `pytest -m unit -q tests/unit/test_domain_enums.py` passes; re-run as part of Task 3's full verify command (26 tests passed).
- **Committed in:** `59b9fad` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix — Rule 1).
**Impact on plan:** Necessary to keep an existing enum-cardinality guard accurate after this plan's own catalog change; no scope creep, no behavior change beyond the test's own literal.

## Issues Encountered

- A full, unfiltered `pytest -m unit` sweep could not be completed standalone in this session: `tests/unit/test_unit_tier_needs_no_database.py` spawns a full nested `pytest -m "unit or contract"` child process by design (G-11-3 regression guard), and that nested run did not return within a practical window here — consistent with this project's own documented history of multi-hour stalls on full-suite sweeps against real external resources (see STATE.md's Phase 11 entries). Not a regression introduced by this plan: Task 3's own named five-file verify command (26 tests) passed cleanly in 0.15s, and a broader `pytest -m unit` run with the eighteen subprocess-spawning modules excluded passed 594/595 (1 skipped) in 26.31s with zero regressions attributable to this plan's changes.
- That one unrelated failure (`tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`) is pre-existing and out of this plan's scope: the test expects `ClaudeCodeWorker.execute({})` to return `FAILED` with no `ANTHROPIC_API_KEY` configured, but this execution environment has a real credential available, so the live adapter actually completed. Not touched — outside the files this plan modifies, and fixing it would mean altering test expectations around credential-dependent behavior unrelated to the observability surface. Logged to the ledger below.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The whole vertical (catalog → emission → `apply_transition` → `run_events` → read model → redaction → `rich` render → Typer command → exit code) is proven end to end on exactly one event type. Plan 12-02 can now widen the `events` command (`--json`, `--type`) and plan 12-03 can add `runs`/`artifacts` commands following the identical thin-wrapper + AST-guard pattern this plan established.
- `RunView` is confirmed byte-identical in field set and order to its pre-plan state (acceptance criterion verified inline).
- No blockers. The pre-existing `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` failure (credential-environment-dependent, unrelated to this plan) should be flagged to whoever next touches `tests/unit/test_worker_registry_names.py` or the Claude Code worker contract suite.

## Self-Check: PASSED

- `src/dark_factory/events/reader.py` — FOUND
- `src/dark_factory/observability/render.py` — FOUND
- `tests/db/test_artifact_created_event.py` — FOUND
- `tests/integration/test_events_cli.py` — FOUND
- `tests/integration/test_cli_commands_are_reads.py` — FOUND
- `tests/unit/test_observability_import_graph.py` — FOUND
- Commit `d46e1af` — FOUND in `git log --oneline --all`
- Commit `26cd573` — FOUND in `git log --oneline --all`
- Commit `59b9fad` — FOUND in `git log --oneline --all`

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-03*
