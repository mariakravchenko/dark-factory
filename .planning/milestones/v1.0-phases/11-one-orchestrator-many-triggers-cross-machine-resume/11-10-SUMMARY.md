---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 10
subsystem: testing
tags: [pytest, ci-guard, settings, gap-closure, G-11-3, subprocess-isolation]

requires:
  - phase: 11-08
    provides: "run_publish_step's push_token threaded as an explicit parameter (Sink B of G-11-3)"
  - phase: 11-09
    provides: "real_log_sink/clarification-driver settings injection and credential_missing tolerating an unconstructible Settings (Sink A/C + latent sibling of G-11-3)"
provides:
  - "A child-process guard (tests/unit/test_unit_tier_needs_no_database.py) that reproduces CI's own unit-or-contract selector with no database and no readable .env, closing the recurrence gap 11-06's import-time sweep could not reach"
  - "An adversarial collection check proving the three live-CLI integration modules no longer abort collection when worker binaries are present on PATH"
  - "A non-vacuous positive control proving the guard's own sanitization has teeth"
affects: [ci-workflow, settings-validation, live-integration-suites]

actuals:
  tokens: 3356
  tasks: 1
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Child-process property guard with explicit env allowlist (never os.environ copy), cwd=tmp_path to keep the repo's git-ignored .env out of reach, and a path-based --ignore of the guard's own file to prevent non-terminating recursion"
    - "Marker expression read out of ci.yml via yaml.safe_load + shlex, rather than restated as a literal, so CI's selector and the guard's own assertion cannot drift apart"
    - "Positive-control pattern: a throwaway offending test proves the sanitization harness has teeth, mirroring test_webhook_import_needs_no_database.py's Test 4"

key-files:
  created:
    - tests/unit/test_unit_tier_needs_no_database.py
  modified:
    - .planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/deferred-items.md

key-decisions:
  - "Included all three live-CLI integration modules (claude-code, copilot, hermes) in Test 2's adversary, not just the two the debug doc originally observed failing -- this sandbox has claude/copilot on PATH but not hermes, so only including the originally-observed two would have under-tested the hermes module, which carries the identical import-time skip_reason() call and is equally exposed to the latent-sibling defect class."
  - "Derived stub binary names from tests.support.live_runtime.LIVE_RUNTIMES's own values rather than a hardcoded list, so Test 2 cannot silently diverge from the binaries the credential probe actually resolves and extends automatically to a fourth adapter."
  - "Did not edit ci.yml's two [ASSUMED] timeout comments -- the measured numbers that would calibrate them only exist after the human-check's real CI run, which this execution explicitly does not perform (see Pending Human Action below)."

patterns-established:
  - "Runtime (execution-time) regression guard as the required complement to an import-time sweep: 11-06 proved import-time safety; this plan proves the analogous property for code that runs during test execution on a conditionally-taken branch."

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "A child process running CI's own `unit or contract` selector, with no database variables and a working directory with no readable .env, exits 0 over the whole tests tree"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_unit_tier_needs_no_database.py::test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file"
        status: pass
      - kind: unit
        ref: "uv run pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py (3 passed in 258.90s)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The guard's positive control reports a non-zero exit and names pydantic's ValidationError for a throwaway test reaching get_settings() unguarded"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_unit_tier_needs_no_database.py::test_the_harness_detects_an_unguarded_settings_read"
        status: pass
    human_judgment: false
  - id: D3
    description: "Collecting the three live-CLI integration modules with stub worker binaries on the child's PATH exits 0 with no collection errors"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_unit_tier_needs_no_database.py::test_live_suite_modules_collect_with_stub_binaries_on_path"
        status: pass
    human_judgment: false
  - id: D4
    description: "Re-run UAT test 1 on a real GitHub-hosted runner and record 3 measured durations + run URL"
    verification: []
    human_judgment: true
    rationale: "Requires pushing this branch / opening a PR and watching a real GitHub Actions run -- a shared-state action requiring the user's own explicit authorization, which this run did not have. Remains pending exactly as 11-VERIFICATION.md already records (status: human_needed)."

duration: ~35min
completed: 2026-10-02
status: complete
---

# Phase 11 Plan 10: Unit-tier-needs-no-database runtime guard Summary

