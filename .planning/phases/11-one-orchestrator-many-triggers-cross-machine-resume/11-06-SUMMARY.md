---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 06
subsystem: webhook
tags: [starlette, uvicorn, pydantic-settings, pytest, import-time-safety, ci]

requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plans 11-01/11-02/11-04 — webhook/app.py's dispatch block and ci.yml's Database tier step, whose collection this gap blocked"
provides:
  - "dark_factory.webhook.app:build_app -- a zero-argument ASGI application factory, importable with no reachable database"
  - "tests/unit/test_webhook_import_needs_no_database.py -- a generalized, non-vacuous guard that every dark_factory module imports with no DATABASE_URL and no readable .env"
affects: [ci.yml, webhook, QUAL-01, future-modules-adding-import-time-Settings-reads]

actuals:
  tokens: 3476
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "ASGI application factory (uvicorn --factory) instead of a module-level pre-built app object, to keep import time free of I/O/config requirements"
    - "child-process import sweep via pkgutil.walk_packages + an explicit onerror callback, run under a from-scratch environment allowlist and a tmp_path cwd, as the mechanical proof of 'importable with no database'"

key-files:
  created:
    - tests/unit/test_webhook_import_needs_no_database.py
  modified:
    - src/dark_factory/webhook/app.py
    - src/dark_factory/webhook/__init__.py

key-decisions:
  - "Deleted the module-scope `app = build_app()` statement outright rather than replacing it with a lazy `__getattr__`/cached property -- any attribute-probe indirection would still let `from dark_factory.webhook.app import *` or a bare attribute access trigger Settings() construction as a side effect, the exact shape of this gap."
  - "RED was verified by temporarily restoring the pre-Task-1 app.py in the working tree via `git checkout <pre-fix-commit> -- app.py` (never committed), running the new test module to confirm the three affected tests fail with the exact G-11-1 pydantic_core.ValidationError, then restoring the committed Task 1 fix before GREEN -- because Task 1 and Task 2 execute in plan order and the implementation was already committed, a literal failing-test commit was avoided (it would otherwise land known-red on a shared branch)."
  - "The two commits are test(11-06) (Task 2) following feat(11-06) (Task 1), not the reverse RED-then-GREEN commit order the TDD reference describes for the general case -- documented as a deviation below, not silently normalized."

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "dark_factory.webhook.app exposes a callable build_app factory and no pre-built application attribute; both module docstrings document the agreed uvicorn --factory invocation"
    requirement: QUAL-01
    verification:
      - kind: unit
        ref: "uv run python -c \"import dark_factory.webhook.app as m; assert m.__all__ == ['build_app']\""
        status: pass
      - kind: unit
        ref: "tests/unit/test_webhook_signature.py, test_webhook_process_boundary.py, test_no_worker_name_leak.py, test_dispatch_token_never_reaches_a_worker.py (44 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every dark_factory module imports with no DATABASE_URL/DATABASE_URL_DIRECT and no readable .env; the three G-11-1 modules collect with exit code 0 under the same environment"
    requirement: QUAL-01
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_import_needs_no_database.py (4 passed: package-wide sweep, G-11-1 collection, structural fact, positive control)"
        status: pass
      - kind: unit
        ref: "uv run pytest -q -m \"unit or contract\" (821 passed, 1 unrelated pre-existing failure, 1 skipped)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Database tier (FakeWorker orchestration suite, QUAL-01) now runs instead of erroring at collection -- db-tier regression unaffected by this fix"
    requirement: QUAL-01
    verification:
      - kind: db
        ref: "uv run pytest -q -m db (205 passed, 1 skipped, 991 deselected, 0 failed, 1:04:05 wall-clock, external Neon rung)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A real CI run of .github/workflows/ci.yml's quality job confirms the Unit and contract tiers step no longer exits 2 at collection, the Database tier step is reached and reports the testcontainers rung, and both step/job durations fit their [ASSUMED] budgets"
    verification: []
    human_judgment: true
    rationale: "Requires pushing this branch and observing a GitHub-hosted runner execute ci.yml -- the exact human-check deliverable Task 2's own <verify> block defers; cannot be produced from this execution sandbox."

