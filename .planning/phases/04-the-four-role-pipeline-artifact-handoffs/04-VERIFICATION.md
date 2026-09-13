---
phase: 04-the-four-role-pipeline-artifact-handoffs
verified: 2026-09-13T12:00:00Z
status: human_needed
score: 20/20 must-haves verified
covered_files: [".dark-factory.yaml", ".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-01-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-02-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-03-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-PLAN.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-04-SUMMARY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW-FIX.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-REVIEW.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-SECURITY.md", ".planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-VALIDATION.md", "migrations/env.py", "migrations/versions/0004_artifacts.py", "src/dark_factory/actions/builtins.py", "src/dark_factory/artifacts/__init__.py", "src/dark_factory/artifacts/paths.py", "src/dark_factory/artifacts/store.py", "src/dark_factory/artifacts/validation.py", "src/dark_factory/config/loader.py", "src/dark_factory/context/__init__.py", "src/dark_factory/context/builder.py", "src/dark_factory/domain/artifacts.py", "src/dark_factory/domain/status.py", "src/dark_factory/input/loaders.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/persistence/models.py", "src/dark_factory/persistence/mutations.py", "src/dark_factory/roles/registry.py", "src/dark_factory/workers/fake.py", "tests/conftest.py", "tests/db/test_artifact_handoff.py", "tests/db/test_artifact_persistence.py", "tests/db/test_artifact_schema_violation_fails_role.py", "tests/db/test_context_builder_retry_isolation.py", "tests/db/test_four_role_pipeline.py", "tests/integration/test_phase4_acceptance.py", "tests/integration/test_real_pipeline_zero_config.py", "tests/integration/test_spec_source_starts_a_run.py", "tests/support/fake_artifacts.py", "tests/unit/test_artifact_models.py", "tests/unit/test_artifact_paths.py", "tests/unit/test_context_builder.py", "tests/unit/test_loaders.py", "tests/unit/test_no_tree_walk.py"]
covered_digest: "v1:sha256:14a91f7288b83f13a9d75a1559dec70a2cf1868d144c12c546c1150fbce82896"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 20/20
  gaps_closed:
    - "tests/integration/test_real_pipeline_zero_config.py's unstable RoleExecution ordering (WARNING-level anti-pattern, not a blocking gap) — fixed by switching the tiebreaker from `.order_by(RoleExecution.attempt)` to `.order_by(RoleExecution.created_at)`, matching the pattern already proven reliable in tests/db/test_four_role_pipeline.py"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (requirements.md, acceptance_criteria.json, design.md, constraints.json, implementation_summary.json, test_report.json, verdict.json)."
    expected: "A person who has never seen this codebase can follow the handoff from acceptance_criteria.json through design.md to verdict.json and see which criterion ids (AC-1, etc.) line up across the files."
    why_human: "The automated gate proves the files exist, validate against their schemas, and are correctly attributed to ArtifactReference rows in Neon -- it does not judge whether the on-disk layout and prose read well to a person seeing it for the first time. This item was explicitly deferred from 04-04-PLAN.md's own <human-check> block to this verification pass."
---

# Phase 4: The Four-Role Pipeline & Artifact Handoffs Verification Report

**Phase Goal:** BA → Architect → Developer → QA hand off through durable artifacts (a file on disk plus an `ArtifactReference` row in Neon), so the pipeline is a sequence of independent role executions rather than one shared agent conversation.
**Verified:** 2026-09-13 (re-verification / digest refresh)
**Status:** human_needed
**Re-verification:** Yes — confirmation re-run after the one open WARNING (flaky `test_real_pipeline_zero_config.py` ordering) was fixed. This pass does not re-derive must-haves from scratch; it (a) confirms nothing besides the fix commit changed since the prior full pass, (b) verifies the fix itself, and (c) refreshes the stale `covered_digest`.

## What changed since the prior pass

`gsd_run query verification.status` reported `"stale"` at the start of this pass because the prior `covered_digest` (`v1:sha256:bdded9fb...`) was computed before commit `ca602b3` landed, while the prior VERIFICATION.md's own "Post-Verification Follow-Up" addendum already narrated that fix as done. `git log 919bace..HEAD` returns nothing — `HEAD` **is** `919bace` (the prior verification commit), and its immediate parent is `ca602b3` (`fix(04): deterministic ordering in test_real_pipeline_zero_config.py to eliminate flakiness`). No other commit landed between the prior full pass and this one. That means:

