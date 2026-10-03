---
phase: 12-observability-audit-surface
plan: 02
subsystem: observability
tags: [events, runs, rich, typer, redaction, sqlalchemy, json]

# Dependency graph
requires:
  - phase: 12-observability-audit-surface
    provides: "12-01's events/reader.py read_events (with its already-declared event_types filter), observability/render.py's DEFAULT_RENDER_WIDTH/_console/render_events_text, domain/views.py's RunView/EventRow/NULL_MARKER/Redactor, and the dark-factory events <run-id> Typer command"
provides:
  - "dark_factory.domain.views.RunListRow -- frozen DTO sibling of RunView (run_id, status, source_kind, created_at, updated_at), no source_ref"
  - "dark_factory.observability.run_detail.read_run_list -- the non-events, write-free read-model sibling of status.py, ordered created_at DESC, id DESC"
  - "dark_factory.observability.render.render_runs_table -- rich table with explicit min_width on id/status/timestamp columns so a UUID is never ellipsized at width 80 or 120"
  - "dark_factory.observability.render.render_events_json -- a single JSON array, keys mirroring the run_events columns, redactor applied once over the whole dumped structure"
  - "dark-factory runs [--status] Typer command -- the entry point to every other command, the only one that produces a run id without the operator already knowing one"
  - "--json and --type (repeatable) on the existing dark-factory events command"
affects: [12-03-runs-and-artifacts-commands, 12-04-qa-verdict-events, 12-06-run-report]

# Actuals (#2632)
actuals:
  tokens: 7833
  tasks: 2
  commits: 3

# Commit ledger (#3968) -- measured, not narrated.
plan_head_before: 02d7bd40e9c2e38b57b471d2cfd726cbba9672c8

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "render_events_json takes no width parameter -- JSON is not a terminal rendering and must never be wrapped, ellipsized or boxed, unlike every other renderer in observability/render.py"
    - "A CLI filter option (--status, --type) is parsed through its enum inside the command body, before any query is constructed, exiting 2 with the offending value named on stderr -- an unknown value must never be indistinguishable from a real empty result"
    - "min_width declared per-column on a rich.table.Table so a long identifier (a UUID) survives rendering at any configured width instead of being silently ellipsized with a '...' character"

key-files:
  created:
    - src/dark_factory/observability/run_detail.py
    - tests/integration/test_runs_cli.py
    - tests/db/test_events_reader_sees_every_bounce.py
  modified:
    - src/dark_factory/domain/views.py
    - src/dark_factory/observability/render.py
    - src/dark_factory/cli.py
    - tests/integration/test_events_cli.py

key-decisions:
  - "RunListRow carries no source_ref -- the runs table's job is triage, and a long free-text task reference is exactly what would force the id column to shrink below its 36-character minimum"
  - "read_run_list orders Run.created_at.desc(), Run.id.desc() -- the id tiebreak is load-bearing, not decoration: two runs created inside one clock tick would otherwise render in an order PostgreSQL is free to vary between calls"
  - "render_runs_table declares min_width=36/13/20/20 on id/status/created_at/updated_at -- empirically required: with no min_width, rich 15.0.0 ellipsizes an over-wide cell at both width 80 and 120, and an ellipsized UUID cannot be pasted into 'resume'"
  - "render_events_json applies redactor once over the whole model_dump(mode='json')-ed list before json.dumps -- redact is recursive over mappings/lists, so the nested payload is covered without a per-key walk"
  - "--type is parsed through EventType per value before read_events is called -- an invalid filter never reaches a query, and a filter matching nothing (0 rows) stays distinguishable from a filter that was rejected (exit 2)"

patterns-established:
  - "Pattern: a read command's filter option is validated through its enum inside the command body, before the query -- status and events --type now share this exact shape"

requirements-completed: []  # OBS-03/TRIG-02 shared with sibling plans in this phase (12-03); requirements.ready-ids reported 0/2 ready -- none marked complete here.

