---
phase: 12-observability-audit-surface
plan: 07
subsystem: security
tags: [redaction, security, github, cli, pytest, sqlalchemy, git]

# Dependency graph
requires:
  - phase: 12-observability-audit-surface
    provides: "12-03's clarification-comment redaction call site, 12-04's completed 22-member EventType catalog, and 12-06's RunReport/render_run_report/read_run_detail/read_quality_gate observability surface"
provides:
  - "tests/db/test_secret_redaction_e2e_full_pipeline.py -- the SC4 whole-pipeline secret sweep: one github:-sourced run seeded with six credential literals across four shapes, driven through intake, a human pause/resume, a real ClaudeCodeWorker role, a quality gate and a published pull request, swept for every literal across all seven D-08 sinks, a whole-table sweep of all five owned tables, and this phase's own four new CLI surfaces (status/runs/events/artifacts --show)"
  - "dark_factory.artifacts.store.scrub_artifact_text_in_place -- a new redaction call site closing a real gap the sweep found: a role's own artifact file content was the one D-08 sink never scrubbed before git.diff.commit_run_artifacts committed it onto the run's working (eventually PR) branch"
  - "orchestrator/runner.py's _run_current_role scrubs every reported artifact file in place immediately after a role reports COMPLETED, before collect_role_artifacts reads the same file for schema validation and checksum computation, so the persisted checksum and the committed content always agree"
  - "tests/unit/test_global_settings_reads_are_declared.py's inventory widened 19 -> 20 entries, with the four pre-existing _run_current_role occurrences renumbered #1-#4 -> #2-#5 to make room for the new artifact-scrub read at #1 (source order)"
affects: []

# Actuals (#2632) -- pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 10913
  tasks: 2
  commits: 2

# Commit ledger (#3968) -- measured, not narrated.
plan_head_before: c4019ea4df3759ecb3e113869bd411fd5c8c9081

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Artifact-content scrub mirrors the log-scrub precedent exactly: dark_factory.artifacts.store.scrub_artifact_text_in_place reads a reported artifact file's text, redacts it with the current known_secrets, and rewrites it only when something changed -- called from orchestrator/runner.py immediately after a role reports COMPLETED and before collect_role_artifacts reads the same file, so the checksum persisted in artifacts.checksum and the content eventually force-added and committed onto the working branch can never disagree."
    - "Hybrid in-process registry for a real-subprocess + fake-worker pipeline: one WorkerRegistry with 'fake' bound to a small local CodingWorker (BA pauses with a seeded question then resumes; ARCHITECTURE/QA complete with seeded-carrying artifact content/summaries) and 'claude-code' bound to the real ClaudeCodeWorker class, pointed at a fake claude binary via PATH -- the only construction this phase's own research found that drives both FakeGitHubClient injection and a real worker subprocess in one run."
    - "A credential-shaped literal planted bare in a diagnostic log line is a self-inflicted false positive unless it is itself pattern-shaped or an exact configured value: a raw password substring extracted from a configured DATABASE_URL is not, by itself, redacted when logged standalone (only the whole URL is a known/pattern value) -- the seeded-constant tuple used for the SWEEP assertions is not interchangeable with the tuple used to construct a log line that expects redaction to fire on every token."
    - "The forbidden search string ('redact' + '(') is built from two concatenated literals, never written contiguously in the module's own source, so the module's own self-check assertion does not trip the exact substring probe the plan's acceptance criteria run externally against the file."

key-files:
  created:
    - tests/db/test_secret_redaction_e2e_full_pipeline.py
  modified:
    - src/dark_factory/artifacts/store.py
    - src/dark_factory/orchestrator/runner.py
    - tests/unit/test_global_settings_reads_are_declared.py

