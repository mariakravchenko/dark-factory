---
phase: 01-walking-skeleton-one-durable-run
verified: 2026-09-08T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/01-walking-skeleton-one-durable-run/01-01-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-01-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-02-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-02-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-03-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-03-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-04-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-04-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-05-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-05-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-06-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-06-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-07-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-07-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-08-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-08-SUMMARY.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-09-PLAN.md
  - .planning/phases/01-walking-skeleton-one-durable-run/01-09-SUMMARY.md
  - README.md
  - alembic.ini
  - migrations/env.py
  - migrations/versions/0001_walking_skeleton.py
  - migrations/versions/0002_role_exec_uniqueness.py
  - pyproject.toml
  - src/dark_factory/__init__.py
  - src/dark_factory/__main__.py
  - src/dark_factory/cli.py
  - src/dark_factory/config/__init__.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/domain/__init__.py
  - src/dark_factory/domain/signal.py
  - src/dark_factory/domain/status.py
  - src/dark_factory/domain/task.py
  - src/dark_factory/domain/views.py
  - src/dark_factory/domain/worker.py
  - src/dark_factory/events/__init__.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/events/redaction.py
  - src/dark_factory/input/__init__.py
  - src/dark_factory/input/loaders.py
  - src/dark_factory/input/resolver.py
  - src/dark_factory/logging.py
  - src/dark_factory/observability/__init__.py
  - src/dark_factory/observability/status.py
  - src/dark_factory/orchestrator/__init__.py
  - src/dark_factory/orchestrator/lifecycle.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/__init__.py
  - src/dark_factory/persistence/engine.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/roles/__init__.py
  - src/dark_factory/roles/registry.py
  - src/dark_factory/workers/__init__.py
  - src/dark_factory/workers/base.py
  - src/dark_factory/workers/fake.py
  - src/dark_factory/workers/registry.py
  - src/dark_factory/workflows/__init__.py
  - src/dark_factory/workflows/pipeline.py
covered_digest: "v1:sha256:004450a9252c07a5d7b29c5ca2f32aba409f096e10c50732ade19e035241a039"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run the documented README full-stack command against a real Neon project running PostgreSQL 17, using the POOLED DATABASE_URL (host contains -pooler) for the app and the DIRECT DATABASE_URL_DIRECT for Alembic: `cp .env.example .env` (fill both URLs), `uv sync --all-extras --dev`, `uv run alembic upgrade head`, `uv run dark-factory run text:\"add a health endpoint\"`, then `uv run dark-factory status <run-id>` and `--json`."
    expected: "`alembic upgrade head` applies cleanly through the direct endpoint; the run prints the run id on line 1, `CREATED -> BA`, `BA -> COMPLETED`, then the summary block, and exits 0; `status` reports COMPLETED / BA / attempt 1 from the pooled endpoint. No prepared-statement / PgBouncer error appears against the pooled host (the NullPool + prepare_threshold=None + pool_pre_ping settings are the thing being exercised for real)."
    why_human: "External managed service (Neon) with PgBouncer transaction pooling. Plan 01-09 declared this as a `user_setup` / end-of-phase human-check and it was NOT performed during execution (recorded as a deferred UAT item). All automated db/integration tests ran against a throwaway PostgreSQL 18.6 instance, never against Neon PG 17 with the pooled vs direct endpoint split. The pooled-endpoint behaviour the engine settings target is not covered by any automated test."
---

# Phase 1: Walking Skeleton — One Durable Run Verification Report

**Phase Goal:** A plain-text task becomes a durable run whose complete lifecycle lives in Neon and can be advanced to a terminal state by any fresh process, with a redacted audit trail — no AI, no GitHub, no quality gate.
**Verified:** 2026-09-08
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The walking-skeleton thesis is achieved in the codebase. A `text:` task becomes a
`runs` row plus a `role_executions` attempt row plus an append-only `run_events`
trail, all written through one mutation module inside one `with session.begin()`
transaction; `advance(run_id)` reconstructs the entire run from columns on every
call and executes exactly one committed step, so the happy path and the
resume/crash path are literally the same code; every persisted JSONB value and
every structlog line passes through one `redact()`. The full test suite
(`267 passed`, exit 0) runs green including every `db` / `integration` proof
against a real PostgreSQL.

