---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
reviewed: 2026-10-01T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - .env.example
  - .github/workflows/ci.yml
  - README.md
  - src/dark_factory/config/settings.py
  - src/dark_factory/github/client.py
  - src/dark_factory/webhook/__init__.py
  - src/dark_factory/webhook/app.py
  - tests/db/test_cross_machine_resume.py
  - tests/db/test_webhook_dispatches_resume.py
  - tests/support/fake_github.py
  - tests/unit/test_ci_enforces_worker_name_guard.py
  - tests/unit/test_dispatch_token_never_reaches_a_worker.py
  - tests/unit/test_qual01_ci_coverage.py
  - tests/unit/test_resume_workflow_reference_doc.py
  - tests/unit/test_settings.py
  - tests/unit/test_trigger_carries_no_lifecycle_logic.py
  - tests/unit/test_webhook_import_needs_no_database.py
  - tests/unit/test_webhook_signature.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-10-01T00:00:00Z (incremental pass, consolidated with 2026-09-30 full-phase review)
**Depth:** standard
**Files Reviewed:** 18 (16 from the 2026-09-30 full-phase review + 2 newly touched by gap-closure plans 11-06/11-07; 3 files overlap between the two passes)
**Status:** issues_found

## Summary

This report consolidates two review passes:

1. **2026-09-30 — full-phase review** (plans 11-01 through 11-05, 16 files): the initial
   `workflow_dispatch` dispatch logic, the `db`-tier CI wiring, and the cross-machine resume
   proof. Found 2 warnings + 2 info findings, carried forward below — **neither warning has
   been addressed yet**, since plans 11-06/11-07 did not touch the code paths they concern.
2. **2026-10-01 — incremental review** (gap-closure plans 11-06, 11-07, 5 files: `README.md`,
   `src/dark_factory/webhook/{app,__init__}.py`, `tests/unit/test_resume_workflow_reference_doc.py`,
   `tests/unit/test_webhook_import_needs_no_database.py`), scoped to exactly the diff those two
   plans introduced. Found 2 issues (1 warning, 1 info) — **both were fixed immediately** in
   commit `ceef301` as part of this review pass, since they were small, well-scoped, and directly
   in code this session's executors had just written.

Net result: **2 open findings remain** (both carried forward from 2026-09-30, both pre-existing
and unrelated to the gap-closure work), **2 findings were found-and-fixed** in this pass.

## Carried Forward — Open (from 2026-09-30 review, unaffected by 11-06/11-07)

### WR-01: Dispatch block (step 7) has no catch-all exception handler, unlike every other step in the same function

**File:** `src/dark_factory/webhook/app.py` (dispatch block introduced by 11-01/11-02; unaffected by 11-06's factory-construction refactor — confirmed still present during this pass)

**Issue:** The module's own docstring promises: "Any unexpected exception is logged with the
exception and returns a fixed 500, never echoed." That promise is implemented for
`resolve_issue_comment` and `submit_answer` (`except Exception: _log.exception(...); return
_SERVER_ERROR`), but **not** for the dispatch block: a plain DB read (`load_run_state`), client
construction (`_dispatch_provider()`), and the dispatch call itself each catch only a narrow
exception type, so a transient DB error or an unexpected exception type propagates unhandled
instead of degrading to the fail-soft `_OK` the module's own design intent calls for (the answer
has already committed by this point, so a 500 would incorrectly invite a GitHub redelivery that
re-takes the no-op branch anyway).

**Fix:** Wrap the whole dispatch step in one outer `except Exception: _log.exception(...)`,
matching the fail-soft shape already used for `GitHubError`. (Full fix snippet in the superseded
2026-09-30 report, preserved in git history at commit `539448c` — this file no longer repeats the
full code block to avoid drift between two copies of the same snippet.)

**Status:** open — not addressed by any plan in this phase; a candidate for a future hardening
plan or an immediate follow-up fix.

### WR-02: `lease_heartbeat_seconds` accepts non-positive values as long as it is less than the TTL

