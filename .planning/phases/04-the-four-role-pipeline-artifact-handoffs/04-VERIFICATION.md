---
phase: 04-the-four-role-pipeline-artifact-handoffs
verified: 2026-09-13T00:00:00Z
status: human_needed
score: 20/20 must-haves verified
covered_files: [".dark-factory.yaml", ".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW-FIX.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-SECURITY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md", "migrations/env.py", "migrations/versions/0004_artifacts.py", "src/dark_factory/actions/builtins.py", "src/dark_factory/artifacts/__init__.py", "src/dark_factory/artifacts/paths.py", "src/dark_factory/artifacts/store.py", "src/dark_factory/artifacts/validation.py", "src/dark_factory/config/loader.py", "src/dark_factory/context/__init__.py", "src/dark_factory/context/builder.py", "src/dark_factory/domain/artifacts.py", "src/dark_factory/domain/status.py", "src/dark_factory/input/loaders.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/persistence/models.py", "src/dark_factory/persistence/mutations.py", "src/dark_factory/roles/registry.py", "src/dark_factory/workers/fake.py", "tests/conftest.py", "tests/db/test_artifact_handoff.py", "tests/db/test_artifact_persistence.py", "tests/db/test_artifact_schema_violation_fails_role.py", "tests/db/test_context_builder_retry_isolation.py", "tests/db/test_four_role_pipeline.py", "tests/integration/test_phase4_acceptance.py", "tests/integration/test_real_pipeline_zero_config.py", "tests/integration/test_spec_source_starts_a_run.py", "tests/support/fake_artifacts.py", "tests/unit/test_artifact_models.py", "tests/unit/test_artifact_paths.py", "tests/unit/test_context_builder.py", "tests/unit/test_loaders.py", "tests/unit/test_no_tree_walk.py"]
covered_digest: "v1:sha256:bdded9fb3d1647e3c59526841fd364ebb6605f9929ac6e0d1490c9501263dd98"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (requirements.md, acceptance_criteria.json, design.md, constraints.json, implementation_summary.json, test_report.json, verdict.json)."
    expected: "A person who has never seen this codebase can follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids (AC-1, etc.) line up across the files."
    why_human: "The automated gate proves the files exist, validate against their schemas, and are correctly attributed to ArtifactReference rows in Neon -- it does not judge whether the on-disk layout and prose read well to a person seeing it for the first time. This item was explicitly deferred from 04-04-PLAN.md's own <human-check> block to this verification pass."
---

# Phase 4: The Four-Role Pipeline & Artifact Handoffs Verification Report

**Phase Goal:** BA → Architect → Developer → QA hand off through durable artifacts (a file on disk plus an `ArtifactReference` row in Neon), so the pipeline is a sequence of independent role executions rather than one shared agent conversation.
**Verified:** 2026-09-13
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | A run started from `spec:./task.md` executes all four roles in order on `FakeWorker` and produces `requirements.md` + `acceptance_criteria.json`, `design.md` + `constraints.json`, `implementation_summary.json`, and `test_report.json` + `verdict.json` under `.dark-factory/runs/<run-id>/`. | ✓ VERIFIED | `tests/db/test_four_role_pipeline.py` (real Neon, re-run by this verifier: 1 passed) and `tests/integration/test_spec_source_starts_a_run.py` (re-run: 2 passed) both green. Independently confirmed by driving `python -m dark_factory run "text:add a health endpoint"` against this repo's real `.dark-factory.yaml` three times outside pytest: each run printed `CREATED → BA → ARCHITECTURE → DEVELOPMENT → QA → COMPLETED`. |
| SC2 | Every artifact has an `ArtifactReference` row in Neon while its content stays on the filesystem — no artifact body is stored in the database. | ✓ VERIFIED | `tests/db/test_artifact_persistence.py` (re-run: 3 passed against real Neon) asserts the 7-row count, checksum round-trip, empty `metadata`, and a body-text sweep across `runs`/`role_executions`/`run_events`/`artifacts`. |
| SC3 | A role's context contains only the prior artifacts its configuration selects, plus repository document paths and any human answers — never a dump of the repository source tree. | ✓ VERIFIED | `tests/unit/test_context_builder.py` (8 tests) and `tests/unit/test_no_tree_walk.py` (4 tests, AST guard with a self-sanity check) both pass in the 287-test unit run this verifier executed. `context/builder.py` reads only named paths (`_resolve_input`, `_read_baseline_docs`, `_read_examples`) — confirmed by direct reading of the source. |
| SC4 | A retried attempt's rebuilt context contains no artifact from the superseded attempt. | ✓ VERIFIED | `tests/db/test_context_builder_retry_isolation.py` (5 tests, re-run against real Neon: all pass) proves content-based (not row-identity) resolution to the higher-numbered `COMPLETED` attempt, survival of the superseded row for audit, and a named `MissingArtifactContentError` for an in-flight-only attempt. `context/builder.py::_latest_completed_execution` filters `status == "COMPLETED"` and orders `attempt DESC LIMIT 1`, which is deterministic within one role because `uq_role_exec_attempt` makes `attempt` a total order per role. |
| SC5 | A machine artifact that violates its JSON schema fails the role with a persisted error instead of advancing the run, and the transition after QA is decided by `verdict.json`, never by summary prose. | ✓ VERIFIED | `tests/db/test_artifact_schema_violation_fails_role.py` (8 tests, re-run against real Neon: all pass), including the two prose-vs-JSON contradiction scenarios. `domain/artifacts.py::Verdict` has two after-validators (duplicate `criterion_id`, declared-vs-computed status disagreement) confirmed by direct reading. |