The only gap is an environmental one: none of the durability evidence was
gathered against the real managed target (Neon PostgreSQL 17 with PgBouncer
pooling). That is a deliberately deferred end-of-phase human check, surfaced
below — not a code defect.

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC1 | `dark-factory run text:"..."` creates a run in Neon, drives it through one configured role using `FakeWorker` with zero external AI, reaches a terminal state | ✓ VERIFIED | `tests/integration/test_walking_skeleton.py::test_run_text_task_reaches_completed_end_to_end` — real `python -m dark_factory run text:...` subprocess against real PG: exit 0, run id on stdout line 1, `CREATED → BA` then `BA → COMPLETED`, `runs.status=COMPLETED`, one `role_executions` row (`role=BA`, `worker=fake`, `attempt=1`, `status=COMPLETED`), events `[RUN_CREATED, ROLE_STARTED, ROLE_COMPLETED, RUN_COMPLETED]`. `FakeWorker` default script, no network. Passed in the 267-test suite run. |
| SC2 | Killing the process mid-run and re-invoking from a brand-new process (no in-memory carryover) continues from the last committed step to the same terminal state | ✓ VERIFIED (behavior-dependent — behavioral test present) | `tests/integration/test_fresh_process_resume.py::test_killed_after_first_commit_then_resumed_by_a_separate_process` — process 1 armed `DARK_FACTORY_CRASH_AFTER=CREATED_BA` (`os._exit`, no unwind) dies the instant `CREATED→BA` commits; committed intermediate state asserted (`BA`, `RUNNING`, `result=None`, events `[RUN_CREATED, ROLE_STARTED]`); a *separate* subprocess with no crash var resumes to `COMPLETED`, same run id, `attempt` stays 1, run count unchanged. Reinforced by `tests/db/test_resume_first_advance.py` (fresh engine + sessionmaker per `advance` indistinguishable from shared; no mutable module-level state). |
| SC3 | `dark-factory status <run-id>` reports state, current role and attempt from state columns, never by folding the event log | ✓ VERIFIED | `tests/db/test_status_from_columns.py` — `RunView` unchanged after inserting a bogus event, deleting every event for the run, and corrupting an event's type; correct with a completely empty `run_events`. `tests/unit/test_status_import_graph.py` — transitive import closure of `dark_factory.observability.status` never reaches `dark_factory.events`. `read_status` issues two selects (`runs` + latest `role_executions`), none against `run_events` (`src/dark_factory/observability/status.py`). `tests/integration/test_status_cli.py` covers text + `--json` field-set parity and exit-2 on unknown/malformed id. |
| SC4 | A crash injected between the sub-writes of a transition leaves a consistent, resumable run — no state change without its `run_events` row, and vice versa | ✓ VERIFIED (behavior-dependent — behavioral test present) | `tests/db/test_transition_atomic.py` — an `after_cursor_execute` listener raises mid-`apply_transition`, parametrized over the `role_executions` write and the `runs` update; post-crash `runs.status` unchanged, `run_events` count unchanged, `role_executions.result` still NULL, then `drive()` reaches `COMPLETED` with no phantom attempt. `tests/db/test_state_event_pairing.py` — across every `advance` in a run (both terminal arms): a status-changing call adds ≥1 event, a no-op adds none; no orphan events. `apply_transition` rejects a status change with empty `events` (`ValueError`, before the transaction opens) and uses exactly one `with session.begin()` / one commit (`src/dark_factory/persistence/mutations.py`). |
| SC5 | A task whose text contains a `DATABASE_URL`-shaped value shows redacted values in every persisted event payload and every log line | ✓ VERIFIED | `tests/integration/test_secret_redaction_e2e.py` — a full run seeded with a credential-bearing task body (PG URI + password + `ghp_` token) and a worker summary carrying credentials; **presence-then-absence**: run asserted `COMPLETED`, `[redacted:` token asserted present in `run_events.payload`, then zero occurrences of seven forbidden literals across event payloads, `role_executions.result`/`error`, a whole-table sweep of all three tables, and a **real structlog sink** (`tests/support/log_sink.real_log_sink`, not `capture_logs`). D-18 scope split (doc-style URI kept in `normalized_task`, live configured values scrubbed everywhere) covered by `test_normalized_task_scope_split_...`. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Plan-level must-haves (spot-checked against code)