key-decisions:
  - "Drove the whole pipeline in-process (start_run/drive with an injected github_client_factory), not through the dark-factory run CLI subprocess -- the CLI always binds default_github_client_factory and would attempt a real GitHub call; only an in-process drive can inject FakeGitHubClient and still exercise a real ClaudeCodeWorker subprocess in the same run, resolving 12-RESEARCH.md's Open Question 3."
  - "Patched get_settings on five modules (persistence.mutations, orchestrator.runner, dark_factory.logging, workers.claude_code, workers.cli_runtime) to one shared seeded Settings instance, and deliberately left persistence.engine's own get_settings untouched -- every sink this test seeds is redacted through one of the five patched modules, while every observability read this test performs (read_status/read_run_detail/read_events/read_run_list/read_quality_gate's default session_factory=new_session) still reaches the real database the test's own fixtures are bound to."
  - "Monkeypatched the test process's cwd to the config tree root before driving: ClaudeCodeWorker's own resolve_dirs() computes the worktree as a sibling of the process's cwd (correct in production, where the CLI is invoked from the repo root) -- an in-process db-tier test needs that same equivalence made explicit, mirroring tests/unit/test_claude_code_worker.py's own repo_dir fixture."
  - "Six seeded credential constants across two configured-vs-pattern-only axes: four configured into Settings (database_url, database_url_direct, github_token, anthropic_api_key) and two free-standing (a ghp_-shaped token, a password= key-value pair) configured nowhere. anthropic_api_key is the load-bearing exact-value-only proof -- its sk-ant- shape matches none of the compiled D-15 patterns, so only known-value substitution can ever catch it."
  - "Placed every credential-text-shaped literal only where its sink's redaction mode can actually catch it: pattern-only literals never went into the github issue body (runs.normalized_task persists task text through scrub_known_values, patterns=False only, by the pre-existing D-18 known-values-only decision -- a pattern-only literal planted there would survive by design and falsely trip this test's own whole-table sweep). Configured literals went into the task text instead, proving the exact-value scrub still fires on that column too."

requirements-completed: [OBS-01, OBS-02, OBS-03]

