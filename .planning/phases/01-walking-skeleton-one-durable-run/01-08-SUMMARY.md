---
phase: 01-walking-skeleton-one-durable-run
plan: 08
subsystem: observability
tags: [typer, cli, sqlalchemy, read-model, redaction, import-graph-guard, tdd, state-06]

requires:
  - phase: 01-04
    provides: "Run / RoleExecution / RunEvent ORM models; the runs column set incl. source_kind/source_ref/base_branch/working_branch/created_at/updated_at"
  - phase: 01-05
    provides: "load_run_state / RunState — the columns-only read discipline read_status mirrors; advance_session_factory session-factory test seam"
  - phase: 01-06
    provides: "cli.py Typer app (run / resume) + exit-code contract; start_run / drive; keyword-only session_factory injection seam"
  - phase: 01-07
    provides: "DARK_FACTORY_CRASH_AFTER test hook that leaves a committed intermediate state at BA"
  - phase: 01-03
    provides: "redact() / scrub_known_values(); Settings.known_secret_values()"
provides:
  - "src/dark_factory/domain/views.py — RunView: a frozen pydantic v2 value object with the exact D-12 field set (run_id, source_kind, source_ref, status, current_role, current_step, latest_attempt, created_at, updated_at, base_branch, working_branch). as_text() renders one `key: value` line per field in declaration order with `-` as the null marker; as_text()/as_json() take an optional `redactor` callable so the caller owns scrubbing and this module imports nothing from dark_factory.events. as_json() serialises via model_dump(mode=json) — datetimes and the status enum as strings, one object, no preamble."
  - "src/dark_factory/observability/status.py — read_status(run_id, *, session_factory=_default_session) -> RunView via exactly two selects (the runs row + the latest role_executions row, ORDER BY attempt DESC LIMIT 1); UnknownRunError(LookupError) when the run row is absent; null current_role/latest_attempt when no role_executions row yet; no run_events query; no import from dark_factory.events (directly or transitively); no write of any kind"
  - "src/dark_factory/observability/__init__.py (empty)"
  - "cli.py — the `status` command: `dark-factory status <run-id>` prints RunView.as_text() and exits 0; `--json` prints RunView.as_json() and routes structlog to stderr; a non-UUID id or an unknown run exits 2 with the message on stderr and an empty stdout (D-05); the source is passed through redact() before rendering in both modes; the command body holds no lifecycle logic"
  - "tests/db/test_status_from_columns.py — 9 db tests: the SC3 proof (RunView compares equal across an inserted / fully-deleted / type-corrupted run_events row and with a completely empty event log), plus null-role/attempt, no-write, field-list shape, and source redaction in both render modes"
  - "tests/unit/test_status_import_graph.py — AST transitive-import-closure guard that dark_factory.observability.status never reaches dark_factory.events (+ a sanity test proving the walk resolves — persistence.mutations does reach it)"
  - "tests/integration/test_status_cli.py — 8 integration tests: happy path in both modes, JSON key-set == text field-set, strict whole-stdout JSON parse, exit-2/empty-stdout for unknown and malformed ids, a run parked at BA by the Plan 07 crash hook reported as BA/attempt 1, and an AST guard on the command body"
affects: ["Phase 11 CI trigger (consumes status --json)", "Phase 12 observability surface (extends RunView / the --json key set)"]

actuals:
  tokens: 7200
  tasks: 2
  commits: 5
  plan_head_before: 09f757ba8c129815f790f3a1300c06ee8fdaf8e6