coverage:
  - id: D1
    description: "dark-factory runs renders a rich table of every run -- id, status, source, created_at, updated_at -- newest first with a deterministic created_at/id tiebreak; --status filters and rejects an unknown value with exit 2 before any query; a 36-character run id survives intact at render width 80 and 120"
    requirement: OBS-03
    verification:
      - kind: integration
        ref: "tests/integration/test_runs_cli.py#test_two_runs_both_appear_with_full_intact_ids_newest_first"
        status: pass
      - kind: integration
        ref: "tests/integration/test_runs_cli.py#test_status_filter_includes_matching_and_excludes_others"
        status: pass
      - kind: integration
        ref: "tests/integration/test_runs_cli.py#test_unknown_status_exits_2_with_empty_stdout"
        status: pass
      - kind: integration
        ref: "tests/integration/test_runs_cli.py#test_render_runs_table_on_an_empty_list_shows_headers_and_no_rows"
        status: pass
      - kind: unit
        ref: "tests/unit/test_observability_import_graph.py#test_every_observability_module_is_swept_and_none_reaches_events"
        status: pass
    human_judgment: false
  - id: D2
    description: "dark-factory events <run-id> supports --json (one clean JSON array, column-shaped keys, same content and seq order as text mode) and a repeatable --type filter that rejects an unknown event-type name with exit 2 before querying; a real QA-verdict-FAIL feedback loop's every ROLE_BOUNCED cycle is readable both through the filter and through the unfiltered trail at the same seq values"
    requirement: TRIG-02
    verification:
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_json_mode_emits_exactly_one_clean_json_array"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_json_element_count_and_seq_order_match_text_mode"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_every_json_element_key_set_equals_the_five_name_column_set"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_type_filter_returns_only_matching_events"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_type_filter_is_repeatable_and_returns_both_types"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_unknown_type_exits_2_with_empty_stdout_before_any_query"
        status: pass
      - kind: integration
        ref: "tests/integration/test_events_cli.py#test_type_filter_matching_nothing_exits_0_with_an_empty_event_list"
        status: pass
      - kind: db
        ref: "tests/db/test_events_reader_sees_every_bounce.py#test_role_bounced_filter_matches_the_unfiltered_trail_at_the_same_seqs"
        status: pass
    human_judgment: false

# Metrics
duration: ~35min (Task 1 pre-committed in a prior session; this session completed Task 2 plus full-tier verification)
completed: 2026-10-03
status: complete
---

# Phase 12 Plan 2: The `runs` List and the Full `events` Contract Summary

**`dark-factory runs [--status]` with a never-ellipsized run id, plus `--json`/`--type` on `dark-factory events`, closing D-03/D-05 of the observability read surface.**

## Performance

- **Duration:** ~35 min this session (Task 1's commit, `ff8d536`, predates this session; this session wrote and verified Task 2 plus the plan's full integration/db/mypy/ruff verification sweep)
- **Started:** 2026-10-03T13:40:00Z (approx, this session)
- **Completed:** 2026-10-03T15:48:00Z
- **Tasks:** 2
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments

- `dark-factory runs` lists every run newest-first with a deterministic `created_at DESC, id DESC` tiebreak; a full 36-character run id survives rendering intact at width 80 and 120 thanks to explicit `min_width` on every column `rich` would otherwise ellipsize.
- `--status` validates against `RunStatus` before any query runs, so a typo gives a named `exit 2` error rather than an indistinguishable empty table.
- `dark-factory events <run-id> --json` emits one clean, parseable JSON array whose element count and `seq` order match text mode exactly, and whose element keys are exactly the five `run_events` columns the DTO carries.
- `--type` is a repeatable, validated filter: an unknown event-type name exits 2 before any query, and a filter matching nothing is a valid, empty answer (exit 0), not a fault.
- A real QA-verdict FAIL bounce, driven in-process end to end, proves the transparency prohibition mechanically: `read_events(event_types=[ROLE_BOUNCED])` returns the one bounce cycle the run actually performed, and the unfiltered `read_events(run_id)` still carries that same row at the same `seq` -- the filter narrows the view without ever rewriting the trail.
- Full `pytest -m integration -q` tier (185 passed, 2 skipped, 0 failed, ~31 min against the configured external PostgreSQL) re-confirmed with zero regressions from this plan's changes.

## Task Commits

Each task was committed atomically:

1. **Task 1: "Which of my runs needs attention?" -- the runs list, with an id you can actually paste** - `ff8d536` (feat) -- committed in a prior session on this branch, before this executor was dispatched
2. **Task 2: The full `events` contract -- machine-readable output and type-focused debugging** - `f7cf823` (test)

**Plan metadata:** see final commit hash in the orchestrator's completion report.

## Files Created/Modified