coverage:
  - id: D1
    description: "One github:-sourced run, seeded with six credential literals across four shapes, reaches COMPLETED with a created pull request and leaves zero seeded secrets across all seven D-08 sinks (artifact files, run_events.payload, role_executions.result/error, human_interactions.question/answer, the captured structlog output, the recorded GitHub comment and pull-request calls, and the committed quality_gate.json)"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_full_pipeline_leaves_zero_leaked_secrets_with_presence_and_marker_proof"
        status: pass
    human_judgment: false
  - id: D2
    description: "The sweep is non-vacuous: every seeded literal is proven present in the literal input before any absence assertion runs, the [redacted: marker is proven present in at least four distinct sinks, and the run's terminal COMPLETED state plus non-null pr_number/pr_url prove the publish sink was provably populated"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_full_pipeline_leaves_zero_leaked_secrets_with_presence_and_marker_proof"
        status: pass
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::seeded_pipeline_run (fixture, presence assertions)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A whole-table sweep over runs, role_executions, run_events, human_interactions and artifacts finds no seeded literal, and this phase's own four new CLI surfaces (status text/--json, runs, events text/--json, artifacts --show) are swept through their real production read-and-render paths for the same literals"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_full_pipeline_leaves_zero_leaked_secrets_with_presence_and_marker_proof (whole-table sweep)"
        status: pass
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_phase_12_cli_surfaces_are_swept_for_the_same_secrets"
        status: pass
    human_judgment: false
  - id: D4
    description: "A real gap the sweep found and this plan closes: a role's own artifact file content was never scrubbed before being committed onto the run's working (eventually PR) branch. Fixed with scrub_artifact_text_in_place, called before collect_role_artifacts reads the same file for schema validation and checksum computation"
    requirement: OBS-01
    verification:
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_full_pipeline_leaves_zero_leaked_secrets_with_presence_and_marker_proof (ARCHITECTURE's design.md sink)"
        status: pass
      - kind: db
        ref: "tests/db/test_four_role_pipeline.py, tests/db/test_artifact_commit_per_role.py, tests/db/test_artifact_handoff.py, tests/db/test_qa_bounce.py, tests/db/test_artifact_persistence.py (regression: 12 passed, zero change in behavior for content with no secret-shaped text)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The module never calls the redaction function directly to compute an expected value -- every assertion runs through production code, and the module's declared seeded-credential constants are provably split between the configured (exact-value) and pattern-only redaction modes"
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_this_module_never_calls_redact_directly"
        status: pass
      - kind: unit
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_at_least_five_seeded_constants_split_between_configured_and_pattern_only"
        status: pass
    human_judgment: false
  - id: D6
    description: "All 22 EventType members are provably emitted by shipped code outside catalog.py, closing OBS-02's event-catalog claim"
    requirement: OBS-02
    verification:
      - kind: other
        ref: "uv run python -c \"...[m.name for m in E if ('EventType.'+m.name) not in src]\" prints 22 []"
        status: pass
      - kind: db
        ref: "tests/db/test_qa_verdict_events.py (plan 12-04, the catalog's final two members)"
        status: pass
    human_judgment: false
  - id: D7
    description: "dark-factory events/runs expose the audit trail and run list (OBS-03), proven against the production CLI and swept for the same seeded secrets in this plan's own sweep"
    requirement: OBS-03
    verification:
      - kind: integration
        ref: "tests/integration/test_events_cli.py, tests/integration/test_runs_cli.py (plans 12-01/12-02)"
        status: pass
      - kind: db
        ref: "tests/db/test_secret_redaction_e2e_full_pipeline.py::test_phase_12_cli_surfaces_are_swept_for_the_same_secrets"
        status: pass
    human_judgment: false

# Metrics
duration: ~2h40min task-commits + authoring + verification; tier runs measured separately (see Performance)
completed: 2026-10-05
status: complete
---

# Phase 12 Plan 7: The Whole-Pipeline Secret Sweep, and the Gap It Found Summary

**One `github:`-sourced run seeded with six credential literals across four shapes -- driven through intake, a human pause/resume, a real `ClaudeCodeWorker` role, a quality gate and a published pull request -- swept clean across all seven D-08 sinks, a whole-table sweep, and the phase's own four new CLI surfaces; the sweep found a real, previously-unscrubbed sink (artifact file content) and this plan closes it with a new `scrub_artifact_text_in_place` call site.**

## Performance

- **Duration:** ~2h40min of task-commit/authoring work; separately measured full-tier verification runs below (sequential executor, real external Neon PostgreSQL 17)
- **Started:** 2026-10-05T08:05:00Z (approx, Task 1 authoring)
- **Completed:** 2026-10-05T12:10:00Z (approx, after full-tier verification)
- **Tasks:** 2/2
- **Files modified:** 4 (1 created, 3 modified)

### Measured tier durations (Task 2)

| Tier | Command | Result | Duration |
|------|---------|--------|----------|
| Unit and contract | `pytest -m "unit or contract" -q --tb=short` | 845 passed, 1 skipped, **1 pre-existing failure** (unrelated) | 8m58s (538s) |
| Database | `pytest -m db -q --tb=short` | 238 passed, 1 skipped, 0 failed | 1h24m29s (5069s) |
| Integration | `pytest -m integration -q --tb=short` | 191 passed, 2 skipped, 0 failed | 34m24s (2064s) |
| Type/lint | `mypy src/dark_factory && ruff check . && ruff format --check .` | mypy: 2 pre-existing errors (unrelated); ruff check: clean; ruff format: 19 pre-existing unformatted files (unrelated, none touched by this plan) | ~15s |
| Migrations | `alembic check` | "No new upgrade operations detected." | ~2s |

## Accomplishments

- `tests/db/test_secret_redaction_e2e_full_pipeline.py` (new, 4 tests) drives one `github:`-sourced run through `BA` (pauses with a seeded `NEEDS_INPUT` question, resumes with a seeded-carrying summary) -> `ARCHITECTURE` (artifact content carries a seeded literal) -> `DEVELOPMENT` (a real `ClaudeCodeWorker` spawning a real, fake `claude` binary, both its own `result` text and its `run_root_writes`-synthesized artifact carrying seeded literals) -> `QA` (PASS verdict) -> the quality gate (one always-passing command whose argv carries a seeded literal) -> the publish step (a real `FakeGitHubClient.create_pull_request` call), and sweeps every one of the seven D-08 sinks plus a whole-five-table sweep plus the phase's own four new CLI surfaces for all six seeded literals.
- The sweep found a real gap: unlike every other D-08 sink, a role's own **artifact file content** was never passed through redaction before `git.diff.commit_run_artifacts` force-added and committed it onto the run's working branch (which becomes the PR branch). Closed with `dark_factory.artifacts.store.scrub_artifact_text_in_place`, called from `orchestrator/runner.py`'s `_run_current_role` immediately after a role reports `COMPLETED` and before `collect_role_artifacts` reads the same file for schema validation and checksum computation -- so the persisted checksum and the eventually-committed content can never disagree.
- The fix's own new `get_settings()` call site shifted the G-11-3 recurrence guard's (`tests/unit/test_global_settings_reads_are_declared.py`) declared inventory for `orchestrator/runner.py::_run_current_role` from 4 occurrences (`#1`-`#4`) to 5 (`#1`-`#5`), with the new read landing first in source order and renumbering the four pre-existing reads. Updated the declared inventory and its pinning test (19 -> 20 entries) to match.
- Confirmed, by regression, that the new artifact-scrub call site changes nothing for content with no secret-shaped text: `tests/db/test_four_role_pipeline.py`, `test_artifact_commit_per_role.py`, `test_artifact_handoff.py`, `test_qa_bounce.py` and `test_artifact_persistence.py` (12 tests) pass unchanged.
- Confirmed all 22 `EventType` members are provably emitted by shipped code outside `catalog.py`, all six TRIG-02 CLI commands (`run`, `resume`, `status`, `runs`, `artifacts`, `events`) are registered, the `observability/` package still holds exactly `render.py`/`run_detail.py`/`status.py` (plus `__init__.py`), and no `tests/integration/test_phase12_acceptance.py` gate was added.
- Ran all four CI tiers plus `alembic check` against real PostgreSQL 17 (external Neon), recording per-tier durations (table above).

## Task Commits

Each task was committed atomically:

1. **Task 1: One seeded run, driven to a pull request, with every sink swept** - `79e0e35` (fix) -- the e2e test plus the artifact-content-scrub production fix it found necessary, committed together since the test would not pass without the fix.
2. **Task 2: The whole suite green, and the phase's own claims re-checked against it** - `6165224` (test) -- the G-11-3 inventory renumbering Task 1's own fix required, discovered while running this task's own unit-tier verification.

**Plan metadata:** (this commit, below)

## Files Created/Modified

- `tests/db/test_secret_redaction_e2e_full_pipeline.py` *(new)* - the SC4 whole-pipeline secret sweep: six seeded credential constants, a hybrid `WorkerRegistry` (`fake` + real `claude-code`), a custom `[BA, ARCHITECTURE, DEVELOPMENT, QA]` config tree with `publishing.create_pr: true`, a module-scoped `_SweptRun` fixture driving the whole pipeline once per depending test, and 4 test functions.
- `src/dark_factory/artifacts/store.py` - `scrub_artifact_text_in_place(root, relative_path, *, known_secrets)`, mirroring `cli_runtime.scrub_log_in_place`'s rationale for a role's own reported artifact file rather than its captured CLI transcript.
- `src/dark_factory/orchestrator/runner.py` - `_run_current_role` scrubs every entry in `result.artifacts` in place, immediately after the `enforce_artifact_scope` block and before `collect_role_artifacts` is called.
- `tests/unit/test_global_settings_reads_are_declared.py` - declared inventory widened 19 -> 20 entries; `_run_current_role`'s four pre-existing occurrences renumbered `#1`-`#4` -> `#2`-`#5`; new `#1` entry documented; pinning test renamed/updated (`test_nineteen_entries_across_twelve_modules` -> `test_twenty_entries_across_twelve_modules`, `== 19` -> `== 20`).

## Decisions Made

See `key-decisions` in the frontmatter for the full list. Summarized:

- Drove the pipeline in-process (`start_run`/`drive` with an injected `github_client_factory`), never through the CLI subprocess, resolving 12-RESEARCH.md's Open Question 3.
- Patched `get_settings` on exactly the five modules whose redaction this test's sinks depend on (`mutations`, `runner`, `logging`, `claude_code`, `cli_runtime`), leaving `persistence.engine`'s own `get_settings` untouched so every observability read in this test still reaches the real test database.
- `monkeypatch.chdir(root)` before driving, mirroring `ClaudeCodeWorker`'s own production assumption that the process's cwd is the repository root.
- Six seeded constants split 4 configured / 2 pattern-only, with `anthropic_api_key` as the load-bearing exact-value-only proof (its shape matches no compiled pattern).
- Placed pattern-only literals only in sinks that pass through the full (`patterns=True`) redaction path, never in the GitHub issue body/task text -- `runs.normalized_task` persists task text through the pre-existing D-18 known-values-only (`patterns=False`) scrub, so a pattern-only literal planted there would legitimately survive by design and falsely trip this test's own whole-table sweep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/2 - Bug / Missing Critical Functionality] Artifact file content was never redacted before commit**
- **Found during:** Task 1, running the e2e sweep against the pipeline as it stood before this plan.
- **Issue:** Every other D-08 sink (events, role-execution columns, the clarification comment, logs, the quality-gate command string) has a `redact()` call site ahead of its respective sink; a role's own *artifact file content* did not. `git.diff.commit_run_artifacts` force-adds and commits the whole `.dark-factory/runs/<run-id>/` tree (including `artifacts/`) onto the run's working branch, which becomes the PR branch -- a permanent, external sink. A credential a role's own output happened to echo into a generated artifact file would have reached that PR diff unscrubbed, violating CLAUDE.md's "must never reach... artifacts" security constraint.
- **Fix:** Added `dark_factory.artifacts.store.scrub_artifact_text_in_place`, called from `orchestrator/runner.py`'s `_run_current_role` for every entry in `result.artifacts`, immediately after a role reports `COMPLETED` and before `collect_role_artifacts` reads the same file for schema validation and checksum computation -- so the checksum persisted in `artifacts.checksum` and the content `commit_run_artifacts` eventually commits always agree.
- **Files modified:** `src/dark_factory/artifacts/store.py`, `src/dark_factory/orchestrator/runner.py`
- **Verification:** `tests/db/test_secret_redaction_e2e_full_pipeline.py`'s own sink sweep (the planted literal in `ARCHITECTURE`'s `design.md` is absent from the committed content, with the `[redacted:` marker present); regression confirmed against 12 pre-existing db-tier tests touching artifact content (`test_four_role_pipeline.py`, `test_artifact_commit_per_role.py`, `test_artifact_handoff.py`, `test_qa_bounce.py`, `test_artifact_persistence.py`) -- all 12 pass unchanged.
- **Committed in:** `79e0e35` (Task 1 commit)

