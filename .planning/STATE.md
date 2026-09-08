---
gsd_state_version: "1.0"
current_phase: 01
current_phase_name: Walking Skeleton — One Durable Run
status: executing
stopped_at: Completed 01-06-PLAN.md
last_updated: "2026-09-08T09:42:04.569Z"
last_activity: 2026-09-07
last_activity_desc: Phase 01 execution started
state_head: 7de973ff587e513ea0f42b4de697dee2b3e8ec76
progress:
  total_phases: 12
  completed_phases: 0
  total_plans: 9
  completed_plans: 6
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-06)

**Core value:** A delivery run is durable — its complete lifecycle state lives in Neon, so any process on any machine can resume exactly where a previous one stopped and still produce a correct, independently verified GitHub PR.
**Current focus:** Phase 01 — Walking Skeleton — One Durable Run

## Current Position

Phase: 01 (Walking Skeleton — One Durable Run) — EXECUTING
Plan: 6 of 9
Status: Ready to execute
Last activity: 2026-09-07 — Phase 01 execution started

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P02 | 20min | 3 tasks | 19 files |
| Phase 01 P03 | 15min | 2 tasks | 9 files |
| Phase 01 P04 | 40min | 3 tasks | 12 files |
| Phase 01 P05 | 35min | 2 tasks | 7 files |
| Phase 01 P06 | 26 min | 3 tasks | 17 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Tracer-first (PROJECT_MODE = mvp) — Phase 1 is a walking skeleton (minimal Neon persistence + enum FSM with resume-first `advance(run_id)` + FakeWorker + one role + `run`/`status`), every later phase adds a vertical slice.
- [Roadmap]: Checkpoint-in-Postgres, not replay — control state read from `runs` columns; `run_events` is append-only audit only.
- [Roadmap]: Postgres-only concurrency — conditional-UPDATE lease + guarded status update; no distributed-lock service.
- [Roadmap]: Real worker adapters split across two phases — Claude Code first (Phase 7) to prove the vertical slice, then Copilot + Hermes (Phase 8) to prove worker independence.
- [Phase 01]: 01-02: WorkerResult is a frozen extra=forbid pydantic v2 model with the 7 WORK-08 fields plus optional error; question-less NEEDS_INPUT rejected by model_validator
- [Phase 01]: 01-02: RunStatus defines all 10 STATE-07 values up front; STOP_STATUSES kept distinct from TERMINAL_STATUSES so Phase 2 adds WAITING_HUMAN to one line (D-06)
- [Phase 01]: 01-02: CodingWorker ABC (execute/resume/capabilities) + WorkerRegistry name->factory map + shipped FakeWorker; contract suite parametrized for Phases 7-8 real adapters
- [Phase 01]: 01-03: Task 1 checkpoint decided known-values-only (D-18) — persisted task text scrubbed only for exact SecretStr values; full D-15 pattern redaction on events/results/logs
- [Phase 01]: 01-03: one recursive redact() is the sole scrubbing path (D-14); scrub_known_values() is a patterns=False alias; idempotent; [redacted:<label>] tokens
- [Phase 01]: 01-03: Settings.known_secret_values() walks model_fields + isinstance(SecretStr) so later-phase credentials are covered automatically; get_settings() lru_cache singleton
- [Phase 01]: 01-04: Task 1 checkpoint = recommended (A1 UUID v4 keys + B1 sa.Enum native_enum=False ten-value CHECK status + C1 BigInteger IDENTITY run_events.seq); migration 0001_walking_skeleton applied + round-tripped against real PostgreSQL 18.6, alembic check shows no ORM drift
- [Phase 01]: 01-04: migrations/env.py resolves the DDL URL DATABASE_URL_DIRECT -> DATABASE_URL -> DARK_FACTORY_TEST_DATABASE_URL and include_name-scopes alembic check to the three owned tables (shared throwaway DB); alembic.ini sqlalchemy.url stays blank
- [Phase 01]: 01-05: create_run is a sibling of apply_transition in mutations.py (one module / one transaction discipline / one redact() call), not a call into it — the ∅→CREATED insert has no row for the expected_status guard
- [Phase 01]: 01-05: apply_transition opens exactly one with session.begin(); no explicit commit call; redact() at the single call site before every result/error/payload write; attempt = SQL MAX(attempt)+1 per run+role inside the transaction (D-19)
- [Phase 01]: 01-05: load_run_state returns a frozen detached RunState built from scalar columns + the single latest role_executions row; never queries run_events; imports nothing from dark_factory.events (STATE-06)
- [Phase 01]: 01-05: test_single_mutation_path.py is an AST source-tree guard proving mutations.py is the only module that constructs RunEvent/RoleExecution or assigns .status
- [Phase 01]: 01-06: advance/drive/start_run/run_state take session_factory / registry / pipeline as keyword-only params with production defaults — the test injection seam; advance still takes exactly one required arg (run_id)
- [Phase 01]: 01-06: lifecycle.transition is typed against a structural Protocol, not RunState, so the pure module imports nothing from dark_factory.persistence and contains no Session
- [Phase 01]: 01-06: start_run(source: str) owns classify->load->create_run and raises before any write; cli wraps it so exit 2 stays reserved for pre-persistence failures. CLI output: run id on stdout line 1, 'PREV -> NEXT' per transition, summary block, exit 0/1/2

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

Three research-flagged decisions, each scheduled inside the phase that first needs it:

- Artifact-content durability for cross-machine resume → resolve in Phase 5 (leading option: commit artifacts to the run's working branch). Schema implications noted in Phase 1.
- Lease TTL vs. unpredictable agent step duration → resolve in Phase 2 (heartbeat every TTL/3; slow-step + competing-process test).
- Exact non-interactive flag/env matrix for the Copilot and Hermes CLIs → hands-on spike in Phase 8; can be spiked earlier to de-risk.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-09-08T09:41:52.433Z
Stopped at: Completed 01-06-PLAN.md
Resume file: None
