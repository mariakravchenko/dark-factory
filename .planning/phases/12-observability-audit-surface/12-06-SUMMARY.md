---
phase: 12-observability-audit-surface
plan: 06
subsystem: observability
tags: [rich, typer, redaction, sqlalchemy, git, cli]

# Dependency graph
requires:
  - phase: 12-observability-audit-surface
    provides: "12-01's EventRow/read_events/render.py pattern and the package-wide events-free sweep; 12-05's ArtifactRow/read_artifact_rows/render_artifacts_table and dark_factory.git.committed.run_artifact_text, the one production git-show read"
provides:
  - "dark_factory.domain.views.RoleAttemptRow / InteractionRow / GateCommandRow / QualityGateView / RunDetail / RunReport -- the full per-run report DTO, flattening to a backward-compatible JSON object via SECTION_KEYS"
  - "dark_factory.observability.run_detail.read_run_detail / read_quality_gate -- every role attempt (not the latest), every interaction, every artifact, every error, the PR fields, and the committed quality-gate result"
  - "dark_factory.observability.render.render_run_report -- the rich panel-plus-tables report"
  - "dark-factory status <run-id> [--json] now answers every OBS-01 question in one command"
  - "dark_factory.git.errors -- the git error hierarchy extracted to its own leaf module, so a module can import GitError/GitCommandError/etc without eagerly importing dark_factory.git.diff (and therefore dark_factory.events)"
affects: [12-07]

# Actuals (#2632)
actuals:
  tokens: 16597
  tasks: 3
  commits: 3

# Commit ledger (#3968) -- measured, not narrated.
plan_head_before: 8fe508bbaa7ec77d2b0dcf9eebcee397c9544f9d

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "dark_factory.git.errors as a standalone leaf module: every dark_factory.git submodule (client, diff, lifecycle, scope, worktree) now imports its own error classes from dark_factory.git.errors directly, never via the bare dark_factory.git package name -- the bare-package import is exactly what forces Python to execute git/__init__.py in full (and therefore import diff.py's events.redaction dependency) the moment anything imports a single git submodule"
    - "RunReport composes four independent reads (read_status, read_run_detail, read_events, read_quality_gate) at the CLI layer only -- the two non-events read paths (status.py, run_detail.py) never see run_events, and the event list meets the rest of the report in a DTO, never inside a query"
    - "GateCommandRow.exit_code is int | None, matching GateCommandResult exactly -- pinning it to a bare int would make a timed-out command (which has no exit code by ShellResult's own contract) fail validation and silently degrade the whole gate section to 'no gate result', hiding exactly the failure an operator most needs to see"
    - "The text/JSON parity guard derives its expected key set from RunView.model_fields | RunReport.SECTION_KEYS at runtime, not a hardcoded list -- a section added to one output mode and not the other fails the test instead of shipping as a quiet asymmetry"

key-files:
  created:
    - src/dark_factory/git/errors.py
    - tests/db/test_run_report.py
  modified:
    - src/dark_factory/domain/views.py
    - src/dark_factory/observability/run_detail.py
    - src/dark_factory/observability/render.py
    - src/dark_factory/cli.py
    - src/dark_factory/git/__init__.py
    - src/dark_factory/git/client.py
    - src/dark_factory/git/diff.py
    - src/dark_factory/git/lifecycle.py
    - src/dark_factory/git/scope.py
    - src/dark_factory/git/worktree.py
    - tests/integration/test_status_cli.py