**2. [Rule 3 - Blocking] The G-11-3 settings-read inventory guard flagged the new call site as undeclared**
- **Found during:** Task 2, running the unit/contract tier's own verification.
- **Issue:** `tests/unit/test_global_settings_reads_are_declared.py` asserts bidirectional set equality between a declared inventory and every `get_settings()` call site discovered by an AST walk. The new artifact-scrub call site lands in source order *ahead of* every pre-existing `get_settings()` read inside `_run_current_role`, which renumbers the four pre-existing declared occurrences (`#1`-`#4` -> `#2`-`#5`) rather than simply adding a fifth at the end -- an undeclared-call-site failure, plus a second, dependent failure in `test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file` (which shells out to re-run the same tier) and a third in the inventory's own `== 19` pinning test.
- **Fix:** Declared the new `#1` entry, renumbered the four pre-existing entries to `#2`-`#5`, updated the module docstring's prose description, and updated the count-pinning test from 19 to 20 entries (renamed to match).
- **Files modified:** `tests/unit/test_global_settings_reads_are_declared.py`
- **Verification:** `pytest -m unit -q tests/unit/test_global_settings_reads_are_declared.py tests/unit/test_unit_tier_needs_no_database.py` -- 8 passed. Full unit/contract tier re-run afterward confirmed only the pre-existing, unrelated credential-dependent failure remains.
- **Committed in:** `6165224` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 real security gap closed with a new production redaction call site, 1 blocking test-guard update the first fix required).
**Impact on plan:** Both necessary -- the first closes a genuine credential-disclosure gap the plan's own sweep exists to find; the second is the mechanical consequence of fixing it (a declared-inventory guard doing exactly its job). No scope creep beyond these two changes.

