---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 04
subsystem: testing
tags: [ci, pytest-markers, testcontainers, yaml, ast-guard, github-actions]

# Dependency graph
requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plan 11-01's tracer verification that the phase's foundational wiring is sound (this plan shares no files with 11-01/11-02/11-03; depends_on is tracer ordering, not a file dependency)"
provides:
  - "ci.yml's quality job runs the db marker tier (tests/db/, ~205 tests collected) via tests/conftest.py's existing testcontainers rung, in a dedicated step with its own timeout, alongside the pre-existing unit/contract step"
  - "tests/unit/test_qual01_ci_coverage.py -- the guard binding QUAL-01's eight scenario nouns (transcribed verbatim from REQUIREMENTS.md) to the tests/db/ modules that already cover them, asserting each carries the db marker and that ci.yml's quality job selects db and never integration"
  - "corrected ci.yml comment stating which tier is excluded and why (credentials, not database availability)"
affects: [11-05]

# Actuals (#2632)
actuals:
  tokens: 2819
  tasks: 2
  commits: 2
plan_head_before: 978be970bd6e79815a65b24e66d054267869e35c

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two named pytest steps (unit/contract, then db) rather than one combined -m selector, so the GitHub Actions log reports each tier's duration separately -- the number the plan's own <human-check> needs to calibrate the [ASSUMED] timeouts"
    - "A source-and-config guard (ast + yaml.safe_load, no database) that binds a requirement's own scenario wording to named test modules and their markers, plus the CI workflow's own selector -- so a coverage claim traces to an executed command, not a file's existence (T-11-15)"

key-files:
  created:
    - tests/unit/test_qual01_ci_coverage.py
  modified:
    - .github/workflows/ci.yml
    - tests/unit/test_ci_enforces_worker_name_guard.py

key-decisions:
  - "tests/unit/test_ci_enforces_worker_name_guard.py's _EXCLUDED_MARKERS tuple (('db', 'integration')) predated this phase and encoded the now-obsolete assumption that CI must never select db -- narrowed to ('integration',) only, since Task 1's own ci.yml change makes the old assertion false by design. Documented as a Rule 1 auto-fix, not a scope-creep addition: without this fix the plan's own Task 1 change fails this pre-existing guard on the very next unit-tier run."
  - "Verified the full unit-or-contract sweep with PATH stripped of the real claude CLI's directory (the same sandbox-local claude binary 11-01/11-02/11-03 already documented as a pre-existing, environment-specific hazard) -- this made tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder take its intended credential-gated FAILED path (fast) instead of spawning a real, multi-minute agentic session against the live Anthropic API. A verification-only technique (no source, test, or CI file encodes or depends on it); production/CI environments are unaffected since GitHub-hosted runners never have this CLI on PATH."

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "ci.yml's quality job selects unit, contract and db; no step selects integration; the workflow declares no services: block or new secret; the job timeout and the db step's own timeout are both raised with a stated [ASSUMED]/calibration-owner comment"
    requirement: QUAL-01
    verification:
      - kind: unit
        ref: "python -c \"import yaml; ...\" structural check (SELECTS_DB True, SELECTS_INTEGRATION False, JOB_TIMEOUT 30)"
        status: pass
      - kind: other
        ref: "uv run pytest -q -m db --collect-only (205 tests collected, non-zero exit)"
        status: pass
    human_judgment: false
  - id: D2
    description: "QUAL-01's eight scenario nouns (role transitions, artifact handoffs, pause/resume, QA rejection, Developer retries, quality-gate retries, failure limits, publishing) each map to an existing tests/db/ module carrying pytest.mark.db, and the map's key set equals the requirement's own wording exactly"
    requirement: QUAL-01
    verification:
      - kind: unit
        ref: "tests/unit/test_qual01_ci_coverage.py -- 4 passed (test_every_qual01_scenario_maps_to_a_module_that_exists, test_every_mapped_module_carries_the_db_marker, test_the_scenario_keys_are_qual01s_own_words, test_ci_runs_the_database_tier)"
        status: pass
    human_judgment: false
  - id: D3
    description: "No regression: the full unit-or-contract tier stays green after both this plan's own guard addition and the pre-existing worker-name-guard test's marker-exclusion fix"
    verification:
      - kind: unit
        ref: "uv run pytest -m \"unit or contract\" -q -- 813 passed, 1 skipped, 374 deselected in 69.92s"
        status: pass
    human_judgment: false
  - id: D4
    description: "The FakeWorker orchestration suite (QUAL-01) actually executes green in a real GitHub Actions run on this branch, with the testcontainers rung confirmed by pytest_report_header, and the [ASSUMED] timeout-minutes values (20/30) replaced or confirmed by measured duration"
    verification: []
    human_judgment: true
    rationale: "must_haves.truths marks the job-budget/rung-confirmation claims 'backstop', and the plan's own Task 1 <human-check> requires reading the GitHub Actions UI after this branch's first real CI run -- no automated proxy exists inside this execution sandbox for GitHub-hosted-runner behavior (no Docker/testcontainers rung was exercised here; the local db-tier check above used the 'external' rung via DARK_FACTORY_TEST_DATABASE_URL, not testcontainers)."

