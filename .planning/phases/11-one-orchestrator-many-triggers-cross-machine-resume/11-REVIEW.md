---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
reviewed: 2026-10-02T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/dark_factory/orchestrator/publish.py
  - src/dark_factory/orchestrator/runner.py
  - tests/db/test_publish_idempotency.py
  - tests/support/live_runtime.py
  - tests/support/log_sink.py
  - tests/unit/test_clarification_comment.py
  - tests/unit/test_global_settings_reads_are_declared.py
  - tests/unit/test_publish_idempotency.py
  - tests/unit/test_publish_step_unit.py
  - tests/unit/test_unit_tier_needs_no_database.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 11: Code Review Report

**Reviewed:** 2026-10-02
**Depth:** standard
**Files Reviewed:** 10
**Status:** clean

## Summary

This is an incremental review scoped to the 10 files changed across gap-closure
plans 11-08/11-09/11-10 (closing G-11-3: CI's `unit or contract` tier failing
without a local `.env`). The actual production-code diff is small and
surgical:

- `src/dark_factory/orchestrator/publish.py`: removed its own
  `get_settings()` call for the git push token and added a required
  `push_token: str | None` keyword parameter, threaded straight through to
  `push_working_branch`.
- `src/dark_factory/orchestrator/runner.py`: one call site updated to compute
  the push token from the already-in-scope `gate_settings` object and pass it
  into `run_publish_step(...)` as the new keyword.

Everything else in the file list is test infrastructure: a new AST-based
recurrence guard (`test_global_settings_reads_are_declared.py`) that pins
every process-global `get_settings()` call site in `src/dark_factory/` to a
declared inventory, a new runtime regression guard
(`test_unit_tier_needs_no_database.py`) that reproduces CI's own
no-database/no-`.env` condition in a child process and runs the real `unit or
contract` selector against it, and updated call sites / fixtures in the
existing publish-idempotency and clarification-comment unit suites to supply
the new `push_token` parameter and a `fake_settings` override.

Verification performed beyond reading the diff:

- `ruff check` on all 10 files: clean.
- `mypy` on both changed source modules: clean.
- Ran every affected unit suite (`test_publish_idempotency.py`,
  `test_publish_step_unit.py`, `test_clarification_comment.py`,
  `test_global_settings_reads_are_declared.py`): 30/30 pass.
- Ran `test_unit_tier_needs_no_database.py` end-to-end (it spawns real child
  `pytest` processes with a sanitized environment and no `.env`): 3/3 pass,
  ~274s, confirming the actual CI-tier failure this phase fixes is closed.
- Ran `tests/db/test_publish_idempotency.py` against the real Postgres
  fixture (crash-between-PR-creation-and-commit, head-branch-scoped adoption,
  no-mutating-call-on-resume): 4/4 pass.
- Grepped every call site of `run_publish_step(...)` in `src/` and `tests/`
  to confirm none were missed when the `push_token` parameter became
  required (none were).
- Confirmed via `grep` that `publish.py` no longer references
  `get_settings`/`Settings` anywhere, including in its own docstrings (no
  stale documentation left behind).
- Confirmed the three `get_settings()` call sites inside
  `runner.py::_run_current_role` (quality-gate settings, push-token-after-
  commit, clarification-failure redaction) are exactly the three declared in
  `test_global_settings_reads_are_declared.py`'s inventory, via direct
  `grep -n "get_settings()"` against the source.

No BLOCKER or WARNING-level defect was found in the reviewed diff. The two
items below are minor, non-blocking observations.

## Info

### IN-01: Fake push-token constant duplicated across test files with slightly different values

**File:** `tests/unit/test_publish_step_unit.py:34-37`, `tests/unit/test_publish_idempotency.py:50-53`
**Issue:** Both files independently define an "obviously-fake, greppable push
token" constant (`_FAKE_PUSH_TOKEN`) following the same `ghp_FAKEfakeFAKEfake...`
shape, differing only in the trailing digit run (`...fake3333...` vs.
`...fake2222...`). This is a small duplication across two files that both
already import shared test support (`tests/support/fake_github.py`,
`tests/support/git_repo.py`). It is harmless today (each file's constant is
self-contained and clearly fake), but a future edit to the "fake token shape"
convention would need to be applied in two places instead of one.
**Fix:** Optional: hoist a single `FAKE_GITHUB_PUSH_TOKEN` constant into
`tests/support/` (e.g. alongside `tests/support/fake_github.py`) and import it
from both unit modules, mirroring how `FakeGitHubClient` itself is already
shared.

### IN-02: AST-based settings-read inventory does not model lambda bodies or default-argument scope as distinct from the enclosing function

**File:** `tests/unit/test_global_settings_reads_are_declared.py:118-168`
**Issue:** `_SettingsCallCollector` pushes a new scope frame only for
`FunctionDef`/`AsyncFunctionDef`/`ClassDef`. A `get_settings()` call written
inside an `ast.Lambda` body, or inside a function's default-argument
expression (which Python evaluates once at *definition* time, in the
*enclosing* scope, not at call time inside the function body), would both be
attributed to the nearest enclosing named function/class scope rather than to
their own true evaluation context. No current call site in `src/dark_factory/`
exercises either shape, so this does not produce a false positive/negative
today, and the guard's bidirectional-equality design means any newly
introduced call site (regardless of exact attribution) would still be caught
as "undeclared" and fail loudly — the recurrence-prevention property this
guard exists for is intact. This is a latent precision gap in the qualname
attribution only, not a coverage gap.
**Fix:** Optional, low priority: add `visit_Lambda` (push/pop a
`"<lambda>"` scope segment) if a future call site ever puts `get_settings()`
inside a lambda, so the inventory's qualname stays meaningful rather than
collapsing into the enclosing function. Not required for correctness of the
recurrence guard as it stands.

---

_Reviewed: 2026-10-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
