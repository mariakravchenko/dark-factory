---
gsd_state_version: "1.0"
current_phase: 10
current_phase_name: GitHub — Issue Intake, Idempotent Publishing, Comment Resume
status: executing
stopped_at: Completed 10-02-PLAN.md
last_updated: "2026-09-27T11:15:33.716Z"
last_activity: 2026-09-26
last_activity_desc: Phase 10 execution started
state_head: 659b3532fd28ae2a0f0e85cac6c9f518239e02ab
progress:
  total_phases: 12
  completed_phases: 0
  total_plans: 57
  completed_plans: 54
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-26)

**Core value:** A delivery run is durable — its complete lifecycle state lives in Neon, so any process on any machine can resume exactly where a previous one stopped and still produce a correct, independently verified GitHub PR.
**Current focus:** Phase 10 — GitHub — Issue Intake, Idempotent Publishing, Comment Resume

## Current Position

Phase: 10 (GitHub — Issue Intake, Idempotent Publishing, Comment Resume) — EXECUTING
Plan: 4 of 6
Status: Ready to execute
Last activity: 2026-09-26 — Phase 10 execution started

Progress: [░░░░░░░░░░] 0% (9/12 phases)

## Performance Metrics

**Velocity:**

- Total plans completed: 51
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 9 | - | - |
| 02 | 7 | - | - |
| 03 | 4 | - | - |
| 04 | 5 | - | - |
| 05 | 6 | - | - |
| 06 | 4 | - | - |
| 07 | 4 | - | - |
| 08 | 6 | - | - |
| 09 | 6 | - | - |

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
| Phase 02 P04 | close-out | 2 tasks | 3 files |
| Phase 02 P05 | 180min | 2 tasks | 3 files |
| Phase 02 P06 | 75min | 2 tasks | 4 files |
| Phase 02 P07 | 120min | 2 tasks | 4 files |
| Phase 03 P01 | 9min | 3 tasks | 10 files |
| Phase 03 P02 | 5min | 2 tasks | 13 files |
| Phase 03 P03 | 22min | 3 tasks | 25 files |
| Phase 03 P04 | 32min | 3 tasks | 7 files |
| Phase 04 P01 | 85min | 3 tasks | 38 files |
| Phase 04 P02 | 15min | 2 tasks | 4 files |
| Phase 04 P03 | 150min | 3 tasks | 17 files |
| Phase 04 P04 | 90min | 3 tasks | 4 files |
| Phase 04 P05 | 17min | 3 tasks | 5 files |
| Phase 05 P04 | ~12min authoring | 3 tasks | 14 files |
| Phase 05 P05 | 20min | 2 tasks | 1 files |
| Phase 05 P06 | 35min | 3 tasks | 3 files |
| Phase 06 P01 | 13min task-commits + ~57min db-tier verification | 3 tasks | 28 files |
| Phase 06 P02 | 55min | 2 tasks | 7 files |
| Phase 06 P03 | 135min | 3 tasks | 5 files |
| Phase 06 P04 | 65min | 2 tasks | 4 files |
| Phase 07 P01 | 9min | 3 tasks | 7 files |
| Phase 07 P02 | 12min | 2 tasks | 2 files |
| Phase 07 P03 | 12min | 3 tasks | 4 files |
| Phase 07 P04 | 14min | 2 tasks | 4 files |
| Phase 08 P06 | 90min | 2 tasks | 21 files |
| Phase 09 P04 | 35min | 2 tasks | 4 files |
| Phase 09 P05 | 25min | 1 tasks | 2 files |
| Phase 09 P06 | 20min | 1 tasks | 2 files |
| Phase 10 P01 | 55min | 3 tasks | 14 files |
| Phase 10 P06 | ~2h40min | 2 tasks | 16 files |
| Phase 10 P02 | 55min | 2 tasks | 3 files |

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
- [Phase 02]: 02-04: no production code changed — plan is proof-only for the 02-03 lease; HITL-07 proven adversarially by a 16-thread statement-level claim and a two-real-process race asserting invariants (one role-execution row, one ROLE_COMPLETED) not winners
- [Phase 02]: 02-04: SC4 reclaim proven twice — forced server-clock expiry (fast path) and a genuine 2s injected-TTL real elapsed wait (honesty check that the DB clock, not the forcing UPDATE, drives expiry); no time_machine/freezegun anywhere (they cannot move the Postgres clock)
- [Phase 02]: 02-04: race test synchronises on the committed DB condition status==BA AND owner_token IS NOT NULL via wait_for (never a fixed sleep); slow-step window set to 15s as a generous upper bound on a remote-Neon child cold-start, not a timing assertion
- [Phase 02]: 02-06: HITL-01 proven by projected-remainder equality — two pause outcomes collected as dicts, only role name + role-execution row identity projected out, remainders asserted equal (the honest form of 'the same code ran')
- [Phase 02]: 02-06: crash-injection runs_update point qualified ('UPDATE RUNS', 'STATUS') so it matches the lifecycle write, not the lease's own UPDATE runs (claim/renew/release touch only owner_token/lock_expires_at/updated_at)
- [Phase 02]: 02-06: proof-only, no production change — pause path already dispatches on the signal with no per-role branch and all five writes are already in one apply_transition transaction; multi-node role_executions row-reuse deferred to Phase 3 (deferred-items.md)
- [Phase 02]: 02-07: tests/integration/test_phase2_acceptance.py is a SIBLING of the Phase 1 gate, not an extension — two mappings (SC1-SC5 and the six requirement ids), each key set asserted exact, each proof file asserted existing/non-empty/contains def test_, a flat missing-path check, and a drift-guard tying the gate to 02-VALIDATION.md's per-requirement test map; grep-proven zero pytest.skip
- [Phase 02]: 02-07: pyproject [tool.ruff] extend-exclude = ['.planning', '.claude'] — ruff 0.16 reformats fenced Python in Markdown; the format/lint gates are scoped to real code so historical planning docs are not rewritten (Rule 3 deviation)
- [Phase 02]: 02-07: Phase 2 CLOSED — full suite 364 passed / 0 skipped (32m34s remote Neon), mypy --strict / ruff check / ruff format --check / alembic check all clean; README walkthrough fresh-eyes human check + production-TTL lease-timing smoke check deferred to /gsd-verify-work
- [Phase 03]: 03-02: PyYAML approved at checkpoint 1 (blocking-human legitimacy gate); pyyaml>=6,<7 runtime + types-PyYAML>=6,<7 dev (PyYAML 6.x ships no py.typed, mypy --strict needs the stub)
- [Phase 03]: 03-02: snapshot storage = reuse runs.workflow JSONB (no Alembic 0004, no config_snapshot column, no models.py/RunState change); column meaning widens from {roles:[...]} to the full effective-config snapshot
- [Phase 03]: 03-02: .dark-factory.yaml / role-YAML key names are the RESEARCH set verbatim (published contract); workflow.roles entries are RunStatus values (BA, ARCHITECTURE, ...), not human names — keeps transition()/answers.py untouched
- [Phase 03]: 03-02: load_effective_config is a pure read raising ConfigError(ValueError) — no Session/runs row/lock; yaml.safe_load only; worker+before/after names validated by membership; instruction path resolved under repo root, .is_file(), 64 KiB cap; config/ import-isolated from settings.py
- [Phase 03]: 03-03: start_run(source, *, session_factory, snapshot) - snapshot is a required kw with no default and no fabricated fallback; _workflow_snapshot + DEFAULT_PIPELINE removed from orchestrator/runner.py; _advance_once builds pipeline = pipeline_from_snapshot(state.workflow) right after the load_run_state / STOP_STATUSES early-return block when no Pipeline is injected
- [Phase 03]: 03-03: cli.py is the sole composition point importing dark_factory.config.loader - run() resolves load_effective_config(Path.cwd()) and maps ConfigError -> Exit(2) before printing the run id / creating a row; two guards lock it: test_no_role_name_literal.py (AST, no RunStatus role literal in orchestrator/ + workflows/pipeline.py) and test_orchestrator_no_live_config_read.py (import closure excludes config.loader; sanity proves cli's closure includes it)
- [Phase 03]: 03-03: DEFAULT_TEST_SNAPSHOT ({roles:[BA]}, legacy bare-string shape) in tests/support/config.py is the shared snapshot the ~15 Phase 1/2 in-process start_run call sites pass; test_pause_mechanism_generic.py swapped its pipeline=_TWO_NODE_PIPELINE arg for a local snapshot=_TWO_NODE_SNAPSHOT
- [Phase 03]: 03-04: _run_current_role fires configured before-hooks after _build_context (ahead of execute-vs-resume) and after-hooks after the lease-loss check, both OUTSIDE with session.begin(); a lost lease raises LeaseLost before the after-hooks; the apply_transition block is unchanged
- [Phase 03]: 03-04: action_registry is a keyword-only param on advance/drive/_advance_once/_run_current_role (default = dark_factory.actions.default_registry), threaded like registry: WorkerRegistry; _role_definition(state, role) is a data lookup by role value, a legacy bare-string roles entry -> {name, before: [], after: []} so hooks are a no-op for Phase 1/2 runs
- [Phase 03]: 03-04: the Phase 3 acceptance gate (tests/integration/test_phase3_acceptance.py) is a SIBLING of test_phase2_acceptance.py mapping SC1-SC4 + ORCH-02/ORCH-03/CFG-01..CFG-05/WORK-02 to present/non-empty/def-test_ proofs; _VALIDATION_PROOF_FILES (13) is drift-guarded against 03-VALIDATION.md; grep for a skip/opt-out call = 0
- [Phase 04]: 04-01: FakeWorker's true (unscripted) default no longer exhausts after one call — repeats a fresh COMPLETED result so the shipped two-role pipeline completes with no explicit script; explicit scripts (incl. empty) still exhaust.
- [Phase 04]: 04-01: build_role_context passes RoleContext as the object itself to worker.execute/resume (not a dict); role_def lookups use .get(...) throughout so the legacy bare-string snapshot shape still resolves.
- [Phase 04]: [Phase 04]: 04-02: _load_spec real loader implemented -- source_kind=spec, source_ref=resolved absolute path, title=first line with heading marker stripped, body=stripped file text; UnresolvableSourceError (not SourceNotSupportedError) on missing/empty file, naming the resolved path.
- [Phase 04]: [Phase 04]: 04-02: SourceNotSupportedError removed from loaders.__all__ (still imported by name everywhere) so the grep-count acceptance criterion (class def + single github: raise) holds without weakening the export.
- [Phase 04]: 04-03: Verdict.computed_status folds criteria+issues order-independently; two after-validators (duplicate criterion_id, declared-status-vs-computed) make verdict.json authoritative (D-04); AcceptanceCriteriaDocument shares the same min-length/no-duplicate-id rules
- [Phase 04]: 04-03: [Rule 1] Fixed a real orchestrator bug found building SC1 -- multi-role pipelines reused the first role's role_executions row for every later role (only _enter_first_role ever inserted a row). Added _enter_role generalising the insert-then-run split to every role; closes WINDOWS.md ledger item #6, open since Phase 2
- [Phase 04]: 04-03: SC1's literal ROADMAP wording names seven artifact filenames (BA also emits requirements.md, ARCHITECTURE also emits design.md, alongside the five JSON D-10 models), not the task prose's 'six' -- proved the literal seven rather than narrowing the shipped BA/ARCHITECTURE outputs contract
- [Phase 04]: [Phase 04]: 04-04: SC4's two-attempt state is constructed by driving apply_transition directly (RoleExecutionWrite insert-then-update per attempt) since no Phase 4 code path produces a genuine retry (QA-FAIL bounce is Phase 9); the query under test remains the real production query
- [Phase 04]: [Phase 04]: 04-04: SC5's QA scenarios use a one-role [QA]-only config tree rather than the full four-role pipeline -- D-06 needs only one QA attempt reaching a terminal state, isolating the proof from BA/ARCHITECTURE/DEVELOPMENT's own outputs contract
- [Phase 04]: [Phase 04]: 04-04: acceptance gate proof-file mappings were reconciled against the actual 04-0N-SUMMARY.md files rather than 04-VALIDATION.md's Wave-0 forecast (e.g. CTX-04 maps to this plan's own new proof, not 04-01's context-builder tests)
- [Phase 04]: [Phase 04]: 04-05: Extraction dispatches on content shape only (structural AcceptanceCriteriaDocument validation, then a carrier-line regex) — never on context.role — keeping D-08's role-agnostic FakeWorker invariant intact while still routing content correctly
- [Phase 04]: [Phase 04]: 04-05: Markdown outputs carry ids via a single accepted carrier-line style ('Criterion <id> met') so the DEVELOPMENT role, whose declared inputs are design.md/constraints.json and not acceptance_criteria.json, still receives ids through the markdown hop
- [Phase 04]: [Phase 04]: 04-05: Every extracted id is filtered to a single whitespace-free token under 64 chars before use, bounding what upstream artifact content can inject downstream (T-04-19/T-04-21)
- [Phase 05]: [Phase 05]: 05-04: is_out_of_scope is a single expression with no empty-list branch -- D-14 zero tolerance falls out of not any(...) over an empty iterable for free, never a special case
- [Phase 05]: [Phase 05]: 05-04: revert_paths branches on git cat-file -e HEAD:<path> before choosing restore vs rm+clean -- a single-mechanism revert silently leaves a newly-created violating file on disk
- [Phase 05]: [Phase 05]: 05-04: write-scope enforcement wired into runner.py after the D-09/D-16 artifact validate/commit/push sequence and before transition(); a violation clears artifact_writes and reuses the existing ROLE_FAILED/RUN_FAILED shape
- [Phase 05]: [Phase 05]: 05-05: G-05-1 closed as a test-defect fix -- test_an_in_scope_edit_completes_with_no_revert now reads the in-scope edit through read_committed(root, working_branch_name(run_id), ...) instead of the work_dir filesystem D-04 deletes on COMPLETED, plus a companion work_dir-gone assertion; zero production changes, all six SC4 scenarios pass against real PostgreSQL 17
- [Phase 05]: [Phase 05]: 05-06: G-05-2 closed — CR-02 revert_paths escape-ordering fix now has 7 unit-tier DB-free regression tests (revert_paths direct + enforce_write_scope's own sort), registered under SC4/ROLE-05; Phase 5 acceptance gate green (12 passed) against real PostgreSQL 17
- [Phase 06]: build_worker_env mirrors git_env(): additive dict comprehension over WORKER_ENV_ALLOWLIST (derived from GIT_ENV_ALLOWLIST + XDG_* entries), never a parent-environment copy/spread/exclusion-filter (D-09, TOOL-04)
- [Phase 06]: shell.execute (D-11) spawns an explicit argv sequence via subprocess.Popen with build_worker_env()'s environment, start_new_session=True, and process-group kill on timeout; performs no permission check of its own -- ToolRegistry.invoke() stays the single enforcement point
- [Phase 06]: MCP transport: build_mcp_server registers per-role closures that all funnel through ToolRegistry.invoke() -- advertised list is never the enforcement boundary; two SDK bugs in RESEARCH's own code sketch (leading-underscore param rejection, **kwargs schema mishandling) plus a JSON/Path argument marshalling gap were discovered and fixed empirically
- [Phase 06]: [Phase 06]: 06-04: SEC-01 sweep of the capability-denial path (artifact tree, worker prompt, event payloads, role-execution columns, logs) plus the Phase 6 acceptance gate mapping all five SC/seven requirement ids to proof files; test_validation_strategy_and_gate_cannot_drift asserts bidirectional set equality against 06-VALIDATION.md.
- [Phase 06]: All 4 deferred human-verification items (db/integration-tier tests needing real PostgreSQL 17) closed 2026-09-20 — user ran the full suite against real Postgres 17: 763 passed, 0 failed. Phase 6 VERIFICATION.md re-verified passed (was human_needed).
- [Phase 06]: 3 long-standing "pre-existing, unrelated" test failures (tests/db/test_artifact_commit_per_role.py x2, tests/integration/test_pr_diff_excludes_artifacts.py x1), carried since 06-01-SUMMARY.md, were a stale test-fixture defect — write_scope: [] (D-14 zero-tolerance) combined with the test's own worker planting a non-artifact file. Fixed test-only (commit ffc333f), zero production changes. Root cause: .planning/debug/resolved/phase4-artifact-commit-bugs.md. Phase 6 complete.
- [Phase 07]: 07-01: ClaudeCodeWorker is a real CodingWorker adapter -- stream-to-file subprocess (never PIPE), Settings.anthropic_api_key/worker_timeout_seconds (D-02/D-03), redact-before-return closes the SEC-01 gap in the force-committed run tree; resume()/capabilities() deliberately stubbed pending 07-03 (WINDOWS.md #10)
- [Phase 07]: [Phase 07]: 07-02: Quoted "on": in ci.yml (not bare on:) -- PyYAML/YAML 1.1 parses a bare `on` key as boolean True, breaking document['on'] lookups in both the plan's verify command and the Task 2 structural guard; quoting is the standard GitHub Actions workaround with zero effect on GitHub's own parser
- [Phase 07]: [Phase 07]: 07-02: TDD RED anchor for the guard-on-the-guard test was the self-detection sanity test, not the main assertion -- a stub _offenders() returning [] trivially passes "no offenders" on an already-compliant workflow, so RED had to target test_the_guard_detects_its_own_subject instead
- [Phase 07]: [Phase 07]: 07-03: NEEDS_INPUT marker regex (MULTILINE anchors line-start; DOTALL+\Z captures multi-line question); resume() shares execute()'s entire spawn/timeout/redact/parse pipeline via _spawn_and_parse(argv, context) so the two entry points cannot drift; capabilities() now native_resume=True; contract suite runs ClaudeCodeWorker with a fake CLI on PATH and no live credential (QUAL-02)
- [Phase 07]: 07-04: --allowedTools derived from context.tools via NATIVE_TOOL_CONTRACT's first real consumer; artifacts.write kept out of the flat _TOOL_NAMES map and emitted as a path-scoped Edit(<glob>/**) specifier instead of a bare tool name; contract's claude_code prose corrected to name cwd=<worktree> (WORKTREE_CONFINEMENT_NOTE) as the real confinement mechanism, replacing a nonexistent --permission-mode claim; reference guard narrowed to a 3-path _ALLOWED_CONSUMERS allowlist, not deleted
- [Phase 09]: [Phase 09]: 09-04: widened enforce_write_scope to cover Signal.ROLE_BOUNCED alongside ROLE_COMPLETED (gap CR-01); WriteScopeViolation handler clears counter_increments/bounce_reason on downgrade but leaves gate_events untouched since the gate artifact is already durably committed by the time the check runs
- [Phase 09]: [Phase 09]: 09-05: applied redact(command, known_secrets=known_secrets) to GateCommandResult.command in run_quality_gate (gap CR-02) — the configured quality_gate.commands text is now redacted before persistence/commit, closing the last gap from 09-VERIFICATION.md; docstring citation fixed from '.claude/CLAUDE.md' to bare 'CLAUDE.md' to satisfy the worker-runtime-name leak guard
- [Phase 09]: 09-06: rebuild derives worktree via ensure_worktree(base_branch, working_branch) from freshly loaded RunState (route 2), mirroring _advance_once, instead of resolving against the config repo root — Extends D-07 durability proof to path resolution itself; avoids a repo_root-named parameter ever holding a worktree path; adds a DB-free AST guard restoring detection for a defect class that previously required real PostgreSQL 17 to surface
- [Phase 10]: [Phase 10] 10-01: Task 1 checkpoint approved installing githubkit>=0.16,<0.17 despite the SUS package-legitimacy flag (driven only by unknown-downloads, no other red flag, name matches the project's locked tech-stack decision)
- [Phase 10]: [Phase 10] 10-01: Task 2 checkpoint selected option A1 -- source_ref = "{owner}/{repo}#{issue_number}", metadata = {owner, repo, issue_number, labels, comment_count} -- for how a GitHub-sourced run records which issue it came from
- [Phase 10]: [Phase 10] 10-01: webhook optional extra pinned to starlette>=0.42,<1 + uvicorn>=0.34,<1 -- smallest surface with exact raw-request-body access for the webhook HMAC check (plan 10-04), TestClient built on httpx already pulled in by githubkit
- [Phase 10]: 10-06: publish step's own commit_run_artifacts runs inside the terminal role's gate-PASS arm, before the generic per-role commit -- it carries the role's artifacts plus quality_gate.json in one commit labelled 'publish'; the later generic commit safely no-ops — Placement matches the plan's literal instruction and avoids introducing a second, distinctly-labelled artifact commit
- [Phase 10]: 10-06: publishing is gated solely on publishing.create_pr -- when false, github_client_factory is never called and no PUBLISH_* event is emitted at all — GIT-05/GIT-06 enabler: a run that publishes nothing must never construct a GitHub client or need github_token configured
- [Phase 10]: 10-06: Rule 1 fix -- tests/conftest.py's shared _write_config_tree now defaults publishing.create_pr to false, not PublishingConfig's true default, to avoid breaking ~24 pre-existing db-tier tests that drive a run to COMPLETED with no repository/GITHUB_TOKEN configured — Confirmed by re-running all 7 previously-at-risk db test modules (23 tests) with zero per-test changes after the fix
- [Phase 10]: 10-02: run_publish_step's Stage 2 (three-way persisted-identifier fast path) and Stage 3 (GitHub-side find_pull_request_for_branch existence check before every create) are sequential, not merged -- Stage 2 makes every ordinary retry free (zero git/GitHub calls); Stage 3 is the crash-safety net for the narrow 'Neon says no PR yet' branch
- [Phase 10]: 10-02: adopted_existing_pr is a plain declared PublishResult field, not computed -- it records an observation (created now vs. found already existing) rather than a derivable fact; runner.py was left untouched per the plan's wave-safety instruction (plan 10-03 owns it in the same wave)

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

- ⚠️ [Phase 9] `tests/db/test_manual_check_loop04_adjacency.py` is an untracked, already-served throwaway script — the only behavioral evidence LOOP-04's adjacency case (a failing role with no earlier role) was ever proven. A future `git clean` would silently lose it. Not phase-blocking (the invariant is independently confirmed by direct code read), but should be either deleted per its own docstring or promoted to a committed `tests/db/` test.
- ⚠️ [Phase 9] Threat IDs `T-09-12` through `T-09-16` were independently reused across plans 09-03/09-04/09-05 for unrelated threats (each plan numbered forward from what its author believed was the last-used id). Documented and disambiguated in `09-SECURITY.md`; a future phase should number threat ids from a single running counter across all of a phase's plans.

Resolved this phase: LOOP-01/LOOP-02 db-tier behavioral proof (Phase 9, gap-closure plan 09-06 — `_CapturingWorker` now derives the worktree via `ensure_worktree` instead of the config repo root; confirmed against real PostgreSQL 17). Plan 10-02 Task 2's db-tier precondition (no PostgreSQL reachable) — resolved via a human-supplied throwaway Neon connection string (the same one used for plan 10-06); the crash-window proof is now committed (`659b353`). Resolved earlier: exact non-interactive flag/env matrix for Copilot and Hermes CLIs (Phase 8 — both adapters shipped functional); artifact-content durability for cross-machine resume (Phase 5, ART-04); lease TTL vs. unpredictable agent step duration (Phase 2).

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-09-27T11:15:33.587Z
Stopped at: Completed 10-02-PLAN.md
Resume file: None