**Score:** 5/5 ROADMAP success criteria verified, 0 present-but-behavior-unverified.

### Requirements Coverage (15 IDs)

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| INTAKE-02 | Operator can start a run from a spec file | ✓ SATISFIED | `_load_spec` real loader (`src/dark_factory/input/loaders.py`); `tests/unit/test_loaders.py` (7 spec tests, part of the 287-pass unit run) + `tests/integration/test_spec_source_starts_a_run.py` (2 passed, re-run) |
| ORCH-04 | Roles communicate through durable artifacts, never shared conversation | ✓ SATISFIED | `RoleContext` (context/builder.py) carries no `WorkerResult` field; `tests/db/test_artifact_handoff.py` (re-run: 2 passed) + `tests/db/test_four_role_pipeline.py` |
| ROLE-01 | BA emits `requirements.md` + `acceptance_criteria.json`, read-only on source | ✓ SATISFIED | `.dark-factory/roles/BA.yaml` outputs; `tests/db/test_four_role_pipeline.py`, `tests/unit/test_artifact_models.py` (19 tests) |
| ROLE-02 | Architect consumes task+BA output+repo, emits `design.md` + `constraints.json` | ✓ SATISFIED | `.dark-factory/roles/ARCHITECTURE.yaml` `inputs: [acceptance_criteria.json]`, `outputs: [design.md, constraints.json]`; proven in `test_four_role_pipeline.py` |
| ROLE-03 | Developer implements, emits `implementation_summary.json` | ✓ SATISFIED | `.dark-factory/roles/DEVELOPMENT.yaml`; `ImplementationSummary` model; proven in `test_four_role_pipeline.py`. Write-scope enforcement explicitly deferred to Phase 5/6 (documented, not silently missing) |
| ROLE-04 | QA verifies each criterion, emits `test_report.json` + `verdict.json` | ✓ SATISFIED | `.dark-factory/roles/QA.yaml` `inputs: [acceptance_criteria.json, implementation_summary.json]` (resolved by declared filename, not pipeline adjacency — confirmed) |
| ROLE-06 | QA verdict (not prose) drives the next orchestrator decision | ✓ SATISFIED | `Verdict` after-validators; `tests/db/test_artifact_schema_violation_fails_role.py`'s prose-contradiction tests, re-run and passing |
| CTX-01 | `ContextBuilder` produces role-specific `RoleContext` | ✓ SATISFIED | `context/builder.py::RoleContext`/`build_role_context`; `tests/unit/test_context_builder.py` |
| CTX-02 | Context prep doesn't copy the whole repo into the prompt | ✓ SATISFIED | `tests/unit/test_no_tree_walk.py` — AST guard over `dark_factory.context` and `dark_factory.artifacts`, with a self-sanity test proving the walk actually trips |
| CTX-03 | Few-shot examples are context only, never application logic | ✓ SATISFIED | `_read_examples` reads inert text; enforced by the same no-`exec`/`eval`/`import_module` AST guard |
| CTX-04 | Retry doesn't leak stale artifacts from a superseded attempt | ✓ SATISFIED | `tests/db/test_context_builder_retry_isolation.py`, re-run against real Neon |
| ART-01 | Run artifacts stored under `.dark-factory/runs/<run-id>/` (`input/`, `artifacts/<role>/`, `verification/`, `logs/`) | ✓ SATISFIED | `artifacts/paths.py::ensure_run_tree`; `tests/unit/test_artifact_paths.py` (11 tests) |
| ART-02 | JSON is authoritative where orchestration depends on a result; Markdown is human documentation | ✓ SATISFIED | `MACHINE_ARTIFACT_MODELS` excludes `requirements.md`/`design.md`; `tests/db/test_artifact_schema_violation_fails_role.py`'s Markdown-completes-unvalidated case |
| ART-03 | Each artifact recorded in Neon as `ArtifactReference`; filesystem holds content | ✓ SATISFIED | `ArtifactReference` ORM class; `tests/db/test_artifact_persistence.py`'s body-text sweep |
| STATE-05 | An `artifacts` table persists artifact metadata | ✓ SATISFIED | `migrations/versions/0004_artifacts.py`; `alembic check` re-run by this verifier: "No new upgrade operations detected." |