**A three-test child-process guard reproduces CI's exact `unit or contract` selector with no database and no `.env`, proving all three sinks of G-11-3 (production push-token read, log-sink settings read, clarification-driver redaction) plus the latent live-suite collection abort are closed, with a non-vacuous positive control.**

## Performance
- **Duration:** ~35min
- **Tasks:** 1 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Added `tests/unit/test_unit_tier_needs_no_database.py`, the runtime analogue of plan 11-06's import-time guard. Test 1 spawns `sys.executable -m pytest` with the marker expression read directly out of `.github/workflows/ci.yml`'s `Unit and contract tiers` step, from a `tmp_path` cwd, with an explicit environment allowlist omitting `DATABASE_URL`/`DATABASE_URL_DIRECT`, over the full `tests/` tree, excluding itself by resolved absolute path.
- Test 2 proves the latent sibling (found incidentally during the 11-10 debug investigation) is closed: all three live-CLI integration modules (`test_claude_code_live.py`, `test_copilot_live.py`, `test_hermes_live.py`) collect with exit 0 and no collection-error text when stub binaries for every `tests.support.live_runtime.LIVE_RUNTIMES` entry are placed first on the child's `PATH` -- this is the condition under which the sibling previously aborted the entire selector with 2 collection errors, 0 tests run, before plan 11-09's `credential_missing` fix landed.
- Test 3 is the positive control: a throwaway test reaching `get_settings()` with no override reports a non-zero exit and names pydantic's `ValidationError` in its output, proving the harness's sanitization has teeth rather than silently leaking a credential.
- Ran all four of the plan's automated `<verify>` commands against the full tree; all four pass (see Task Commits / verification detail below).

## Task Commits
1. **Task 1: The whole tier, proven green in a child process that has no database and no environment file** - `8a4f313` (test)

## Files Created/Modified
- `tests/unit/test_unit_tier_needs_no_database.py` - New unit-tier guard module: Test 1 (full-tier property), Test 2 (latent-sibling adversary), Test 3 (positive control). Module docstring documents the working-directory and allowlist reasoning, the path-based recursion guard, the `ci.yml`-derived marker-expression extraction, and the single-entry `get_settings` cache ordering limitation.
- `.planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/deferred-items.md` - Logged the pre-existing, out-of-scope `ruff format` drift across 19 unrelated files (predating this plan) rather than reformatting files this plan did not touch.

## Verification Detail (measured)

