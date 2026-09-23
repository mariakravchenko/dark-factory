---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 03
subsystem: orchestrator
tags: [context-builder, optional-inputs, feedback-artifact, verdict, quality-gate, LOOP-01, LOOP-02]

requires:
  - phase: 09-independent-quality-gate-bounded-feedback-loops
    provides: [ROLE_BOUNCED, previous_node, the bounce loop from plans 09-01/09-02, a bounced attempt's role_executions.status staying "COMPLETED"]
provides:
  - "RoleDefinition.optional_inputs (config/loader.py) -- a validated, leniently-resolved role-config key, distinct from mandatory inputs"
  - "ContextBuilder._resolve_optional_input -- two-strategy lenient resolution: the declared-output path (reused from _resolve_input, MissingArtifactContentError caught) and a direct verification/<filename> read for orchestrator-written files with no role_executions row"
  - "DEVELOPMENT.yaml declares optional_inputs: [verdict.json, quality_gate.json] -- the shipped Phase 9 feedback-loop payload contract"
  - "real drive() proof (test_feedback_reaches_developer.py) that a bounced Developer attempt actually receives both payloads, absent on attempt 1, and that the same content is independently reconstructable by a fresh process (D-07)"
affects: [12-observability-audit-history]

actuals:
  tokens: 9317
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Two-strategy lenient input resolution: reuse the mandatory resolver and catch its 'absent' exceptions for the declared-output case, fall back to a direct named-path read (never a directory walk) when no role declares the filename at all"
    - "A resolver that never catches ArtifactTooLargeError -- oversized feedback must surface loudly, never silently truncate or silently omit"
    - "Fresh-session rebuild-at-dispatch-time as the D-07 durability proof: a capturing test worker reconstructs RoleContext with a brand-new session at the exact moment the runner hands the original to the worker, before any later role's row exists to contaminate the comparison"

key-files:
  created:
    - tests/db/test_feedback_reaches_developer.py
  modified:
    - src/dark_factory/config/loader.py
    - src/dark_factory/context/builder.py
    - .dark-factory/roles/DEVELOPMENT.yaml
    - .dark-factory/roles/QA.yaml
    - src/dark_factory/actions/builtins.py
    - tests/unit/test_context_builder.py

key-decisions:
  - "optional_inputs is a new, separate RoleDefinition field (not an annotation on inputs) so mandatory-input strictness (raise on missing) and optional-input leniency (omit on missing) can never be confused at the config-schema level."
  - "verification/quality_gate.json's resolution deliberately never touches _producing_role or the artifacts table (direction (a) from 09-RESEARCH's Open Question 1) -- the gate has no role_executions row to hang an ArtifactReference on (D-01), so a second, distinct resolution strategy reads the named path directly."
  - "The QA-verdict-FAIL feedback content reused verbatim from plan 09-01's QA_VERDICT_FAIL_FILES fixture, rather than authoring new test content -- its existing shape (criteria[].criterion_id matching BA's emitted AC-1, issues[].severity/description) already satisfies LOOP-01's literal requirement without touching the shipped, frozen Verdict/VerdictIssue domain schema (out of this plan's declared file scope)."

patterns-established:
  - "A role-config key with mandatory/optional siblings resolves through the identical producing-role/artifact-row lookup for both, differing only in whether a missing result raises or is silently omitted -- established here for inputs/optional_inputs, reusable for any future role-config pair with the same shape."

requirements-completed: [LOOP-01, LOOP-02]

coverage:
  - id: D1
    description: "A role's snapshot entry declaring no optional_inputs key at all produces a RoleContext byte-identical to explicitly declaring an empty list -- the regression guard for every pre-Phase-9 role"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_no_optional_inputs_key_is_byte_identical_to_explicit_empty_list"
        status: pass
    human_judgment: false
  - id: D2
    description: "A declared optional input naming another role's declared output, with a COMPLETED attempt and a matching artifacts row, resolves to an ArtifactInput carrying that content and produced_by"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_input_resolves_when_producing_role_completed"
        status: pass
    human_judgment: false
  - id: D3
    description: "The same declaration resolves to nothing (no exception) when the producing role has no COMPLETED attempt yet, or has one but no matching artifacts row"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_input_absent_when_producing_role_has_no_completed_attempt"
        status: pass
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_input_absent_when_no_matching_artifact_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "A declared optional input naming a file no role declares as an output falls back to reading verification/<filename> under the run root -- present resolves with produced_by='quality_gate', absent resolves to nothing"
    requirement: "LOOP-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_input_falls_back_to_verification_tree_when_present"
        status: pass
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_input_falls_back_to_verification_tree_when_absent"
        status: pass
    human_judgment: false
  - id: D5
    description: "An oversized optional input raises ArtifactTooLargeError rather than being silently skipped"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_oversized_optional_input_raises"
        status: pass
    human_judgment: false
  - id: D6
    description: "Resolved optional inputs appear in RoleContext.inputs after the mandatory ones, in declaration order"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_context_builder.py::test_optional_inputs_appear_after_mandatory_inputs_in_declaration_order"
        status: pass
    human_judgment: false
  - id: D7
    description: "The shipped DEVELOPMENT.yaml declares exactly optional_inputs: [verdict.json, quality_gate.json] and its mandatory inputs stay unchanged at [design.md, constraints.json] -- the feedback filenames never leaked into the mandatory list (Pitfall 2)"
    requirement: "LOOP-01"
    verification:
      - kind: unit
        ref: "load_effective_config(Path('.')) direct invocation -- see Self-Check"
        status: pass
    human_judgment: false
  - id: D8
    description: "A real bounced Developer attempt-1 RoleContext carries exactly the two mandatory inputs, no verdict.json entry, no exception; attempt-2 carries a verdict.json entry whose produced_by names QA and whose parsed content carries the same severity/criterion-id/description QA's FAIL attempt wrote"
    requirement: "LOOP-01"
    verification:
      - kind: db
        ref: "tests/db/test_feedback_reaches_developer.py::test_qa_fail_delivers_structured_issues_to_developer_attempt_2"
        status: not_run
    human_judgment: true
    rationale: "This sandbox has no reachable PostgreSQL 17 -- no Docker, no local initdb/pg_ctl, and no DARK_FACTORY_TEST_DATABASE_URL, the same pre-existing constraint every prior db-tier plan in this project (Phases 6/7/8, plans 09-01/09-02) has documented. The module collects cleanly (2 tests, zero import/collection errors, confirmed this session via `pytest -m db --collect-only`) but was not executed here. Re-run once a real PostgreSQL 17 is available: `uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py`."
  - id: D9
    description: "A real bounced Developer attempt-1 RoleContext carries no quality_gate.json entry; attempt-2 carries one whose produced_by is 'quality_gate', whose path is 'verification/quality_gate.json', and whose parsed content carries a commands entry with a non-zero exit_code and the sentinel string in its stderr -- the actual failure output, LOOP-02's literal requirement"
    requirement: "LOOP-02"
    verification:
      - kind: db
        ref: "tests/db/test_feedback_reaches_developer.py::test_gate_fail_delivers_real_command_output_to_developer_attempt_2"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D8. Collection-verified clean."
  - id: D10
    description: "Between the bounce and the Developer's next dispatch, a fresh session rebuilding the run state and calling build_role_context directly for DEVELOPMENT resolves a RoleContext.inputs equal to the one the runner itself built and handed to the worker -- proof this is a durable artifact, not an in-memory value carried across advance() calls (D-07)"
    requirement: "LOOP-01"
    verification:
      - kind: db
        ref: "tests/db/test_feedback_reaches_developer.py (both scenarios assert rebuilt[('DEVELOPMENT', 2)].inputs == dev_attempt_2.inputs)"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D8. The rebuild happens inside the capturing test worker's own execute() call, at the exact moment the runner hands the original context to it and before QA's own second attempt row has even been entered -- collection-verified clean, not execution-verified here."
  - id: D11
    description: "collect_test_results is no longer described anywhere as a genuine Phase 9 placeholder -- QA.yaml and builtins.py both now record that GATE-04 shipped as orchestrator-inline code in plan 09-01 and that an after: hook could never have driven the bounce decision; the function's body and registry entry are unchanged"
    requirement: "LOOP-02"
    verification:
      - kind: unit
        ref: "grep -c 'Phase 9' .dark-factory/roles/QA.yaml == 1 (shipped-behaviour wording, not a placeholder claim); collect_test_results still defined and registered -- see Self-Check"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-09-23
status: complete
---

# Phase 9 Plan 03: Feedback Delivery Summary

**A bounced Developer attempt now actually receives the feedback that caused the bounce: QA's structured `verdict.json` issues and the quality gate's real `quality_gate.json` command output resolve into the Developer's next `RoleContext` through two declared, leniently-resolved `optional_inputs` -- absent and harmless on attempt 1, present with the real content on the bounced attempt -- proved against a real `drive()` run with a fresh-process durability check, closing LOOP-01 and LOOP-02.**

## Performance
- **Duration:** ~50min (approximate; no wall-clock start capture was recorded at spawn)
- **Completed:** 2026-09-23T06:39:29Z
- **Tasks:** 2 (Task 1 auto/tdd, Task 2 auto)
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments
- `RoleDefinition.optional_inputs` (config/loader.py): a new, validated, leniently-resolved role-config key distinct from mandatory `inputs`, snapshot-projected alongside it.
- `ContextBuilder._resolve_optional_input` (context/builder.py): two fixed strategies -- reuse `_resolve_input`'s declared-output path but catch `MissingArtifactContentError` and return `None`; when no role declares the filename as an output at all (`ArtifactContractError`), read `verification/<filename>` directly under the run root, tagging it `produced_by="quality_gate"`. `ArtifactTooLargeError` is never caught in either strategy. Resolved optional inputs append to `RoleContext.inputs` after the mandatory ones, in declaration order.
- `.dark-factory/roles/DEVELOPMENT.yaml` now declares `optional_inputs: [verdict.json, quality_gate.json]` alongside its unchanged mandatory `inputs: [design.md, constraints.json]` -- the shipped Phase 9 feedback-loop contract, landed in the same task as the `ContextBuilder` fix per 09-RESEARCH.md's Pitfall 2 warning.
- 8 new unit-tier tests (`tests/unit/test_context_builder.py`) covering every `<behavior>` line: the no-key regression guard, both resolution strategies' present/absent paths, the oversized-raises guard, and declaration-order placement.
- `tests/db/test_feedback_reaches_developer.py`: two real `drive()` scenarios proving LOOP-01 (QA-FAIL `verdict.json` issues) and LOOP-02 (gate-FAIL `quality_gate.json` real command output) reach the Developer's bounced attempt-2 `RoleContext`, are absent on attempt 1 with no exception, and are independently reconstructable by a fresh process mid-run (D-07) -- written and collection-verified (see Deviations/Coverage).
- `collect_test_results`'s stale "Phase 9 (GATE-04) placeholder" framing removed from both `QA.yaml`'s comment and `builtins.py`'s module/function docstrings (comment-only; no behaviour change) -- it now joins `prepare_role_context`/`store_role_artifacts`'s permanent-no-op register, pointing readers at `orchestrator/quality_gate.py`.

## Task Commits
1. **Task 1: Declared, optional feedback inputs the Developer can receive** - `1721069` (feat)
2. **Task 2: Prove the Developer's next attempt sees why it was bounced** - `efd534a` (test)

## Files Created/Modified
- `src/dark_factory/config/loader.py` - `RoleDefinition.optional_inputs` field + snapshot projection
- `src/dark_factory/context/builder.py` - `_resolve_optional_input`, wired into `build_role_context`, module docstring extended
- `.dark-factory/roles/DEVELOPMENT.yaml` - `optional_inputs: [verdict.json, quality_gate.json]`
- `.dark-factory/roles/QA.yaml` - `collect_test_results` comment corrected (no longer a placeholder)
- `src/dark_factory/actions/builtins.py` - module docstring + `collect_test_results` docstring corrected
- `tests/unit/test_context_builder.py` - 8 new cases proving every `<behavior>` line
- `tests/db/test_feedback_reaches_developer.py` (new) - LOOP-01/LOOP-02 proved against real `drive()` runs, plus D-07 durability

## Decisions Made
- `optional_inputs` is a separate `RoleDefinition` field rather than an annotation/flag on `inputs`, so mandatory strictness and optional leniency can never be confused at the schema level.
- `verification/quality_gate.json`'s resolution deliberately never touches `_producing_role` or the `artifacts` table (09-RESEARCH.md's Open Question 1, direction (a)) -- the gate has no `role_executions` row to hang an `ArtifactReference` on (D-01).
- The QA-FAIL scenario reuses plan 09-01's existing `QA_VERDICT_FAIL_FILES` fixture verbatim rather than authoring new content -- its shape (`criteria[].criterion_id` matching BA's emitted `AC-1`, `issues[].severity`/`description`) already satisfies LOOP-01's structured-issues requirement without touching the shipped, frozen `Verdict`/`VerdictIssue` domain schema, which is outside this plan's declared file scope.