- All 5 ROADMAP success criteria, all 15 requirement IDs, all required artifacts, and all key links verified in the prior pass rest on evidence that still applies unchanged — the source tree they were checked against is identical (confirmed by `git log` showing zero drift beyond the one fix commit, which only touches the file already itemized below).
- The only thing that needed re-checking on its merits is the fix itself, folded into the body below (no longer a separate addendum).

### Fix verification

`git show ca602b3` confirms a single-line, single-file diff:

```diff
- .order_by(RoleExecution.attempt)
+ .order_by(RoleExecution.created_at)
```

in `tests/integration/test_real_pipeline_zero_config.py`. Read directly from the current source (`tests/integration/test_real_pipeline_zero_config.py:85`), the file now reads `.order_by(RoleExecution.created_at)`, exactly matching the pattern already used successfully by `tests/db/test_four_role_pipeline.py:206` (`grep -n "order_by(RoleExecution" tests/db/test_four_role_pipeline.py tests/integration/test_real_pipeline_zero_config.py` — both now identical). This is not a novel, unproven ordering strategy: it is the same key the codebase already relies on elsewhere and that the prior verification found "passes reliably."

**Why the fix is structurally sound (not just a re-run count):** `src/dark_factory/persistence/models.py`'s own documentation of `role_executions.created_at` explains the previous bug's mechanism precisely — the old key (`attempt`) has **no possible tiebreaker** because every role's first attempt shares `attempt == 1` by design, so a 4-way tie was a certainty, not a rare race. `created_at` is different in kind: each role's `RoleExecution` row is written inside its own `with session.begin():` transaction (`src/dark_factory/persistence/mutations.py::apply_transition`/`_write_role_execution`), one per sequential orchestrator step, each using `server_default=sa.func.now()`. Because the four role steps run one after another in a single Python process (not concurrently) with real work between them, their transaction-start timestamps are overwhelmingly likely to differ — this is a probabilistic improvement over a mathematically guaranteed tie, and it is the exact same reasoning that already makes `test_four_role_pipeline.py` reliable.

**Regression re-check performed by this verifier (current HEAD):**

| Check | Command | Result |
|-------|---------|--------|
| Unit suite | `uv run pytest -m unit -q` | `287 passed` (identical count to the prior pass) |
| Static types | `uv run mypy src/dark_factory` | `Success: no issues found in 52 source files` |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Fixed test collects correctly | `uv run pytest tests/integration/test_real_pipeline_zero_config.py --collect-only -q` | `1 test collected` |
| Source diff matches commit message | `git show ca602b3 -- tests/integration/test_real_pipeline_zero_config.py` | 1 file changed, 1 insertion(+), 1 deletion(-), exactly as described |

**Limitation disclosed, not glossed over:** this verifier could **not** independently re-execute `tests/integration/test_real_pipeline_zero_config.py` against real Neon in this sandboxed session. The test's provisioning ladder (`tests/conftest.py`) needs Docker, a local PostgreSQL 17 `initdb`, or `DARK_FACTORY_TEST_DATABASE_URL` (sourced from the git-ignored `.env`); this session has no Docker daemon, no local `initdb`, and this session's file-access guard blocks any command that reads `.env` (a deliberate secret-protection control this verifier did not attempt to route around). Attempting the test directly failed at the provisioning step with `pytest.UsageError: No PostgreSQL 17 is reachable`, not a test failure. This is an environment constraint of this verification session, not evidence against the fix. The claimed 5/5 real-Neon re-run (by a separate executor agent with DB access, per the dispatch) is therefore accepted on the strength of: the code-diff match confirmed above, the proven-reliable identical ordering pattern already used elsewhere in this codebase, the structural reasoning above for why the new key is not merely "less likely to tie" but categorically different from the old guaranteed-tie key, and the unrelated regression suite (287 unit tests, mypy, ruff) staying green. It is not independently re-confirmed against Neon by this verifier, and that gap is recorded here rather than silently absorbed into a clean PASS.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | A run started from `spec:./task.md` executes all four roles in order on `FakeWorker` and produces `requirements.md` + `acceptance_criteria.json`, `design.md` + `constraints.json`, `implementation_summary.json`, and `test_report.json` + `verdict.json` under `.dark-factory/runs/<run-id>/`. | ✓ VERIFIED | Unchanged from prior pass — `tests/db/test_four_role_pipeline.py` and `tests/integration/test_spec_source_starts_a_run.py` re-run green against real Neon by the prior verifier; source tree identical (confirmed via `git log` showing no drift). |
| SC2 | Every artifact has an `ArtifactReference` row in Neon while its content stays on the filesystem — no artifact body is stored in the database. | ✓ VERIFIED | Unchanged — `tests/db/test_artifact_persistence.py` (3 passed against real Neon in prior pass); source unchanged. |
| SC3 | A role's context contains only the prior artifacts its configuration selects, plus repository document paths and any human answers — never a dump of the repository source tree. | ✓ VERIFIED | `tests/unit/test_context_builder.py` and `tests/unit/test_no_tree_walk.py` re-run by this verifier as part of the 287-test unit suite — all pass. `context/builder.py` unchanged. |
| SC4 | A retried attempt's rebuilt context contains no artifact from the superseded attempt. | ✓ VERIFIED | Unchanged — `tests/db/test_context_builder_retry_isolation.py` (5 tests, real Neon, prior pass); `context/builder.py` unchanged (confirmed via `git log`/file content). |
| SC5 | A machine artifact that violates its JSON schema fails the role with a persisted error instead of advancing the run, and the transition after QA is decided by `verdict.json`, never by summary prose. | ✓ VERIFIED | Unchanged — `tests/db/test_artifact_schema_violation_fails_role.py` (8 tests, real Neon, prior pass); `domain/artifacts.py::Verdict` unchanged. |