duration: ~35min
completed: 2026-09-30
status: complete
---

# Phase 11 Plan 04: CI runs the database tier, and a guard keeps the coverage claim honest Summary

**`.github/workflows/ci.yml` now runs the ~205-test `FakeWorker` orchestration suite (`db` marker) in its own timed step alongside the existing unit/contract tier, and a new source-and-config guard binds QUAL-01's eight scenario nouns to real, `db`-marked test modules and asserts the workflow still selects that marker.**

## Performance

- **Duration:** ~35 min (task-commit work; no multi-hour full-suite wait was required by this plan's own `<verify>`/`<verification>` blocks, which scope to `unit`, `contract`, and `-m db --collect-only` rather than a full run)
- **Completed:** 2026-09-30
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `.github/workflows/ci.yml`'s `quality` job gained a dedicated `Database tier (FakeWorker orchestration suite, QUAL-01)` step running `uv run pytest -q -m db` — GitHub-hosted `ubuntu-latest`'s Docker daemon resolves `tests/conftest.py`'s testcontainers rung with no `services:` block and no new secret (D-05). The `Unit and contract tiers` step is unchanged in behavior.
- The workflow's comment now states both halves correctly: `db` runs because the hosted runner supplies Docker; `integration` stays excluded because some of its tests need real agent-CLI credentials the runner does not have — an unrelated reason from database availability, spelled out so a future reader cannot "fix" the exclusion away.
- Job-level `timeout-minutes` raised 15 → 30; the new db step carries its own `timeout-minutes: 20` — both marked `[ASSUMED]` with an explicit post-first-run calibration comment, closing nothing until the plan's own `<human-check>` runs against a real CI job.
- `tests/unit/test_qual01_ci_coverage.py` (new, `unit` tier, 4 tests): binds QUAL-01's eight scenario nouns — transcribed verbatim from `.planning/REQUIREMENTS.md` line 145 — to the twelve pre-existing `tests/db/` modules that cover them (Phases 4–10; no `tests/db/` file touched by this plan), asserts every mapped module carries `pytest.mark.db` (bare or list form, via an `ast` walk that a misspelled marker cannot satisfy), asserts the map's key set equals the requirement's own wording exactly, and parses `ci.yml` with `yaml.safe_load` to assert a step selects `db` and none selects `integration`.
- Found and fixed a real, pre-existing regression this plan's own Task 1 change triggers: `tests/unit/test_ci_enforces_worker_name_guard.py` asserted CI must never select `db`, which was true before this phase and is now false by design.
- Full `unit or contract` sweep: 813 passed, 1 skipped, 374 deselected in 69.92s — zero regressions beyond the one fixed above.

## Task Commits

1. **Task 1: CI runs the database tier, on the runner's own Docker, with a stated budget** - `864e8d2` (feat)
2. **Task 2: "Covered" means "CI ran it" — the guard that keeps QUAL-01 honest** - `4b5de2e` (test) — also carries the Rule 1 fix to `test_ci_enforces_worker_name_guard.py`, discovered while running this task's own required `unit or contract` sweep

## Files Created/Modified

- `.github/workflows/ci.yml` — split test step, corrected D-05 comment, raised job timeout to 30 with a 20-minute db-step timeout, both `[ASSUMED]`.
- `tests/unit/test_qual01_ci_coverage.py` (new) — the QUAL-01 coverage guard: scenario map, marker-presence AST check, key-set-equals-requirement-wording check, CI-selector YAML check.
- `tests/unit/test_ci_enforces_worker_name_guard.py` — `_EXCLUDED_MARKERS` narrowed from `("db", "integration")` to `("integration",)`.

## Decisions Made

See `key-decisions` in the frontmatter for full rationale on both items below:

- Fixed `test_ci_enforces_worker_name_guard.py`'s stale `_EXCLUDED_MARKERS` tuple (Rule 1 — a pre-existing guard's assumption invalidated by this plan's own, explicitly planned change) rather than leaving it red or widening this plan's own `files_modified` claim after the fact.
- Verified the `unit or contract` sweep with a `PATH` stripped of the sandbox's real `claude` CLI directory, so the already-documented (11-01/11-02/11-03) pre-existing hazard — a real `claude` binary on `PATH` making `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` spawn a genuine agentic session against the live API instead of hitting its intended credential gate — took the fast, intended path instead of stalling verification for many minutes. No file was changed to achieve this; it is purely how the verification command was invoked in this sandbox, and has no bearing on CI (GitHub-hosted runners never have this CLI on `PATH`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_ci_enforces_worker_name_guard.py`'s excluded-marker assertion predated D-05 and broke on landing**
- **Found during:** Task 2, running the plan's own required `uv run pytest -m "unit or contract" -q --tb=short` verification
- **Issue:** `tests/unit/test_ci_enforces_worker_name_guard.py::test_ci_workflow_gates_on_worker_name_guard` (a Phase 7 guard, QUAL-04) asserted no `quality`-job step's pytest invocation selects `db` or `integration` — encoding the pre-Phase-11 assumption this plan's whole purpose is to invalidate. Failed immediately after Task 1's `ci.yml` change: `step 'Database tier (...)' pytest invocation selects excluded marker 'db'`.
- **Fix:** Narrowed `_EXCLUDED_MARKERS` from `("db", "integration")` to `("integration",)`, with a comment citing 11-CONTEXT.md D-05 and this phase as the reason `db` is no longer excluded.
- **Files modified:** `tests/unit/test_ci_enforces_worker_name_guard.py`
- **Verification:** Both tests in that file pass (2 passed); the guard's own self-detection test (`test_the_guard_detects_its_own_subject`) still trips on a synthetic removal of the leak-guard step, confirming the fix didn't weaken the guard's actual subject.
- **Committed in:** `4b5de2e` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — a pre-existing guard's assumption invalidated by this plan's own explicitly planned, approved change).
**Impact on plan:** Necessary for Task 1's change to land without breaking an existing, correctly-functioning guard on an unrelated requirement (QUAL-04). No scope creep — no new production behavior beyond what the plan specified; the fixed test's own subject (CI still gates on the worker-name leak guard) is unchanged.