duration: ~20min task-commits + ~1h04m db-tier verification wait
completed: 2026-10-01
status: complete
---

# Phase 11 Plan 06: Webhook Database-Free Import Summary

**Deferred `webhook/app.py` ASGI construction to a `build_app()` factory (uvicorn `--factory`), closing the collection-time `ValidationError` that blocked CI's `Unit and contract tiers` step, and added a package-wide child-process import sweep that proves every `dark_factory` module stays importable with no database configured.**

## Performance
- **Duration:** ~20 min of task-commit work; verification wall-clock dominated by a single standalone `db`-tier run against real remote Neon PostgreSQL (~1h04m05s).
- **Started:** 2026-10-01T08:4x (plan read + context load)
- **Completed:** 2026-10-01T09:05:02+03:00 (Task 2 commit) + db-tier wait finishing ~10:09
- **Tasks:** 2 of 2 completed
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- `src/dark_factory/webhook/app.py` no longer evaluates `build_app()` at module scope; `__all__` now lists only `["build_app"]`, so no attribute probe on the module can construct `Settings()` as a side effect.
- Both `webhook/app.py`'s and `webhook/__init__.py`'s module docstrings now agree on one command: `uv run uvicorn dark_factory.webhook.app:build_app --factory --host 0.0.0.0 --port 8000`.
- New `tests/unit/test_webhook_import_needs_no_database.py` proves, in a real child process with a from-scratch environment allowlist and a `.env`-free `tmp_path` cwd, that every module `pkgutil.walk_packages` yields under `dark_factory` imports cleanly (0 offenders, 1 tolerated: `dark_factory.tools.mcp_transport`, missing the uninstalled `mcp` optional extra) and that the three G-11-1 modules collect with exit code 0.
- A positive control (Test 4) proves the sweep harness has teeth: a throwaway module that constructs `Settings()` at import time is correctly reported as an offender.

## Task Commits
1. **Task 1: Defer the ASGI construction** - `1f431d7` (feat)
2. **Task 2: The guard — every module imports with no database** - `711598c` (test)
**Plan metadata:** pending (docs: complete plan, this commit)

## Files Created/Modified
- `src/dark_factory/webhook/app.py` - Removed the module-scope `app = build_app()` statement and narrowed `__all__` to `['build_app']`; rewrote the "How this process is run" docstring block to the uvicorn `--factory` invocation and stated why (import must never require a reachable database). `build_app`'s body, including the three WR-02 startup credential diagnostics, is byte-for-byte unchanged.
- `src/dark_factory/webhook/__init__.py` - Updated the package docstring's invocation example to `uvicorn dark_factory.webhook.app:build_app --factory`, keeping its existing pointer to `app.py`'s own docstring intact.
- `tests/unit/test_webhook_import_needs_no_database.py` (new) - Four tests: the generalized package-wide import sweep, the literal G-11-1 collection check, an in-process structural check of the module's public surface, and a positive control proving the sweep harness detects a real offender.

