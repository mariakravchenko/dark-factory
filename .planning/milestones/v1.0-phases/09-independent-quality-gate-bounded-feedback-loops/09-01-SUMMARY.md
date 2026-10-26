---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 01
subsystem: orchestrator
tags: [quality-gate, verdict, shell-execute, event-catalog, GATE-01, GATE-02, GATE-03, GATE-04]

requires:
  - phase: 04-the-four-role-pipeline-artifact-handoffs
    provides: "QA's verdict.json output, Verdict.computed_status, collect_role_artifacts's D-09 schema validation"
  - phase: 06-tools-permissions-the-credential-boundary
    provides: "shell_execute (credential-bounded, timeout + process-group-kill), redact()"
provides:
  - "orchestrator/quality_gate.py: run_quality_gate / write_quality_gate_result / GateCommandResult / QualityGateResult"
  - "runner.py wiring: reads the terminal role's verdict.json, runs the gate only on a PASS verdict, downgrades to ROLE_FAILED on either a FAIL verdict or a FAIL gate"
  - "three new EventType members: QUALITY_GATE_STARTED, QUALITY_GATE_PASSED, QUALITY_GATE_FAILED"
  - "unit-tier proof of the PASS/FAIL fold, D-09 run-all-commands ordering, argv splitting, redaction and output capping"
  - "db-tier proof (written, collection-verified, not execution-verified -- see Deviations) that a real drive() run gates on the gate and on the verdict"
affects: [09-02-bounded-feedback-loops, 12-observability-audit-history]

actuals:
  tokens: 11890
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Computed-field PASS/FAIL fold (QualityGateResult.status), mirroring Verdict.computed_status's 'never hand-set' discipline"
    - "Structural terminal-role detection via next_node(pipeline, node.name) is None, never a role-name literal"
    - "A gitignored per-run artifact write placed BEFORE the role's own commit_run_artifacts call so it rides that one existing force-added commit, rather than requiring a second commit"

key-files:
  created:
    - src/dark_factory/orchestrator/quality_gate.py
    - tests/unit/test_quality_gate.py
    - tests/db/test_quality_gate_gates_the_run.py
  modified:
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/events/catalog.py
    - tests/unit/test_domain_enums.py
    - tests/support/fake_artifacts.py
    - tests/db/test_artifact_schema_violation_fails_role.py

key-decisions:
  - "Task 1's checkpoint (EventType naming) was pre-answered by the user before dispatch: Option A1, three purpose-built members (QUALITY_GATE_STARTED/PASSED/FAILED), following the CAPABILITY_DENIED precedent."
  - "The gate-execution block is placed BEFORE commit_run_artifacts (inside the collect_role_artifacts success branch), not after enforce_write_scope as the plan's action text first sketched -- see Deviations for why this was necessary."
  - "The gate always runs on a PASS verdict regardless of the configured commands list; an empty list folds to a vacuous PASS with no special case, matching every existing db test's default empty quality_gate.commands."

patterns-established:
  - "Independent-quality-gate audit tie: an orchestrator-only step with no role_executions row still gets a first-class run_events trace, via purpose-built EventType members spliced into the existing ROLE_COMPLETED/ROLE_FAILED dispatch arms."

requirements-completed: [GATE-01, GATE-02, GATE-03, GATE-04]

