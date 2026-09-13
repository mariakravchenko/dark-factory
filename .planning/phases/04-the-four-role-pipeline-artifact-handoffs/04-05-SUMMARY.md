---
phase: 04-the-four-role-pipeline-artifact-handoffs
plan: 05
subsystem: testing
tags: [fakeworker, artifact-synthesis, criterion-ids, pydantic, pytest, gap-closure]

# Dependency graph
requires:
  - phase: 04-the-four-role-pipeline-artifact-handoffs (04-01..04-04)
    provides: BA->ARCHITECTURE->DEVELOPMENT->QA pipeline scaffolding, artifact persistence, and FakeWorker's placeholder artifact synthesis that this plan makes input-aware
provides:
  - "context.inputs -> criterion-id extraction -> artifact-content synthesis data path in FakeWorker"
  - "Unit derivation/falsification proof (rename-follows) distinguishing genuine id derivation from two coinciding literals"
  - "Content-assertion regression guard on the zero-config integration pipeline (tests/integration/test_real_pipeline_zero_config.py)"
  - "Reconciled 04-VALIDATION.md proof map and test_phase4_acceptance.py drift guard"
affects: [phase-05-worker-runtime-integration, phase-07-task-aware-content]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 10673
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Role-agnostic dispatch on input content shape (structural pydantic validation, then textual carrier-line regex) rather than on context.role, preserving D-08"
    - "Markdown carrier-line convention (`Criterion <id> met`) as the mechanism by which ids survive a role hop whose declared inputs exclude the origin JSON document"

key-files:
  created:
    - tests/unit/test_fake_worker_synthesis.py
  modified:
    - src/dark_factory/workers/fake.py
    - tests/integration/test_real_pipeline_zero_config.py
    - tests/integration/test_phase4_acceptance.py
    - .planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md

key-decisions:
  - "Extraction dispatches on content shape only (structural AcceptanceCriteriaDocument validation, then a carrier-line regex) — never on context.role — keeping D-08's role-agnostic FakeWorker invariant intact while still routing content correctly"
  - "Markdown outputs carry ids via a single accepted carrier-line style ('Criterion <id> met') so the DEVELOPMENT role, whose declared inputs are design.md/constraints.json and not acceptance_criteria.json, still receives ids through the markdown hop"
  - "Every extracted id is filtered to a single whitespace-free token under 64 chars before use, bounding what upstream artifact content can inject downstream (T-04-19/T-04-21)"

patterns-established:
  - "Regression tests for synthesized content compare against the origin artifact's own emitted ids rather than a hardcoded expectation, so the test cannot coincidentally pass the way the original defect did"

requirements-completed: [ORCH-04, ROLE-04, ART-01, ART-02]

coverage:
  - id: D1
    description: "A zero-config `dark-factory run` produces a design.md that names the same criterion ids acceptance_criteria.json declares"
    requirement: "ART-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py#test_structural_extraction_carries_ids_into_design_and_constraints"
        status: pass
      - kind: integration
        ref: "tests/integration/test_real_pipeline_zero_config.py#test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script"
        status: pass
    human_judgment: false
  - id: D2
    description: "verdict.json's criterion_id values are derived from the acceptance_criteria.json content the QA role actually received, not a literal inside the worker (D-05)"
    requirement: "ROLE-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py#test_derived_verdict_matches_acceptance_criteria_order"
        status: pass
      - kind: integration
        ref: "tests/integration/test_real_pipeline_zero_config.py#test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script"
        status: pass
    human_judgment: false
  - id: D3
    description: "Renaming the origin criterion id moves the id in every downstream artifact with no other code change — the falsification test distinguishing derivation from coincidence"
    requirement: "ORCH-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py#test_renaming_origin_id_moves_every_downstream_id"
        status: pass
    human_judgment: false
  - id: D4
    description: "implementation_summary.json names the criterion ids the DEVELOPMENT role received, proving ids survive the markdown hop through design.md when acceptance_criteria.json is not in that role's declared inputs"
    requirement: "ROLE-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py#test_markdown_hop_extraction_survives_into_implementation_summary"
        status: pass
      - kind: integration
        ref: "tests/integration/test_real_pipeline_zero_config.py#test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script"
        status: pass
    human_judgment: false
  - id: D5
    description: "The zero-config integration test fails if any downstream artifact stops carrying BA's ids — the gate is no longer existence-only"
    requirement: "ART-01"
    verification:
      - kind: integration
        ref: "tests/integration/test_real_pipeline_zero_config.py#test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script"
        status: pass
    human_judgment: false
  - id: D6
    description: "FakeWorker still never branches on which role it is executing (D-08): id extraction dispatches on input content shape only"
    requirement: "ORCH-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_fake_worker_synthesis.py#test_extraction_result_is_independent_of_role_value"
        status: pass
    human_judgment: false
  - id: D7
    description: "A fresh-eyes reader (someone who has never seen this codebase) can open a real run's artifacts/ tree and follow the id handoff, judging that the layout itself reads well"
    verification: []
    human_judgment: true
    rationale: "04-VALIDATION.md's Manual-Only row (updated by this plan's Task 3) explicitly keeps this readability judgment as a re-check at /gsd-verify-work even though the underlying id-alignment content is now machine-asserted by D1-D5 above — whether an on-disk layout 'reads well' to a first-time human viewer is not something a test decides."

# Metrics
duration: ~17min (span across the 4 task commits; distributed across multiple execution sessions/continuations, with two DB-gated verify runs executed by the project owner directly)
completed: 2026-09-13
status: complete
---

