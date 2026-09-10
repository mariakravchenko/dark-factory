---
phase: 02-pause-resume-single-owner-execution
fixed_at: 2026-09-10T11:17:52Z
review_path: .planning/phases/02-pause-resume-single-owner-execution/02-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-09-10T11:17:52Z
**Source review:** .planning/phases/02-pause-resume-single-owner-execution/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03 — no Critical findings; Info findings excluded by `critical_warning` scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: A single transient heartbeat-renewal error aborts an in-flight step with no retry

**Files modified:** `src/dark_factory/orchestrator/lease.py`
**Commit:** e9a231a
**Applied fix:** Rewrote `_heartbeat` in `run_lease` to distinguish "renewal raised"
(transient) from "renewal executed and matched no row" (authoritative loss). A
raised exception now increments a `consecutive_errors` counter, logs
`lease.renew_error` with the attempt number, and `continue`s the loop instead of
declaring the lease lost. The lease is only surrendered on a transient error once
`consecutive_errors * interval >= ttl - interval` (with the shipped defaults
ttl=900s / interval=300s that is the 2nd consecutive failed beat, i.e. one
retry). A renewal that executes and returns `False` is still treated as an
immediate authoritative loss, unchanged. The `finally: hb_session.close()` still
runs on every path including `continue`.

**Human verification note:** this fix introduces new loop control flow (the
`consecutive_errors` threshold). It is covered by the 193 passing unit tests and
by `ruff`/`mypy`, but the DB-backed heartbeat integration tests
(`tests/integration/test_heartbeat_slow_step.py`,
`tests/integration/test_lease_expiry_reclaim.py`,
`tests/db/test_lease_lost_aborts_step.py`) could **not** run in this environment
(no Docker, no local PostgreSQL 17). Recommend running the `db`/`integration`
tiers against a real PostgreSQL 17 before the phase proceeds, to confirm the
retry window interacts correctly with `lease_ttl_seconds` reclaim timing.

### WR-02: The worker runs outside the lease-validity window; concurrent execution is possible if an owner stalls past its TTL

**Files modified:** `src/dark_factory/orchestrator/lease.py`
**Commit:** 3617bb3
**Applied fix:** Added a new paragraph to the `lease.py` module docstring —
"What the lease guarantees — and what it does not." — stating explicitly that the
guarantee is *no concurrent durable mutation*, not *no concurrent execution*: the
worker call in `_run_current_role` runs outside the lease-validity window and is
not cancellable, so a stalled owner past `lease_ttl_seconds` can have its worker
running concurrently with a second process's worker, while durable state stays
correct via the `expected_owner_token` fence in `apply_transition`. The docstring
records that this is harmless with `FakeWorker` and names the two candidate
mitigations (poll `lease.lease_lost` on a timer + process-group kill; or worker
adapter re-verifies ownership before any irreversible side effect) to be
addressed before Phase 7 credentialled agent subprocesses.

**Deferred (not in Phase 2 scope):** the actual subprocess-kill / pre-side-effect
re-verification work. The review states "No change required for Phase 2; record
the limitation explicitly and address before real workers land." Only the
docstring note was actionable now; the mitigation is deferred to Phase 7.

### WR-03: Uncaught exception types from the mutation path bypass the D-05 exit-code contract

**Files modified:** `src/dark_factory/cli.py`
**Commit:** 19f4ccb
**Applied fix:** Added `LookupError` and `ValueError` to the
`_ORCHESTRATION_ERRORS` tuple, with an explanatory comment. `apply_transition`
and its helpers raise bare `LookupError` (missing `runs` row at lock time,
missing `role_executions` row, no WAITING `human_interaction` in answer mode) and
bare `ValueError` (from the `RoleExecutionWrite` / `HumanInteractionWrite`
guards); these now route through `_report_orchestration_error` → clean exit 2
instead of escaping as an unhandled traceback and Typer exit 1 (the code D-05
reserves for "persisted FAILED"). The pre-existing `except ValueError` for
`UUID(run_id)` parsing in `resume` / `status` is a separate, earlier catch and is
unaffected.

## Verification

**Environment:** all gates below ran inside the isolated review-fix worktree
(`.claude/worktrees/rf-02-...`), using `uv run` (worktree-local venv sync).
Results are reproducible from the branch tip after the worktree is
fast-forwarded into it.

- `python -m ast.parse` (Tier 2 syntax) — PASS for both modified files after each edit.
- `ruff check` + `ruff format --check` on `lease.py` and `cli.py` — PASS (all checks passed; 2 files already formatted).
- `mypy` (strict) on `lease.py` and `cli.py` — PASS (no issues found in 2 source files).
- `pytest -m unit` — **193 passed**, 171 deselected in 0.82s.
- `pytest -m "db or integration"` — **NOT RUN**: 164 errors, all
  `pytest.UsageError: No PostgreSQL 17 is reachable` (Docker absent, no local
  `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset). Pre-existing environment
  limitation, not a regression from these fixes. These tiers must be run against
  a real PostgreSQL 17 to fully verify WR-01 and WR-03.

## Skipped Issues

None.

---

_Fixed: 2026-09-10T11:17:52Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