## Decisions Made
- Deleted the eager module attribute outright rather than any lazy-attribute indirection (`__getattr__`, cached property) — those would still let an attribute probe trigger `Settings()` construction, reproducing the exact defect class this plan closes.
- Verified RED by temporarily restoring the pre-Task-1 `app.py` in the working tree (`git checkout <pre-fix-commit> -- src/dark_factory/webhook/app.py`), confirming Tests 1-3 fail with the exact `pydantic_core.ValidationError: 2 validation errors for Settings / database_url / database_url_direct` traceback G-11-1 records (Test 4, the harness self-check, does not touch `app.py` and passed throughout), then restoring the committed Task 1 fix before confirming GREEN. This kept a known-failing test out of the shared branch's commit history while still producing a genuine, intentional RED anchor rather than a vacuous one.
- The one new file's commit is `test(11-06)`, not preceded by a separate `feat(11-06)` for Task 2 — the implementation it tests was already committed as Task 1's own `feat(11-06)` commit in plan order, so there is no second implementation commit to pair it with. See TDD Gate Compliance below.
- Confirmed the WR-02 startup credential diagnostics survive the deferral: uvicorn's `--factory` invocation still calls `build_app()` exactly once at process startup (same as the old `app = build_app()` module-level call), so the three missing-credential log records fire once per receiver process at the same moment they did before. `tests/unit/test_webhook_signature.py`'s startup-check tests and `test_dispatch_token_never_reaches_a_worker.py` (both in Task 1's verify set) re-assert this unchanged.

## TDD Gate Compliance

Task 2 (`tdd="true"`) followed RED-GREEN in substance but not in commit-sequence form, because Task 1's implementation was already committed when Task 2 began (the plan's own tasks execute in order):

