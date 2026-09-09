---
gsd_state_version: "1.0"
current_phase: 02
current_phase_name: Pause, Resume & Single-Owner Execution
status: executing
stopped_at: Completed 02-03-PLAN.md
last_updated: "2026-09-09T17:59:13.293Z"
last_activity: 2026-09-09
last_activity_desc: Phase 02 execution started
state_head: 487f45df5872a24b8696b365f3b33b7cd6ca20ba
progress:
  total_phases: 12
  completed_phases: 1
  total_plans: 16
  completed_plans: 12
  percent: 8
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-06)

**Core value:** A delivery run is durable — its complete lifecycle state lives in Neon, so any process on any machine can resume exactly where a previous one stopped and still produce a correct, independently verified GitHub PR.
**Current focus:** Phase 02 — Pause, Resume & Single-Owner Execution

## Current Position

Phase: 02 (Pause, Resume & Single-Owner Execution) — EXECUTING
Plan: 4 of 7
Status: Ready to execute
Last activity: 2026-09-09 — Completed 02-03 (tracer: pause + resume --answer end to end under a Postgres lease)

Progress: [█░░░░░░░░░] 8%

## Performance Metrics

**Velocity:**

- Total plans completed: 11
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 9 | - | - |
| 02 | 2 | - | - |

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
| Phase 01 P07 | 40min | 3 tasks | 5 files |
| Phase 01 P08 | 40min | 2 tasks | 7 files |
| Phase 01 P09 | 45min | 2 tasks | 3 files |
| Phase 02 P01 | 55min | 3 tasks | 7 files |
| Phase 02 P02 | 11min | 2 tasks | 12 files |
| Phase 02 P03 | 95min | 2 tasks | 13 files |

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
- [Phase 01]: 01-07: DARK_FACTORY_CRASH_AFTER — shipped test-only env var read inside _maybe_crash_after every call (never cached at import), inert unless set, os._exit(137) after a named committed transition ('<PREV>_<NEXT>'); one function, wired after apply_transition in both step funcs
- [Phase 01]: 01-07: SC2 proven across two real OS processes sharing only the DB (child env from an allowlist, not os.environ.copy); SC4 proven with an after_cursor_execute listener parametrized over the role_executions and runs sub-writes — full rollback + still resumable
- [Phase 01]: 01-07: STATE-08 complete — killed run resumed by a fresh process to the same terminal state/attempt, and a fresh-engine-per-step drive is byte-identical to a shared-engine drive; orchestrator module holds no mutable public state across a drive
- [Phase 01]: 01-08: read_status lives in a new observability/ tier, does two selects (runs row + latest role_executions row), imports nothing from dark_factory.events transitively (AST import-graph guard), and performs no write — SC3 proven invariant under an inserted/deleted/corrupted run_events row
- [Phase 01]: 01-08: source redaction for status output is applied by the CLI via an injected redactor (functools.partial(redact, known_secrets=...)), so RunView and the read path stay free of any dark_factory.events import while the source is still scrubbed in both text and --json modes
- [Phase 01]: 01-08: RunView is a frozen pydantic DTO with the exact D-12 field set; as_text() and as_json() share one model_dump(mode=json) renderer and iterate model_fields so the text field set and JSON key set cannot drift
- [Phase 01]: 01-09: SC5 proven end to end — a real run seeded with four credential shapes in its task text + a credential in the FakeWorker summary reaches COMPLETED, leaves a [redacted: token, and leaves zero seeded/configured secrets across every event payload, every role_executions result/error, a whole-table sweep, and a real structlog sink (presence-then-absence)
- [Phase 01]: 01-09: phase acceptance gate (tests/integration/test_phase_acceptance.py) maps SC1-SC5 to named proof files and fails (never skips) on a missing/empty proof, criterion named in the message
- [Phase 01]: 01-09: real-Neon human check DEFERRED to /gsd-verify-work — automated substitute run against throwaway PostgreSQL 18.6 (no Neon PG17 project provisioned); carried PG-18.6-vs-17 deviation since 01-01
- [Phase 02]: 02-01: Task 1 checkpoint = recommended (A2-TEXT + A3-NOT-NULL + A4-ONE-REVISION) — human_interactions.question is a single TEXT column (newline-join of WorkerResult.questions), role_execution_id is NOT NULL, and one revision 0003_pause_resume_lease carries the table + partial unique index + the two runs lease columns together
- [Phase 02]: 02-01: _INTERACTION_STATUS is the _RUN_STATUS idiom reused at length=16 (VARCHAR+CHECK interaction_status, native_enum=False); WAITING/ANSWERED/CANCELLED enforced by PostgreSQL, CANCELLED declared but written nowhere this phase (inert CHECK value)
- [Phase 02]: 02-01: partial unique index uq_one_waiting_interaction_per_run (run_id WHERE status='WAITING') makes 'one open question per run' a DB invariant; runs.owner_token/lock_expires_at nullable no-default (NULL == claimable); revision 0003 applied + round-tripped, alembic check clean over the four owned tables
- [Phase 02]: 02-01: claim-don't-check proven before orchestrator/lease.py exists — one UPDATE ... WHERE (owner_token IS NULL OR lock_expires_at < func.now()) RETURNING; every expiry value/comparison is func.now(); db test module grep-clean of process-clock reads
- [Phase 02]: 02-02: STOP_STATUSES gains WAITING_HUMAN and is now a strict superset of the unchanged TERMINAL_STATUSES; EventType gains exactly QUESTION_CREATED/RUN_PAUSED/HUMAN_ANSWER_RECEIVED/RUN_RESUMED, pinned at ten members by a unit test
- [Phase 02]: 02-02: Open Decision 2 resolved in code — Settings.lease_ttl_seconds=900 / lease_heartbeat_seconds=300 as plain env-overridable ints, with a model_validator(mode=after) rejecting a non-positive TTL and a heartbeat>=TTL (message names both fields); neither field enters known_secret_values()
- [Phase 02]: 02-02: engine connect_args gains application_name=dark-factory (pg_stat_activity attribution for the HITL-08 idle-in-transaction proof); FakeWorker gains sleep_ms kwarg + DARK_FACTORY_FAKE_SLEEP_MS knob read at call time, inert when unset, inherited by resume()
- [Phase 02]: 02-02: tests/support/subprocess_runner.py is the single child-env allowlist (child_env/spawn/popen/run_id_from_stdout/wait_for); test_fresh_process_resume.py imports it. Fixtures use_lease_settings (env + get_settings cache-clear, 2s/1s) and force_lease_expiry (server-clock UPDATE, since time-machine cannot move the PG clock). HumanInteraction added to _LIFECYCLE_CTORS AST guard
- [Phase 02]: 02-03: claim-don't-check Postgres lease (one conditional UPDATE ... RETURNING) + run_lease context manager owning a daemon heartbeat; DB-clock-only expiry; token fence folded into apply_transition
- [Phase 02]: 02-03: submit_answer checks WAITING_HUMAN + pending-question preconditions BEFORE claiming the lease (deviation from plan prose) so a terminal/non-waiting run yields NotWaitingForHuman/exit 2, not LeaseNotAcquired/exit 0
- [Phase 02]: 02-03: column-driven resume — the persisted RESUMING marker on the role-execution row selects worker.resume() over worker.execute(); zero in-memory carryover across a crash

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

Last session: 2026-09-09T17:59:13.264Z
Stopped at: Completed 02-03-PLAN.md
Resume file: None