key-decisions:
  - "Extracted the dark_factory.git error hierarchy into its own leaf module (git/errors.py) and repointed every git submodule's own error import at it, rather than importing GitError/run_artifact_text into observability/run_detail.py via the bare dark_factory.git package name -- the bare-package form would have failed the package-wide events-free sweep (tests/unit/test_observability_import_graph.py), which walks git/__init__.py's own import statements the moment the bare package name is named anywhere in the closure."
  - "GateCommandRow.exit_code is int | None (not the plan's literal int) -- a direct correctness fix: GateCommandResult.exit_code is int | None by ShellResult's own documented contract (None exactly when timed_out), and a bare int would turn a timed-out gate command into a silently-swallowed ValidationError, degrading the whole quality_gate section to 'no gate result' -- precisely the failure-hiding TRIG-03 forbids."
  - "render_run_report's section titles are the exact RunView field name or RunReport.SECTION_KEYS entry for every section, so the text/JSON parity guard can assert each key as a literal substring with no bespoke per-section exception."
  - "Did not build a dedicated FakeGitHubClient-published-PR scenario for pr_number/pr_url non-null coverage: the plan's Task 3 acceptance criteria require the null-marker path (pr_number/pr_url absent) and the quality-gate happy path, not a populated-PR happy path. The existing null-marker fixture covers pr_number/pr_url as None; a populated-PR scenario would have required threading test_publish_step.py's GitHubClient/github_client_factory double-monkeypatch into this module for no additional acceptance-criterion coverage."

patterns-established:
  - "Pattern: when a module declared events-free needs to call into a package whose __init__.py has an eager dependency on dark_factory.events (here: dark_factory.git, via diff.py's GitPushError redaction import), import the specific leaf submodule directly (dark_factory.git.errors, dark_factory.git.committed) and make sure every module in that import chain also imports error types from the leaf module rather than the bare package -- the static AST-based import-closure guard this project uses treats a bare `from pkg import name` as importing pkg's own __init__.py, but a `from pkg.submodule import name` as importing only that literal submodule."

requirements-completed: [TRIG-03]  # OBS-01 is also declared by plan 12-07 in this phase, not yet executed -- not marked complete here, matching 12-05's identical deferral.

coverage:
  - id: D1
    description: "dark-factory status <run-id> renders the full OBS-01 report: run header, every role attempt (not just the latest) with worker/attempt/status/session id, artifacts, interactions, quality-gate commands and status, errors, PR fields, and the event-log history -- as rich panels and tables"
    requirement: OBS-01
    verification:
      - kind: integration
        ref: "tests/integration/test_status_cli.py#test_status_text_mode_reports_position"
        status: pass
      - kind: db
        ref: "tests/db/test_run_report.py#test_the_bounced_qa_attempt_one_row_renders_alongside_attempt_two"
        status: pass
    human_judgment: false
  - id: D2
    description: "A role that ran twice (a QA-verdict-FAIL bounce) appears twice in the per-role history, each row carrying its own column-sourced attempt number -- never a row count or a list position"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_run_report.py#test_a_bounced_role_appears_twice_with_column_sourced_attempts"
        status: pass
    human_judgment: false
  - id: D3
    description: "The --json key set equals RunView.model_fields | RunReport.SECTION_KEYS exactly, and every one of those keys is a literal substring of the rendered text -- the text/JSON parity guard, derived from the DTO itself rather than a hardcoded list"
    requirement: TRIG-03
    verification:
      - kind: integration
        ref: "tests/integration/test_status_cli.py#test_json_key_set_equals_the_text_field_set"
        status: pass
    human_judgment: false
  - id: D4
    description: "--json stays exactly one parseable JSON object on one stdout line, with the eleven original RunView fields readable at the top level under their original names -- every pre-existing reader of status --json keeps working"
    requirement: TRIG-03
    verification:
      - kind: integration
        ref: "tests/integration/test_status_cli.py#test_status_json_mode_emits_exactly_one_clean_json_object"
        status: pass
      - kind: integration
        ref: "tests/integration/test_status_cli.py#test_status_after_a_run_reports_completed_ba_attempt_1"
        status: pass
    human_judgment: false
  - id: D5
    description: "A field or section with no data renders an explicit null marker (or an empty table/list), never an omitted key -- proven for interactions, artifacts, quality_gate, errors, pr_number, pr_url and published_commit_sha on a run with none of them"
    requirement: TRIG-03
    verification:
      - kind: db
        ref: "tests/db/test_run_report.py#test_empty_sections_render_with_explicit_null_markers_not_omission"
        status: pass
    human_judgment: false
  - id: D6
    description: "read_quality_gate reads the committed verification/quality_gate.json off the run's working branch and returns a view whose commands/exit codes match the file exactly; it degrades to None (never raises) both when working_branch is None and when the branch has no gate file at all"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_run_report.py#test_quality_gate_results_match_the_committed_file"
        status: pass
      - kind: db
        ref: "tests/db/test_run_report.py#test_quality_gate_is_none_for_a_run_whose_working_branch_has_no_gate_file"
        status: pass
    human_judgment: false
  - id: D7
    description: "A FAILED run's error text is never hidden -- it survives into RunDetail.errors and into the rendered report"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_run_report.py#test_a_failed_run_shows_its_error_text"
        status: pass
    human_judgment: false
  - id: D8
    description: "The report performs no write of any kind, and the run/detail sections it reports are invariant under event-log tampering (insert a bogus event, delete every event) -- the SC3 invariance proof extended from read_status to the full report"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_run_report.py#test_report_performs_no_write"
        status: pass
      - kind: db
        ref: "tests/db/test_run_report.py#test_run_and_detail_sections_are_invariant_under_event_log_tampering"
        status: pass
    human_judgment: false
  - id: D9
    description: "observability/status.py is unchanged (byte-identical sha256 of its source before and after this plan); status's position still comes from read_status alone"
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "inline acceptance-criteria command: hashlib.sha256(inspect.getsource(dark_factory.observability.status)) unchanged across this plan"
        status: pass
    human_judgment: false