## Issues Encountered

- **This execution sandbox has no Docker and no local `initdb`** (confirmed consistent with 01-RESEARCH.md and every later phase's own finding on the same machine) — `tests/conftest.py`'s probe ladder resolved to the `external` rung via `DARK_FACTORY_TEST_DATABASE_URL` (the Neon test branch set during plan 11-01) for the local `-m db --collect-only` check, not the `testcontainers` rung this plan's D-05 premise is actually about. **This means the testcontainers-specific claim (Docker pre-installed on `ubuntu-latest`, `pytest_report_header` reporting `testcontainers`) is unverified from inside this sandbox and remains exactly what the plan's own `<human-check>` on Task 1 requires a real CI run to confirm** — recorded here rather than asserted as proven.
- **The sandbox's pre-existing real-`claude`-CLI hazard** (documented in 11-01/11-02/11-03 SUMMARYs: a genuine `claude` binary on `PATH`, authenticated via this machine's own logged-in session, makes `test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` spawn a real multi-minute agentic run instead of hitting its intended `ANTHROPIC_API_KEY`-absent credential gate) reproduced here too — several verification attempts stalled for minutes with a spawned `claude --output-format json --permission-mode dontAsk -p ...` child process before this was diagnosed and worked around locally (see Decisions Made). Not a code defect in this plan's own files; the underlying adapter behavior is unchanged by this plan and was not touched.
- **`uv run mypy src/dark_factory` reports 2 pre-existing errors** (`src/dark_factory/tools/mcp_transport.py` — `Cannot find implementation or library stub for module named "mcp.server"`), confirmed via `git stash` to be present identically before this plan's changes. Unrelated to any file this plan modifies (`ci.yml`, two `tests/unit/` files); not fixed, per the executor's scope-boundary rule.

## User Setup Required

None for this plan directly. The plan's own Task 1 `<human-check>` is the one outstanding action: after this branch's first real CI run, read the GitHub Actions UI for the `quality` job's two test-step durations, confirm the `pytest_report_header` line reports the `testcontainers` rung, and replace the `[ASSUMED]` `timeout-minutes` values (30 job-level, 20 on the db step) with measured ones if either assumption proves wrong. This closes 11-RESEARCH.md Assumption A1 and Open Question 2 — nothing short of that real run can close them.

## Next Phase Readiness

- Plan 11-05 (deployer-facing `resume.yml` reference documentation) is unaffected by this plan's scope — no file this plan touches intersects plan 11-05's `files_modified` per the phase's wave-safety note.
- The phase's success criterion 3 (`.planning/ROADMAP.md` Phase 11 SC3) is now mechanically true for the parts verifiable without a real CI run: the `db` marker tier is selected by `ci.yml`, `integration` is not, and the coverage guard proves the requirement's own eight scenario nouns trace to modules that both exist and carry that marker.
- One open item, not a blocker: Task 1's `<human-check>` (the real-CI-run confirmation of the testcontainers rung and the two `[ASSUMED]` timeout values) is still outstanding — it requires a real GitHub Actions run on this branch, which this execution sandbox cannot produce. Recorded above under Issues Encountered rather than silently marked done.

## Self-Check: PASSED

Both claimed files (`.github/workflows/ci.yml`, `tests/unit/test_qual01_ci_coverage.py`) and the modified guard file (`tests/unit/test_ci_enforces_worker_name_guard.py`) found on disk with the expected content; both claimed commits (`864e8d2`, `4b5de2e`) found in git history via `git log --oneline --all`.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-09-30*