| Plan | Representative must-have | Status | Evidence |
| ---- | ----------------------- | ------ | -------- |
| 01-01 | pytest markers `unit/db/integration/contract` registered; `.env` git-ignored; `.env.example` holds names only | ✓ | `pyproject.toml [tool.pytest.ini_options].markers`; `uv run pytest -m "unit or contract"` → 173 passed, no marker warning; `.env` is git-ignored; `.env.example` documented (not read — secret guard). |
| 01-02 | `RunStatus` = all 10 STATE-07 values in one closed set; `TERMINAL_STATUSES`/`STOP_STATUSES` named constants; `WorkerResult` field-locked; `FakeWorker([])` raises `ScriptExhaustedError`; NEEDS_INPUT without questions rejected | ✓ | `src/dark_factory/domain/status.py`, `src/dark_factory/domain/worker.py` (`extra="forbid"`, `frozen`, `model_validator`), `src/dark_factory/workers/fake.py`; `tests/unit/test_domain_*`, `tests/unit/test_workers.py`, `tests/contract/`. |
| 01-03 | one `redact()`, recursive; PG-URI → `[redacted:database_url]`; sensitive dict key → `[redacted:<key>]`; `gh[porsu]_` / `github_pat_` tokens; `Authorization: Bearer`; known-value skip <8 chars; `patterns=False` leaves prose; real-sink log test | ✓ | `src/dark_factory/events/redaction.py`, `src/dark_factory/config/settings.py` (`known_secret_values`, `SecretStr`), `src/dark_factory/logging.py` (processor after `merge_contextvars`, before `JSONRenderer`); `tests/unit/test_redaction.py`, `test_log_redaction.py`, `test_settings.py`. |
| 01-04 | `alembic upgrade head` creates exactly `runs`/`role_executions`/`run_events`, no `human_interactions`/`artifacts`; downgrade/upgrade round-trips; `alembic check` no drift; `runs.status` carries all 10; branch + counter columns present; `run_events.seq` DB-generated identity; `timestamptz` from `func.now()`; `NullPool` + `pool_pre_ping` + `prepare_threshold=None`; Alembic on `DATABASE_URL_DIRECT` | ✓ | `migrations/versions/0001_walking_skeleton.py`, `src/dark_factory/persistence/models.py`, `src/dark_factory/persistence/engine.py`, `migrations/env.py`; `tests/db/test_migrations.py`, `tests/db/test_schema_shape.py` (passed in suite). |
| 01-05 | `mutations.py` is the sole constructor of `RunEvent` / assigner of `Run.status` / writer of `RoleExecution` (source-tree proof); one `with session.begin()`, no explicit `commit()`; redaction inside before every write; empty-events status change rejected; `expected_status` guard → `ConcurrentTransition`, nothing written; `attempt` = `MAX+1` in SQL; `load_run_state` returns a detached value object, never queries `run_events` | ✓ | `src/dark_factory/persistence/mutations.py`, `src/dark_factory/persistence/repositories.py`; `tests/unit/test_single_mutation_path.py` (AST walk + self-check), `tests/db/test_apply_transition.py`, `tests/db/test_load_run_state.py`. |
| 01-06 | `advance(run_id)` takes only an id, reconstructs from Neon every call, one committed step; `lifecycle.transition` pure (no Session, no I/O, reads only the mapped signal); illegal `(status, signal)` → `IllegalTransitionError`; ordered role list, no role count; `STOP_STATUSES` stop condition; terminal `advance` = zero writes; `resume` = identical drive loop; scripted FAILED → FAILED + ROLE_FAILED/RUN_FAILED, exit 1; exit 0/1/2 per D-05; `classify` pure, no I/O, BOM/whitespace not accepted, empty → `UnresolvableSourceError`; `spec:`/`github:` classify then loader raises `SourceNotSupportedError`, exit 2, no run | ✓ | `src/dark_factory/orchestrator/{runner,lifecycle}.py`, `src/dark_factory/workflows/pipeline.py`, `src/dark_factory/input/{resolver,loaders}.py`, `src/dark_factory/cli.py`; `tests/unit/test_lifecycle.py`, `test_resolver.py`, `test_loaders.py`, `tests/db/test_run_failure_path.py`, `test_terminal_advance_noop.py`, `tests/integration/test_exit_codes.py`, `test_unsupported_source.py`. |
| 01-07 | resumed run keeps its run id + attempt; injected crash inside `apply_transition` rolls back all sub-writes and stays resumable; every status-changing `advance` gains ≥1 event in the same commit; no orphan events; fresh engine/sessionmaker per `advance` reaches the same terminal state; no mutable module-level orchestrator state; crash hook inert unless env var set, in exactly one function | ✓ | `tests/integration/test_fresh_process_resume.py` (incl. `test_crash_hook_lives_in_exactly_one_function...` AST check), `tests/db/test_transition_atomic.py`, `test_state_event_pairing.py`, `test_resume_first_advance.py`; `src/dark_factory/orchestrator/runner.py::_maybe_crash_after`. |
| 01-08 | `read_status` queries only `runs` + latest `role_executions`, imports nothing from `events`; output invariant under event-log insert/delete/corruption; correct with empty event log; text + `--json` carry the same D-12 field set; `source` passed through redaction in both modes; unknown id → exit 2, empty stdout; freshly-created run → null role/attempt; no write of any kind | ✓ | `src/dark_factory/observability/status.py`, `src/dark_factory/domain/views.py`, `src/dark_factory/cli.py::status`; `tests/db/test_status_from_columns.py`, `tests/unit/test_status_import_graph.py`, `tests/integration/test_status_cli.py`. |
| 01-09 | end-to-end seeded run leaves zero secret occurrences across `run_events.payload`, `role_executions.result`/`error`, whole-table sweep and a real log sink, with ≥1 `[redacted:` token proving redaction ran; the five SCs each have a named passing test asserted present by the acceptance gate; `README.md` documents a paste-able full-stack run command + the deferred schema-shaping decisions | ✓ (automated) / ⚠️ (real-Neon run — see Human Verification) | `tests/integration/test_secret_redaction_e2e.py`, `tests/integration/test_phase_acceptance.py`, `README.md`. |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/dark_factory/domain/status.py` | `RunStatus` (10 values) + `TERMINAL_STATUSES` + `STOP_STATUSES` | ✓ VERIFIED | All 10 STATE-07 values; both sets are named module constants; imported by lifecycle, runner, models, repositories. |
| `src/dark_factory/domain/worker.py` | `WorkerResult` / `WorkerResultStatus` / `WorkerCapabilities` / `ArtifactRef` | ✓ VERIFIED | `frozen`, `extra="forbid"`; NEEDS_INPUT-without-question validator; defaults are `[]` not `None`. Wired into signal, fake, contract suite, runner. |
| `src/dark_factory/workers/{base,fake,registry}.py` | `CodingWorker` ABC, scripted `FakeWorker`, name→factory `WorkerRegistry` | ✓ VERIFIED | ABC with `execute`/`resume`/`capabilities`; `FakeWorker` consumes script in order, raises `ScriptExhaustedError`; `default_registry` binds `"fake"` to one process-lifetime instance (WR-05 fix). Wired into runner via `registry.get(node.worker)` — no name conditional. |
| `src/dark_factory/events/redaction.py` | one recursive `redact()` + `scrub_known_values` | ✓ VERIFIED | Single implementation; compiled D-15 pattern table; sensitive-key set; ≥8-char known-value floor; idempotent tokens. Called from `logging.py` processor and `mutations.py` (only two callers). |
| `src/dark_factory/config/settings.py` | `Settings` (SecretStr) + `get_settings` + `known_secret_values` | ✓ VERIFIED | `SecretStr` fields; `known_secret_values()` walks `model_fields` by `isinstance`; `log_level` validator. `lru_cache` singleton. |
| `src/dark_factory/logging.py` | `configure_logging()` installing the redaction processor | ✓ VERIFIED | Only `structlog.configure` call site; processor sits after `merge_contextvars`, before `JSONRenderer`; honours `Settings.log_level` (WR-02 fix). Wired on `run`/`resume`/`status --json` via `_route_logs_to_stderr` (WR-01 fix). |
| `src/dark_factory/persistence/models.py` | `Base`, `Run`, `RoleExecution`, `RunEvent` | ✓ VERIFIED | SQLAlchemy 2.0 typed ORM, separate from pydantic; VARCHAR+CHECK status (all 10), `seq` identity, `timestamptz` server defaults, nullable branch cols, non-null zero-default counters, `uq_role_exec_attempt`. |
| `src/dark_factory/persistence/engine.py` | `build_engine` + `new_session` (Neon-safe) | ✓ VERIFIED | `NullPool`, `pool_pre_ping=True`, `connect_args={"prepare_threshold": None}`; one tenacity retry on the initial connect only; scheme normalised to `postgresql+psycopg://`; no Neon import/hostname. |
| `migrations/versions/0001_walking_skeleton.py` | first revision: 3 tables, no `human_interactions`/`artifacts` | ✓ VERIFIED | Column set mirrors the ORM one-for-one; `downgrade` drops all three; `alembic check` clean (test passed in suite). |
| `migrations/versions/0002_role_exec_uniqueness.py` | `UNIQUE (run_id, role, attempt)` defence-in-depth (IN-02 fix) | ✓ VERIFIED | Separate reversible revision; matching `UniqueConstraint` in the ORM. |
| `migrations/env.py` | Alembic on `DATABASE_URL_DIRECT`, `target_metadata = Base.metadata` | ✓ VERIFIED | Resolution order `DATABASE_URL_DIRECT` → `DATABASE_URL` → `DARK_FACTORY_TEST_DATABASE_URL`; `include_name` scopes autogenerate/`check` to the three owned tables (shared test schema — deviation #2). |
| `src/dark_factory/persistence/mutations.py` | `create_run` + `apply_transition` — the one mutation path | ✓ VERIFIED | Sole writer (AST-proven); one `with session.begin()`; redaction at the single call site (incl. `runs.workflow`, WR-08 fix); `expected_status` guard; SQL `MAX(attempt)+1`; empty-events status change rejected. |
| `src/dark_factory/persistence/repositories.py` | `load_run_state` + `RunState` | ✓ VERIFIED | Two selects (`runs` + latest `role_executions` by `created_at DESC, attempt DESC, id DESC` — WR-04 fix); never selects `run_events`; returns a frozen detached pydantic value object. |
| `src/dark_factory/orchestrator/lifecycle.py` | pure `transition` + `IllegalTransitionError` | ✓ VERIFIED | Typed against a structural `_RunStateView` Protocol — no persistence import; reads only `status`/`current_role`/`current_step` + the mapped `Signal`; enumerated graph; raises on any pair not in it. |
| `src/dark_factory/orchestrator/runner.py` | `advance`, `drive`, `start_run` + the crash hook | ✓ VERIFIED | `advance` opens a fresh session, `load_run_state`, returns early when terminal, one `apply_transition`; nothing carried between calls; `RUN_COMPLETED` only when `next_status is COMPLETED` (WR-03 fix); `_maybe_crash_after` inert unless env var set, one call path. |
| `src/dark_factory/workflows/pipeline.py` | one-role `DEFAULT_PIPELINE`, iterated as an ordered list | ✓ VERIFIED | `RoleNode`/`Pipeline` frozen dataclasses; `current_node`/`next_node`/`index_of`; no role count encoded. |
| `src/dark_factory/input/resolver.py` | pure `classify` | ✓ VERIFIED | Prefix table `{text:,spec:,github:}`; `str.startswith` on code points; no I/O; empty/unmatched → `UnresolvableSourceError`. |
| `src/dark_factory/input/loaders.py` | `{SourceKind: loader}` mapping; text loader real, spec/github raise | ✓ VERIFIED | `_LOADERS` dict dispatch (no kind conditionals); `_load_text` strips quotes/whitespace, refuses empty; `_load_spec`/`_load_github` raise `SourceNotSupportedError` naming the phase. |
| `src/dark_factory/cli.py` | Typer app: `run`, `resume`, `status` + D-05 exit codes | ✓ VERIFIED | Both drivers are thin wrappers over `drive`; run id echoed on line 1 before the loop; one line per transition; summary block; orchestration errors → stderr diagnostic + exit 2 (WR-07); COMPLETED → 0, persisted FAILED → 1. |
| `src/dark_factory/observability/status.py` | `read_status` + `UnknownRunError` | ✓ VERIFIED | Two selects, no `run_events`, no `events` import; raises `UnknownRunError`; null role/attempt for a run with no `role_executions`; no write. |
| `src/dark_factory/domain/views.py` | `RunView` D-12 field set + `as_text`/`as_json` | ✓ VERIFIED | Frozen; declaration order = render order; optional `redactor` applied to `source_kind`/`source_ref` in both modes; branch fields always shown with `-`. |
| `README.md` | paste-able full-stack Neon run command + recorded schema decisions | ✓ VERIFIED | §"Run the walking skeleton against a real Neon project" (pooled vs direct URL guidance, `alembic upgrade head`, `run`, `status`, `--json`); exit-code table; §"Decisions recorded here, enforced later" (branch cols → Phase 5, counters → Phase 9, artifacts-as-references / no `artifacts` table). |
| `tests/support/log_sink.py` | real-sink structlog capture helper | ✓ VERIFIED | Attaches the production chain to a `StringIO`; explicitly not `structlog.testing.capture_logs`; restores prior config. Reused by the SC5 e2e test. |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `orchestrator/runner.py` | `persistence/repositories.py` | `advance` calls `load_run_state` first on every invocation | ✓ WIRED |
| `orchestrator/runner.py` | `persistence/mutations.py` | commits its single step through `apply_transition`, never writes state directly | ✓ WIRED (AST-proven sole writer) |
| `orchestrator/runner.py` | `workers/registry.py` | worker obtained by `registry.get(node.worker)`, no name conditional | ✓ WIRED |
| `cli.py` | `orchestrator/runner.py` | `run` and `resume` both call `drive(...)` | ✓ WIRED |
| `persistence/mutations.py` | `events/redaction.py` | `redact()` / `scrub_known_values` on result, error and every payload before `session.add` | ✓ WIRED |
| `logging.py` | `events/redaction.py` | redaction processor in the `structlog.configure` chain before the renderer | ✓ WIRED |
| `migrations/env.py` | `persistence/models.py` | `target_metadata = Base.metadata` | ✓ WIRED (`alembic check` clean) |
| `observability/status.py` | `persistence/models.py` | selects `Run` + latest `RoleExecution`, never `RunEvent` | ✓ WIRED |
| `cli.py::status` | `observability/status.py` | `read_status` is the command's only data source; body has no `RunStatus` comparison | ✓ WIRED (`test_status_command_body_carries_no_lifecycle_logic`) |
| `tests/integration/test_fresh_process_resume.py` | `src/dark_factory/__main__.py` | two independent `python -m dark_factory` subprocesses sharing only the DB | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Rendered / persisted value | Source | Real data? | Status |
| -------------------------- | ------ | ---------- | ------ |
| `status` output (state/role/step/attempt/timestamps) | `read_status` → `runs` + latest `role_executions` columns | Yes — live column reads, proven invariant under event-log vandalism | ✓ FLOWING |
| `run_events` stream for a run | `apply_transition` / `create_run` `session.add(RunEvent(...))` inside the commit | Yes — one row per `EventWrite`, ordered by DB `seq` | ✓ FLOWING |
| `role_executions.attempt` | `SELECT coalesce(max(attempt),0)+1` inside the transaction | Yes — computed in SQL under the `runs` row lock, never an in-memory counter | ✓ FLOWING |
| `RunState` fed to `advance` | `load_run_state` scalar column reads → frozen pydantic object | Yes — no ORM instance, no session retained; fresh-engine-per-step test proves nothing cached is load-bearing | ✓ FLOWING |
| redacted payload / log line | `redact(value, known_secrets=get_settings().known_secret_values())` | Yes — e2e seeded-secret sweep finds zero leaks + ≥1 `[redacted:` token | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Package imports from src layout | `uv run python -c 'import dark_factory'` (via `uv run pytest` collection) | suite collected & ran | ✓ PASS |
| Lint | `uv run ruff check .` | `All checks passed!` | ✓ PASS |
| Types (strict) | `uv run mypy src/dark_factory` | `Success: no issues found in 36 source files` | ✓ PASS |
| Unit + contract tier | `uv run pytest -m "unit or contract" -q` | `173 passed, 94 deselected in 0.23s` | ✓ PASS |
| Full suite incl. db + integration (vs. the throwaway test PostgreSQL) | `uv run pytest -q` (with `DARK_FACTORY_TEST_DATABASE_URL` set) | `267 passed in 637.34s`, exit 0 | ✓ PASS |
| Phase acceptance gate | `tests/integration/test_phase_acceptance.py` | all 5 SC mapped to existing proof files carrying `def test_` | ✓ PASS (within the suite run) |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | — | No `scripts/*/tests/probe-*.sh` and no probe declared in any PLAN/SUMMARY | N/A |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| INTAKE-01 | 01-06 | Start a run from plain text | ✓ SATISFIED | `cli.run` → `start_run` → `classify`/`load` → `create_run`; `test_walking_skeleton`, `test_exit_codes`. |
| INTAKE-04 | 01-06 | Deterministic source classification, no LLM, no repo/GitHub/run | ✓ SATISFIED | `input/resolver.classify` pure prefix; `tests/unit/test_resolver.py`. |
| INTAKE-05 | 01-06 | Source-specific loader → one `NormalizedTask`, origin-agnostic | ✓ SATISFIED | `input/loaders.load` mapping; `domain/task.NormalizedTask`; `tests/unit/test_loaders.py`. |
| ORCH-01 | 01-06 | Deterministic orchestrator, not one LLM loop | ✓ SATISFIED | Pure `lifecycle.transition`; `runner.advance` enumerated control flow; no model call anywhere on the path. |
| ORCH-05 | 01-06 | Only the orchestrator changes lifecycle state; a worker result never drives a transition | ✓ SATISFIED | `signal_from_result` reads only `result.status`; `WorkerResult` frozen; `test_single_mutation_path`. |
| ORCH-06 | 01-05, 01-07 | Every lifecycle mutation in a single transaction through one mutation path | ✓ SATISFIED | `mutations.py` sole writer (AST proof); one `with session.begin()`; `test_apply_transition`, `test_transition_atomic`. |
| STATE-01 | 01-01, 01-04 | SQLAlchemy + Alembic + PostgreSQL; only `DATABASE_URL`; no provider logic | ✓ SATISFIED | `engine.py`, `models.py`, `migrations/env.py`; no Neon import/hostname; scheme normalisation only. |
| STATE-02 | 01-04, 01-08, 01-09 | `runs` table column set | ✓ SATISFIED | `models.Run` + migration 0001; `test_schema_shape`. |
| STATE-03 | 01-04, 01-05, 01-08 | `role_executions` one row per attempt | ✓ SATISFIED | `models.RoleExecution` (+ `uq_role_exec_attempt`); attempt starts at 1, retry = new row; `test_apply_transition`. |
| STATE-06 | 01-04, 01-05, 01-08 | `run_events` append-only; position read from columns, never by folding events | ✓ SATISFIED | `models.RunEvent.seq`; `load_run_state`/`read_status` never query `run_events`; `test_status_from_columns`, `test_status_import_graph`. |
| STATE-07 | 01-02 | 10-value status set; active role stored separately | ✓ SATISFIED | `domain/status.RunStatus`; `runs.status` CHECK carries all 10; `runs.current_role` separate. |
| STATE-08 | 01-06, 01-07 | Execution fully reconstructable from persisted data | ✓ SATISFIED | `RunState` = columns only; `test_resume_first_advance`, `test_fresh_process_resume`. |
| WORK-01 | 01-02 | One `CodingWorker` contract — `execute`/`resume`/`capabilities` | ✓ SATISFIED | `workers/base.py` ABC; contract suite. |
| WORK-03 | 01-02, 01-06 | No worker-specific branching in orchestrator/workflow | ✓ SATISFIED | Registry lookup only; `tests/unit/test_no_worker_name_leak.py` (scan exempts `workers/`, `config/`). |
| WORK-08 | 01-02 | Every adapter normalizes to one `WorkerResult` shape | ✓ SATISFIED | `domain/worker.WorkerResult` (`extra="forbid"`, defaults `[]`). |
| WORK-10 | 01-02, 01-06 | `FakeWorker` returns a scripted sequence, no external AI | ✓ SATISFIED | `workers/fake.py`; `tests/unit/test_workers.py`, contract suite, every db/integration drive. |
| SEC-02 | 01-03, 01-05, 01-09 | Redaction applied to persisted payloads + logs from the first persistence code, not retrofitted | ✓ SATISFIED | `redaction.py` invoked inside `create_run`/`apply_transition` and in the structlog chain; `test_secret_redaction_e2e` (presence-then-absence). |

No ORPHANED requirements: ROADMAP §"Phase 1" lists exactly these 17 IDs and every one appears in a PLAN `requirements:` field. REQUIREMENTS.md marks all 17 `[x]` / "Complete", consistent with the code and tests.

### Cross-Cutting Invariants

| Invariant (from ROADMAP) | Status | Evidence |
| ------------------------ | ------ | -------- |
| Every lifecycle mutation commits in ONE transaction through one mutation path | ✓ | `tests/unit/test_single_mutation_path.py`; one `with session.begin()` in `mutations.py`. |
| Every `resume()` input is a persisted column — zero in-memory carryover | ✓ | `RunState` fields all columns; `tests/db/test_resume_first_advance.py`; runner docstring + no mutable module state. |
| Control state read from state columns, never by folding `run_events` | ✓ | `load_run_state` / `read_status`; `tests/unit/test_status_import_graph.py`, `tests/db/test_status_from_columns.py`. |
| Only the orchestrator mutates lifecycle state; worker results are typed signals | ✓ | `signal_from_result` (status-only); frozen `WorkerResult`; `lifecycle.transition` pure. |
| Secret redaction applied in the first persistence code, never retrofitted | ✓ | Redaction present inside `create_run` from Plan 04/05; `test_secret_redaction_e2e`. |
| No worker-name branching outside adapters | ✓ | `tests/unit/test_no_worker_name_leak.py` (guard active now, hard CI gate is Phase 7). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | `grep -rnE "TODO|FIXME|XXX|TBD|HACK|PLACEHOLDER|not yet implemented|coming soon"` over `src/` | ℹ️ Info | Zero matches. No debt markers in phase-modified source. |
| `persistence/repositories.py:101`, `workers/fake.py:49`, `workflows/pipeline.py:61` | — | `return None` | ℹ️ Info | All legitimate: unknown-run sentinel, unset-env sentinel, last-node sentinel — each has a caller that handles `None`. Not stubs. |
| `persistence/engine.py:82` | — | bare `pass` | ℹ️ Info | Body of `with engine.connect(): pass` — the cold-start warm-up connection. Intentional. |

### Test Quality Audit

| Aspect | Finding |
| ------ | ------- |
| Disabled tests on requirements | None — `grep` for `skip`/`xfail`/`todo` across `tests/` returns nothing on requirement-linked files. |
| Circular tests | None — no test generates its expected values by running the system under test; SC assertions are on independently-stated event sequences, status literals and secret literals. |
| Assertion strength | Behavioural / value-level throughout: subprocess exit codes + stdout contract, exact event-type sequences, column values, presence-then-absence secret sweeps, AST structural guards. The SC5 proof explicitly asserts a `[redacted:` token is present *before* any absence assertion (guards against the false-green on an unwritten payload). |
| Coverage quantity | Full suite `267 passed` (173 unit/contract + 94 db/integration), exit 0. |

### Decision Coverage

CONTEXT.md carries a large `<decisions>` set (D-01…D-23). Spot-check of the
load-bearing ones against shipped artifacts: D-01 (run id on stdout line 1) —
`cli.run`; D-02 (resume-first `advance`) — `runner.advance`; D-05 (0/1/2 exit
codes) — `cli._drive_and_exit` + `test_exit_codes`; D-06 (`STOP_STATUSES` one-line
Phase-2 edit) — `domain/status`; D-08 (all 10 statuses from revision 0001) —
`models` + migration; D-09 (no role count) — `workflows/pipeline`; D-11 (status
read imports no events) — `test_status_import_graph`; D-14 (one `redact()`) —
`events/redaction`; D-18 (`patterns=False` for task text) —
`scrub_known_values` + `test_normalized_task_scope_split`; D-19 (counters are
columns) — `models` + `apply_transition`; D-21/D-22 (no `artifacts` table,
append-only `run_events`) — migration 0001 + README. All observed. Non-blocking
gate — no drift found.

### Assessment of Known Deviations (not re-discovered — evaluated)

| # | Deviation | Assessment |
| - | --------- | ---------- |
| 1 | All `db`/`integration` tests ran against PostgreSQL 18.6, not Neon-parity PG 17 | **Does not undermine any durability claim.** The guarantees rest on standard SQL/MVCC: single-transaction commit/rollback (`with session.begin()`), `SELECT … FOR UPDATE` row lock, `GENERATED BY DEFAULT AS IDENTITY` for `run_events.seq`, `VARCHAR + CHECK` for status, `timestamptz` + `now()`. All behave identically 17 ↔ 18. 267/267 pass on 18.6. The residual risk is Neon/PgBouncer-specific (pooled endpoint, prepared-statement negotiation) — covered by the Human Verification item below, not by a version bump. Recorded as INFO. |
| 2 | Shared test schema; `alembic check` / autogenerate scoped via `include_name` to the three owned tables; per-test isolation via a rolled-back outer transaction | **Acceptable.** `include_name` only prevents autogenerate from proposing to drop unrelated tables; it does not weaken drift detection on `runs`/`role_executions`/`run_events`. Isolation via `join_transaction_mode="create_savepoint"` + outer rollback is a standard, sound pattern. No impact on the goal. |
| 3 | Plan 01-09's real-Neon acceptance human-check was **not** performed (`human_verify_mode: end-of-phase`) | **Genuine open item — surfaced as the single Human Verification item.** README documents the command; it has never been run against a real Neon project with the pooled + direct URL split. |
| 4 | `tests/integration/test_status_cli.py::test_json_key_set_equals_the_text_field_set` has a hard-coded 120 s subprocess timeout and occasionally times out against the slow remote PG | **Not a logic defect.** Passed in this verifier's full-suite run (`267 passed`) and reported 8/8 in isolation. Recorded as INFO — consider raising/removing the fixed timeout or gating it on a faster backend. |
| 5 | WR-07 resolved as "stderr diagnostic + exit 2" for orchestration errors, rather than "persist FAILED + exit 1" | **Satisfies the D-05 contract.** The caught set (`ConcurrentTransition`, `IllegalTransitionError`, `DriveLoopExhausted`, `RunNotFoundError`, `ScriptExhaustedError`, `UnknownWorkerError`) all leave nothing new persisted — the transaction rolled back or never opened — which is exactly the "exit 2 = nothing persisted/advanced" case. A *scripted* `WorkerResult(status=FAILED)` still flows through the normal `ROLE_FAILED` branch → persists `FAILED` + `RUN_FAILED` → exit 1 (`test_exit_codes.py::test_exit_1_when_the_worker_script_supplies_a_failed_result`, passing). The one edge — a run left at `BA`/`RUNNING` after `IllegalTransitionError` on a Phase-1 `NEEDS_INPUT` result — is squarely Phase 2 scope (pause/resume). No contract violation. |

### Human Verification Required

#### 1. Real-Neon full-stack run (deferred end-of-phase check, Plan 01-09 `user_setup`)

**Test:** With a real Neon project on PostgreSQL 17, set `DATABASE_URL` to the
**pooled** connection string (host contains `-pooler`, scheme rewritten to
`postgresql+psycopg://`) and `DATABASE_URL_DIRECT` to the **direct** string
(host without `-pooler`). Then, from a clean checkout:
`cp .env.example .env` and fill both URLs → `uv sync --all-extras --dev` →
`uv run alembic upgrade head` → `uv run dark-factory run text:"add a health endpoint"` →
`uv run dark-factory status <run-id>` and `uv run dark-factory status <run-id> --json`.

**Expected:** `alembic upgrade head` applies cleanly through the direct endpoint
(creates `runs`, `role_executions`, `run_events`). `run` prints the run id on
line 1, then `CREATED → BA`, `BA → COMPLETED`, then the summary block, exit 0.
`status` reports `COMPLETED` / `current_role: BA` / `latest_attempt: 1` read
through the pooled endpoint. No PgBouncer / prepared-statement error against the
pooled host — the `NullPool` + `prepare_threshold=None` + `pool_pre_ping`
settings in `engine.py` are what this exercises for real.

**Why human:** External managed service with PgBouncer transaction pooling. The
automated suite only ever ran against a throwaway PostgreSQL 18.6 with a single
URL; the pooled-vs-direct behaviour and Neon cold-start path that `engine.py` and
`migrations/env.py` specifically target have no automated coverage. This was
explicitly deferred at execution time.

### Gaps Summary

No code gaps. Every ROADMAP Success Criterion maps to a named, currently-passing
automated test; all 17 phase requirements have a real code + test basis; the six
cross-cutting invariants are each enforced by a structural or behavioural test;
`ruff` and `mypy --strict` are clean; there are no debt markers or stubs in
phase-modified source. The single outstanding item is environmental — the
deferred real-Neon full-stack run — and is recorded above for a human to execute.
Status is `human_needed` on that basis, not on any missing deliverable.

---

_Verified: 2026-09-08_
_Verifier: Claude (gsd-verifier)_