tech-stack:
  added: []
  patterns:
    - "The status read path is an architecture constraint, not only a behaviour: observability/status.py imports nothing from dark_factory.events and a unit test walks the transitive dark_factory import closure to prove it — a read path that CAN fold the audit log will eventually be made to"
    - "read_status does its own two selects (runs row + latest role_executions row) rather than reusing load_run_state, because RunView needs six more runs columns (source, timestamps, branches) than RunState carries — same columns-only discipline, one extra query avoided"
    - "RunView owns rendering (as_text / as_json) but not scrubbing: both methods take an optional `redactor` callable the CLI supplies (functools.partial(redact, known_secrets=...)), so the DTO and the read path stay free of any dark_factory.events import while the source is still redacted in BOTH output modes (T-01-01)"
    - "as_text() and as_json() share one _rendered_fields() built from model_dump(mode='json') and iterate type(self).model_fields, so the text field set and the JSON key set cannot drift"
    - "read_status takes the same keyword-only session_factory injection seam as advance/drive/run_state (01-06), so a db test drives it through advance_session_factory with no monkeypatching; it still 'takes exactly one required argument, the run id'"

key-files:
  created:
    - "src/dark_factory/domain/views.py"
    - "src/dark_factory/observability/__init__.py"
    - "src/dark_factory/observability/status.py"
    - "tests/db/test_status_from_columns.py"
    - "tests/unit/test_status_import_graph.py"
    - "tests/integration/test_status_cli.py"
  modified:
    - "src/dark_factory/cli.py — added the `status` command + `_route_logs_to_stderr` helper; +49 lines"

key-decisions:
  - "Source redaction is applied by the CLI via an injected `redactor`, not inside observability/status.py or domain/views.py: the plan action says as_text() 'passes the source through the redaction path', but redact() lives in dark_factory.events.redaction and the same plan forbids the status read path from importing dark_factory.events transitively. Resolution: as_text()/as_json() accept an optional `redactor` param; cli.py passes functools.partial(redact, known_secrets=get_settings().known_secret_values()). Source is redacted in both modes (T-01-01); the import-graph guard stays green. (Rule 3 - blocking, contradictory plan wording.)"
  - "read_status implements its own two selects instead of calling load_run_state — RunView's D-12 field set needs source_kind/source_ref/created_at/updated_at/base_branch/working_branch, none of which RunState exposes; reusing it would still require a second Run read."
  - "The import-graph test walks the transitive closure by AST-parsing each dark_factory module file and BFS-ing over its `import` / `from dark_factory... import` targets — a shallow check on status.py's own imports would miss a helper two hops away. A sanity test asserts the walk really resolves (persistence.mutations provably reaches dark_factory.events)."
  - "--json routes structlog to stderr via configure_logging(PrintLoggerFactory(file=sys.stderr)) before emitting (T-01-34). Nothing in the status path currently logs, so this is defensive — the integration test parses the entire stdout strictly regardless."
  - "ruff format run alongside ruff check (CLAUDE.md mandates both; plan <verify> lists only ruff check) — one test file rewrapped, committed as style(01-08); same call every prior 01-0x executor made."

patterns-established:
  - "observability/ is now a tier: read models live here, import persistence + domain, and never import events. Phase 12's richer status surface extends RunView and adds to observability/ without touching the orchestrator."
  - "A CLI read command (status) is a pure render over a read-model function — no status comparison, no branching on lifecycle state; an AST test enforces it, seeding Phase 11's 'every trigger funnels into one advance' discipline."

requirements-completed: [STATE-02, STATE-03, STATE-06]