**All 15 requirement IDs: SATISFIED.** `.planning/REQUIREMENTS.md` marks all 15 `[x]` Complete, mapped to Phase 4, consistent with the codebase evidence above. No orphaned requirements found (the phase's declared set in all four plans' frontmatter exactly matches REQUIREMENTS.md's Phase 4 mapping).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/versions/0004_artifacts.py` | `artifacts` table DDL + downgrade | ✓ VERIFIED | Present, `down_revision="0003_pause_resume_lease"`, `uq_artifact_role_execution_path` present |
| `migrations/env.py` `_OWNED_TABLES` | includes `"artifacts"` | ✓ VERIFIED | Confirmed via grep and a passing `alembic check` (re-run) |
| `src/dark_factory/domain/artifacts.py` | 5 D-10 machine-artifact models | ✓ VERIFIED | `AcceptanceCriteriaDocument`, `ConstraintsDocument`, `ImplementationSummary`, `TestReport`, `Verdict` all present, frozen/extra-forbid |
| `src/dark_factory/context/builder.py` | `RoleContext` + `build_role_context` | ✓ VERIFIED | Present; `RoleContext.outputs` field confirmed present (CR-01 fix) |
| `src/dark_factory/artifacts/{paths,store,validation}.py` | path safety, capped read, schema dispatch | ✓ VERIFIED | Present; `collect_role_artifacts` dispatches by filename via `MACHINE_ARTIFACT_MODELS` |
| `.dark-factory/roles/{BA,ARCHITECTURE,DEVELOPMENT,QA}.yaml` | four-role pipeline config | ✓ VERIFIED | All four present, `inputs`/`outputs` chain confirmed; `before: []` / `after: []` (or `[collect_test_results]` for QA) confirmed post-WR-01-fix |
| `src/dark_factory/roles/registry.py` | role catalog | ✓ VERIFIED | Post-WR-02-fix: only `ba_role` remains (the one entry with a real consumer); `architect_role`/`developer_role`/`qa_role` confirmed absent |
| `src/dark_factory/workers/fake.py` | `FakeWorker` | ✓ VERIFIED | Post-CR-01-fix: `_default_script(context)` is artifact-aware, confirmed by direct reading and by three independent manual CLI runs all reaching `COMPLETED` in correct role order |
| `tests/db/test_four_role_pipeline.py`, `test_artifact_persistence.py`, `test_context_builder_retry_isolation.py`, `test_artifact_schema_violation_fails_role.py` | SC1/SC2/SC4/SC5 db proofs | ✓ VERIFIED | All present, substantive (1/3/5/8 tests respectively), zero skips, and re-run green against real Neon by this verifier |
| `tests/integration/test_phase4_acceptance.py` | acceptance gate | ✓ VERIFIED | 6 test functions / 24 collected cases (parametrized), maps all 5 SCs + 15 requirement IDs, zero opt-out calls, drift-guarded against `04-VALIDATION.md`; re-run green (24 passed) |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `orchestrator/runner.py` | `context/builder.py` | `_run_current_role` calls `build_role_context` | ✓ WIRED (confirmed by reading `runner.py` and by all db tests exercising the real path) |
| `orchestrator/runner.py` | `artifacts/validation.py` | `collect_role_artifacts` runs after a `COMPLETED` result, can force `Signal.ROLE_FAILED` | ✓ WIRED (`test_artifact_schema_violation_fails_role.py` exercises this directly) |
| `.dark-factory/roles/QA.yaml` | `.dark-factory/roles/BA.yaml` | QA declares `acceptance_criteria.json` in `inputs`; BA declares it in `outputs`; resolved via snapshot, not adjacency | ✓ WIRED (`test_four_role_pipeline.py` asserts QA's captured `RoleContext.inputs` contains exactly `acceptance_criteria.json` + `implementation_summary.json`, produced by roles two and one steps earlier respectively) |
| `artifacts/validation.py` | `domain/artifacts.py` | `MACHINE_ARTIFACT_MODELS` dispatch table | ✓ WIRED (read directly; all 5 filenames present) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/integration/test_real_pipeline_zero_config.py` | 85 | `.order_by(RoleExecution.attempt)` across **multiple roles in one run**, with no tiebreaker, while every role's first attempt is `attempt == 1` | ⚠️ WARNING | **Reproduced live against real Neon by this verifier**: re-ran this exact test 4 times — it failed 3 of 4 times with `AssertionError: completed_roles != ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]` (rows returned in a non-insertion order because the `ORDER BY` has no way to break the tie among four rows that all have `attempt == 1`). This is the regression test the 04-REVIEW-FIX (`8d670ee`, CR-01) added to prove the shipped `.dark-factory.yaml` completes with no explicit script — its own REVIEW-FIX.md claims a "Follow-up verification... passes," which is true only intermittently. **The underlying production behavior is not broken**: three independent manual `python -m dark_factory run "text:..."` invocations against this repo's real config (bypassing pytest entirely) all printed the correct `CREATED → BA → ARCHITECTURE → DEVELOPMENT → QA → COMPLETED` sequence, and `tests/db/test_four_role_pipeline.py` (which orders by `RoleExecution.created_at`, a monotonic column) passes reliably. The defect is confined to this one test file's query, not to any production code path or to any of the 15 officially-mapped requirement proofs (this file is not in `test_phase4_acceptance.py`'s `SUCCESS_CRITERIA`/`REQUIREMENTS` mapping or in `04-VALIDATION.md`'s proof list). **Recommended fix:** add a deterministic secondary sort key, e.g. `.order_by(RoleExecution.attempt, RoleExecution.role)` or `.order_by(RoleExecution.created_at)` (matching the pattern `test_four_role_pipeline.py` already uses). |

No other anti-patterns (TBD/FIXME/XXX, disabled tests, circular test fixtures, hollow props, or hardcoded stub returns) were found across the files this phase touched. `grep -rn "TBD\|FIXME\|XXX"` across all `covered_files` returned no unresolved debt markers.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit suite green | `uv run pytest -m unit -q` | `287 passed` | ✓ PASS |
| Static types clean | `uv run mypy src/dark_factory` | `Success: no issues found in 52 source files` | ✓ PASS |
| Lint clean | `uv run ruff check .` | `All checks passed!` | ✓ PASS |
| Schema drift | `uv run alembic check` | `No new upgrade operations detected.` | ✓ PASS |
| BA→ARCHITECTURE handoff (db) | `pytest tests/db/test_artifact_handoff.py` | `2 passed` (real Neon) | ✓ PASS |
| Retry isolation (db) | `pytest tests/db/test_context_builder_retry_isolation.py` | `6 passed`* | ✓ PASS |
| Schema-violation / verdict-not-prose (db) | `pytest tests/db/test_artifact_schema_violation_fails_role.py` | `8 passed` (real Neon) | ✓ PASS |
| Four-role pipeline (db) | `pytest tests/db/test_four_role_pipeline.py` | `1 passed` (real Neon) | ✓ PASS |
| Artifact persistence / body-text sweep (db) | `pytest tests/db/test_artifact_persistence.py` | `3 passed` (real Neon) | ✓ PASS |
| spec: loader end-to-end (integration) | `pytest tests/integration/test_spec_source_starts_a_run.py` | `2 passed` (real Neon) | ✓ PASS |
| Acceptance gate (integration) | `pytest tests/integration/test_phase4_acceptance.py` | `24 passed` | ✓ PASS |
| CR-01 zero-config regression test | `pytest tests/integration/test_real_pipeline_zero_config.py` (4 repeat runs) | `1 passed, 3 failed` (flaky — see Anti-Patterns) | ⚠️ FLAKY |
| Manual zero-config CLI proof (bypassing pytest) | `python -m dark_factory run "text:add a health endpoint"` ×3 | All 3: `CREATED → BA → ARCHITECTURE → DEVELOPMENT → QA → COMPLETED` | ✓ PASS |

*combined with tests/db/test_artifact_handoff.py in one run (8 total).

### Requirements Coverage Gate / Decision Coverage

No `04-CONTEXT.md` `<decisions>` trackable-entry scan was run as a separate gate step beyond the requirements/artifact/key-link checks above, since every decision this phase's plans record (D-01 through D-10) is directly traceable to a shipped artifact or test already itemized above (e.g. D-01 filename-based input resolution → `ARCHITECTURE.yaml`/`QA.yaml` `inputs`; D-04 verdict fold → `Verdict.computed_status`; D-09 schema-failure gate → `collect_role_artifacts` wiring).

## Human Verification Required

### 1. Fresh-eyes readability of a real run's artifact tree

**Test:** Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (`requirements.md`, `acceptance_criteria.json`, `design.md`, `constraints.json`, `implementation_summary.json`, `test_report.json`, `verdict.json`).
**Expected:** A person who has never seen this codebase can follow the handoff from `acceptance_criteria.json` through `design.md` to `verdict.json` and see which criterion ids line up across files.
**Why human:** The automated gate (and this verifier's re-runs) prove the files exist, validate against schema, and are correctly attributed to `ArtifactReference` rows in Neon — none of that establishes whether the on-disk layout and (FakeWorker-synthesized, currently placeholder-quality) prose reads well to a human. This item was explicitly deferred to this verification pass by `04-04-PLAN.md`'s own `<human-check>` block, not invented by this verifier.

## Gaps Summary

No must-have truth, artifact, or key link failed. All 5 ROADMAP success criteria and all 15 requirement IDs have real, re-executed, passing evidence against production Neon — not just SUMMARY.md claims. The three code-review fix commits (`8d670ee` CR-01, `c34ee77` WR-01, `b42d6c8` WR-02) are present on this branch and their claimed effects were independently confirmed by reading the current source (not the historical diff) and by re-running the affected tests.

One reproducible defect was found and is documented above under Anti-Patterns: `tests/integration/test_real_pipeline_zero_config.py` is flaky (order-dependent assertion failing ~75% of the time in this verifier's re-runs) due to an unstable `ORDER BY` with ties. This does not indicate a broken production capability — three independent manual CLI invocations confirm the zero-config four-role pipeline completes correctly and in order every time — and the flaky file is not part of any of the 15 officially-mapped requirement proofs or the 5 success-criterion proofs. It is flagged as a WARNING requiring a follow-up fix (add a deterministic secondary sort key), not a phase-blocking gap.

Overall status is `human_needed` solely because of the one pre-existing, explicitly-deferred manual UAT item above — not because of any failed or uncertain automated check.

## Post-Verification Follow-Up (2026-09-13)

The flaky `test_real_pipeline_zero_config.py` ordering defect flagged above under Anti-Patterns / Behavioral Spot-Checks was fixed immediately after this verification: `.order_by(RoleExecution.attempt)` → `.order_by(RoleExecution.created_at)`, matching `test_four_role_pipeline.py`'s existing pattern (commit `ca602b3`). Re-run 5/5 consecutive times against real Neon — all passed (no failures, versus the prior 1/4 pass rate). `uv run pytest -m unit -q` (287 passed) and `uv run mypy src/dark_factory --strict` (clean) re-confirmed as a regression sanity check. This closes the one WARNING-level anti-pattern this report found; the phase's automated-check status is now fully clean with zero open findings at any severity.

---

_Verified: 2026-09-13_
_Verifier: Claude (gsd-verifier)_