## Issues Encountered

- **Self-inflicted false positive while authoring the sweep's log-redaction proof (test-authoring only, no production impact):** the first draft of the diagnostic `structlog` log line joined *all* seeded literals, including the bare password substrings extracted from the two configured `DATABASE_URL`/`DATABASE_URL_DIRECT` constants. A bare password token, logged standalone, is not itself a configured value or a pattern match (only the whole URL is), so it correctly survived redaction -- tripping the test's own absence assertion. Fixed by logging only the six credential *shapes* (the whole URLs, the tokens, the key-value pair), never the bare password fragments, matching how a real credential actually appears in any real sink. No production code was touched for this; it was purely a test-construction error, caught by the test itself on its first run.
- **Pre-existing, out-of-scope failures (confirmed again this session, documented identically in every prior Phase 12 plan's SUMMARY):**
  - `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this sandbox because a live `ANTHROPIC_API_KEY`/`claude` CLI is present, so the live adapter completes instead of the test's expected credential-absent `FAILED`. Unrelated to this plan's files.
  - `uv run mypy src/dark_factory` reports 2 pre-existing `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` (optional `mcp` extra not installed in this sandbox).
  - `uv run ruff format --check .` reports pre-existing unformatted files across the repo, none of which this plan touches (confirmed: none of this plan's four touched files appear in the reformat list).

All plan-scoped verification -- Task 1's and Task 2's own `<verify>`/`<acceptance_criteria>` commands, all four CI tiers, `mypy`/`ruff check`/`ruff format --check` on every file this plan touched, and `alembic check` -- passed cleanly (modulo the three pre-existing, unrelated, previously-documented issues above).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 12's fourth success criterion is proven: one seeded run reaches `COMPLETED` with a created pull request and leaves zero seeded secrets across all seven D-08 sinks, the five database tables, and all four new Phase 12 CLI surfaces -- non-vacuously, with presence-then-absence, marker-presence and terminal-state proof.
- The sweep found and closed a real, previously-unmitigated credential-disclosure gap (artifact file content), the same class of defect 12-03 found and closed for the clarification comment -- this phase has now closed every D-08 sink it set out to prove.
- All 22 `EventType` members are provably emitted, all six TRIG-02 CLI commands are registered, and `OBS-01`/`OBS-02`/`OBS-03` all have at least one named proof file in this phase's own test suite.
- No blockers for the next phase. Phase 12 (Observability & Audit Surface) is complete: all 7 plans executed.

---
*Phase: 12-observability-audit-surface*
*Completed: 2026-10-05*

## Self-Check: PASSED

- FOUND: tests/db/test_secret_redaction_e2e_full_pipeline.py
- FOUND: src/dark_factory/artifacts/store.py
- FOUND: src/dark_factory/orchestrator/runner.py
- FOUND: tests/unit/test_global_settings_reads_are_declared.py
- FOUND: commit 79e0e35
- FOUND: commit 6165224