# Phase 04 Plan 05: FakeWorker Criterion-ID Extraction and Handoff Regression Guard Summary

**FakeWorker's artifact synthesis now threads `context.inputs` through structural-then-textual criterion-id extraction so BA's ids provably reach design.md, implementation_summary.json, test_report.json, and verdict.json, with a rename-follows falsification proof and content-asserting integration/acceptance gates closing UAT gap G-04-1.**

## Performance

- **Duration:** ~17 min of commit-to-commit span (7e2b69a → 9a6dfc0), executed across multiple sessions/continuations; the two DB-gated `<verify>` runs (Task 2 integration test, Task 3 acceptance gate) were executed by the project owner directly against their own `.env`-configured Postgres
- **Tasks:** 3 of 3 completed
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- Replaced FakeWorker's two independent hardcoded criterion-id literals with a single origin-id constant plus a role-agnostic, content-shape-dispatched extraction helper (structural `AcceptanceCriteriaDocument` validation, then a carrier-line regex), threaded into every synthesized D-10 document and into Markdown outputs via a `Criterion <id> met` carrier line
- Added a unit derivation/falsification suite (`tests/unit/test_fake_worker_synthesis.py`) proving the four shipped role shapes (BA/ARCHITECTURE/DEVELOPMENT/QA) chain ids correctly, that a substituted non-`AC`-shaped origin id moves through every downstream artifact (rename-follows), and that extraction is bounded/defensive and role-value-independent
- Gave the zero-config integration gate (`tests/integration/test_real_pipeline_zero_config.py`) content assertions comparing every downstream artifact's ids against BA's own emitted ids (never a hardcoded expectation), closing the existence-only gap that let G-04-1 ship uncaught
- Reconciled `04-VALIDATION.md`'s Per-Task/Requirement Verification Map and Manual-Only row, and `tests/integration/test_phase4_acceptance.py`'s proof tuples and `_VALIDATION_PROOF_FILES` drift guard, with the two new proof files

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread context.inputs into FakeWorker artifact synthesis so every output carries the upstream criterion ids** (TDD) - `7e2b69a` (test, RED) → `cac5b2c` (feat, GREEN)
2. **Task 2: Give the zero-config integration gate content assertions so a broken handoff cannot ship green again** - `48cc03d` (test)
3. **Task 3: Reconcile the phase validation ledger and acceptance-gate proof map with the new proofs** - `9a6dfc0` (docs)

**Plan metadata:** (this commit)

## Files Created/Modified
- `src/dark_factory/workers/fake.py` - Adds origin-id constant, carrier-line regex, id cap, and a role-agnostic `context.inputs` extraction helper threaded through `_default_script`/`_synthesize_artifact_content`/`_synthesize_machine_artifact`
- `tests/unit/test_fake_worker_synthesis.py` - New: derivation, falsification (rename-follows), bounded/defensive, and role-independence proofs driven through the public `FakeWorker().execute(context)` entry point
- `tests/integration/test_real_pipeline_zero_config.py` - Adds content assertions comparing ARCHITECTURE/DEVELOPMENT/QA artifact content against BA's own emitted criterion ids, resolved through `ArtifactReference` rows
- `tests/integration/test_phase4_acceptance.py` - Registers both new proof files against SC1/ORCH-04/ROLE-04/ART-02 in the proof tuples and `_VALIDATION_PROOF_FILES`
- `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md` - Adds a `04-05 T1-T2` verification map row and updates the Manual-Only row to record that id-alignment is now machine-asserted, leaving fresh-eyes readability as the sole remaining manual re-check

## Decisions Made
- Kept the entire fix inside `src/dark_factory/workers/fake.py` — no change to `domain/artifacts.py`, `context/builder.py`, role YAMLs, or `.dark-factory.yaml`, per the plan's explicit scope boundary
- Did not add a field to `ImplementationSummary`; the existing `summary` string carries the ids, keeping D-10's published model shapes unchanged
- Left task/spec-aware content generation out of scope entirely (Phase 7's concern per D-07) — only criterion-id plumbing was touched

## Deviations from Plan

None - plan executed exactly as written.

The two DB-gated `<verify>` commands (Task 2's `tests/integration/test_real_pipeline_zero_config.py` run and Task 3's `tests/integration/test_phase4_acceptance.py` run) were executed by the project owner in their own terminal against their `.env`-configured Postgres, rather than by the executor directly — the harness sandbox blocks reading `.env` via a secret-read guard. This is not a Rule 1-4 deviation: no code or behavior differs from what the plan specified. It is only a note on how verification was carried out. Task 3's run produced a genuine, user-confirmed PASS: `24 passed in 4.12s`.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The FakeWorker criterion-id data path, its unit derivation/falsification proof, and the content-asserting integration/acceptance gates are all in place and green
- Phase 4's five success criteria and fifteen requirement IDs all have passing automated verification; the sole remaining manual item (fresh-eyes readability of the on-disk artifact layout) is explicitly deferred to `/gsd-verify-work`
- No blockers for subsequent phases; task/spec-aware artifact content generation remains correctly scoped to Phase 7

---
*Phase: 04-the-four-role-pipeline-artifact-handoffs*
*Completed: 2026-09-13*

## Self-Check: PASSED

All 5 files created/modified (src/dark_factory/workers/fake.py, tests/unit/test_fake_worker_synthesis.py, tests/integration/test_real_pipeline_zero_config.py, tests/integration/test_phase4_acceptance.py, .planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md) confirmed present on disk. All 4 commits (7e2b69a, cac5b2c, 48cc03d, 9a6dfc0) confirmed present in git log.