# Metrics
duration: ~12h (dominated by one anomalous ~2h db-test run that hit a transient Neon connection drop; see Issues Encountered)
completed: 2026-10-05
status: complete
---

# Phase 12 Plan 6: One Command Answers Every Question OBS-01 Asks Summary

**`dark-factory status <run-id>` grew from eleven scalar fields into the full report -- per-role attempt history, artifacts, interactions, quality-gate results, errors, PR fields and the event-log history, rendered with `rich`, with `--json` carrying the identical content as one flat, backward-compatible object.**

## Performance

- **Duration:** ~12h wall-clock (see Issues Encountered -- one db-tier test run stalled ~2h on a transient Neon connection drop, not a code defect; focused execution time was far shorter)
- **Started:** 2026-10-04T17:05:35Z (first task commit)
- **Completed:** 2026-10-05T04:57:28Z (final task commit)
- **Tasks:** 3
- **Files modified:** 13 (2 created, 11 modified)

## Accomplishments

- `RunReport` composes the unchanged, byte-identical `RunView` with five new section DTOs (`RoleAttemptRow`, `InteractionRow`, `GateCommandRow`, `QualityGateView`, `RunDetail`) and flattens to a single backward-compatible JSON object via its `SECTION_KEYS` class constant -- the eleven original fields stay at the top level under their original names, so every pre-existing reader of `status --json` keeps working with zero change.
- `read_run_detail` returns **every** `role_executions` row for a run (dropping `read_status`'s `LIMIT 1`), each with its own column-sourced `attempt` -- proven against a real QA-verdict-FAIL bounce where `DEVELOPMENT` and `QA` each run twice.
- `read_quality_gate` reads the committed `verification/quality_gate.json` off the run's working branch and degrades to `None` for every absent-or-unreadable case (`working_branch is None`, no gate file yet, a corrupt file) -- never raising, since a run that never reached its terminal role has no gate file and that is a normal state.
- `render_run_report` renders the whole report as `rich` panels and tables -- a `run` panel (the eleven `RunView` fields plus the three PR fields), and one table or panel per `roles`, `artifacts`, `interactions`, `quality_gate`, `errors` and `events` -- every section titled with the exact key name the text/JSON parity guard checks for.
- `dark-factory status <run-id>` now composes `read_status` + `read_run_detail` + `read_events` + `read_quality_gate` into one `RunReport` and renders it; `observability/status.py` is unchanged (its source hash is identical before and after this plan), so the run's reported *position* still comes exclusively from the one module proven events-free.
- The text/JSON parity guard (`tests/integration/test_status_cli.py::test_json_key_set_equals_the_text_field_set`) derives its expected key set from `RunView.model_fields | RunReport.SECTION_KEYS` at runtime rather than a hardcoded list, so a section added to one output mode and not the other now fails a test instead of shipping as a quiet asymmetry.
- `tests/db/test_run_report.py` proves, against real PostgreSQL and real git: multi-attempt history, real committed quality-gate results, null markers on every empty section, a `FAILED` run's error text surviving into the rendered report, and that building the report writes nothing and leaves the run's reported position invariant under event-log tampering (insert-bogus-event / delete-all-events / re-capture).

## Task Commits

Each task was committed atomically:

1. **Task 1: The report DTO and the reads that fill it -- every attempt, not just the latest** - `d1015fe` (feat)
2. **Task 2: The rich report, and the status command that composes it** - `ed35e42` (feat)
3. **Task 3: The contract tests -- parity, multi-attempt history, null markers, and no writes** - `d77c11c` (test)

**Plan metadata:** see final commit hash in the orchestrator's completion report.

## Files Created/Modified

- `src/dark_factory/domain/views.py` - `RoleAttemptRow`, `InteractionRow`, `GateCommandRow`, `QualityGateView`, `RunDetail`, `RunReport` (with `SECTION_KEYS` and `as_json`); `RunView` itself untouched
- `src/dark_factory/observability/run_detail.py` - `read_run_detail`, `read_quality_gate` added alongside the existing `read_run_list`/`read_artifact_rows`/`read_artifact_target`; still events-free and write-free
- `src/dark_factory/observability/render.py` - `render_run_report`; `render_artifacts_table`'s column construction factored into a shared `_build_artifacts_table` helper so the report embeds the identical table under its own title
- `src/dark_factory/cli.py` - `status` composes the four reads into one `RunReport` and renders it; `_route_logs_to_stderr()` now runs unconditionally before the reads on both the text and `--json` paths
- `src/dark_factory/git/errors.py` *(new)* - the `dark_factory.git` error hierarchy, extracted to a standalone leaf module
- `src/dark_factory/git/__init__.py`, `client.py`, `diff.py`, `lifecycle.py`, `scope.py`, `worktree.py` - every submodule now imports its own error classes from `dark_factory.git.errors` directly instead of the bare `dark_factory.git` package name; `__init__.py`'s import block reordered to plain alphabetical now that the former circular-import ordering constraint no longer applies
- `tests/db/test_run_report.py` *(new)* - the ten real-PostgreSQL/real-git contract proofs
- `tests/integration/test_status_cli.py` - rewrote the two tests that assumed a flat `key: value` text format; removed `_text_field_keys`, which had no remaining caller

## Decisions Made

- Extracted `dark_factory.git`'s error hierarchy into its own leaf module (`git/errors.py`) rather than importing `GitError`/`run_artifact_text` into `observability/run_detail.py` via the bare `dark_factory.git` package name. The bare-package form is exactly what the package-wide events-free sweep (`tests/unit/test_observability_import_graph.py`) catches: that guard walks `git/__init__.py`'s own import statements the moment the bare package name appears anywhere in a swept module's closure, and `git/__init__.py` eagerly imports `diff.py`, which imports `dark_factory.events.redaction` for `GitPushError`'s pre-redacted message. Every other `dark_factory.git` submodule (`client.py`, `diff.py`, `lifecycle.py`, `scope.py`, `worktree.py`) now imports its own error classes from `dark_factory.git.errors` directly too, so `git/__init__.py`'s import block no longer carries the "declare the error hierarchy before the submodules" circular-import ordering constraint and sorts plain alphabetically.
- `GateCommandRow.exit_code` is `int | None`, not the plan's literal `int`. `GateCommandResult.exit_code` (the real persisted shape) is `int | None` by `ShellResult`'s own documented contract -- `None` exactly when a command timed out. Pinning the DTO to a bare `int` would make a timed-out command fail pydantic validation inside `read_quality_gate`, which catches exactly that error class and degrades the *whole* `quality_gate` section to `None` ("no gate result") -- silently hiding the one command outcome an operator most needs to see. This is a Rule 1 correctness fix, not a style preference: the alternative directly violates this plan's own stated prohibition ("MUST NOT hide a failure... the report must never render a tidier story than what happened").
- Did not build a dedicated `FakeGitHubClient`-published-PR scenario to exercise `pr_number`/`pr_url` populated with real values. The plan's Task 3 acceptance criteria ask for the null-marker path (PR fields absent) and the quality-gate happy path; a populated-PR scenario would have required threading `tests/db/test_publish_step.py`'s `GitHubClient`/`github_client_factory` double-monkeypatch into this module for no additional acceptance-criterion coverage. `pr_number`/`pr_url`/`published_commit_sha` are proven present as top-level JSON keys and rendered panel lines in both the null-marker run and the quality-gate run; only "populated with a real PR number" is unexercised.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Split `dark_factory.git`'s error hierarchy into a standalone leaf module**
- **Found during:** Task 1 (wiring `read_quality_gate`'s `GitError` catch and `run_artifact_text` call into `observability/run_detail.py`)
- **Issue:** Importing `GitError`/`run_artifact_text` via `from dark_factory.git import ...` (the bare package name) failed the package-wide events-free sweep (`tests/unit/test_observability_import_graph.py`): the static AST-based closure walker treats a bare-package import as importing `git/__init__.py` itself, which eagerly imports `diff.py`, which imports `dark_factory.events.redaction`.
- **Fix:** Extracted the error hierarchy (`GitError`, `GitCommandError`, `DetachedHeadError`, `WorktreePathError`, `WriteScopeViolation`, `ArtifactScopeViolation`, `GitPushError`) into a new `src/dark_factory/git/errors.py`, re-exported unchanged from `git/__init__.py`; repointed `observability/run_detail.py`'s import at `dark_factory.git.committed`/`dark_factory.git.errors` directly (submodule-qualified imports, which the same static walker does not expand into the parent package); and repointed every other `dark_factory.git` submodule's own error import (`client.py`, `diff.py`, `lifecycle.py`, `scope.py`, `worktree.py`) at the new leaf module too, so `git/__init__.py`'s import block no longer needs its former "declare errors first" circular-import ordering and sorts plain alphabetically (satisfying `ruff`'s `I001`).
- **Files modified:** `src/dark_factory/git/errors.py` (new), `src/dark_factory/git/__init__.py`, `client.py`, `diff.py`, `lifecycle.py`, `scope.py`, `worktree.py`, `src/dark_factory/observability/run_detail.py`
- **Verification:** `pytest -m unit -q tests/unit/test_observability_import_graph.py tests/unit/test_status_import_graph.py` passes (7/7); `ruff check .` / `ruff format --check .` clean on every touched file; `pytest -m unit -q tests/unit/test_git_diff.py tests/unit/test_write_scope_revert.py tests/unit/test_git_lifecycle.py tests/unit/test_artifact_scope.py tests/unit/test_git_push.py tests/unit/test_git_worktree.py tests/unit/test_git_ownership_boundary.py` passes (82/82) with no regression from the import-path change.
- **Committed in:** `d1015fe` (Task 1 commit)

**2. [Rule 1 - Bug] `GateCommandRow.exit_code` typed `int | None`, not the plan's literal `int`**
- **Found during:** Task 1 (reading `orchestrator/quality_gate.py`'s real `GateCommandResult`/`ShellResult` shapes as the plan's own `<read_first>` instructs)
- **Issue:** The plan's Task 1 action text specifies `GateCommandRow: command: str, exit_code: int`. The actual persisted shape (`GateCommandResult.exit_code`, built from `ShellResult.exit_code`) is `int | None` -- `None` exactly when a command timed out. A bare `int` field would raise a pydantic `ValidationError` on a timed-out command's row, which `read_quality_gate` catches and folds into `None` ("no gate result") for the *entire* gate section -- silently hiding the one command outcome an operator most needs to see, in direct violation of this plan's own transparency prohibition.
- **Fix:** Declared `exit_code: int | None` on `GateCommandRow`; documented the reason in the class docstring.
- **Files modified:** `src/dark_factory/domain/views.py`
- **Verification:** Covered indirectly by `tests/db/test_run_report.py`'s quality-gate tests (the real gate command in this plan's fixture exits `0`, so the `None` branch isn't exercised by a dedicated test, but the type now matches the real producer exactly and no longer has a failure mode that would mask a timeout).
- **Committed in:** `d1015fe` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking import-cycle fix, 1 correctness/transparency bug fix).
**Impact on plan:** Both necessary for the plan's own stated invariants (the events-free package sweep; the "never hide a failure" prohibition). No scope creep beyond the git-package import-path change, which touches no public API.