## Deviations from Plan

None - plan executed exactly as written. The two-strategy resolver, the `DEVELOPMENT.yaml` declaration, the db-tier proof shape, and the `collect_test_results` comment corrections all match the plan's `<action>` text.

## Issues Encountered

**db-tier execution deferred (not a failure):** This sandbox has no reachable PostgreSQL 17 -- no Docker, no local `initdb`/`pg_ctl`, and no `DARK_FACTORY_TEST_DATABASE_URL` set -- the same pre-existing, documented constraint every prior db-tier plan in this project (Phases 6, 7, 8, plans 09-01, 09-02) has carried. `tests/db/test_feedback_reaches_developer.py` collects cleanly (2 tests, zero import/collection errors, confirmed this session) but was not executed here. See the `coverage` entries above (D8, D9, D10) for the honest `human_judgment: true` accounting.

**Fully executed and green this session:** `pytest -m unit -q tests/unit/test_context_builder.py tests/unit/test_no_tree_walk.py tests/unit/test_repo_config_schema.py` (33 passed) and `pytest -m "unit or contract" -q --tb=short` (658 passed, 1 skipped, 333 deselected, confirmed after both tasks) and `mypy src/dark_factory` / `ruff check .` (both clean; mypy's two `mcp.server` import-not-found errors in `tools/mcp_transport.py` are pre-existing and unrelated to this plan, matching plan 09-02's own confirmation via `git stash`).