coverage:
  - id: D1
    description: "read_status(run_id) reconstructs a RunView from the runs row plus the single latest role_executions row alone; UnknownRunError on an unknown id; null current_role/latest_attempt for a run with no role_executions row yet; performs no INSERT/UPDATE/DELETE"
    requirement: "STATE-06"
    verification:
      - kind: integration
        ref: "tests/db/test_status_from_columns.py (test_reports_status_role_and_attempt_from_columns, test_unknown_run_id_raises_unknown_run_error, test_run_with_no_role_execution_yet_reports_null_role_and_attempt, test_read_status_performs_no_write) — real PostgreSQL 18.6"
        status: pass
    human_judgment: false
  - id: D2
    description: "SC3 — the RunView a run reports compares equal before and after an extra run_events row is inserted, after every run_events row for the run is deleted, and after an event's type is rewritten to an unrecognised string; and it is still correct with a completely empty event log"
    requirement: "STATE-06"
    verification:
      - kind: integration
        ref: "tests/db/test_status_from_columns.py::test_runview_survives_insert_delete_and_corruption_of_run_events, ::test_runview_correct_with_a_completely_empty_event_log — real PostgreSQL 18.6"
        status: pass
    human_judgment: false
  - id: D3
    description: "The status read path (dark_factory.observability.status) imports nothing from dark_factory.events, transitively or directly"
    requirement: "STATE-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_status_import_graph.py::test_status_read_path_never_imports_the_events_module (+ ::test_the_walk_actually_resolves_transitive_imports sanity)"
        status: pass
    human_judgment: false
  - id: D4
    description: "RunView carries exactly the D-12 field set; as_text() renders one `key: value` line per field including base_branch / working_branch with a null marker; the source is passed through the redaction path before rendering in both text and --json modes"
    requirement: "STATE-02"
    verification:
      - kind: integration
        ref: "tests/db/test_status_from_columns.py::test_runview_exposes_the_full_d12_field_set, ::test_as_text_renders_one_line_per_field_including_the_branch_fields, ::test_source_reference_is_redacted_in_both_render_modes"
        status: pass
    human_judgment: false
  - id: D5
    description: "`dark-factory status <id>` prints the D-12 text field list and exits 0; `--json` prints exactly one clean JSON object with the same field set; an unknown or malformed id exits 2 with an empty stdout and the message on stderr; the command body calls read_status and contains no comparison to a RunStatus member"
    requirement: "STATE-03"
    verification:
      - kind: integration
        ref: "tests/integration/test_status_cli.py (8 tests: both modes, key-set equality, strict JSON parse, unknown/malformed exit-2, crash-hook BA report, command-body AST guard) — CLI as subprocess vs real PostgreSQL 18.6"
        status: pass
      - kind: other
        ref: "manual: `uv run dark-factory status <id>` / `--json` / unknown-id — 11-line field list, 11-key JSON object, exit 2 on unknown"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-09-08
status: complete
---

# Phase 01 Plan 08: Status From Columns Summary

**`dark-factory status <run-id>` reports a run's position — status, current role, attempt, source (redacted), timestamps, branches — from the `runs` row plus the latest `role_executions` row alone, in an 11-field `key: value` list and, under `--json`, the identical field set as one clean JSON object; `read_status` in the new `observability/` tier imports nothing from `dark_factory.events` (proven by a transitive import-graph guard) and its output is provably invariant under an inserted, fully-deleted or type-corrupted `run_events` row (SC3).**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-09-08
- **Tasks:** 2 (both `tdd="true"`, RED → GREEN)
- **Files created:** 6; **modified:** 1 (`src/dark_factory/cli.py`)

## Accomplishments

- `RunView` (`domain/views.py`): frozen pydantic v2 value object, exactly the D-12 field set, `as_text()` / `as_json()` sharing one `model_dump(mode="json")`-based renderer so the text field set and JSON key set cannot drift; both take an optional `redactor` so the source is scrubbed in both modes without this module importing `dark_factory.events`.
- `read_status` (`observability/status.py`): two selects (runs row + latest `role_executions` row), `UnknownRunError` when absent, null role/attempt when no execution yet, no `run_events` query, no write, no events import.
- The `status` CLI command: text list, `--json` object, exit 2 + empty stdout for unknown/malformed ids, structlog routed to stderr under `--json`, no lifecycle logic in the body.
- SC3 locked by `tests/db/test_status_from_columns.py` (9 db tests) — the event-log vandalism sequence is the centrepiece — and by `tests/unit/test_status_import_graph.py` (the architecture constraint).

## Task Commits