coverage:
  - id: D1
    description: "run_quality_gate executes every configured command through shell_execute with cwd set to the run's worktree and the configured timeout (GATE-01, D-01, D-03, D-10)"
    requirement: "GATE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_two_passing_commands_yield_pass_with_two_entries_in_order"
        status: pass
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py::test_gate_pass_completes_the_run_and_persists_both_command_results"
        status: not_run
    human_judgment: true
    rationale: "The unit-tier proof runs real child processes via shell_execute and is fully verified (pass). The db-tier proof requires a reachable PostgreSQL 17 -- this sandbox has no Docker, no local initdb/pg_ctl, and no DARK_FACTORY_TEST_DATABASE_URL, the same pre-existing constraint every prior db/integration-gated plan in this project has documented (see Phase 6/7/8 SUMMARY.md precedent). Collection-verified clean: 3 tests collected, zero import/collection errors. Re-run once a real Postgres 17 is available: `uv run pytest -m db -q tests/db/test_quality_gate_gates_the_run.py`."
  - id: D2
    description: "All configured commands run even after an earlier one fails -- the persisted commands list always has one entry per configured command (D-09)"
    requirement: "GATE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_a_failing_first_command_does_not_stop_the_second_and_yields_fail"
        status: pass
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py::test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D1. Collection-verified clean."
  - id: D3
    description: "QualityGateResult.status is a computed field folded from exit_code==0 and timed_out==False over every command, PASS iff all satisfy it; no constructor argument can hand-set it"
    requirement: "GATE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_quality_gate_result_cannot_be_constructed_with_an_explicit_status"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_quality_gate_result_status_key_order_is_commands_then_status"
        status: pass
    human_judgment: false
  - id: D4
    description: "A gate whose commands produced a non-zero exit_code never reaches RunStatus.COMPLETED on that attempt, regardless of the worker's own success-claiming summary (GATE-02, GATE-03)"
    requirement: "GATE-02"
    verification:
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py::test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D1. Satisfied by construction in runner.py (the signal is derived from gate_result.status alone, never from result.summary or any worker-authored text) and collection-verified; not execution-verified in this sandbox."
  - id: D5
    description: "verification/quality_gate.json exists after the gate runs and parses as an object with exactly the keys status and commands, each command entry with exactly command/exit_code/stdout/stderr/timed_out (GATE-04, D-11)"
    requirement: "GATE-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_write_quality_gate_result_writes_under_verification"
        status: pass
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py::test_gate_pass_completes_the_run_and_persists_both_command_results"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D1. The db-tier scenario additionally proves the file is readable from the run's *committed working branch* after COMPLETED cleanup removes the worktree -- collection-verified, not execution-verified here."
  - id: D6
    description: "Captured stdout/stderr are redacted against known secret values before entering the model, and capped at 16 KiB per stream with an explicit dropped-byte marker, never a silent truncation (T-09-03, T-09-06)"
    requirement: "GATE-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_a_known_secret_value_in_stdout_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_stdout_over_the_cap_is_tail_preserved_with_an_explicit_drop_marker"
        status: pass
    human_judgment: false
  - id: D7
    description: "A FAIL verdict short-circuits before the gate ever runs -- no gate command executes, no QUALITY_GATE_STARTED event is written -- closing 09-RESEARCH.md's Critical Mechanics Gap 1"
    requirement: "GATE-03"
    verification:
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py::test_a_failing_verdict_short_circuits_the_gate_entirely"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D1. This is the single scenario that proves 09-RESEARCH.md's headline gap is closed; collection-verified clean, re-run command above applies."
  - id: D8
    description: "The gate's start/pass/fail are visible in the audit trail via three purpose-built EventType members, spliced into the existing ROLE_COMPLETED/ROLE_FAILED event-dispatch arms without disturbing their existing order (D-02)"
    requirement: "GATE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_domain_enums.py::test_event_type_has_exactly_fifteen_members_with_the_phase_two_five_six_and_nine_types"
        status: pass
      - kind: db
        ref: "tests/db/test_quality_gate_gates_the_run.py (all three scenarios assert run_events counts)"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D1."
  - id: D9
    description: "The gate is orchestrator-only, structurally detected (next_node(pipeline, node.name) is None), never a role-name literal or a live config-loader read -- the existing AST guards stay green"
    requirement: "GATE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_no_role_name_literal.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_orchestrator_no_live_config_read.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_no_tree_walk.py"
        status: pass
      - kind: unit
        ref: "tests/unit/test_single_mutation_path.py"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-09-23
status: complete
---

# Phase 9 Plan 01: Independent Quality Gate Summary

**After a PASS QA verdict, Dark Factory itself runs the repository's own `quality_gate.commands` via `shell_execute`, folds PASS/FAIL from exit codes alone into a computed field that cannot be hand-set, writes `verification/quality_gate.json`, and downgrades the run to `FAILED` on either a FAIL verdict or a FAIL gate -- closing 09-RESEARCH.md's Critical Mechanics Gap 1 (a FAILing verdict previously reached `COMPLETED` unconditionally).**