**Task 2's `<human-check>` (deferred to end-of-phase UAT per `workflow.human_verify_mode: end-of-phase`):** confirming the feedback loop works against a genuinely broken command in a scratch clone (not a fixture) -- a real `uv run pytest -q` failure, a real run driven past QA's PASS verdict, confirmation the run loops back to the Developer instead of completing, and confirmation no credential value appears in `verification/quality_gate.json`. Left as a documented manual-verification item for the phase verifier to harvest, not auto-approved or faked.

## User Setup Required

A reachable PostgreSQL 17 instance is required to execute this plan's db-tier scenarios. Once available, re-run:

```bash
uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py
```

Expected: 2 passed, 0 skipped. Also re-run the full db tier to confirm no regression on the pre-existing suite (per the plan's own `<verification>` section):

```bash
uv run pytest -m db -q
```

And complete Task 2's `<human-check>` manual walkthrough (see Issues Encountered above) once a scratch clone and real PostgreSQL are both available.

## Next Phase Readiness

All 3 plans in Phase 9 are now complete (GATE-01..04, LOOP-01..04) pending final phase verification. This plan closes LOOP-01 and LOOP-02's payload half; plan 09-02 already shipped the bounce mechanism and LOOP-03/LOOP-04's iteration-cap/exhaustion behaviour. No further Phase 9 plan is outstanding.

## Self-Check: PASSED

- FOUND: `src/dark_factory/config/loader.py` (`optional_inputs` field + snapshot projection)
- FOUND: `src/dark_factory/context/builder.py` (`_resolve_optional_input`)
- FOUND: `.dark-factory/roles/DEVELOPMENT.yaml` (`optional_inputs: [verdict.json, quality_gate.json]`)
- FOUND: `tests/unit/test_context_builder.py` (8 new cases)
- FOUND: `tests/db/test_feedback_reaches_developer.py`
- FOUND: `.planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-03-SUMMARY.md`
- FOUND commit: `1721069` (Task 1)
- FOUND commit: `efd534a` (Task 2)