1. **Task 1 (RED):** `61a56b4` `test(01-08)` — `tests/db/test_status_from_columns.py` + `tests/unit/test_status_import_graph.py`; RED = `dark_factory.domain.views` / `dark_factory.observability.status` absent
2. **Task 1 (GREEN):** `7e6e97d` `feat(01-08)` — `domain/views.py`, `observability/__init__.py`, `observability/status.py`; 9 db + 2 import-graph tests green
3. **Task 2 (RED):** `b48f4d3` `test(01-08)` — `tests/integration/test_status_cli.py`; RED = no `status` command (exit 2)
4. **Task 2 (GREEN):** `435f494` `feat(01-08)` — the `status` command + `_route_logs_to_stderr` in `cli.py`; 8 integration tests green
5. **Follow-up:** `409ddb8` `style(01-08)` — `ruff format` rewrap of one assert message in the Task 2 test (CLAUDE.md mandates `ruff format` alongside `ruff check`)

**Plan metadata:** docs commit (this SUMMARY + STATE + ROADMAP + REQUIREMENTS).

`plan_head_before = 09f757ba8c129815f790f3a1300c06ee8fdaf8e6`; `git rev-list --count 09f757b..HEAD` = 5.

## RunView field list & the --json key set (Phase 11 / 12 extend, do not replace)

Declaration order = rendered order for both `as_text()` and `as_json()`:

| field | source column | text render | JSON render |
|---|---|---|---|
| `run_id` | `runs.id` | str | str |
| `source_kind` | `runs.source_kind` | str (through redactor) | str (through redactor) |
| `source_ref` | `runs.source_ref` | str or `-` (through redactor) | str or `null` (through redactor) |
| `status` | `runs.status` | `RunStatus` value | enum value string |
| `current_role` | `runs.current_role` | str or `-` | str or `null` |
| `current_step` | `runs.current_step` | int or `-` | int or `null` |
| `latest_attempt` | latest `role_executions.attempt` (or `None`) | int or `-` | int or `null` |
| `created_at` | `runs.created_at` | ISO-8601 | ISO-8601 |
| `updated_at` | `runs.updated_at` | ISO-8601 | ISO-8601 |
| `base_branch` | `runs.base_branch` | `-` (null until Phase 5) | `null` |
| `working_branch` | `runs.working_branch` | `-` (null until Phase 5) | `null` |

`as_text()` → one `key: value` line per row, in this order. `as_json()` → `json.dumps` of the same 11 keys as one object, no preamble, no trailing text.

## Decisions Made

- **Source redaction moved to the CLI via an injected `redactor`.** See Deviations #1.
- **`read_status` does its own two selects**, not `load_run_state` — `RunView` needs six `runs` columns `RunState` does not expose.
- **The import-graph test walks the transitive closure** by AST-parsing each `dark_factory` module and BFS-ing its imports; a sanity test proves the walk resolves (`persistence.mutations` genuinely reaches `dark_factory.events`).
- **`--json` routes structlog to stderr** (`configure_logging(PrintLoggerFactory(file=sys.stderr))`) before emitting — defensive; nothing in the status path logs today (T-01-34).

## Deviations from Plan

### 1. [Rule 3 - Blocking] Source redaction applied by the CLI, not inside `as_text()` / the read path