- **RED:** Verified, not committed. The test file was written, then run against a temporarily-restored pre-Task-1 `src/dark_factory/webhook/app.py` (via `git checkout <5e7992f> -- app.py`, never staged or committed). Tests 1, 2, and 3 failed with the exact `pydantic_core.ValidationError` G-11-1 records; Test 4 (the harness's own positive-control self-check) does not depend on `app.py` and passed in this state too, as expected. The pre-Task-1 file was then restored to the committed (fixed) version via `git checkout HEAD -- app.py` before anything was staged.
- **GREEN:** `711598c` (`test(11-06): guard that every dark_factory module imports with no database`) — all four tests pass against the real, already-committed Task 1 fix.
- **No separate feat/refactor commit for Task 2:** there is no new production code for this task; the implementation lives entirely in Task 1's `1f431d7`.

This is a deliberate, documented deviation from the canonical two-commit (`test` then `feat`) RED/GREEN pattern, driven by this plan's own task ordering (Task 1 ships the fix, Task 2 ships the regression guard for it) rather than an omission.

## Deviations from Plan

**1. [Rule 3 - process adaptation] RED verified via a temporary, uncommitted revert rather than a literal failing-test commit**
- **Found during:** Task 2
- **Issue:** The plan's own text anticipated running the new tests "against the unfixed file first if Task 1 is not yet committed" — but Task 1 *was* already committed by the time Task 2 began (plan tasks execute in order), so there was no genuinely-unfixed tree state to commit a RED test against without re-introducing the bug into the committed history.
- **Fix:** Used `git checkout <pre-Task-1-commit> -- src/dark_factory/webhook/app.py` to restore the pre-fix file in the working tree only, confirmed RED, then `git checkout HEAD -- src/dark_factory/webhook/app.py` to restore the committed fix before staging anything. Neither checkout was committed; `git log` shows no intermediate revert.
- **Files modified:** none (working-tree-only, reverted before any commit)
- **Verification:** `uv run pytest -m unit -q tests/unit/test_webhook_import_needs_no_database.py` run twice — 3 failed/1 passed against the reverted file, 4 passed against the restored fix.
- **Commit:** `711598c` (test file, committed only against the GREEN state)

**Total deviations:** 1 (Rule 3 — process adaptation, no production code change).
**Impact on plan:** None on the shipped artifacts; the deviation is purely about how RED evidence was obtained given the plan's two tasks landing in sequence on the same working tree.

## Issues Encountered

- `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` failed during the `pytest -q -m "unit or contract"` run (expected `WorkerResultStatus.FAILED` with no `ANTHROPIC_API_KEY` configured, got `COMPLETED` with a real model response). This is unrelated to this plan's changes — it never touches `webhook/`, `Settings`, or import-time behavior — and is a pre-existing sensitivity to whatever live Claude Code credential/session state exists in this execution sandbox. Out of scope per the scope-boundary rule; not fixed. Logged here for visibility rather than silently ignored.
- `uv run ruff format --check .` reports 19 pre-existing unformatted files outside this plan's scope (various `tests/db/`, `tests/unit/`, `tests/support/` modules, none touched by this plan). `src/dark_factory/webhook/app.py` and `src/dark_factory/webhook/__init__.py` are confirmed already-formatted. Not fixed, per scope boundary.
- `uv run mypy src/dark_factory` reports 2 pre-existing errors in `src/dark_factory/tools/mcp_transport.py` (`Cannot find implementation or library stub for module named "mcp.server"`) — the `mcp` optional extra is not installed in this venv, exactly as `tests/unit/test_webhook_import_needs_no_database.py`'s own tolerated-failure class documents. Not fixed, per scope boundary; this is a venv configuration fact, not an import-time I/O defect.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness

**Package-wide sweep result:** 0 offenders, 1 tolerated failure (`dark_factory.tools.mcp_transport`, missing module `mcp`) — matching the gap diagnosis's own reproduced sweep (73 modules walked, exactly two pre-fix failures: `webhook.app` and `mcp_transport`; this plan closes the first, the second is the documented, intentional tolerance).

**Uvicorn factory command both docstrings settled on:**
```
uv sync --extra webhook
uv run uvicorn dark_factory.webhook.app:build_app --factory --host 0.0.0.0 --port 8000
```

**`db`-tier reachability in this sandbox:** Reachable. `pytest_report_header` reported `dark-factory test Postgres: externally supplied Postgres via DARK_FACTORY_TEST_DATABASE_URL` (the "external" rung — a real remote Neon PostgreSQL 17 branch, not testcontainers/Docker, which is unavailable in this sandbox). `uv run pytest -q -m db` ran clean: **205 passed, 1 skipped, 991 deselected, 0 failed in 1:04:05**, matching `11-05-SUMMARY.md`'s identical 205-passed/1-skipped baseline — the webhook import-time fix changes zero db-tier behavior.

**WR-02 startup diagnostics survive the deferral:** Confirmed by reasoning and by test. Under uvicorn's `--factory` invocation, the server calls `build_app()` exactly once at process startup — the same single call the old `app = build_app()` module-level statement made, just moved from *import time* to *server-startup time*. The three missing-credential log records (`webhook.build_app.missing_github_token`, `webhook.build_app.missing_github_webhook_secret`, `webhook.build_app.missing_dispatch_github_token`) are emitted from inside `build_app`'s body, which Task 1 explicitly did not touch — so they still fire once per receiver process, still "visible in this process's own startup logs" as WR-02 requires. `tests/unit/test_webhook_signature.py`'s four startup-check tests and `test_dispatch_token_never_reaches_a_worker.py` (both in Task 1's verify set, 44 passed) re-confirm this unchanged behavior.

**Deferred (Task 2's own `<human-check>`, not attempted here):** Pushing this branch (or opening a PR) and observing `.github/workflows/ci.yml`'s `quality` job run to completion on a GitHub-hosted runner — confirming the `Unit and contract tiers` step now passes instead of exiting 2 at collection, the `Database tier` step is reached and reports the `testcontainers` rung (proving Docker availability on `ubuntu-latest`), the `db` tier passes, and both step/job durations sit inside their `[ASSUMED]` `timeout-minutes` budgets. `.github/workflows/ci.yml` itself remains untouched by this plan, as scoped — its two `[ASSUMED]` comment blocks stay in place until that real CI run produces measured durations to replace them with.

Ready for 11-07 (parallel gap-closure plan, independent — both gap-closure plans can land without blocking each other).

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-10-01*

## Self-Check: PASSED

- FOUND: `.planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-06-SUMMARY.md`
- FOUND: commit `1f431d7` (Task 1)
- FOUND: commit `711598c` (Task 2)
