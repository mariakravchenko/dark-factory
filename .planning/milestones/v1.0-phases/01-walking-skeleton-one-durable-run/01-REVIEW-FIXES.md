---
phase: 01-walking-skeleton-one-durable-run
source_review: .planning/phases/01-walking-skeleton-one-durable-run/01-REVIEW.md
fixed_at: 2026-09-08
findings_in_scope: 17
fixed: 13
skipped: 4
status: partially-resolved
---

# Phase 1: Code Review Fixes

Applied fixes for `01-REVIEW.md`. All 8 warnings fixed; 5 of 9 info items fixed;
4 info items intentionally skipped (recorded below). Each fix is an atomic
commit on `gsd/phase-01-walking-skeleton-one-durable-run`; the suite is green
after every commit.

## Warnings — all fixed

| ID | Commit | Outcome |
|----|--------|---------|
| WR-01 | `fd0d421` | **fixed** — `run` and `resume` now call `_route_logs_to_stderr()` before any lifecycle work, so the structlog redaction processor is always installed and library logs go to stderr, keeping the parseable `run` stdout contract clean. |
| WR-02 | `9df8e3d` | **fixed** — `configure_logging()` resolves the level from `Settings.log_level` via `logging.getLevelNamesMapping()`; a `field_validator` normalises the string to upper case and rejects an unknown name loudly. New unit tests in `test_settings.py` (incl. one asserting `LOG_LEVEL=WARNING` filters an `info` event on the real sink). |
| WR-03 | `9c5ad7e` | **fixed** — `_run_current_role` appends `RUN_COMPLETED` only when `next_status is RunStatus.COMPLETED`, not on every role completion. Single-role happy path unchanged. |
| WR-04 | `3de93b1` | **fixed** — `load_run_state` and `read_status` order the latest `role_executions` row by `created_at DESC, attempt DESC, id DESC` instead of `attempt DESC` alone (attempt restarts at 1 per role). No schema change; deterministic tiebreakers. |
| WR-05 | `01c53f6` | **fixed** — `default_registry` binds `"fake"` to a lazily-built process-lifetime `FakeWorker` so its script cursor advances across the repeated `registry.get()` calls a drive loop makes; a multi-entry `DARK_FACTORY_FAKE_SCRIPT` now advances and can raise `ScriptExhaustedError`. `WorkerRegistry` itself is unchanged (still a name→callable map); `WORK-03` and the no-carryover invariant are intact. `tests/unit/test_workers.py` and the contract suite stay green. |
| WR-06 | `63387f2` | **fixed** — `events/redaction.py`: (a) a bare 40/64-hex token is now redacted unconditionally except when introduced as a git object (`commit`/`sha`/`revision <hash>`), so a third-party PAT in prose is caught while a bare git SHA in prose survives; (b) the DB-URI credential span widened to `[^\s@]+` so a password with special characters no longer defeats the match; (c) the `Authorization: Bearer` token class widened to include base64 `+` `/` `=`. New unit tests cover each; the D-18 scope split and the surviving-git-SHA test are preserved. |
| WR-07 | `e51126f` | **fixed** — `_drive_and_exit` catches `ConcurrentTransition`, `IllegalTransitionError`, `DriveLoopExhausted`, `RunNotFoundError`, `ScriptExhaustedError`, `UnknownWorkerError`, prints a one-line stderr diagnostic, and exits **2** ("not a clean terminal outcome / nothing persisted") instead of letting a traceback escape as exit 1 (which the D-05 contract reserves for a persisted FAILED). New integration test drives the reachable NEEDS_INPUT case. Bad-invocation still exits 2; a real persisted FAILED still exits 1. |
| WR-08 | `a10bb51` | **fixed** — `create_run` passes `runs.workflow` through `redact()` at the single scrub call site, matching every other JSONB write in `mutations.py`. |

## Info — fixed

| ID | Commit | Outcome |
|----|--------|---------|
| IN-02 | `eceb788` | **fixed** — new reversible Alembic revision `0002_role_exec_uniqueness` adds `UNIQUE (run_id, role, attempt)` on `role_executions`, plus the matching `UniqueConstraint` in `RoleExecution.__table_args__`. `0001` left untouched. Verified against the test DB: `upgrade → downgrade 0001 → upgrade`, and `alembic check` reports no drift. Revision id kept ≤ 32 chars for `alembic_version.version_num`. |
| IN-04 | `8ec8a56` | **fixed** — `new_session()` annotated `-> Session` and exported; the unchecked `cast(Session, ...)` at each call site is gone. |
| IN-05 | `8ec8a56` | **fixed** — the duplicated private `_default_session()` wrappers in `orchestrator/runner.py` and `observability/status.py` are removed; both use the typed `new_session` directly as the `session_factory` default. |
| IN-06 | `0c1914b` | **fixed** — `_kv_replacement` re-emits the captured quote (`group(3)`) on both sides, so `token="abc"` becomes `token="[redacted:token]"` and cannot unbalance a surrounding JSON string. |
| IN-07 | `fb54da4` | **fixed** — `redact()` now recurses into `set`/`frozenset` (returned as a list, like `tuple`) and decodes/redacts/re-encodes `bytes`/`bytearray` (non-UTF-8 passes through unchanged). Defence-in-depth; JSONB is JSON-typed so neither is reachable on the persistence path. |

## Info — skipped (with reason)

| ID | Reason |
|----|--------|
| IN-01 | No change required — the D-18 scope split is a conscious decision (pattern redaction does **not** run over persisted task text; only exact known secret values are scrubbed there). The finding is a flag for sign-off, not a defect. Adding the pattern table to task text would over-redact legitimate prose and contradict D-18. |
| IN-03 | The de-duplication (import `_RUN_STATUS` into migration `0001` instead of redefining it) would require editing `0001`, which is already applied — out of bounds for this pass. The `alembic check` drift gate already fails loudly on divergence, so the risk the finding describes is covered. |
| IN-08 | Purely stylistic micro-optimisation (`current_node` does an index scan then re-indexes); the review itself notes "correctness is fine". Not worth a change against otherwise-stable code. |
| IN-09 | Explicitly out of Phase 1 scope per the review ("Out of Phase 1 scope; noted because..."). Role-name → run-status indirection is a Phase 3 concern (config-driven pipelines); no custom role names exist yet. |

## Verification

Commands run from the repo root (`.env` sourced for the `db` / `integration` tiers).

- `uv run ruff check .` → **PASS** (exit 0), "All checks passed!"
- `uv run ruff format --check` over all tracked `*.py` → **PASS**, "82 files already formatted".
  (`ruff format --check .` also reports 7 pre-existing Markdown files under
  `.claude/` and `.planning/` — untouched by this work, flagged identically at
  the pre-fix baseline.)
- `uv run mypy src/dark_factory` (strict) → **PASS** (exit 0), "no issues found in 36 source files".
- `uv run pytest -m "unit or contract" -q` → **173 passed, 94 deselected** (exit 0).
- `uv run pytest -m "db or integration" -q` → **94 passed, 173 deselected** (exit 0, 641 s against the remote throwaway Postgres).
- Full suite: the two runs above partition every marker exactly (173 passed / 94
  deselected and 94 passed / 173 deselected — no unmarked test), so all **267**
  tests pass. Migration `0002` additionally verified by hand:
  `alembic upgrade head` → `alembic downgrade 0001_walking_skeleton` →
  `alembic upgrade head`, then `alembic check` → "No new upgrade operations detected."

_Fixer: Claude (gsd-code-fixer) · 2026-09-08_