- **Found during:** Task 1.
- **Issue:** The plan action for `domain/views.py` says "Pass the source value through the redaction path before rendering", and the Task 1 behaviour list includes "The rendered source value is passed through the redaction path". But `redact()` lives in `dark_factory.events.redaction`, and the same plan's invariants require `observability/status.py` — **and its whole transitive `dark_factory` import closure** — to import nothing from `dark_factory.events`. `read_status` returns a `RunView`, so `views.py` is in that closure; `views.py` importing `redact` would fail `tests/unit/test_status_import_graph.py`.
- **Fix:** `RunView.as_text()` / `as_json()` take an optional `redactor: Callable[[Any], Any]` parameter. `cli.py` (which is *not* in the read path's closure) constructs `functools.partial(redact, known_secrets=get_settings().known_secret_values())` and passes it. The source is redacted in **both** output modes (threat model T-01-01, mitigation preserved); the read path and the DTO stay free of any `dark_factory.events` import; the import-graph guard is green.
- **Files:** `src/dark_factory/domain/views.py`, `src/dark_factory/cli.py`, `tests/db/test_status_from_columns.py` (the redaction test imports `redact` itself and drives it through `view.as_text(redactor=...)` / `view.as_json(redactor=...)`).
- **Verification:** `test_source_reference_is_redacted_in_both_render_modes` — a `postgresql://u:pw@host/db` `source_ref` renders as `[redacted:database_url]` in text and JSON; the import-graph test passes.
- **Committed in:** `61a56b4`, `7e6e97d`, `435f494`.

### 2. [Rule 3 - Tooling] `ruff format` run alongside `ruff check`

- **Found during:** Task 2 verification.
- **Issue:** `.claude/CLAUDE.md` mandates `ruff check` + `ruff format`; the plan `<verification>` lists only `ruff check .`. `ruff format --check` rewrapped one multi-line assert message in `tests/integration/test_status_cli.py`.
- **Fix:** `uv run ruff format` on the file — whitespace only, no behaviour change. Committed as `409ddb8` `style(01-08)` because the Task 2 GREEN commit was already made. Same call every prior 01-0x executor made.
- **Committed in:** `409ddb8`.

---

**Total deviations:** 1 blocking (redaction seam resolving contradictory plan wording), 1 tooling. No scope creep — every file in `files_modified` was produced with the specified exports and behaviour; `RunView` carries exactly the D-12 field set and nothing more.

## Issues Encountered

- **db / integration tiers run against PostgreSQL 18.6** via `DARK_FACTORY_TEST_DATABASE_URL` (the operator's throwaway instance — no Docker, no local `initdb`, `DATABASE_URL[_DIRECT]` unprovisioned), carried forward from `01-01` / `01-04`. Full suite: **240 passed in 596 s, exit 0**. Secret value never surfaced to stdout, this SUMMARY, a fixture default, or any committed file — sourced via a one-line scratchpad wrapper (`set -a; . ./.env; set +a; exec "$@"`), same technique as `01-04`.
- **A `head -1` pipe on `dark-factory run` during a manual check killed the process (SIGPIPE) right after `CREATED → BA` committed** — an accidental live demonstration: `status` then correctly reported `status: BA, latest_attempt: 1` from the durable intermediate state, exactly like `test_status_reports_ba_for_a_run_left_mid_flight_by_the_crash_hook`.

## User Setup Required

None - no external service configuration required (the `db` / `integration` tiers need a throwaway PostgreSQL 17+ in the git-ignored `.env`, unchanged since `01-01`).

## Verification Results

| Command | Result |
|---|---|
| `pytest -m db -q tests/db/test_status_from_columns.py` | 9 passed (plan floor ≥ 7) |
| `pytest -m unit -q tests/unit/test_status_import_graph.py` | 2 passed |
| `pytest -m integration -q tests/integration/test_status_cli.py` | 8 passed |
| `pytest -q` (full suite, real PostgreSQL 18.6) | **240 passed in 596.30s**, exit 0, no marker warnings |
| `pytest -m "unit or contract" -q` | 158 passed |
| `mypy src/dark_factory` (strict) | Success: no issues found in 36 source files |
| `ruff check .` | All checks passed |
| `ruff format --check src tests` | 77 files already formatted |
| `dark-factory status <id>` / `--json` / unknown-id | 11-line `key: value` list / 11-key JSON object / exit 2 |

## Next Phase Readiness

- **Phase 11 (CI trigger):** `status --json` emits a stable 11-key object from state columns; a CI step can poll it. The `--json` stdout is a clean single-object stream (logs go to stderr).
- **Phase 12 (observability surface):** extend `RunView` and add to `observability/` — the tier now exists with the "no events import" guard; Phase 12 adds the per-role pipeline / event list / artifact list D-12 deliberately omitted.
- **Unchanged blockers:** the three research-flagged decisions (artifact-content durability → Phase 5, lease TTL → Phase 2, Copilot/Hermes flag matrix → Phase 8).

## Self-Check: PASSED

- All 6 files in `key-files.created` verified present on disk.
- Commits `61a56b4`, `7e6e97d`, `b48f4d3`, `435f494`, `409ddb8` verified in `git log` on `gsd/phase-01-walking-skeleton-one-durable-run`.
- Re-ran every plan `<verification>` command post-commit: full `pytest -q` 240 passed (real PostgreSQL 18.6), `mypy src/dark_factory` clean (36 files), `ruff check .` clean, `dark-factory status <id> --json` emits one parseable 11-key object.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the plan-level `check tdd-red-evidence` verb gate is not enforced. Both tasks still followed a RED → GREEN cycle:

| Task | RED (`test(01-08)`) | GREEN (`feat(01-08)`) | RED failure observed |
|------|---------------------|-----------------------|----------------------|
| 1 | `61a56b4` | `7e6e97d` | `ModuleNotFoundError: dark_factory.domain.views` (target module absent) — collection error on `tests/db/test_status_from_columns.py`; the import-graph test's main assertion also failed on "module does not exist on disk". Continuing the 01-02..01-06 "module absent" RED convention. |
| 2 | `b48f4d3` | `435f494` | 7 of 8 integration tests failed (`assert 2 == 0` / "expected exactly one `status` command function") because the `status` command did not exist. The 8th (`test_malformed_run_id_exits_2_with_empty_stdout`) passed at RED because an unknown Typer subcommand also exits 2 with an empty stdout — not a gate violation, the genuine RED is the other seven. |

`tests/unit/test_status_import_graph.py::test_the_walk_actually_resolves_transitive_imports` is a green-at-RED sanity guard (same shape as 01-05's `test_single_mutation_path.py`) — it encodes an invariant that already held.

## Threat surface / stub scan

- **T-01-32 (a tampered / missing `run_events` row changing what `status` reports):** `read_status` selects only `runs` + the latest `role_executions` row, imports nothing from the events module transitively (AST closure guard), and `test_runview_survives_insert_delete_and_corruption_of_run_events` + `test_runview_correct_with_a_completely_empty_event_log` prove equal output across an inserted event, a fully deleted event log and a corrupted event type.
- **T-01-01 (a credential in the source displayed at the terminal / in a CI log):** the source is passed through `redact()` before rendering in both `as_text()` and `as_json()`; `test_source_reference_is_redacted_in_both_render_modes` covers both.
- **T-01-33 (the read model acquiring the ability to write):** no `session.begin()` / `session.add` / `session.commit` / attribute assignment anywhere in `observability/`; `test_read_status_performs_no_write` asserts the run's `updated_at` and all three tables' row counts are unchanged across three `read_status` calls.
- **T-01-34 (log output interleaved on the `--json` stdout stream):** `--json` calls `_route_logs_to_stderr()` before emitting; the integration test parses the entire stdout strictly (`startswith("{")`, `endswith("}")`, single line, `json.loads`).
- **T-01-27 (an unknown-run failure emitting a partial record):** `read_status` raises `UnknownRunError` before constructing any `RunView`; the CLI exits 2 with an empty stdout, asserted by `test_unknown_run_id_exits_2_with_empty_stdout`.
- **Stubs:** none. `base_branch` / `working_branch` render as `-` because the columns are null until Phase 5 (D-20) — they are shown deliberately, not stubbed. No skipped tests, no `TODO`/`FIXME`, no new network endpoints or auth paths.

---
*Phase: 01-walking-skeleton-one-durable-run*
*Completed: 2026-09-08*
