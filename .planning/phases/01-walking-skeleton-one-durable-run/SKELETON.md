# Walking Skeleton — Dark Factory

**Phase:** 1
**Generated:** 2026-09-07

## Capability Proven End-to-End

An operator runs `dark-factory run text:"add a health endpoint"` and a durable run is created in Neon, driven through the Business Analyst role by `FakeWorker`, and carried to `COMPLETED` — with every lifecycle step committed as a single transaction that any brand-new process can pick up and finish via `dark-factory resume <run-id>`.

This is the whole-application tracer: one real CLI route, one real DB write, one real DB read, one deterministic role step, one redacted audit trail. No AI, no GitHub, no git worktree, no quality gate.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.12 (`requires-python = ">=3.12"`) | `enum.StrEnum`, `tomllib`, `datetime.UTC`; every pinned dependency ships 3.12 wheels; avoids the `>=3.11` floor `pygit2` would impose (`CLAUDE.md` Technology Stack) |
| Packaging / env | `uv` + PEP 621 `pyproject.toml` + committed `uv.lock`, `src/` layout, `[project.scripts] dark-factory = "dark_factory.cli:app"` | Project standard; one tool for resolution, lockfile, venv and Python pinning; `uv run` is the single command surface in CI |
| CLI framework | Typer 0.27.x (vendors Click since 0.26 — no separate `click` pin) | Type-hint commands map 1:1 onto `run` / `resume` / `status`; `typer.Exit(code=…)` gives the D-05 exit-code contract directly |
| Data layer | Neon PostgreSQL 17 via SQLAlchemy 2.0 typed ORM (`Mapped[...]`) + psycopg 3 (`postgresql+psycopg://`) + Alembic 1.19 | Named in the spec. Sync API only. `NullPool` + `pool_pre_ping=True` + `connect_args={"prepare_threshold": None}` for a short-lived CLI against Neon's PgBouncer pooler; Alembic DDL against the **direct** (non-`-pooler`) endpoint |
| Boundary models | pydantic v2 models kept **separate** from SQLAlchemy ORM classes (no SQLModel) | The project needs divergence between the persisted row and the validated boundary object — JSONB payload shapes, secret handling, event serialization (`CLAUDE.md` "What NOT to Use") |
| Durable-execution engine | Hand-rolled `enum.StrEnum` FSM + a pure `lifecycle.transition()` + a resume-first `advance(run_id)`; the authoritative state is the `runs.status` **column** | The spec forbids a separate orchestration cluster or lock service. In-memory FSM state cannot survive `kill -9`; durability and observability are the same requirement |
| Lifecycle mutation | ONE module, `persistence/mutations.py`, holding `create_run()` and `apply_transition()`; each opens exactly one `with session.begin():` and commits once | ORCH-06 / SC4. A crash between sub-writes rolls back everything, so a status change can never exist without its `run_events` row |
| Control-state read model | `runs` columns + the latest `role_executions` row. `run_events` is append-only audit and is **never** folded to compute position | STATE-06 / SC3. `observability/status.py` does not import `events/` — an architecture constraint, not just a behavioural one |
| Retry / iteration counters | Explicit non-null integer columns: `role_executions.attempt`, `runs.qa_developer_iterations`, `runs.quality_gate_iterations` (default 0) — never derived by counting rows or folding events | D-19 (one-way). Checkpoint-not-replay. Defined in migration `0001`, enforced in Phase 9 |
| Status representation | `sa.Enum(RunStatus, native_enum=False)` — VARCHAR + CHECK carrying all ten STATE-07 values from migration `0001` | Avoids `ALTER TYPE … ADD VALUE` in later phases; trivially editable; mypy-friendly with `enum.StrEnum` (RESEARCH Pitfall 6) |
| Event ordering | DB-generated monotonic `BigInteger` identity column `run_events.seq`; `ORDER BY seq`, never `ORDER BY created_at` | Timestamps skew across machines once Phase 11 introduces cross-machine resume |
| Secret handling | `pydantic-settings` `Settings` with `SecretStr` fields is the single choke point; one recursive `redact()` wired at exactly two points — a `structlog` processor and inside `apply_transition()` before every JSONB write | SEC-02 / D-14 (one-way). Redaction from the first persistence code, never retrofitted |
| Worker abstraction | `CodingWorker` ABC (`execute` / `resume` / `capabilities`) + a `WorkerRegistry` name→factory map; `FakeWorker` is **shipped package code** under `src/dark_factory/workers/`, not a test fixture | WORK-01/03/10. The registry is the seam Phases 7-8 slot real runtimes into with zero orchestrator edits |
| Artifact durability (recorded, not built) | The future `artifacts` table (Phase 4) will store `ArtifactReference` metadata only — `id, run_id, role_execution_id, type, path, checksum, metadata, created_at`. Content lives on the filesystem under `.dark-factory/runs/<run-id>/` and (Phase 5) travels between machines by being committed to a `.dark-factory/` path on the run's working branch, excluded from the published diff | D-21 / ROADMAP open decision 1. Phase 1 creates **no** `artifacts` table; the decision is recorded here and in the `0001` migration docstring because it shapes the schema |
| Directory layout | `src/dark_factory/` with `config/`, `domain/`, `input/`, `orchestrator/`, `workflows/`, `roles/`, `workers/`, `persistence/`, `events/`, `observability/` + `cli.py`, `__main__.py`, `logging.py`; `migrations/` and `tests/{unit,db,integration,contract}/` at repo root | The Phase-1 slice of the amended spec §72 layout, narrowed in `01-RESEARCH.md` § "Recommended Project Structure" |
| Test infrastructure | pytest 9.x with `unit` / `db` / `integration` / `contract` markers; Postgres provisioning chosen by a probe ladder (testcontainers `postgres:17-alpine` → `pytest-postgresql` → an externally supplied `DARK_FACTORY_TEST_DATABASE_URL`); per-test isolation via `Session(bind=conn, join_transaction_mode="create_savepoint")` inside a rolled-back outer transaction | Docker / `initdb` / a live `DATABASE_URL` are all unverified on the target machine, so the choice is made by probe, recorded, and never assumed |