**File:** `src/dark_factory/config/settings.py:142-163` (pre-existing since Phase 2; reachable from this phase's new `tests/db/test_cross_machine_resume.py` and `tests/support/subprocess_runner.py::child_env`, which both pass this field through to real subprocess config — confirmed still present during this pass)

**Issue:** `_lease_intervals_are_coherent` validates `lease_ttl_seconds > 0` and
`lease_heartbeat_seconds < lease_ttl_seconds`, but never checks `lease_heartbeat_seconds > 0`. A
config of `LEASE_HEARTBEAT_SECONDS=0` or a negative value passes validation cleanly, producing a
meaningless heartbeat interval that fails later (deep inside a heartbeat thread) instead of
loudly at settings-load time — the exact failure mode this validator exists to prevent for
sibling fields.

**Fix:** Add a `lease_heartbeat_seconds <= 0` check raising `ValueError`, mirroring the existing
`lease_ttl_seconds` check. (Full fix snippet preserved in git history at commit `539448c`.)

**Status:** open — pre-existing field, not owned by this phase's scope; a candidate for a
dedicated settings-hardening plan.

## Found and Fixed (2026-10-01 incremental pass, gap-closure plans 11-06/11-07)

### Fixed — Per-worker credential drift-guard was vacuous for `hermes` on row deletion

**File:** `tests/unit/test_resume_workflow_reference_doc.py`
**Issue:** `test_the_ci_handoff_section_names_every_worker_credential` asserted only that the
credential env var appeared *somewhere* in the whole README section, not scoped to the specific
worker's own table row. Since `hermes` shares its credential (`ANTHROPIC_API_KEY`) with
`claude-code`, deleting the entire `hermes` row would not have been caught by this guard (the
credential string would still be found via `claude-code`'s row) — only the companion binary test
would have caught it, silently narrowing the guard's coverage for exactly the worker it was least
effective for.
**Fix applied (commit `ceef301`):** Scoped the assertion to lines containing the worker's own
`` `{worker_name}` `` marker before checking for the credential string on those lines. Verified:
all 55 tests in the affected files pass, `ruff check`/`ruff format --check` clean on the touched
file, ids-parametrized over `LIVE_RUNTIMES` so a future adapter addition exercises the same guard.

### Fixed — Orphaned one-word line in refreshed module docstring

**File:** `src/dark_factory/webhook/__init__.py`
**Issue:** 11-06's docstring edit (deferring ASGI construction to a factory) reflowed the
invocation sentence but left "the optional" stranded alone on its own 12-character line — a
leftover artifact `ruff format` does not catch (it never touches docstring prose).
**Fix applied (commit `ceef301`):** Re-wrapped the paragraph so no line is an orphaned fragment.

## Info — Carried Forward, Open (from 2026-09-30 review, non-blocking)

### IN-01: `_dispatch_cache`/`_client_cache` single-element-list caches are not thread-safe under concurrent first requests

**File:** `src/dark_factory/webhook/app.py` (pre-existing pattern, not introduced by this phase; unaffected by 11-06's refactor)

Benign under the project's current deployment model (no data corruption, no leaked secret — just
a redundant object construction on a rare race); worth a `threading.Lock()` guard only if this
code is ever expected to run under meaningful concurrent first-request load. Not blocking.

### IN-02: Guard 1's `run_state_unavailable` skip reason has zero test coverage by design

**File:** `src/dark_factory/webhook/app.py` (pre-existing, documented as intentionally untested — "cannot happen here in practice")

Not a functional defect; flagged only so a future reviewer does not mistake the constant's
presence for tested behavior. Not blocking.

## Unrelated Observation (not scored, flagged for visibility)

A full `pytest -m unit` run during the incremental pass surfaced
`tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
failing because this sandbox has a real `claude` CLI and `ANTHROPIC_API_KEY` on `PATH`, so the
test's "expected FAILED with no credentials" assumption doesn't hold here and the adapter makes a
real API call instead. This is a pre-existing environment-dependent test-isolation gap, already
noted independently in 11-06-SUMMARY.md and 11-07-SUMMARY.md as out of scope for this phase's
requirements (TRIG-01/TRIG-04/HITL-06/QUAL-01) — not re-scored here, carried forward as a known
sandbox artifact for a future test-isolation pass.

---

_Reviewed: 2026-10-01T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer, incremental pass) + orchestrator (consolidation with 2026-09-30 full-phase review)_
_Depth: standard_