- `src/dark_factory/domain/views.py` - `RunListRow` frozen DTO sibling of `RunView` (run_id, status, source_kind, created_at, updated_at)
- `src/dark_factory/observability/run_detail.py` *(new)* - `read_run_list(*, status, session_factory)`, events-free/write-free, ordered `created_at DESC, id DESC`
- `src/dark_factory/observability/render.py` - `render_runs_table` (explicit `min_width` per column) and `render_events_json` (single JSON array, redactor applied once over the whole structure, no `width` parameter)
- `src/dark_factory/cli.py` - `runs` command (`--status`, validated before querying); `events` command extended with `--json` / `--type` (repeatable, validated per-value)
- `tests/integration/test_runs_cli.py` *(new)* - real-subprocess proof: intact ids, newest-first ordering, `--status` filter/rejection, empty-table header rendering
- `tests/integration/test_events_cli.py` - extended with `--json`/`--type` subprocess proof: one clean array, count/seq parity with text mode, exact key set, repeatable filter, unknown-value rejection, empty-match success
- `tests/db/test_events_reader_sees_every_bounce.py` *(new)* - drives a real QA-verdict FAIL bounce (`AttemptAwareFourRoleWorker` + `QA_VERDICT_FAIL_FILES`, the same scenario `tests/db/test_qa_bounce.py` already proves at the persistence layer) and asserts the `read_events` filtered/unfiltered parity at the `seq` level

## Decisions Made

- `RunListRow` deliberately omits `source_ref` to keep the `id` column's 36-character minimum achievable at narrow widths.
- `render_events_json` takes no `width` argument by design -- JSON output must never be wrapped or ellipsized, so there is nothing for a width to configure.
- The new db-tier test duplicates (rather than imports) `test_qa_bounce.py`'s private `_write_four_role_tree` helper, since that module's helper is prefixed `_` and this test suite has no cross-db-module import convention to date.

## Deviations from Plan

None - plan executed exactly as written. Task 1 was already implemented and committed (`ff8d536`) before this executor session began; this session verified it, then implemented and verified Task 2 (`f7cf823`) per the plan's own action/verify/acceptance-criteria text.

## Issues Encountered

- **Pre-existing `mcp_transport.py` mypy gap (out of scope):** `uv run mypy src/dark_factory` reports two `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` because the optional `mcp` extra is not installed in this sandbox (`uv pip show mcp` confirms it is absent). Not caused by this plan -- none of the five files this plan modified (`domain/views.py`, `events/reader.py` (unchanged), `observability/run_detail.py`, `observability/render.py`, `cli.py`) are `mcp_transport.py`, and all five pass `mypy` cleanly when checked directly. Logged to `deferred-items.md`.
- **Pre-existing `ruff format` drift across 19 files (out of scope, carried from Phase 11's `11-10` entry):** `uv run ruff format --check .` names the same 19 pre-existing files Phase 11 already deferred. This plan's new file, `tests/db/test_events_reader_sees_every_bounce.py`, is confirmed independently formatted. Logged to `deferred-items.md`.
- A full unscoped `pytest -m unit -q` sweep was not run standalone in this session, per this project's own documented history of multi-hour/stalled full-suite sweeps against real external resources driven by a nested subprocess-spawning regression guard (see STATE.md's Phase 11 entries and `12-01-SUMMARY.md`'s identical note). The task-scoped unit verify commands this plan's own `<verify>` names (`tests/unit/test_observability_import_graph.py`, `tests/unit/test_status_import_graph.py`) passed cleanly (7 passed in 0.06s).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The `runs`/`events` read surface is now feature-complete for this plan's scope: `runs [--status]`, `events [--json] [--type ...]`. Plan 12-03 can add the `artifacts` command following the identical thin-wrapper + AST-guard pattern 12-01/12-02 established, and plan 12-04 can extend the `events` catalog with QA-verdict events without touching this plan's CLI surface.
- `RunView` and `EventRow` are unchanged by this plan; `RunListRow` is confirmed to carry exactly the five declared fields in the declared order.
- No blockers introduced by this plan. The two pre-existing out-of-scope issues (mcp mypy gap, 19-file ruff format drift) are recorded in `deferred-items.md` for a future environment-hygiene pass.

## Self-Check: PASSED

- `src/dark_factory/observability/run_detail.py` - FOUND
- `tests/integration/test_runs_cli.py` - FOUND
- `tests/db/test_events_reader_sees_every_bounce.py` - FOUND
- Commit `ff8d536` - FOUND in `git log --oneline --all`
- Commit `f7cf823` - FOUND in `git log --oneline --all`

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-03*