## Stack Touched in Phase 1

- [x] **Project scaffold** — `uv init --package`, `pyproject.toml` (deps + `[project.scripts]` + `[tool.pytest.ini_options]` + `[tool.ruff]` + `[tool.mypy]` strict), `uv.lock`, `.gitignore`, `.env.example` — Plan 01
- [x] **Routing — one real route** — the Typer command `dark-factory run text:"…"` (plus `resume` and `status`), reachable both as the console script and as `python -m dark_factory` — Plans 05, 07
- [x] **Database — one real write AND one real read** — write: `create_run()` inserts the `runs` row (status `CREATED`) plus its `RUN_CREATED` event in one transaction. Read: `load_run_state()` reconstructs the entire run from `runs` + the latest `role_executions` on *every* `advance()` call, and `read_status()` renders it for the `status` command — Plans 04, 05, 07
- [x] **UI — one interactive element wired to the persistence layer** — for this CLI-only project the interactive element is the `run` / `resume` drive loop: it prints the run id on stdout line 1, then one line per committed state transition (`CREATED → BA`, `BA → COMPLETED`), each line backed by a real committed row — Plan 05
- [x] **Deployment — documented local full-stack run command** — `uv sync --all-extras --dev && uv run alembic upgrade head && uv run dark-factory run text:"add a health endpoint"` against a real Neon project (`DATABASE_URL` pooled for the app, `DATABASE_URL_DIRECT` for Alembic), documented in `README.md` — Plan 08

## Out of Scope (Deferred to Later Slices)

Explicitly not in the skeleton, so later phases do not re-litigate Phase 1's minimalism:

- Real agent runtimes of any kind — `FakeWorker` is the only worker (Phases 7-8)
- GitHub in every form: issue intake, clarification comments, PR publishing, webhooks (Phase 10)
- `WAITING_HUMAN`, `human_interactions`, `resume --answer "…"`, safe process release (Phase 2)
- Postgres lease / single-owner concurrency / heartbeat (`locked_by`, `lock_expires_at`) (Phase 2)
- `.dark-factory.yaml`, `.dark-factory/roles/*.yaml`, per-run config snapshot, `ActionRegistry` (Phase 3)
- The Architect / Developer / QA roles, artifact handoffs, the `artifacts` table, `ArtifactReference` persistence, filesystem artifact writes, the `spec:` loader (Phase 4)
- Isolated worktree, working branch, any `git` invocation at all (Phase 5)
- `ToolRegistry`, per-role permissions, the subprocess credential-allowlist boundary, MCP (Phase 6)
- Independent quality gate, bounded feedback loops, enforcement of `qa_developer_iterations` / `quality_gate_iterations` (Phase 9)
- The `runs` / `artifacts` / `events` CLI subcommands, Rich per-role pipeline visualisation, full `run_events` catalog coverage (Phase 12)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2:** a run stops mid-role for a human answer, releases its process, and is resumed later by exactly one process under a Postgres lease
- **Phase 3:** the pipeline shape and role behaviour move into repository YAML, snapshotted per run
- **Phase 4:** BA → Architect → Developer → QA hand off through durable artifacts with machine-readable verdicts
- **Phase 5:** every run owns a working branch and clean worktree, and its artifacts travel to another machine
- **Phase 6:** roles receive only granted capabilities; workers never see an infrastructure credential
- **Phase 7:** Claude Code performs a role for real, with the orchestrator runtime-agnostic
- **Phase 8:** the same role runs unchanged on Copilot and Hermes, chosen purely in configuration
- **Phase 9:** the platform re-runs the repository's own commands itself and bounds every retry
- **Phase 10:** a GitHub issue starts a run and a verified result becomes exactly one pull request
- **Phase 11:** a run started locally finishes in CI through Neon alone
- **Phase 12:** the observability surface that makes the whole run explainable