**Score:** 5/5 ROADMAP success criteria verified, 0 present-but-behavior-unverified.

### Requirements Coverage (15 IDs)

All 15 requirement IDs (INTAKE-02, ORCH-04, ROLE-01, ROLE-02, ROLE-03, ROLE-04, ROLE-06, CTX-01, CTX-02, CTX-03, CTX-04, ART-01, ART-02, ART-03, STATE-05) remain **✓ SATISFIED**, unchanged from the prior pass's evidence table — the implementation files backing each requirement (`context/builder.py`, `domain/artifacts.py`, `.dark-factory/roles/*.yaml`, `persistence/models.py`, `migrations/versions/0004_artifacts.py`, etc.) are byte-identical to the prior pass (confirmed: `git log 919bace..HEAD` is empty, i.e. current `HEAD` is the exact commit the prior verification covered). `.planning/REQUIREMENTS.md` still marks all 15 `[x]` Complete, mapped to Phase 4. No orphaned requirements.

### Required Artifacts

All artifacts verified in the prior pass (`migrations/versions/0004_artifacts.py`, `src/dark_factory/domain/artifacts.py`, `src/dark_factory/context/builder.py`, `src/dark_factory/artifacts/{paths,store,validation}.py`, `.dark-factory/roles/{BA,ARCHITECTURE,DEVELOPMENT,QA}.yaml`, `src/dark_factory/roles/registry.py`, `src/dark_factory/workers/fake.py`, the four `db`-tier proof test files, and `tests/integration/test_phase4_acceptance.py`) remain ✓ VERIFIED — unchanged file content, re-confirmed by the `git log` no-drift check above plus this pass's own regression re-run of the unit suite, mypy, and ruff.

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `orchestrator/runner.py` | `context/builder.py` | `_run_current_role` calls `build_role_context` | ✓ WIRED (unchanged) |
| `orchestrator/runner.py` | `artifacts/validation.py` | `collect_role_artifacts` runs after a `COMPLETED` result, can force `Signal.ROLE_FAILED` | ✓ WIRED (unchanged) |
| `.dark-factory/roles/QA.yaml` | `.dark-factory/roles/BA.yaml` | QA declares `acceptance_criteria.json` in `inputs`; BA declares it in `outputs`; resolved via snapshot, not adjacency | ✓ WIRED (unchanged) |
| `artifacts/validation.py` | `domain/artifacts.py` | `MACHINE_ARTIFACT_MODELS` dispatch table | ✓ WIRED (unchanged) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Status |
|------|------|---------|----------|--------|
| `tests/integration/test_real_pipeline_zero_config.py` | 85 (was) | `.order_by(RoleExecution.attempt)` with no tiebreaker across a guaranteed 4-way tie | ~~⚠️ WARNING~~ | **RESOLVED** (commit `ca602b3`) — now `.order_by(RoleExecution.created_at)`, confirmed by direct read of current source and by diffing the fix commit. See "Fix verification" above for the full analysis. |