- `uv run pytest -m unit -q tests/unit/test_unit_tier_needs_no_database.py` -> **3 passed in 258.90s** (0:04:18). This is the guard's own Test 1 child's dominant cost; consistent with the planning measurement of 275.12s for the sanitized full tier.
- `uv run pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py tests/unit/test_qual01_ci_coverage.py tests/unit/test_ci_enforces_worker_name_guard.py` -> **10 passed in 2.73s** (the three pre-existing CI-parsing guards are unaffected).
- `uv run ruff check .` -> **All checks passed!** `uv run ruff format --check .` -> 19 pre-existing, unrelated files would be reformatted (see Deviations); the new module itself is independently confirmed already formatted.
- The plan's raw sanitized-child invocation (`env -u DATABASE_URL -u DATABASE_URL_DIRECT ... python -c "...pytest.main(['-q','-m','unit or contract', ...])"`) -> **836 passed, 1 skipped, 374 deselected, 1 warning in 256.82s**, exit 0. This confirms the sanitized full-tier collection no longer aborts on this machine (it aborted with 2 collection errors during planning, before plan 11-09's Task 3 landed) and that all twelve previously-failing G-11-3 node ids are now green under CI's own no-database condition.
- `uv run mypy tests/unit/test_unit_tier_needs_no_database.py` -> **Success: no issues found in 1 source file.**
- `uv run mypy src/dark_factory` -> 2 pre-existing errors in `src/dark_factory/tools/mcp_transport.py` (optional `mcp` extra not installed in this venv) -- unrelated to this plan, which touches no production file; unchanged before/after.
- Phase-level regression, normal (unsanitized) local run from the repo root with the guard now present: `uv run pytest -q -m "unit or contract"` -> **1 failed, 838 passed, 1 skipped, 374 deselected, 1 warning in 530.59s** (0:08:50) -- roughly double the pre-guard baseline of 270.86s, as the plan's own `<verification>` note anticipated (the guard's own Test 1 spawns a second full sanitized tier). The 1 failure, `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`, is the pre-existing, out-of-scope environment-dependent failure already recorded in `deferred-items.md` under plan 11-07 (this sandbox has a live `ANTHROPIC_API_KEY` and `claude` CLI configured, so the adapter makes a real call and returns `COMPLETED` instead of the test's expected `FAILED`) -- unrelated to this plan's file and not introduced by it.
- `db` tier: not run in this sandbox for this plan (not required by `<verification>`); deferred to the human check below, which runs it on the real hosted runner per `.github/workflows/ci.yml`.

## Decisions Made
See `key-decisions` in frontmatter: included all three live-CLI modules (not just the two originally observed failing) in Test 2's adversary; derived stub binary names from the `LIVE_RUNTIMES` registry; left `ci.yml`'s `[ASSUMED]` timeout comments untouched pending the human check's measured numbers.

## Deviations from Plan

### Auto-fixed Issues

None - the guard module itself required no fix-up; all three tests were green on first write.

### Out-of-scope (logged, not fixed)

**1. Pre-existing `ruff format` drift, 19 files** - Found during: Task 1's `<verify>` run of `ruff format --check .`. 19 files unrelated to this plan (e.g. `tests/unit/test_write_scope_guard_covers_bounce.py`, traced to phase-9 commit `932a278`) would be reformatted. This plan's own new file is independently confirmed already formatted. Logged to `deferred-items.md` per the scope boundary rule rather than reformatted.

**2. Pre-existing environment-dependent test failure** - Found during: the phase-level regression run of the normal (unsanitized) `unit or contract` tier. `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` fails in this sandbox because a live `ANTHROPIC_API_KEY` and `claude` CLI are both configured, so the adapter makes a real call. Already recorded under plan 11-07 in `deferred-items.md`; unrelated to this plan's file.

**Total deviations:** 0 auto-fixed, 2 logged as out-of-scope (both pre-existing, both already recorded in `deferred-items.md`). **Impact:** none on this plan's deliverable -- the new guard module's own three tests are fully green and non-vacuous.

## Issues Encountered

None beyond the two out-of-scope items above.

## User Setup Required / Pending Human Action

**The plan's `<human-check>` verification item remains pending by design and was explicitly NOT attempted, NOT simulated, and NOT marked done in this run.** This execution was scoped to exclude any `git push`, PR creation, or `gh` workflow dispatch.

To close it: push this branch (or open a PR) and let `.github/workflows/ci.yml`'s `quality` job run on a real GitHub-hosted runner, then record, in order: (1) the `Unit and contract tiers` step passes -- 0 failed, with this plan's new guard module among the passing tests; (2) the `Database tier (FakeWorker orchestration suite, QUAL-01)` step is actually reached and its `pytest_report_header` line reads `dark-factory test Postgres: testcontainers`, proving Docker is genuinely available on `ubuntu-latest`; (3) the `db` tier passes against the `11-06-SUMMARY.md` baseline of 205 passed / 1 skipped; (4) the measured wall-clock duration of the `Unit and contract tiers` step, of the `Database tier` step, and of the whole `quality` job, each checked against its `[ASSUMED]` budget (`timeout-minutes: 20` / `30`). The pre-guard baseline for the first of those is 36.81s on the hosted runner, so the measured delta is this guard's real cost where it matters. See `.planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-VERIFICATION.md` (status: human_needed) for the existing tracked record of this same pending item, and `.planning/debug/ci-unit-tier-settings-validation-g-11-3.md` for the original failure this guard exists to catch locally.

Once those numbers are in hand, replace `ci.yml`'s two `[ASSUMED]` comment blocks with the measured values -- deliberately not done in this plan, for the same reason plan 11-06 deferred the identical edit: the numbers do not exist until that run completes.

## Next Phase Readiness

The automated half of G-11-3's gap closure is complete and independently verified: the guard is in place, green, and non-vacuous, and all three local automated `<verify>` commands plus the phase-level regression pass. What remains is the human check above -- a real-runner CI confirmation that requires the user's own explicit push authorization. All twelve of G-11-3's originally-reported failures are confirmed closed locally under CI's own no-database condition.

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-10-02*

## Self-Check: PASSED

- FOUND: tests/unit/test_unit_tier_needs_no_database.py
- FOUND: 8a4f313 (task commit)