## Performance
- **Duration:** ~50min (approximate; no wall-clock start capture was recorded at spawn)
- **Completed:** 2026-09-23T05:26:08Z
- **Tasks:** 2 (Task 1 tracer, Task 2 auto; Task 1's checkpoint was pre-answered before dispatch)
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- New `src/dark_factory/orchestrator/quality_gate.py`: `GateCommandResult`/`QualityGateResult` (computed `status` field, `extra="forbid"`, frozen), `run_quality_gate` (shlex-split argv, redact-then-cap captured output), `write_quality_gate_result`.
- `orchestrator/runner.py` now reads the terminal role's `verdict.json` back after `collect_role_artifacts` succeeds, structurally detects "this is the pipeline's terminal role" via `next_node(pipeline, node.name) is None` (never a role-name literal), and:
  - a FAIL verdict short-circuits to `ROLE_FAILED` before the gate ever runs;
  - a PASS verdict runs the configured `quality_gate.commands` and downgrades to `ROLE_FAILED` on a non-PASS gate result.
- Three new `EventType` members (`QUALITY_GATE_STARTED`/`PASSED`/`FAILED`, D-02) spliced into the existing `ROLE_COMPLETED`/`ROLE_FAILED` event-dispatch arms; the catalog's module docstring no longer claims these arrive in Phase 12.
- 20 new unit-tier tests (`tests/unit/test_quality_gate.py`) proving the PASS/FAIL fold, D-09 run-all-commands ordering, real argv splitting/no-shell-interpretation, redaction, output capping and the `status=` construction guard.
- 3 new db-tier scenarios (`tests/db/test_quality_gate_gates_the_run.py`) driving real `drive()` runs against `[BA, ARCHITECTURE, DEVELOPMENT, QA]` -- written and collection-verified; execution deferred to a real PostgreSQL 17 (see Deviations).

## Task Commits
1. **Task 1: End-to-end "the repository's own commands decide, not the agent"** - `4a7a19e` (feat)
2. **Task 2: Prove it against a real run** - `bd2ad27` (test)

## Files Created/Modified
- `src/dark_factory/orchestrator/quality_gate.py` - new module: the gate's execution, redaction/capping and D-11 result shape
- `src/dark_factory/orchestrator/runner.py` - verdict-read + gate block wired into `_run_current_role`; new imports (`json`, `read_artifact_text`, `Verdict`, `VerdictStatus`, `next_node`, `run_quality_gate`, `write_quality_gate_result`)
- `src/dark_factory/events/catalog.py` - three new `EventType` members + docstring update
- `tests/unit/test_quality_gate.py` - pure-tier proof of the module's `<behavior>` contract
- `tests/unit/test_domain_enums.py` - `EventType` exact-count assertion 12 -> 15
- `tests/db/test_quality_gate_gates_the_run.py` - real `drive()` proof of GATE-01..04
- `tests/support/fake_artifacts.py` - `QA_VERDICT_FAIL_FILES` constant + `LazyFourRoleWorker`'s optional `qa_files` override
- `tests/db/test_artifact_schema_violation_fails_role.py` - docstring updated to record the Phase 4 deferral this plan closes; assertions untouched

## Decisions Made
- Task 1's `checkpoint:decision` (how to name the quality-gate audit events in `EventType`) was pre-answered by the user before this plan was dispatched: **Option A1** -- three purpose-built members, `QUALITY_GATE_STARTED`/`QUALITY_GATE_PASSED`/`QUALITY_GATE_FAILED` -- the plan's own recommended option and the naming Task 2's own `<action>` text already assumed. Not re-asked; logged here as the record of that decision.
- The gate always runs on a PASS verdict, even with an empty `quality_gate.commands` list -- an empty list folds to a vacuous PASS with no special case (matches `Verdict.computed_status`'s own `all(...)` discipline and the pre-existing default every other db test in this repository already carries).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - missing critical durability] Moved the gate-execution block from "after `enforce_write_scope`" to "before `commit_run_artifacts`", and had `verification/quality_gate.json` ride that role's own existing commit instead of proposing a second one**

- **Found during:** Task 1, while implementing the runner.py wiring exactly as the plan's action text describes it ("insert one new block ... immediately after the existing `enforce_write_scope` block").
- **Issue:** `.dark-factory/runs/<run_id>/` is gitignored (`.gitignore`: `.dark-factory/runs/`). The plan's literal placement writes `verification/quality_gate.json` to disk *after* the terminal role's own `commit_run_artifacts` call has already run. On a run that reaches `COMPLETED`, the worktree is then removed by `_cleanup_run_worktree`, whose only recovery step (`wip_commit_if_dirty`) stages with a plain `git add -A` -- which, verified empirically in this session, **never** stages a brand-new file under an ignored path (only `git add -f` does). The gate's result file would therefore be silently lost the moment a `COMPLETED` run's worktree is cleaned up, directly contradicting Task 2's own acceptance criterion that scenario 1 (gate PASS) must read the file back "from the run's committed working branch."
  A second candidate fix -- calling `commit_run_artifacts` a second time with a distinct `role="quality_gate"` label, after the existing terminal-role commit -- was rejected because it introduces a *second* `ARTIFACT_COMMIT_SUBJECT_PREFIX`-labelled commit per completed run, which breaks the pre-existing, out-of-plan-scope invariant `tests/db/test_artifact_commit_per_role.py::test_one_artifact_commit_per_role_force_added_and_source_edits_survive` asserts (`role_order == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]`, `len(role_order) == len(set(role_order))`).
- **Fix:** The verdict-read + gate-execution block now sits *inside* the `collect_role_artifacts` success branch, immediately before the pre-existing `commit_run_artifacts(work_dir, run_id, role=node.name)` call. Since that call already force-adds (`git add -f`) the *whole* `.dark-factory/runs/<run_id>` tree in one commit, writing the gate result first means it rides that one existing, already-scheduled commit -- no second commit, no change to `test_artifact_commit_per_role.py`'s invariant, and the file survives worktree cleanup on `COMPLETED`. Verified empirically in a throwaway repo that `git add -f -- <dir>` picks up a brand-new file under an ignored directory even when other files in that directory were already tracked from a prior commit.
- **Files modified:** `src/dark_factory/orchestrator/runner.py` (placement only; the block's own logic is otherwise as specified)
- **Commit:** `4a7a19e`

**2. [Rule 3 - blocking environment gap] Created no `.env` file; ran with inline placeholder `DATABASE_URL`/`DATABASE_URL_DIRECT` env vars for local verification only**
- **Found during:** running the plan's own `<verify>` unit-tier commands -- `pytest -m unit` fails at *collection* time with no environment configured at all, because `tests/integration/test_claude_code_live.py`/`test_copilot_live.py` call `get_settings()` at module scope and `Settings.database_url`/`database_url_direct` have no default.
- **Fix:** Supplied `DATABASE_URL`/`DATABASE_URL_DIRECT` as inline, visibly-fake placeholder values (matching `.env.example`'s own documented placeholder shape) on the `pytest` invocation only -- never written to any tracked or persisted file. This is local verification setup, not a code or config change.
- **Files modified:** none.

### None beyond the above
Every other part of the plan (the module's shape, the runner's verdict/gate decision logic, the three event types, the db-tier scenario set) was implemented exactly as specified.

## Issues Encountered

**db-tier execution deferred (not a failure):** This sandbox has no reachable PostgreSQL 17 -- no Docker, no local `initdb`/`pg_ctl`, and no `DARK_FACTORY_TEST_DATABASE_URL` set -- the same pre-existing, documented constraint every prior db/integration-gated plan in this project (Phases 6, 7, 8) has carried and recorded. `tests/db/test_quality_gate_gates_the_run.py` collects cleanly (3 tests, zero import/collection errors, confirmed this session) but was not executed here. See the `coverage` entries above (D1, D2, D4, D5, D7, D8) for the honest `human_judgment: true` accounting.

## User Setup Required

A reachable PostgreSQL 17 instance is required to execute this plan's three db-tier scenarios. Once available, re-run:

```bash
uv run pytest -m db -q tests/db/test_quality_gate_gates_the_run.py
```

Expected: 3 passed, 0 skipped. Also re-run the full db tier to confirm no regression on the pre-existing suite (per the plan's own `<verification>` section):

```bash
uv run pytest -m db -q
```

## Next Phase Readiness

Plan 09-02 (bounded feedback loops, `Signal.ROLE_BOUNCED`) can proceed: the verdict-read and gate-execution logic this plan built is the exact seam 09-02 upgrades from a terminal `ROLE_FAILED` outcome to the bounded bounce loop, at the same two `signal = Signal.ROLE_FAILED` assignment sites this plan introduced (`qa_verdict_fail`, `quality_gate_fail`). No other Phase 9 plan depends on anything this plan did not ship.

## Self-Check: PASSED

- FOUND: `src/dark_factory/orchestrator/quality_gate.py`
- FOUND: `tests/unit/test_quality_gate.py`
- FOUND: `tests/db/test_quality_gate_gates_the_run.py`
- FOUND: `.planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-01-SUMMARY.md`
- FOUND commit: `4a7a19e` (Task 1)
- FOUND commit: `bd2ad27` (Task 2)
- FOUND commit: `6015e5d` (metadata)