No other anti-patterns (TBD/FIXME/XXX, disabled tests, circular test fixtures, hollow props, or hardcoded stub returns) were found across `covered_files`. `grep -rn "TBD\|FIXME\|XXX"` across all `covered_files` returns no unresolved debt markers. **Zero open anti-pattern findings at any severity as of this pass.**

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit suite green | `uv run pytest -m unit -q` | `287 passed` (re-run by this verifier, matches prior count) | ✓ PASS |
| Static types clean | `uv run mypy src/dark_factory` | `Success: no issues found in 52 source files` (re-run) | ✓ PASS |
| Lint clean | `uv run ruff check .` | `All checks passed!` (re-run) | ✓ PASS |
| Fix commit present & matches description | `git show ca602b3 --stat` / `git show ca602b3 -- tests/integration/test_real_pipeline_zero_config.py` | 1 file, 1 insertion/1 deletion, `.order_by(RoleExecution.attempt)` → `.order_by(RoleExecution.created_at)` | ✓ PASS |
| Fixed test collects (no execution) | `uv run pytest tests/integration/test_real_pipeline_zero_config.py --collect-only -q` | `1 test collected` | ✓ PASS |
| Fixed test executes against real Neon (this verifier, this session) | `uv run pytest tests/integration/test_real_pipeline_zero_config.py -q` | `pytest.UsageError: No PostgreSQL 17 is reachable` (provisioning ladder exhausted — no Docker, no local `initdb`, `.env`-sourced `DARK_FACTORY_TEST_DATABASE_URL` inaccessible under this session's secret-file read guard) | ? SKIP — environment limitation, not a test failure; see "Fix verification" limitation note above |
| Ordering pattern now matches the codebase's own proven-reliable convention | `grep -n "order_by(RoleExecution" tests/db/test_four_role_pipeline.py tests/integration/test_real_pipeline_zero_config.py` | Both use `.order_by(RoleExecution.created_at)` | ✓ PASS |
| No drift since prior full pass | `git log 919bace..HEAD` | empty (HEAD == 919bace) | ✓ PASS |

All db-tier and integration-tier evidence not listed above (four-role pipeline, artifact persistence, retry isolation, schema-violation, spec-loader, acceptance gate) is carried forward unchanged from the prior pass per the no-drift confirmation, since the underlying source has not moved.

### Requirements Coverage Gate / Decision Coverage

Unchanged from the prior pass — every `04-CONTEXT.md` decision (D-01 through D-10) remains traceable to a shipped artifact or test, and no code touching those decisions changed in this window.

## Human Verification Required

### 1. Fresh-eyes readability of a real run's artifact tree

**Test:** Run `uv run dark-factory run spec:./task.md` against this repository with a short real spec file, then open `.dark-factory/runs/<run-id>/artifacts/` by hand and read the seven files (`requirements.md`, `acceptance_criteria.json`, `design.md`, `constraints.json`, `implementation_summary.json`, `test_report.json`, `verdict.json`).
**Expected:** A person who has never seen this codebase can follow the handoff from `acceptance_criteria.json` through `design.md` to `verdict.json` and see which criterion ids line up across files.
**Why human:** The automated gate proves the files exist, validate against schema, and are correctly attributed to `ArtifactReference` rows in Neon — none of that establishes whether the on-disk layout and prose reads well to a human. This item was explicitly deferred to this verification pass by `04-04-PLAN.md`'s own `<human-check>` block, not invented by this verifier. Unchanged and still outstanding — no new reason found to close it programmatically.

## Gaps Summary

No must-have truth, artifact, or key link failed, and the phase's single prior open finding — the flaky ordering in `tests/integration/test_real_pipeline_zero_config.py` — is now resolved: the fix commit (`ca602b3`) is present on `HEAD`, its diff exactly matches the documented change, it adopts an ordering key already proven reliable elsewhere in this codebase, and the surrounding regression suite (287 unit tests, mypy, ruff) stays green. This verifier could not personally re-execute that one test against real Neon in this sandboxed session (no reachable PostgreSQL 17 backend was available through any of the three provisioning rungs, and this session's secret-file read guard correctly blocked access to the `.env`-sourced test database URL) — that limitation is disclosed above rather than papered over, and it is the reason the separate executor's 5/5 real-Neon claim is accepted on strong circumstantial and structural evidence rather than independently reproduced by this pass.

Overall status remains `human_needed` solely because of the one pre-existing, explicitly-deferred manual UAT item above (fresh-eyes artifact-tree readability) — not because of any failed or uncertain automated check. There are zero open gaps and zero open anti-pattern findings at any severity.

---

_Verified: 2026-09-13 (re-verification / digest refresh)_
_Verifier: Claude (gsd-verifier)_