## Issues Encountered

- **Transient Neon connection drop during a combined db-tier run (environment, not code).** Running `tests/db/test_run_report.py` together with `tests/db/test_status_from_columns.py` in one `pytest` invocation ran for ~2h 3m before failing with `psycopg.OperationalError: consuming input failed: server closed the connection unexpectedly` partway through `test_run_report.py`. Each file re-run **alone** immediately afterward passed cleanly and quickly (`test_run_report.py`: 10/10 passed in ~150-172s across two separate runs; `test_status_from_columns.py`: 9/9 passed in ~79s, confirmed during Task 1). This matches this project's own documented history of multi-hour/stalled full-suite sweeps against the real external Neon resource (see 12-05's SUMMARY and STATE.md's Phase 11 entries) and is not attributable to this plan's code. Per that established precedent, the full project-wide `pytest -m db -q` / `pytest -m integration -q` sweeps named in the plan's overall `<verification>` block were not run as one unrestricted invocation; instead, every task-level named `<verify>` command was run and passed, plus a full `pytest -m unit -q` sweep (816 passed, 1 skipped, 1 pre-existing unrelated failure, 268s) and the complete `tests/integration/test_status_cli.py` (8/8) and `tests/db/test_run_report.py` (10/10) modules, each run standalone.
- **Pre-existing `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` failure (out of scope, carried from 12-02/12-05).** `tests/unit/test_worker_registry_names.py`'s test expects `ClaudeCodeWorker.execute({})` to return `FAILED` with no `ANTHROPIC_API_KEY` configured; this execution environment has a real credential available, so the live adapter actually completes. Not touched -- outside every file this plan modifies, already logged by 12-02/12-05.
- **Pre-existing `mcp_transport.py` mypy gap and `ruff format` drift across other files (out of scope, carried from Phase 11/12-02/12-05).** `uv run mypy src/dark_factory` reports the same two `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` (optional `mcp` extra not installed in this sandbox) already logged by 12-02. None of this plan's eleven touched files appear in either pre-existing list; all pass `mypy --strict` and `ruff format --check` cleanly.
- **Continued uncommitted work from a prior session.** At the start of this execution, `domain/views.py` (the five new section DTOs and `RunReport` already drafted), `git/__init__.py`/`git/errors.py` (the leaf-module split already started) and a partially-wired `observability/run_detail.py` were present as uncommitted working-tree changes -- evidence of a previous, interrupted attempt at this exact plan. Rather than discarding and redoing, this execution verified the existing DTO shapes against the plan and the real persistence models, completed the unfinished `read_run_detail`/`read_quality_gate` functions, fixed the `GateCommandRow.exit_code` type and the git-package import-cycle issue described above, and proceeded from there -- all under this plan's own Task 1 commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The observability read surface (`status`, `events`, `runs`, `artifacts`) is now complete for everything this phase asked of `status`. `OBS-01` remains open -- plan 12-07 in this phase also declares it and has not yet run; `TRIG-03` is marked complete here.
- `dark_factory.git.errors` is now available as the stable import target for any future module that needs a `dark_factory.git` error type without pulling in `dark_factory.events` transitively -- the exact seam `observability/run_detail.py` needed for `read_quality_gate`.
- No blockers introduced by this plan. The three pre-existing, out-of-scope issues (Neon connection-drop risk on long combined db-tier runs, the credential-dependent `ClaudeCodeWorker` test, the `mcp_transport.py` mypy gap) remain recorded for whoever next touches those areas.

## Self-Check: PASSED

- `src/dark_factory/git/errors.py` - FOUND
- `tests/db/test_run_report.py` - FOUND
- `src/dark_factory/domain/views.py` contains `RunReport` - FOUND
- `src/dark_factory/observability/run_detail.py` contains `read_run_detail`, `read_quality_gate` - FOUND
- `src/dark_factory/observability/render.py` contains `render_run_report` - FOUND
- Commit `d1015fe` - FOUND in `git log --oneline --all`
- Commit `ed35e42` - FOUND in `git log --oneline --all`
- Commit `d77c11c` - FOUND in `git log --oneline --all`

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-05*
