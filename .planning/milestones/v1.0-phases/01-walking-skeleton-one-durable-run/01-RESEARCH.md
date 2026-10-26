# Phase 1: Walking Skeleton — One Durable Run - Research

**Researched:** 2026-09-07
**Domain:** Durable, resumable CLI orchestration core — deterministic enum FSM + resume-first `advance(run_id)`, one atomic DB mutation path, secret redaction from the first persistence code (Python 3.12 + SQLAlchemy 2.0 sync + psycopg3 + Alembic + Neon Postgres + Typer + pydantic v2 + structlog)
**Confidence:** HIGH on stack and how-to-wire-it (stack is pre-pinned and re-verified against PyPI this session; the SQLAlchemy/psycopg3/structlog/Typer APIs are stable and well documented); MEDIUM on the exact schema column set and the crash-injection test seam (reasoned synthesis from the project's own ARCHITECTURE.md / PITFALLS.md plus SQLAlchemy docs — no single authoritative source prescribes them).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `dark-factory run text:"..."` blocks until the run reaches a terminal state. It creates the `runs` row (status `CREATED`), prints the run id on its own line to stdout immediately (so a killed process is still recoverable), then loops the resume-first `advance(run_id)` entrypoint until `COMPLETED` or `FAILED`.
- **D-02:** `advance(run_id)` is the single orchestrator entrypoint and is always resume-first: it reconstructs all state from Neon on every call, executes exactly one step, commits through the one mutation path, and returns the new state. `run` and `resume` are both thin wrappers around a drive loop over `advance(run_id)`. — *Reversibility: costly — spine of the durability thesis.*
- **D-03:** `dark-factory resume <run-id>` ships in Phase 1 with **no** `--answer` argument — it runs the same drive loop as `run`. Phase 2 extends the *same* command with `--answer`. There is no separate `advance` CLI command.
- **D-04:** `run` and `resume` emit: run id on its own first line, then one line per state transition (`CREATED → BA`, `BA → COMPLETED`), then a short final summary block (run id, terminal state, last role, attempt). Plain text. Machine-readable detail is left to `status` / `events`.
- **D-05:** Exit codes for `run` / `resume`: `0` when the run reaches `COMPLETED`; `1` when the run reaches `FAILED` (a real, persisted terminal delivery failure); `2` for bad invocation (unresolvable input, unknown run-id, config/validation error — nothing persisted or advanced). — *Reversibility: costly — the Phase 11 CI trigger encodes these three codes.*
- **D-06:** In Phase 2+, the same drive loop additionally halts (exit `0`) when the run reaches `WAITING_HUMAN`. Recorded now so the loop's stop-condition set is designed with that seam in mind.
- **D-07:** The Phase-1 pipeline is the single **real** role **Business Analyst (`BA`)** — not a synthetic placeholder, not Developer. BA is read-only on repository source (no worktree/git needed — that is Phase 5). — *Reversibility: costly — later phases assume `BA` is first and the run-status enum was exercised for real from Phase 1.*
- **D-08:** Happy-path state sequence is `CREATED → BA → COMPLETED`. The run does not pass through `ARCHITECTURE` / `DEVELOPMENT` / `QA` / `VERIFYING` / `PUBLISHING`. The full STATE-07 enum is defined in code; only `CREATED`, `BA`, `COMPLETED`, `FAILED` are reachable in Phase 1.
- **D-09:** The one-role pipeline `["BA"]` is a hardcoded Python default in Phase 1. The orchestrator iterates an in-memory ordered role list that happens to have one entry — it must not bake in a role *count* (no "call these N roles"). Phase 3 externalises pipeline shape to YAML.
- **D-10:** `FakeWorker` returns a scripted sequence of `WorkerResult`s (WORK-10). Happy path: one `WorkerResult(status=COMPLETED, summary=…, questions=[], artifacts=[], changed_files=[], worker_session_id="fake-<uuid>", metadata={})`. A scripted `WorkerResult(status=FAILED, …)` drives the `FAILED` terminal path and the crash-consistency test. `NEEDS_INPUT` is in the enum but not exercised until Phase 2. Phase 1 does not persist `ArtifactReference` rows or write artifact files.
- **D-11:** `dark-factory status <run-id>` reads only from state columns — the `runs` row plus the latest `role_executions` row for that run. It never folds `run_events` to compute position (SC3).
- **D-12:** Default `status` output is a plain-text `key: value` field list: run id, source (redacted), status, current role, current step, latest attempt number, `created_at`, `updated_at` (`base_branch` / `working_branch` shown even though null until Phase 5). No Rich per-role pipeline visualisation — that is Phase 12.
- **D-13:** `status` supports `--json`, emitting the same fields as a single JSON object. Ships in Phase 1 because it makes the "position comes from columns" property cleanly testable.
- **D-14:** A single `redact(value) -> value` function (recursive over dict / list / str) is the one redaction path. Wired in two places from the first persistence code: (a) as a `structlog` processor on every log event, and (b) at the one lifecycle mutation path, applied to every JSONB payload before write (`run_events.payload`, `role_executions.result`, `role_executions.error`). — *Reversibility: one-way — a value that reaches Neon or a log file un-redacted is unrecoverable.*
- **D-15:** Pattern set caught in Phase 1: (1) Postgres/DB connection URIs with credentials (`postgres://`, `postgresql://`, `postgresql+psycopg://`, `…user:pass@host…`); (2) `key=value` / `key: value` pairs whose key matches a sensitivity list (`password`, `passwd`, `secret`, `secret_key`, `token`, `api_key`, `apikey`, `access_key`, `database_url`, `github_token`, `authorization`, `bearer`); (3) GitHub token shapes (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` prefixes; 40-hex classic PAT in a github-ish context); (4) `Authorization: Bearer <…>` header values.
- **D-16:** Exact-value redaction *in addition to* pattern redaction: the `pydantic-settings` object (with `SecretStr` fields) is the single source of the live `DATABASE_URL` / `GITHUB_TOKEN` / worker-credential values; `redact()` also does literal-substring replacement of those known values wherever they appear.
- **D-17:** Placeholder format is a labeled token — `[redacted:database_url]`, `[redacted:github_token]`, `[redacted:secret]`, etc.; `[redacted]` when the label is unknown.
- **D-18:** Scope split. Pattern-based redaction (D-15) applies to every persisted `run_events.payload`, every `role_executions.result` / `error`, and every log line. The stored task source / persisted `NormalizedTask` is scrubbed only for **exact matches of the known live secret values** (D-16), not by generic pattern — a task that legitimately discusses connection-string syntax keeps its wording; a real leaked credential value is removed everywhere. Raw task text otherwise persists as given.
- **D-19:** Retry / feedback-loop counters are explicit integer columns — never derived. `role_executions.attempt` covers per-role attempts. The two bounded feedback-loop counters — `qa_developer_iterations`, `quality_gate_iterations` — are non-null integer columns on `runs`, default `0`, incremented only in the one mutation path. Defined in the Phase 1 schema; enforced in Phase 9. — *Reversibility: one-way — an Alembic migration against persisted run rows.*
- **D-20:** `runs` carries `base_branch` and `working_branch` columns from the Phase 1 schema, nullable, unused until Phase 5.
- **D-21:** Artifact-content durability (open decision 1) intended approach, recorded for schema shape only: the future `artifacts` table (Phase 4) stores `ArtifactReference` metadata only — `id, run_id, role_execution_id, type, path, checksum, metadata, created_at` — never artifact content. Content lives on the filesystem under `.dark-factory/runs/<run-id>/` and (Phase 5) travels between machines by being committed to a `.dark-factory/` path on the run's working branch, excluded from the published diff. **Phase 1 does not create the `artifacts` table.**
- **D-22:** `run_events` is append-only: `id, run_id, role_execution_id` (nullable)`, type, payload` (JSONB, redacted)`, created_at`. `type` is a string/enum drawn from the event catalog in PROJECT.md. Phase 1 emits at least `RUN_CREATED`, `ROLE_STARTED`, `ROLE_COMPLETED` / `ROLE_FAILED`, `RUN_COMPLETED` / `RUN_FAILED`.
- **D-23:** The resolver classifies the `text:` / `spec:` / `github:` prefix deterministically (prefix match, no LLM, no repo inspection, no GitHub call, no network, does not create a run — INTAKE-04). Phase 1 implements only the `text:` loader; the `spec:` (Phase 4) and `github:` (Phase 10) classification arms exist but their loaders raise a clean "not yet supported" error. Every source normalises to one `NormalizedTask`, after which the orchestrator is origin-agnostic (INTAKE-05).

### Claude's Discretion

- CLI drive model, resume command shape, `run`/`resume` output, exit codes (D-01…D-06) — user delegated with "you decide"; the recorded choices are the decisions to implement, not loose defaults.
- Skeleton role & state path (D-07…D-10), `status` output (D-11…D-13), redaction behavior (D-14…D-18) — settled from spec/roadmap/invariants at the user's explicit request. "The planner may refine details but should treat the shape as decided."
- Not delegated / still Claude's to choose within the above: exact schema column types (UUID vs bigint ids, native PG enum vs CHECK), the crash-injection test mechanism, test-isolation strategy, the internal module split, the redaction regex specifics.

### Deferred Ideas (OUT OF SCOPE for Phase 1)

- Rich per-role pipeline visualisation in `status` — Phase 12.
- `resume --answer "..."`, `WAITING_HUMAN`, safe process release — Phase 2.
- Postgres lease / single-owner concurrency / heartbeat (`locked_by`, `lock_expires_at`) — Phase 2.
- Config-driven `workflow.roles` in YAML + per-run config snapshot — Phase 3.
- `spec:` loader — Phase 4; `github:` loader + issue intake — Phase 10.
- `ArtifactReference` persistence + filesystem artifact writes — Phase 4; cross-machine artifact travel — Phase 5.
- Full `run_events` catalog coverage and the `runs` / `events` / `artifacts` CLI subcommands — Phase 12.
- Enforcement of `qa_developer_iterations` / `quality_gate_iterations` caps — Phase 9 (columns defined now).
- `human_interactions` table — Phase 2. `artifacts` table — Phase 4.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTAKE-01 | Operator can start a run from plain text — `dark-factory run text:"..."` | Typer CLI skeleton (§Code Examples 7); `run` command wires resolver → `create_run` → drive loop |
| INTAKE-04 | Input resolver classifies source deterministically, no LLM, no repo/GitHub/network, does not create a run | `input/resolver.py` pure prefix match returning `(SourceKind, locator)`; raises before any persistence (§Pattern 6, §Code Examples 8) |
| INTAKE-05 | Every source loaded through a source-specific loader, normalized to one `NormalizedTask`; orchestrator then origin-agnostic | `input/loaders.py` registry `{kind: loader_fn}`; `NormalizedTask` pydantic v2 model persisted to `runs.normalized_task` JSONB (§Standard Stack, §Code Examples 8) |
| ORCH-01 | Deterministic orchestrator drives the lifecycle; never one LLM loop | `orchestrator/lifecycle.py` pure `transition()`; `orchestrator/runner.py` `advance()` + `drive()`; no LLM anywhere in Phase 1 (FakeWorker) (§Pattern 1, §Pattern 2) |
| ORCH-05 | Only the orchestrator changes lifecycle state; a worker result never directly drives a transition | `WorkerResult` → `Signal` (pure mapping) → `lifecycle.transition()` is the only code computing next status; FakeWorker returns a value, never sets state (§Pattern 2, Anti-Pattern 5) |
| ORCH-06 | Every lifecycle mutation written in a single DB transaction through one mutation path | `persistence/mutations.py::apply_transition()` — one `with session.begin():` writes role_execution + runs + run_events, commits once (§Pattern 3, §Code Examples 1, PITFALL 1) |
| STATE-01 | Stack is SQLAlchemy + Alembic + PostgreSQL (Neon); app uses only `DATABASE_URL`, no provider-specific logic | `postgresql+psycopg://` engine from `SecretStr`; no `neon` imports; pooled URL for app, direct URL for Alembic (§Standard Stack, §Pitfall 3, §Code Examples 3) |
| STATE-02 | `runs` table persists identity, source, workflow, status, current role, current step, repository, base/working branch, PR number/URL, timestamps | `runs` schema (§Architecture Patterns → Schema); `workflow` JSONB holds `{"roles":["BA"]}` placeholder now |
| STATE-03 | `role_executions` table: one row per attempt (role, worker, status, attempt, worker_session_id, result/error JSONB, timestamps) | `role_executions` schema; `attempt` computed in SQL inside the mutation tx, never in memory (§Schema, §Pattern 1) |
| STATE-06 | `run_events` append-only audit trail; current position read from state columns, never recomputed by folding events | `run_events` schema with monotonic `seq`; `status` read model touches only `runs` + `role_executions` (D-11, SC3) (§Anti-Pattern 1, §Code Examples 7) |
| STATE-07 | Run status ∈ {CREATED, BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING, COMPLETED, WAITING_HUMAN, FAILED}; active role stored separately | `RunStatus` `enum.StrEnum` with all 10 values in the first migration; `current_role` is a separate column (§Schema, §State of the Art) |
| STATE-08 | Complete execution reconstructable from persisted data alone | Everything `advance()`/`resume()` needs is a column or JSONB field; zero in-memory carryover (§Pattern 1, PITFALL 2) |
| WORK-01 | All runtimes implement one `CodingWorker` contract — `execute()`, `resume()`, `capabilities()` | `workers/base.py` ABC; FakeWorker subclasses it (§Pattern 4, §Code Examples 5) |
| WORK-03 | No worker-specific branching in orchestrator/workflow code | `WorkerRegistry.get(name)` factory lookup; orchestrator reads only `WorkerCapabilities` / `WorkerResult` fields (§Pattern 4, Anti-Pattern 2, PITFALL 6) |
| WORK-08 | Every adapter normalizes output to one `WorkerResult` (status COMPLETED\|NEEDS_INPUT\|FAILED, summary, questions, artifacts, changed_files, worker_session_id, metadata) | `domain/worker.py::WorkerResult` frozen pydantic v2 model (§Code Examples 5) |
| WORK-10 | A `FakeWorker` returns a scripted sequence of `WorkerResult`s, no external AI call | `workers/fake.py` — `__init__(script)`, pops one per `execute()` (§Code Examples 5, D-10) |
| SEC-02 | Secret redaction applied to persisted event payloads and logs from the first persistence code, not retrofitted | `events/redaction.py::redact()`; wired as structlog processor + at `apply_transition()` before every JSONB write (§Pattern 5, §Code Examples 4, PITFALL 10) |
</phase_requirements>

## Summary

Phase 1 is pure plumbing for the durability thesis, and every foundational pattern the remaining eleven phases build on is fixed here. There is no AI, no GitHub, no git, no concurrency lease, no config file, no artifacts table — a plain-text task becomes a `runs` row in Neon, a hardcoded one-role pipeline `["BA"]` runs it through an in-process `FakeWorker`, and a resume-first `advance(run_id)` drive loop carries it to `COMPLETED` or `FAILED`. The load-bearing work is: (1) **one atomic mutation path** — a single function that writes the `role_executions` result, the `runs` state columns, and the `run_events` audit row inside one `with session.begin():` block and commits exactly once, so a crash between sub-writes rolls everything back (SC4); (2) **resume-first `advance()`** — reconstruct the entire run state from Neon on every call, execute exactly one committed step, return the new status, with zero object carried between iterations, so the "kill it and re-run from a fresh process" path (SC2) is literally the same code as the happy path; (3) **redaction wired at birth** — one recursive `redact()` used both as a `structlog` processor and inside the mutation path before every JSONB write, sourcing exact secret values from the `pydantic-settings` `SecretStr` object (SC5).

The stack is already pinned in `STACK.md` / `CLAUDE.md` and was re-verified against the PyPI registry during this research (SQLAlchemy 2.0.52, Alembic 1.19.2, psycopg 3.3.5, pydantic 2.13.5, pydantic-settings 2.15.0, Typer 0.27.2, structlog 26.1.0, testcontainers 4.15.0 — all current). Do **not** re-litigate library choices. The research below is entirely *how to wire them together correctly for this phase*: the synchronous SQLAlchemy 2.0 `Session.begin()` transaction idiom, `postgresql+psycopg://` with `connect_args={"prepare_threshold": None}` + `NullPool` for a short-lived CLI against Neon's PgBouncer pooler, Alembic pointed at the **direct** (un-pooled) Neon endpoint, the SQLAlchemy `after_cursor_execute` event as the crash-injection test seam, the `join_transaction_mode="create_savepoint"` test-isolation fixture, and the `structlog` processor signature.

**Primary recommendation:** Build the persistence core first — SQLAlchemy 2.0 models + first Alembic migration for `runs` / `role_executions` / `run_events`, the `redact()` function, and the single `apply_transition()` mutation function — then the pure `lifecycle.transition()`, then `advance()` + the drive loop, then `FakeWorker` + `WorkerRegistry`, then the Typer CLI and the input resolver last. Write the crash-injection test (SC4) and the fresh-process resume test (SC2) in the same plan that introduces `advance()`, not as a follow-up. Every JSONB write goes through `apply_transition()`; nothing else touches `runs.status`, `role_executions`, or `run_events`.

## Architectural Responsibility Map

Dark Factory Phase 1 is a CLI + database process — no browser / SSR / API / CDN tiers. "Tier" below maps to the ARCHITECTURE.md component layers, which is what the planner and plan-checker should sanity-check task assignments against.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Source classification (`text:`/`spec:`/`github:`) | Input / Trigger (`input/resolver`) | — | Deterministic, pre-run, zero I/O, does not create a run (INTAKE-04) |
| Task normalization → `NormalizedTask` | Input (`input/loaders`) | Domain (model) | Per-source loader; after this the orchestrator is origin-agnostic (INTAKE-05) |
| Run creation (`CREATED` row + `RUN_CREATED`) | Orchestrator (`create_run`) | Persistence, Events | First write; goes through the one mutation path |
| Next-status decision | Orchestrator pure core (`lifecycle.transition`) | — | The *only* code that computes a status change (ORCH-01/05) |
| One-step execution + drive loop | Orchestrator runner (`advance`, `drive`) | Persistence, Workers | Resume-first; reconstruct-then-step; zero carryover (D-02) |
| Atomic lifecycle mutation | Persistence (`mutations.apply_transition`) | Events | Single transaction: role_execution + runs + run_events (ORCH-06, SC4) |
| Audit events | Events (`run_events` writer, inside `apply_transition`) | Persistence | Append-only; written in the same tx as the state change (STATE-06) |
| Secret redaction | Events / Security (`redact`) | Persistence, Logging | Egress boundary: structlog processor + pre-JSONB-write (SEC-02, SC5) |
| Worker execution | Workers adapter (`FakeWorker`) | — | Scripted `WorkerResult`; no AI (WORK-10) |
| Worker selection | Workers (`WorkerRegistry`) | — | name → factory; no `if worker ==` (WORK-03) |
| Status read | Observability (`read_status`) | Persistence | `runs` + latest `role_executions` only; never folds events (SC3) |
| CLI surface (`run` / `resume` / `status`) | Trigger (`cli.py`) | Orchestrator, Observability | Thin: parse, call `create_run`/`drive`/`read_status`, map exit codes (D-01/04/05) |
| Config + secret loading | Config (`settings`) | — | pydantic-settings `SecretStr`; the single source of known secret values for `redact()` (D-16) |

**Tier-assignment sanity checks for the planner:**
- `lifecycle.transition()` must be a **pure function** — no `Session`, no I/O, no `WorkerResult` parsing beyond reading `.status`. If a task puts a DB call in `lifecycle.py`, it is misassigned.
- The Typer command bodies must contain **no lifecycle logic** — a command that inspects `runs.status` to decide what to do next is doing the orchestrator's job.
- `read_status` (the `status` command's data source) must **not import the events module**. SC3 is an architecture constraint, not just a behavioural one.
- `FakeWorker` lives in `src/dark_factory/workers/fake.py` (shipped package code), **not** in `tests/` — it is a named deliverable (WORK-10) reused by later contract tests.

## Standard Stack

Pinned in `STACK.md` / `CLAUDE.md`. Re-verified against the PyPI JSON registry API (`pypi.org/pypi/<pkg>/json`) on 2026-09-07 — versions and upload dates below are `[VERIFIED: PyPI registry]`. **Do not substitute alternatives** — the stack is a locked project decision.

### Core (Phase 1 actually uses these)

| Library | Version (verified 2026-09-07) | Purpose in Phase 1 | Why Standard |
|---------|-------------------------------|--------------------|--------------|
| **Python** | 3.12 (`>=3.12`) | Runtime | `enum.StrEnum`, `tomllib`, `datetime.now(UTC)`; every dep supports it `[VERIFIED: PyPI classifiers]` |
| **SQLAlchemy** | 2.0.52 (2026-08-11) | ORM + Core for `runs`, `role_executions`, `run_events`; the `Session.begin()` transaction | Named in spec; typed `Mapped[...]` models; `JSONB`; `with_for_update`; **sync API** `[VERIFIED: PyPI registry]` |
| **psycopg (v3)** | 3.3.5 (2026-08-31) | Driver behind `postgresql+psycopg://` | psycopg2 is maintenance-only; v3.2+ negotiates prepared statements through PgBouncer 1.22+ `[VERIFIED: PyPI registry]` `[CITED: psycopg.org/psycopg3/docs/advanced/prepare.html]` |
| **Alembic** | 1.19.2 (2026-09-04) | First migration: `runs` / `role_executions` / `run_events` | The migration tool for SQLAlchemy; autogenerate from 2.0 models; **run against Neon direct endpoint** `[VERIFIED: PyPI registry]` |
| **pydantic** | 2.13.5 (2026-08-28) | `NormalizedTask`, `WorkerResult`, `WorkerCapabilities`, `RunView` (status DTO), JSONB payload shapes | v2 is the boundary-validation standard; keep **separate from** ORM classes (no SQLModel) `[VERIFIED: PyPI registry]` |
| **pydantic-settings** | 2.15.0 (2026-08-07) | Load `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`(opt), `LOG_LEVEL` from env / `.env`; `SecretStr` fields | The single choke point for infra secrets and the source of known secret values for `redact()` (D-16) `[VERIFIED: PyPI registry]` |
| **Typer** | 0.27.2 (2026-08-28) | `run` / `resume` / `status` commands; `typer.Exit(code=…)` for D-05 | Type-hint commands; vendors Click since 0.26 (no separate `click` pin); bundles Rich `[VERIFIED: PyPI registry]` |
| **structlog** | 26.1.0 (2026-06-06) | Structured logging + the `redact` processor + `run_id`/`role`/`attempt` context binding | Redaction processor + bound context satisfies "no secrets in logs" + "run reconstructable" from day one `[VERIFIED: PyPI registry]` |
| **uv** | 0.12.x (0.12.7 present on this machine) | Deps, lockfile, venv, Python pinning, `[project.scripts]` console entry | Project standard; `uv.lock` committed; `uv run dark-factory …` `[VERIFIED: local `uv --version`]` |

### Supporting (Phase 1)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **rich** | 15.0.0 (transitive via Typer) | `status` field list rendering if desired; tracebacks | Optional — D-12 says plain `key: value`, so `typer.echo` is enough. No Rich pipeline view (Phase 12). |
| **tenacity** | 9.1.4 | Retry-once wrapper around the initial DB connect (Neon cold-start 300–800 ms) | Only the idempotent connect; **not** for the drive loop `[CITED: neon.com/docs/connect/connection-latency]` |
| **PyYAML** | 6.0.3 | Not used in Phase 1 (config file is Phase 3) | — |

### Dev / Test (Phase 1)

| Library | Version (verified 2026-09-07) | Purpose | Note |
|---------|-------------------------------|---------|------|
| **pytest** | 9.1.1 | Test runner; markers `unit` / `db` / `integration` | `[tool.pytest.ini_options]` in `pyproject.toml` `[VERIFIED: PyPI registry]` |
| **testcontainers[postgres]** | 4.15.0 (2026-07-24) | Ephemeral `postgres:17-alpine` for `db` / `integration` tests | Session-scoped; `PostgresContainer("postgres:17-alpine", driver="psycopg")` → `get_connection_url()` returns `postgresql+psycopg://…` `[VERIFIED: PyPI registry]` `[CITED: testcontainers.com/guides/getting-started-with-testcontainers-for-python]` |
| **pytest-postgresql** | 9.1.0 | Docker-free fallback (needs local `initdb`/`pg_ctl` on PATH) | Use if the dev/CI box cannot run Docker `[VERIFIED: PyPI registry]` |
| **polyfactory** | 3.3.0 (2026-02-22) — **newer major than STACK.md's `>=2,<3`** | Build `WorkerResult` / `NormalizedTask` / ORM-row fixtures | pydantic-v2-native. **Bump the pin to `>=3,<4`** — flag for the planner `[VERIFIED: PyPI registry]` |
| **time-machine** | 3.5.0 (2026-08-25) — **newer major than STACK.md's `>=2`** | Deterministic Python-side timestamps; groundwork for Phase 2 lease-expiry tests | Limited Phase-1 use (timestamps come from DB `func.now()`). **Bump the pin to `>=3,<4`** `[VERIFIED: PyPI registry]` |
| **ruff** | 0.16.6 | lint + format | `I`, `UP`, `B`, `SIM`, `RUF` rule sets `[CITED: STACK.md]` |
| **mypy** | 2.3.1 | `--strict` static typing | `plugins = ["pydantic.mypy"]`; SQLAlchemy 2.0 needs no plugin `[CITED: STACK.md]` |

### Alternatives Considered (all rejected — locked decisions)

| Instead of | Rejected alternative | Why rejected here |
|------------|----------------------|-------------------|
| SQLAlchemy 2.0 typed ORM + separate pydantic models | **SQLModel** | Fuses the two classes; the project needs divergence (JSONB payloads, secret handling). Listed in "What NOT to Use". |
| `postgresql+psycopg://` (v3) | psycopg2, **asyncpg** | psycopg2 maintenance-only; asyncpg + PgBouncer transaction pooling = prepared-statement hazard + async coloring for zero gain. |
| Synchronous SQLAlchemy | Async SQLAlchemy / async core | One run at a time, blocked on subprocess wall-clock. Async adds function coloring; explicitly out of scope. |
| Hand-rolled enum FSM + `advance()` | Temporal / DBOS / Prefect / Celery / `transitions` as source of truth | Spec forbids a separate orchestrator / lock service. `transitions` may validate legality in memory but must never own persistence. |
| `enum.StrEnum` + first migration defines all 10 status values | CHECK constraint only / add values later | STATE-07 is a fixed closed set — define it once; native PG enum or `sa.Enum` is fine. |

**Installation (Phase 1 subset):**
```bash
uv init --package --python 3.12 dark-factory
cd dark-factory
uv add \
  "sqlalchemy>=2.0.40,<2.1" \
  "psycopg[binary]>=3.2,<4" \
  "alembic>=1.19,<2" \
  "pydantic>=2.9,<3" \
  "pydantic-settings>=2.9,<3" \
  "typer>=0.27,<1" \
  "structlog>=25,<27" \
  "tenacity>=9,<10"
uv add --dev \
  "pytest>=9,<10" \
  "testcontainers[postgres]>=4.15,<5" \
  "pytest-postgresql>=9,<10" \
  "polyfactory>=3,<4" \
  "time-machine>=3,<4" \
  "ruff>=0.16" "mypy>=2.3"
```
> `psycopg[binary]` for dev speed; production build uses pure `psycopg` + system libpq. `PyYAML` / `githubkit` / `rich`-direct are **not** Phase 1 deps.

## Package Legitimacy Audit

Ran `gsd-tools query package-legitimacy check --ecosystem pypi …` for the full Phase 1 set on 2026-09-07.

| Package | Registry | Age (latest release) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|----------------------|-----------|-------------|---------|-------------|
| sqlalchemy | PyPI | 2026-08-11 | seam: unknown | sqlalchemy.org | SUS (`too-new`, `unknown-downloads`) | **Approved** — see note |
| alembic | PyPI | 2026-09-04 | seam: unknown | github.com/sqlalchemy/alembic | SUS (`too-new`, `unknown-downloads`) | **Approved** |
| psycopg | PyPI | 2026-08-31 | seam: unknown | psycopg.org | SUS (`too-new`, `unknown-downloads`) | **Approved** |
| pydantic | PyPI | 2026-08-28 | seam: unknown | github.com/pydantic/pydantic | SUS (`too-new`, `unknown-downloads`) | **Approved** |
| pydantic-settings | PyPI | 2026-08-07 | seam: unknown | github.com/pydantic/pydantic-settings | SUS (`unknown-downloads`) | **Approved** |
| typer | PyPI | 2026-08-28 | seam: unknown | github.com/fastapi/typer | SUS (`too-new`, `unknown-downloads`) | **Approved** |
| structlog | PyPI | 2026-06-06 | seam: unknown | (repo url null in seam) | SUS (`unknown-downloads`, `no-repository`) | **Approved** — repo is github.com/hynek/structlog |
| pyyaml | PyPI | — | seam: unknown | — | SUS | Not a Phase 1 dep — ignore |
| tenacity | PyPI | — | seam: unknown | github.com/jd/tenacity | SUS | **Approved** |
| rich | PyPI | — | seam: unknown | github.com/Textualize/rich | SUS | **Approved** (transitive via Typer) |
| testcontainers | PyPI | 2026-07-24 | seam: unknown | github.com/testcontainers/testcontainers-python | SUS | **Approved** |
| polyfactory | PyPI | 2026-02-22 | seam: unknown | github.com/litestar-org/polyfactory | SUS | **Approved** (bump pin to `>=3,<4`) |
| time-machine | PyPI | 2026-08-25 | seam: unknown | github.com/adamchainz/time-machine | SUS | **Approved** (bump pin to `>=3,<4`) |
| pytest | PyPI | — | seam: unknown | github.com/pytest-dev/pytest | SUS | **Approved** |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all of them — **but every SUS verdict is a false positive** driven by exactly two non-risk signals: `too-new` (the *latest version* was published within the seam's recency window — true of every actively-maintained library) and `unknown-downloads` (the seam could not retrieve PyPI download stats in this environment). These are the canonical, most-downloaded packages in the Python ecosystem, **named directly in the project spec, `STACK.md`, and `CLAUDE.md`**, each with a well-known first-party source repo, and each version was independently confirmed against the PyPI JSON registry this session. **The planner does not need a `checkpoint:human-verify` per package** — the risk this gate exists to catch (hallucinated / slopsquatted names) does not apply to a pre-pinned, spec-mandated stack. If the planner wants one belt-and-braces step, a single `checkpoint:human-verify` on "review `uv.lock` after first `uv sync`" covers the whole set.

*No package in this research was discovered via WebSearch or training data alone — all originate from the project's own pinned `STACK.md` / `CLAUDE.md`.*

## Architecture Patterns

### System Architecture Diagram (Phase 1 data flow)

```
  dark-factory run text:"..."                        dark-factory resume <run-id>
            │                                                  │
            ▼                                                  │
  input/resolver.classify(raw)                                 │
    "text:"|"spec:"|"github:" prefix match                     │
    → (SourceKind, locator)   [no I/O, no run]  ──┐            │
            │  unresolved → exit 2                 │            │
            ▼                                      │            │
  input/loaders.load(kind, locator)               │            │
    text  → NormalizedTask                        │            │
    spec  → SourceNotSupportedError → exit 2      │            │
    github→ SourceNotSupportedError → exit 2      │            │
            │                                     │            │
            ▼                                     │            │
  orchestrator.create_run(NormalizedTask)         │            │
    apply_transition( ∅ → CREATED,               │            │
      insert runs row, event RUN_CREATED )        │            │
            │  print run_id  (stdout, line 1)     │            │
            ▼                                     ▼            ▼
  ┌───────────────────  drive(run_id)  ──────────────────────────┐
  │  loop:                                                       │
  │    status = advance(run_id)   ◀── fresh Session every call   │
  │    print transition line  (D-04)                             │
  │    if status in {COMPLETED, FAILED}: break   (Phase 2 += WAITING_HUMAN)
  └──────────────────────────┬──────────────────────────────────┘
                             ▼
        advance(run_id):   (resume-first — D-02)
          state = load_run_state(session, run_id)   # runs + latest role_executions; ZERO carryover
          if state.status in TERMINAL: return state.status
          node  = workflow.current_node(state)      # from ["BA"] + state.current_role
          if state.status == CREATED:
              apply_transition(CREATED → BA,
                 insert role_executions(role=BA, worker="fake", attempt=1, status=RUNNING),
                 event ROLE_STARTED)                 # one committed step
              return BA
          # state.status == BA
          worker  = registry.get(node.worker)       # "fake"  — no if worker ==
          result  = worker.execute(build_context(state))   # scripted WorkerResult
          signal  = signal_from_result(result)      # ROLE_COMPLETED | ROLE_FAILED
          nxt, _  = lifecycle.transition(state, signal)     # PURE — BA→COMPLETED | BA→FAILED
          apply_transition(BA → nxt,
             update role_executions(status, result=redact(...), worker_session_id),
             event ROLE_COMPLETED|ROLE_FAILED  +  RUN_COMPLETED|RUN_FAILED)
          return nxt

        apply_transition(...) — the ONE mutation path:
          with session.begin():                      # single tx, commit once
            run = session.get(Run, id, with_for_update=True)
            assert run.status == expected             # guarded (rowcount/optimistic)
            <write role_executions row/update>        # result/error JSONB = redact(...)
            run.status = next ; run.current_role = ...; run.updated_at = func.now()
            session.add(RunEvent(type=..., payload=redact(...)))   # seq = DB identity
          # COMMIT here — or ROLLBACK of ALL of it on any exception

  Neon Postgres:  runs · role_executions · run_events        (no human_interactions, no artifacts)
  structlog:  every event dict → redact() processor → JSON sink
```

### Recommended Project Structure (Phase 1 slice of the amended §72 layout)

```
dark-factory/
  pyproject.toml            # [project.scripts] dark-factory = "dark_factory.cli:app"
  uv.lock
  alembic.ini              # sqlalchemy.url left blank — env.py reads DATABASE_URL_DIRECT
  migrations/
    env.py                 # points at the DIRECT (un-pooled) Neon endpoint
    versions/0001_walking_skeleton.py   # runs, role_executions, run_events
  src/dark_factory/
    __main__.py            # `python -m dark_factory` → cli.app  (needed for the subprocess resume test)
    cli.py                 # Typer app: run | resume | status(--json)
    logging.py             # structlog.configure(...) with the redaction processor
    config/
      settings.py          # pydantic-settings Settings(SecretStr ...); known-secret-value set
    domain/
      task.py              # NormalizedTask (pydantic v2)
      worker.py            # WorkerResult, WorkerResultStatus, WorkerCapabilities, ArtifactRef
      signal.py            # Signal enum + signal_from_result()
      status.py            # RunStatus (StrEnum, all 10 STATE-07 values), TERMINAL set
      views.py             # RunView (status read DTO)
    input/
      resolver.py          # classify(raw) -> (SourceKind, locator)   [pure]
      loaders.py           # {SourceKind: loader_fn}; text loader; spec/github raise NotSupported
    orchestrator/
      lifecycle.py         # transition(state, signal) -> (next_status, current_role)   [PURE]
      runner.py            # advance(run_id), drive(run_id), create_run(task)
    workflows/
      pipeline.py          # hardcoded Pipeline(roles=["BA"]); current_node(state); no role COUNT
    roles/
      registry.py          # BA role definition: name="BA", worker="fake"  (minimal in P1)
    workers/
      base.py              # CodingWorker ABC: execute / resume / capabilities
      registry.py          # WorkerRegistry: name -> factory; get() raises UnknownWorkerError
      fake.py              # FakeWorker(script: Sequence[WorkerResult])   [shipped, not in tests/]
    persistence/
      engine.py            # create_engine(postgresql+psycopg://, NullPool, prepare_threshold=None); sessionmaker
      models.py            # SQLAlchemy 2.0 Mapped[...] models: Run, RoleExecution, RunEvent
      repositories.py      # load_run_state(session, run_id) -> RunState; read_status(run_id) -> RunView
      mutations.py         # apply_transition(...) — THE one mutation path
    events/
      catalog.py           # EventType enum (RUN_CREATED, ROLE_STARTED, ...)
      redaction.py         # redact(value, *, known_secrets, patterns=True) -> value
    observability/
      status.py            # read_status — imports repositories, NOT events
  tests/
    conftest.py            # pg container fixture, db_session (savepoint), settings override, log capture, FakeWorker factory
    unit/                  # lifecycle, redaction, resolver, WorkerResult validation  (no DB)
    db/                    # apply_transition atomicity, advance() single-step, status-from-columns
    integration/           # CLI subprocess: run → kill → resume → COMPLETED; secret-grep end-to-end
    contract/              # test_coding_worker_contract.py  parametrized over [FakeWorker]  (QUAL-02 seam)
```

### Pattern 1: Resume-first `advance(run_id)` — the happy path IS the resume path

**What:** One execution entrypoint. Every call: (1) `load_run_state(session, run_id)` reconstructs the whole run from Neon — status, current_role, latest attempt, workflow snapshot — into a plain value object with **no reference to any prior in-memory object**; (2) determine the current node from the workflow + `current_role`; (3) if terminal, return; (4) execute exactly **one** step; (5) commit that step through `apply_transition()`; (6) return the new status. `create_run()` writes the `CREATED` row then the drive loop calls `advance()`. `resume` calls the identical drive loop. `run` calls the identical drive loop.

**When to use:** Always, from day one. Do **not** build a separate "happy path" that keeps `NormalizedTask` / the worker / counters in memory between steps — it will diverge from resume and resume will rot (PITFALL 2).

**Rule:** if `advance()` / `resume()` needs a value, it is a **column or a JSONB field, not a local variable**. Phase-1 list: `normalized_task`, `workflow` snapshot, `status`, `current_role`, `current_step`, per-role `attempt`, `qa_developer_iterations`, `quality_gate_iterations`.

**One-step granularity (Claude's discretion — recommendation):** treat `CREATED → BA` (mark the role started, insert the `role_executions` row) and `BA → COMPLETED/FAILED` (run the worker, record the result, transition) as **two separate committed `advance()` calls**. The 1-role happy path is therefore 2 `advance()` calls. This makes the mid-run kill test meaningful: kill after the `CREATED → BA` commit, a fresh process resumes cleanly at `BA`. (Alternative: fold both into one call. Rejected — it removes the interesting crash window and makes "exactly one step" ambiguous.)

**Drive loop stop conditions:** `{COMPLETED, FAILED}` in Phase 1. Design the set as a named constant `STOP_STATUSES` so Phase 2 adds `WAITING_HUMAN` by editing one line (D-06).

### Pattern 2: Deterministic control / typed signal — only the orchestrator changes state

**What:** `lifecycle.transition(state, signal) -> (next_status, next_current_role)` is a **pure function** — no `Session`, no I/O, no `WorkerResult` beyond `.status` already mapped to a `Signal`. It is the only code that produces a status change. `FakeWorker` returns a `WorkerResult`; `signal_from_result()` maps `COMPLETED→ROLE_COMPLETED`, `FAILED→ROLE_FAILED` (`NEEDS_INPUT→ROLE_NEEDS_INPUT` defined but unreachable in Phase 1); `transition()` maps `(BA, ROLE_COMPLETED) → (COMPLETED, "BA")` because `["BA"]` is the last role, and `(BA, ROLE_FAILED) → (FAILED, "BA")`. `(CREATED, <enter>) → (BA, "BA")`.

**When to use:** Always. This is the founding constraint ("not one giant LLM loop", ORCH-01/05).

**Trade-off:** You enumerate the state graph explicitly. That is the feature — it is tiny (`CREATED`, `BA`, `COMPLETED`, `FAILED` reachable), reviewable, and unit-testable with no DB and no mocks.

```
CREATED ──enter──▶ BA ──ROLE_COMPLETED──▶ COMPLETED     (["BA"] is last → no next role)
                    │
                    └──ROLE_FAILED──────▶ FAILED
```
`current_role` is a **separate column** from `status` (STATE-07) so a future `WAITING_HUMAN` knows where to return.

### Pattern 3: One atomic mutation path (`apply_transition`) — transactional outbox, applied internally

**What:** A single function in `persistence/mutations.py` is the only code that writes `runs.status` / `runs.current_role` / `runs.*_iterations`, any `role_executions` row, or any `run_events` row. It opens **one** transaction, does **all** the related writes, and commits **once**. The `run_events` insert is part of the same transaction as the state change it describes — never a fire-and-forget log afterward. Redaction is applied to every JSONB payload *inside* this function, immediately before `session.add`, so nothing can bypass it.

**Signature shape (recommendation — one function, intent-described):**
```python
def apply_transition(
    session: Session,
    *,
    run_id: UUID,
    expected_status: RunStatus,          # optimistic guard
    next_status: RunStatus,
    next_current_role: str | None,
    role_execution: RoleExecutionWrite | None,   # insert-or-update spec (result/error already RAW; redacted here)
    events: Sequence[EventWrite],                 # e.g. [ROLE_COMPLETED, RUN_COMPLETED]
    counter_increments: Mapping[str, int] = {},   # {"qa_developer_iterations": 1}  — unused in P1
) -> RunStatus:
```
Alternative: one thin function per lifecycle event (`start_role`, `complete_role`, `fail_role`, `create_run`). Both satisfy D-14 as long as **only this module** touches those tables. The single-generic-function form is easier to prove ("grep: `RunEvent(` appears only in `mutations.py`").

**When to use:** every lifecycle mutation, including `create_run` (the `∅ → CREATED` insert + `RUN_CREATED` event go through it too).

**Crash-consistency guarantee (SC4):** because all sub-writes are in one `with session.begin():` block, a `SIGKILL` / exception between any two of them causes Postgres to `ROLLBACK` the whole transaction — there is never a `runs.status` change without its `run_events` row, or an event without its state change. The test proves this by injecting an exception mid-transaction (see §Code Examples 2).

**Warning signs the planner should reject in a plan:** any task that calls `session.commit()` more than once per lifecycle event; `run_events` written through a logging handler or a second `Session`; a bare `UPDATE runs SET status=…` anywhere outside `mutations.py`.

### Pattern 4: Worker as a port; registry lookup, never a name branch

**What:** `CodingWorker` is an ABC with `execute(context) -> WorkerResult`, `resume(context, previous, answer) -> WorkerResult`, `capabilities() -> WorkerCapabilities`. `WorkerRegistry` maps a string name to a factory callable. The orchestrator calls `registry.get(role.worker)` and then only reads `WorkerResult` / `WorkerCapabilities` fields — never the worker's name — for behavioural decisions. `FakeWorker` implements the same ABC with a scripted `list[WorkerResult]`.

**When to use:** Always (WORK-01/03/08/10, Anti-Pattern 2). Even though Phase 1 has one worker, the registry and the ABC are the seam Phases 7–8 slot Claude Code / Copilot / Hermes into with zero orchestrator edits.

**Phase-1 CI guard (cheap, recommended now even though the roadmap formally schedules it at Phase 7):** a `unit` test that greps `src/dark_factory/` outside `workers/` and `config/` for the literals `"claude"`, `"copilot"`, `"hermes"` and fails if found.

### Pattern 5: Redaction at birth — one `redact()`, two wiring points

**What:** One recursive `redact(value, *, known_secrets, patterns=True)` over `Mapping` / `list` / `str`. Wired:
1. **structlog processor** — `def redaction_processor(logger, method_name, event_dict): return redact(event_dict, known_secrets=SECRETS)`. Placed in the `structlog.configure(processors=[...])` chain *after* the event dict is assembled and *before* the renderer (`JSONRenderer` / `KeyValueRenderer`).
2. **Mutation path** — `apply_transition()` calls `redact()` on `role_executions.result`, `role_executions.error`, and every `run_events.payload` before `session.add`.

**Two redaction modes (D-18):** pattern + exact-value for events/results/logs; **exact-value only** for the persisted `NormalizedTask` / `runs.source_ref` (so a task that legitimately discusses `postgres://` syntax keeps its wording). Expose this as the `patterns: bool` flag or a separate `scrub_known_values(value)` helper.

**Known-secret-value source (D-16):** iterate the `pydantic-settings` `Settings` instance's `SecretStr` fields, call `.get_secret_value()`, build `{value: label}` (e.g. `{<db url>: "database_url", <token>: "github_token"}`). Skip values shorter than ~8 chars to avoid pathological substring replacement.

**Pattern set (D-15) — compile once, module-level:**
| Target | Regex (starting point — tune) | Replacement |
|--------|-------------------------------|-------------|
| Postgres URI w/ creds | `(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:[^\s:/@]+@\S+` | `[redacted:database_url]` |
| GitHub fine-grained PAT | `\bgithub_pat_[A-Za-z0-9_]{22,}\b` | `[redacted:github_token]` |
| GitHub classic/OAuth tokens | `\b(gh[porsu])_[A-Za-z0-9]{36,}\b` | `[redacted:github_token]` |
| `Authorization: Bearer` | `(?i)authorization"?\s*[:=]\s*"?bearer\s+[A-Za-z0-9._\-]+` | `[redacted:authorization]` |
| sensitive `key=value` / `key: value` | `(?i)\b(password\|passwd\|secret\|secret_key\|token\|api_key\|apikey\|access_key\|database_url\|github_token\|authorization\|bearer)\b(\s*[:=]\s*)("?)([^\s"',}]+)\3` | `\1\2[redacted:\1]` |
| dict key match | key ∈ sensitivity list → value replaced with `[redacted:<key>]` regardless of shape | — |
| 40-hex classic PAT | `(?i)(github[^\n]{0,40}?)\b[0-9a-f]{40}\b` — **github-ish context only** to avoid clobbering git SHAs | `\1[redacted:github_token]` `[ASSUMED]` |

**Test (SC5):** unit tests per row above; then an end-to-end `integration` test — run with task text containing `postgres://user:pass@host/db` **and** the live fake `DATABASE_URL` value; query every `run_events.payload`, every `role_executions.result`/`error`, and the captured log sink; assert the literal password and the URI regex → **zero hits**, and `[redacted:` present.

### Pattern 6: The resolver never touches the world (INTAKE-04)

**What:** `classify(raw: str) -> tuple[SourceKind, str]` is pure string work — `raw.startswith("text:" | "spec:" | "github:")`. No file read, no `os.path`, no network, no git, no DB, no run creation. Unmatched prefix → `UnresolvableSourceError` → CLI exit `2` with nothing persisted. Loader selection is a `{SourceKind: loader_fn}` dict (not an `if kind ==` chain). The `text` loader builds a `NormalizedTask`; `spec` / `github` loaders raise `SourceNotSupportedError("… not supported until Phase 4 / Phase 10")` → exit `2`.

### Anti-Patterns to Avoid (Phase-1-relevant subset of ARCHITECTURE.md / PITFALLS.md)

- **Reconstructing control state by folding `run_events`.** Authoritative state is `runs` columns + latest `role_executions`. `run_events` is append-only audit. `read_status` must not even import the events module (SC3). *(Anti-Pattern 1)*
- **`if worker == "fake"` / any worker-name branch outside `workers/`.** Registry + `WorkerCapabilities` only. *(Anti-Pattern 2, PITFALL 6)*
- **A transaction spanning the worker call.** In Phase 1 `FakeWorker` is in-process and instant, so it is tempting to wrap the whole `advance()` in one `Session`. Don't — establish the boundary now: `txn { load } → (no DB) worker.execute() → txn { apply_transition }`. Phase 2's real lease depends on this habit. *(Anti-Pattern 3, PITFALL 4)*
- **`session.commit()` more than once per lifecycle event.** *(PITFALL 1)*
- **`datetime.now()` / `datetime.utcnow()` into a persisted column.** Use `server_default=func.now()` / `onupdate=func.now()`; `run_events` ordering uses the monotonic `seq` identity column, never `created_at`. *(PITFALL 21)*
- **In-memory retry counters.** `attempt` and both `*_iterations` are columns, incremented only in `apply_transition`. *(PITFALL 13, D-19)*
- **Passing `os.environ` anywhere near a subprocess.** Not exercised in Phase 1 (no subprocess worker) but do not write helper code that does `os.environ.copy()`. *(Anti-Pattern 4, PITFALL 10)*
- **Storing large content in JSONB.** Phase 1 payloads are tiny; keep `run_events.payload` a small explicit dict, never `vars(obj)` / `model_dump()` of a whole context. *(Anti-Pattern 7, PITFALL 22)*
- **Alembic through the `-pooler` host.** DDL + PgBouncer transaction pooling do not mix — `env.py` uses the direct endpoint. *(PITFALL 22)*

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Single-commit multi-row transaction | Manual `BEGIN`/`COMMIT` string SQL, or `try/except` around several `session.commit()` calls | `with session.begin():` block (SQLAlchemy 2.0) — one BEGIN, one COMMIT, automatic ROLLBACK on exception | The context manager *is* the atomicity guarantee for SC4; hand-rolled sequencing reintroduces the dual-write gap |
| Test isolation between DB tests | `DELETE FROM` / `TRUNCATE` in every teardown; manual savepoint bookkeeping via `after_transaction_end` event | `Session(bind=connection, join_transaction_mode="create_savepoint")` inside an outer `connection.begin()` that the fixture rolls back | Native since SQLAlchemy 2.0; the old event-hook recipe is obsolete and fragile |
| Ephemeral Postgres for tests | Docker-compose file + wait-for-it scripts; a shared dev DB | `testcontainers` `PostgresContainer("postgres:17-alpine")` session-scoped fixture | ~3 s once; production parity (Neon *is* Postgres 17); auto-teardown |
| Secret scrubbing | Ad-hoc `.replace()` calls at each call site; scrubbing "when we remember" | One recursive `redact()` wired as a structlog processor + one call inside `apply_transition` | SEC-02 is "from the first persistence code, not retrofitted" — retrofitting after a leak is a data-scrubbing incident |
| Enum state machine | `dict` of magic strings; `transitions` library as source of truth | `enum.StrEnum` + a small pure `transition()` function; authoritative value is the `runs.status` column | Durability + observability are the same requirement — in-memory FSM state cannot survive `kill -9` |
| CLI arg parsing / exit codes | `sys.argv` slicing; bare `sys.exit(2)` | Typer commands + `raise typer.Exit(code=…)` | Type-hint validation, `--help`, `--json` option, consistent error exit; Click (vendored) already maps bad params to exit 2 |
| Settings + secret handling | `os.getenv` scattered; plain-string passwords in a config object | `pydantic-settings` `BaseSettings` with `SecretStr` fields | Single choke point; `SecretStr.__repr__` returns `**********`; the source of known values for `redact()` |
| Monotonic event ordering | `ORDER BY created_at`; a Python counter | `BIGINT` identity / `BIGSERIAL` `seq` column, `ORDER BY seq` | Timestamps skew across machines (Phase 11); identity is DB-generated and gap-tolerant |

**Key insight:** In this phase almost every "custom solution" is a way to silently break the durable-run thesis. The atomic-commit block, the column-not-variable rule, and redaction-at-birth are not conveniences — they are the acceptance criteria (SC2/SC4/SC5) expressed as code.

## Runtime State Inventory

Phase 1 is **greenfield** — fresh git repo, zero application code, no prior deployment, no datastore yet provisioned by this project. Not a rename/refactor/migration phase.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the Neon database is created *by* this phase's first Alembic migration. No pre-existing rows, collections, or keys. | Create schema via `migrations/versions/0001_*.py` |
| Live service config | None — no n8n, Datadog, Tailscale, Cloudflare, etc. The only external service is Neon, configured solely by `DATABASE_URL` / `DATABASE_URL_DIRECT` env vars. | Operator provisions a Neon project + database; supplies both connection strings |
| OS-registered state | None — no Task Scheduler / launchd / systemd / pm2. The CLI is a foreground process invoked on demand. | — |
| Secrets / env vars | New: `DATABASE_URL` (pooled), `DATABASE_URL_DIRECT` (direct/un-pooled, for Alembic), `LOG_LEVEL` (opt), `GITHUB_TOKEN` (opt, unused in Phase 1 but load it so `redact()` knows its value). No key rename — these names are introduced here. | Define in `config/settings.py`; document in `.env.example` |
| Build artifacts | None yet. After `uv init` / `uv sync`: `.venv/`, `uv.lock`, `src/dark_factory.egg-info` (editable install metadata) — all fresh, none stale. | Commit `uv.lock`; `.gitignore` `.venv/`, `*.egg-info/` |

**Nothing found in any category that requires a data migration or a state-rename task** — verified by inspecting the repo (`/Users/maryiakrauchanka/portfolio/dark-factory/` contains only `.claude/`, `.git/`, `.planning/`, and an unrelated `seed-app-new.sh` VibeGuard seeder to be ignored/removed).

## Common Pitfalls

### Pitfall 1: Non-atomic "store result + transition + emit event" (directly = SC4 failure)

**What goes wrong:** the role finishes and the code writes `role_executions.result`, then `UPDATE runs SET status`, then `INSERT run_events` in separate commits. A `SIGKILL` / OOM / CI-timeout between any two leaves Neon with a `status` that disagrees with the latest `role_execution`, or a completed role with no event. The run is unresumable or resumes into the wrong branch.
**Why it happens:** each write is individually simple; "save as you go" feels safe; ORM lazy-flush hides the transaction boundary.
**How to avoid:** the single `apply_transition()` (§Pattern 3). One `with session.begin():`; all related writes inside; commit once. Model the legal transitions as an enum table and assert legality before writing.
**Warning signs:** more than one `session.commit()` per lifecycle event; `run_events` via a logging handler; `UPDATE runs SET status` outside `mutations.py`; no crash-injection test.

### Pitfall 2: State that needs the original process's memory (= SC2 failure)

**What goes wrong:** `advance()` computes the workflow / attempt number / "which role we're in" once and passes it down the stack; only some of it is persisted. A fresh process rebuilds a *different* context and the run diverges.
**How to avoid:** the column-not-variable rule (§Pattern 1). Build the resume path first; the drive loop calls `advance()` which reloads from Neon every iteration — the happy path exercises resume on every step. Write the fresh-process test in the same plan.
**Warning signs:** `resume` taking any parameter other than `run_id`; `advance()` holding a `NormalizedTask` across iterations; `attempt` computed in Python from a counter instead of `SELECT max(attempt)+1` inside the mutation tx.

### Pitfall 3: Neon connection handling for a short-lived CLI

**What goes wrong:** a large SQLAlchemy pool, or a connection cached across the ~5-min Neon autosuspend, throws `server closed the connection unexpectedly` on the next query; DDL run through the `-pooler` host misbehaves; SQLAlchemy's default named prepared statements hit "prepared statement does not exist" through PgBouncer transaction pooling.
**How to avoid:** `create_engine(url, poolclass=NullPool, pool_pre_ping=True, connect_args={"prepare_threshold": None})` for the app (§Code Examples 3). `NullPool` because the process runs a handful of queries and exits. `prepare_threshold=None` disables client-side prepared-statement caching (psycopg3 ≥ 3.2 + PgBouncer ≥ 1.22 — Neon's pooler — would otherwise need negotiation). Alembic `env.py` uses `DATABASE_URL_DIRECT` (the non-`-pooler` host). Wrap the *initial* connect in a retry-once-on-`OperationalError` (Neon cold start 300–800 ms).
**Warning signs:** `alembic.ini` / `env.py` referencing a `-pooler` host; `pool_size` > 5; `OperationalError` after an idle gap; `prepared statement "__asyncpg_…" does not exist` (wrong driver) or `… does not exist` after a pooled reconnect.

### Pitfall 4: `status` recomputing position from the event log (= SC3 failure)

**What goes wrong:** `status` (or a shared read helper) folds `run_events` to derive "current role / attempt", so a malformed or missing event changes what `status` reports.
**How to avoid:** `read_status(run_id)` selects **only** `runs` + the latest `role_executions` row (`ORDER BY attempt DESC LIMIT 1`, scoped to `current_role`). Put it in `observability/status.py` with **no import of `events/`**. Test: mutate a `run_events` row to a bogus type and assert `status` output is unchanged; plus an architecture test asserting the import graph.

### Pitfall 5: Redaction that misses a sink, or is added after the fact (= SC5 failure / incident)

**What goes wrong:** `redact()` is applied to `run_events.payload` but not to `role_executions.result`; or structlog is configured before the processor is written; or `capture_logs` in tests bypasses the processor chain so the test passes while the real log file leaks.
**How to avoid:** apply `redact()` to **all three** JSONB targets inside `apply_transition` (single call site); configure structlog once in `logging.py` with the processor in the chain; for the SC5 test, emit to a real `StringIO`/file sink (not `structlog.testing.capture_logs`, which skips processors) and grep that. Also unit-test `redact()` per pattern and per exact value.
**Warning signs:** `redact` imported in only one of `mutations.py`'s write blocks; structlog `configure()` called in more than one place; the only redaction test uses `capture_logs`.

### Pitfall 6: `enum.StrEnum` / native PG enum evolution

**What goes wrong:** defining the status column as a native PG `ENUM` with only the 4 reachable Phase-1 values, then needing `ALTER TYPE … ADD VALUE` (which cannot run inside a transaction on older PG and is awkward in Alembic) for Phase 2+.
**How to avoid:** STATE-07 is a **fixed closed set of 10** — define **all ten** in the first migration (native PG enum *or* `sa.Enum(RunStatus, native_enum=False)` → a `VARCHAR` + `CHECK`). Recommendation: `native_enum=False` CHECK constraint — trivially editable, no `ALTER TYPE`, and mypy-friendly with `enum.StrEnum`. `role_executions.status` and `run_events.type` similarly.

### Pitfall 7: `run` exit-code / stdout ordering (D-01, D-04, D-05)

**What goes wrong:** the run id is printed *after* the drive loop (so a process killed mid-run leaves the operator no id to resume with); or a validation error after the run row is created still exits `2` (should be `1` or a real terminal state); or an unhandled exception exits `1` and is indistinguishable from a persisted `FAILED`.
**How to avoid:** print `run_id` on stdout line 1 **immediately after** `create_run` returns, **before** entering `drive()`. Exit `2` is reserved for failures **before** anything is persisted (unresolvable input, unknown run-id, settings/validation error). Once a `runs` row exists, the outcome is `0` (COMPLETED) or `1` (FAILED) — map from the terminal `RunStatus`, and let genuinely unexpected exceptions propagate as Typer's default (also non-zero) but log them distinctly.

## Code Examples

> Sources: SQLAlchemy 2.0 docs (`docs.sqlalchemy.org/en/20/`), psycopg3 docs (`psycopg.org/psycopg3/docs/`), structlog docs (`www.structlog.org`), Typer docs (`typer.tiangolo.com`), testcontainers-python (`testcontainers.com`). Snippets are idiomatic patterns for the pinned versions; treat as skeletons, not copy-paste.

### 1. The one mutation path — single-transaction commit (SQLAlchemy 2.0 sync)

```python
# persistence/mutations.py
from sqlalchemy.orm import Session
from sqlalchemy import func

from dark_factory.domain.status import RunStatus
from dark_factory.events.redaction import redact
from dark_factory.persistence.models import Run, RoleExecution, RunEvent

class ConcurrentTransition(RuntimeError): ...

def apply_transition(
    session: Session,
    *,
    run_id,
    expected_status: RunStatus,
    next_status: RunStatus,
    next_current_role: str | None,
    role_execution: "RoleExecutionWrite | None",
    events: "Sequence[EventWrite]",
    known_secrets,
) -> RunStatus:
    with session.begin():                     # BEGIN … COMMIT once; ROLLBACK on any exception
        run = session.get(Run, run_id, with_for_update=True)   # short row lock; NOT held across a worker call
        if run is None:
            raise LookupError(run_id)
        if run.status != expected_status:     # optimistic guard (Phase 2 adds the lease)
            raise ConcurrentTransition(f"{run.status} != {expected_status}")

        if role_execution is not None:
            if role_execution.mode == "insert":
                session.add(RoleExecution(
                    run_id=run_id, role=role_execution.role, worker=role_execution.worker,
                    status=role_execution.status, attempt=role_execution.attempt,   # attempt precomputed via SELECT max()+1 in the same session
                    worker_session_id=role_execution.worker_session_id,
                    result=redact(role_execution.result, known_secrets=known_secrets) if role_execution.result else None,
                    error=redact(role_execution.error, known_secrets=known_secrets) if role_execution.error else None,
                ))
            else:  # update the current attempt row
                re = session.get(RoleExecution, role_execution.id, with_for_update=True)
                re.status = role_execution.status
                re.worker_session_id = role_execution.worker_session_id
                re.result = redact(role_execution.result, known_secrets=known_secrets) if role_execution.result else None
                re.error = redact(role_execution.error, known_secrets=known_secrets) if role_execution.error else None
                re.updated_at = func.now()

        run.status = next_status
        run.current_role = next_current_role
        run.updated_at = func.now()

        for ev in events:
            session.add(RunEvent(
                run_id=run_id,
                role_execution_id=ev.role_execution_id,
                type=ev.type.value,
                payload=redact(ev.payload, known_secrets=known_secrets),   # every JSONB payload redacted here
            ))
    return next_status
```
Notes: `session.get(..., with_for_update=True)` is SQLAlchemy 2.0's `SELECT … FOR UPDATE` — it locks the row for the *duration of this short transaction only*. `func.now()` = DB clock (PITFALL 21). `run_events.seq` is a DB identity column — not set here.

### 2. Crash-injection test seam (SC4) — `after_cursor_execute` event raises mid-transaction

```python
# tests/db/test_transition_atomic.py
import pytest
from sqlalchemy import event

class SimulatedCrash(RuntimeError): ...

def test_transition_between_subwrites_rolls_back(engine, db_state_factory):
    run = db_state_factory(status="BA", role="BA", attempt=1)   # committed baseline

    fired = {"n": 0}
    @event.listens_for(engine, "after_cursor_execute")
    def boom(conn, cursor, statement, params, context, executemany):
        # crash *after* the role_executions UPDATE has hit the wire, *before* COMMIT
        if statement.lstrip().upper().startswith("UPDATE ROLE_EXECUTIONS") and fired["n"] == 0:
            fired["n"] = 1
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        advance(run.id)                      # calls apply_transition internally

    event.remove(engine, "after_cursor_execute", boom)

    # ── the invariant: no half-state ──
    with Session(engine) as s:
        r = s.get(Run, run.id)
        assert r.status == "BA"                                   # runs.status unchanged
        assert s.scalar(select(func.count()).select_from(RunEvent)
                        .where(RunEvent.run_id == run.id)) == baseline_event_count
        # latest role_execution result still NULL — the UPDATE was rolled back

    # ── and it is still resumable ──
    assert drive(run.id) == RunStatus.COMPLETED
```
Companion structural test — *no state change without its event*:
```python
def test_every_status_change_has_exactly_one_event(engine, fresh_run):
    before = event_count(fresh_run.id)
    status = advance(fresh_run.id)            # CREATED -> BA
    assert event_count(fresh_run.id) == before + 1     # ROLE_STARTED
    # (BA -> COMPLETED advance emits ROLE_COMPLETED + RUN_COMPLETED = +2; assert the pairing, never 0)
```
Alternative seams (documented, not recommended as primary): monkeypatch `Session.commit` to raise (proves DB-level all-or-nothing but less illustrative); real `subprocess` `SIGKILL` (highest fidelity — use for SC2, see #6).

### 3. Neon engine + Alembic env (psycopg3, pooled vs direct)

```python
# persistence/engine.py
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from dark_factory.config.settings import get_settings

def build_engine():
    s = get_settings()
    return create_engine(
        s.database_url.get_secret_value(),           # postgresql+psycopg://…-pooler.…neon.tech/db
        poolclass=NullPool,                          # short-lived CLI: don't retain Neon connections
        pool_pre_ping=True,                          # resume after a long idle → verify before use
        connect_args={"prepare_threshold": None},    # PgBouncer transaction-pool safety (psycopg3)
        future=True,
    )

SessionLocal = sessionmaker(bind=build_engine(), expire_on_commit=False, class_=__import__("sqlalchemy.orm", fromlist=["Session"]).Session)
```
```python
# migrations/env.py  (excerpt)
import os
from alembic import context
from dark_factory.persistence.models import Base

url = os.environ["DATABASE_URL_DIRECT"]              # the NON -pooler host — DDL must not go through PgBouncer
context.config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata
# ... standard offline/online run blocks; use a NullPool engine here too
```
`[CITED: neon.com/docs/connect/choose-connection]` (pooled for app traffic, direct for migrations); `[CITED: psycopg.org/psycopg3/docs/advanced/prepare.html]` and SQLAlchemy discussion #12522 (`prepare_threshold=None` with PgBouncer).

### 4. `redact()` + structlog wiring

```python
# events/redaction.py
import re
from collections.abc import Mapping

_SENSITIVE_KEYS = frozenset({
    "password","passwd","secret","secret_key","token","api_key","apikey",
    "access_key","database_url","github_token","authorization","bearer",
})
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:[^\s:/@]+@\S+"), "[redacted:database_url]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "[redacted:github_token]"),
    (re.compile(r"\b(gh[porsu])_[A-Za-z0-9]{36,}\b"), "[redacted:github_token]"),
    (re.compile(r"(?i)authorization\"?\s*[:=]\s*\"?bearer\s+[A-Za-z0-9._\-]+"), "[redacted:authorization]"),
    (re.compile(r"(?i)\b(password|passwd|secret|secret_key|token|api_key|apikey|access_key|database_url|github_token|authorization|bearer)\b(\s*[:=]\s*)(\"?)([^\s\"',}]+)\3"), r"\1\2[redacted:\1]"),
]

def _redact_str(v: str, known: Mapping[str, str]) -> str:
    for value, label in known.items():
        if len(value) >= 8 and value in v:
            v = v.replace(value, f"[redacted:{label}]")
    for pat, repl in _PATTERNS:
        v = pat.sub(repl, v)
    return v

def redact(value, *, known_secrets: Mapping[str, str], patterns: bool = True):
    if isinstance(value, Mapping):
        out = {}
        for k, val in value.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                out[k] = f"[redacted:{k.lower()}]"
            else:
                out[k] = redact(val, known_secrets=known_secrets, patterns=patterns)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, known_secrets=known_secrets, patterns=patterns) for v in value]
    if isinstance(value, str):
        return _redact_str(value, known_secrets) if patterns else _scrub_known(value, known_secrets)
    return value
```
```python
# logging.py
import structlog
from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact

def _redaction_processor(logger, method_name, event_dict):
    return redact(event_dict, known_secrets=get_settings().known_secret_values())

def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,          # run_id / role / attempt bound here
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redaction_processor,                             # ← D-14 wiring point (a)
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        cache_logger_on_first_use=True,
    )
```
A structlog processor is `(logger, method_name, event_dict) -> event_dict` `[CITED: www.structlog.org/en/stable/processors.html]`. Bind per-run context with `structlog.contextvars.bind_contextvars(run_id=..., role=..., attempt=...)` at the top of `advance()`.

### 5. `CodingWorker` / `WorkerResult` / `FakeWorker`

```python
# domain/worker.py
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class WorkerResultStatus(StrEnum):
    COMPLETED = "COMPLETED"; NEEDS_INPUT = "NEEDS_INPUT"; FAILED = "FAILED"

class ArtifactRef(BaseModel):            # shape only — not persisted in Phase 1
    model_config = ConfigDict(extra="forbid")
    type: str; path: str; checksum: str | None = None

class WorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: WorkerResultStatus
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    worker_session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

class WorkerCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)
    native_resume: bool = False
    session_id: bool = False
    structured_output: bool = True
    non_interactive: bool = True
    emits_changed_files: bool = False
    max_prompt_bytes: int | None = None
```
```python
# workers/base.py
from abc import ABC, abstractmethod
class CodingWorker(ABC):
    @abstractmethod
    def execute(self, context) -> "WorkerResult": ...
    @abstractmethod
    def resume(self, context, previous: "WorkerResult", answer: str | None) -> "WorkerResult": ...
    @abstractmethod
    def capabilities(self) -> "WorkerCapabilities": ...
```
```python
# workers/fake.py
from collections.abc import Sequence
from uuid import uuid4
from dark_factory.workers.base import CodingWorker
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus, WorkerCapabilities

class FakeWorker(CodingWorker):
    def __init__(self, script: Sequence[WorkerResult] | None = None):
        self._script = list(script) if script is not None else [
            WorkerResult(status=WorkerResultStatus.COMPLETED, summary="BA analysis complete",
                         worker_session_id=f"fake-{uuid4()}")
        ]
        self._i = 0
    def execute(self, context) -> WorkerResult:
        r = self._script[self._i]; self._i += 1; return r
    def resume(self, context, previous, answer) -> WorkerResult:
        return self.execute(context)
    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(native_resume=False, session_id=True, structured_output=True)
```
```python
# workers/registry.py
from collections.abc import Callable
class UnknownWorkerError(KeyError): ...
class WorkerRegistry:
    def __init__(self) -> None:
        self._f: dict[str, Callable[[], "CodingWorker"]] = {}
    def register(self, name: str, factory: Callable[[], "CodingWorker"]) -> None:
        self._f[name] = factory
    def get(self, name: str) -> "CodingWorker":
        try: return self._f[name]()
        except KeyError: raise UnknownWorkerError(name) from None
# bootstrap (Phase 1): registry.register("fake", FakeWorker)
```

### 6. Fresh-process resume test (SC2) — subprocess

```python
# tests/integration/test_fresh_process_resume.py
import subprocess, sys, os

def test_kill_then_resume_reaches_same_terminal_state(pg_url, monkeypatch):
    env = {**os.environ, "DATABASE_URL": pg_url, "DATABASE_URL_DIRECT": pg_url,
           "DARK_FACTORY_CRASH_AFTER": "CREATED_BA"}          # a test hook: os._exit(137) after that commit
    p1 = subprocess.run([sys.executable, "-m", "dark_factory", "run", 'text:"do the thing"'],
                        capture_output=True, text=True, env=env, timeout=30)
    run_id = p1.stdout.splitlines()[0].strip()                # D-01: id on line 1, printed before the crash
    assert p1.returncode != 0                                 # process died mid-run

    env.pop("DARK_FACTORY_CRASH_AFTER")
    p2 = subprocess.run([sys.executable, "-m", "dark_factory", "resume", run_id],
                        capture_output=True, text=True, env=env, timeout=30)
    assert p2.returncode == 0
    assert "→ COMPLETED" in p2.stdout
    # DB assertion: runs.status == COMPLETED, exactly one role_executions row (attempt=1, not reset)
```

### 7. Typer CLI skeleton

```python
# cli.py
import json, typer
from dark_factory.domain.status import RunStatus
from dark_factory.input.resolver import classify, UnresolvableSourceError
from dark_factory.input.loaders import load, SourceNotSupportedError
from dark_factory.orchestrator.runner import create_run, drive
from dark_factory.observability.status import read_status, UnknownRunError

app = typer.Typer(no_args_is_help=True, add_completion=False)

@app.command()
def run(source: str) -> None:
    try:
        kind, locator = classify(source)
        task = load(kind, locator)
    except (UnresolvableSourceError, SourceNotSupportedError) as e:
        typer.echo(str(e), err=True); raise typer.Exit(code=2)
    run_id = create_run(task)
    typer.echo(str(run_id))                       # D-01: line 1, before the loop
    final = drive(run_id, on_transition=lambda a, b: typer.echo(f"{a} → {b}"))   # D-04
    _summary(run_id, final)
    raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)   # D-05

@app.command()
def resume(run_id: str) -> None:                  # no --answer in Phase 1 (D-03)
    try: read_status(run_id)
    except UnknownRunError: typer.echo(f"unknown run: {run_id}", err=True); raise typer.Exit(code=2)
    typer.echo(run_id)
    final = drive(run_id, on_transition=lambda a, b: typer.echo(f"{a} → {b}"))
    _summary(run_id, final)
    raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)

@app.command()
def status(run_id: str, json_: bool = typer.Option(False, "--json")) -> None:
    try: view = read_status(run_id)               # runs + latest role_executions ONLY (D-11 / SC3)
    except UnknownRunError: typer.echo(f"unknown run: {run_id}", err=True); raise typer.Exit(code=2)
    typer.echo(json.dumps(view.model_dump(mode="json")) if json_ else view.as_text())
```
`[CITED: typer.tiangolo.com]` — `typer.Exit(code=…)`; Click (vendored) already maps `BadParameter` to exit 2. Add `src/dark_factory/__main__.py` (`from dark_factory.cli import app; app()`) for `python -m dark_factory`.

### 8. Input resolver + text loader

```python
# input/resolver.py
from enum import StrEnum
class SourceKind(StrEnum):
    TEXT = "text"; SPEC = "spec"; GITHUB = "github"
class UnresolvableSourceError(ValueError): ...
_PREFIXES = {"text:": SourceKind.TEXT, "spec:": SourceKind.SPEC, "github:": SourceKind.GITHUB}
def classify(raw: str) -> tuple[SourceKind, str]:
    for prefix, kind in _PREFIXES.items():
        if raw.startswith(prefix):
            return kind, raw[len(prefix):]
    raise UnresolvableSourceError(f"cannot classify source: {raw!r}")   # no I/O, no run created
```
```python
# input/loaders.py
from dark_factory.domain.task import NormalizedTask
from dark_factory.input.resolver import SourceKind
class SourceNotSupportedError(NotImplementedError): ...

def _load_text(locator: str) -> NormalizedTask:
    text = locator.strip().strip('"')
    return NormalizedTask(source_kind="text", source_ref=None,
                          title=text.splitlines()[0][:120] if text else "", body=text, metadata={})
def _load_spec(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError("spec: sources are not supported until Phase 4")
def _load_github(locator: str) -> NormalizedTask:
    raise SourceNotSupportedError("github: sources are not supported until Phase 10")

_LOADERS = {SourceKind.TEXT: _load_text, SourceKind.SPEC: _load_spec, SourceKind.GITHUB: _load_github}
def load(kind: SourceKind, locator: str) -> NormalizedTask:
    return _LOADERS[kind](locator)
```

## State of the Art

| Old Approach | Current Approach (use this) | When Changed | Impact for Phase 1 |
|--------------|---------------------------|--------------|--------------------|
| `sessionmaker` + manual `try/commit/except/rollback` | `with session.begin():` context-managed transaction | SQLAlchemy 1.4 → 2.0 | The atomic-commit block for `apply_transition` (SC4) |
| `@event.listens_for(Session, "after_transaction_end")` savepoint-restart recipe for test isolation | `Session(bind=conn, join_transaction_mode="create_savepoint")` | SQLAlchemy 2.0.0 | The `db_session` fixture in `conftest.py` |
| `postgresql+psycopg2://` | `postgresql+psycopg://` (psycopg 3) | psycopg3 GA / SQLAlchemy 1.4.27+ | Engine URL scheme; psycopg2 is maintenance-only |
| `class RunStatus(str, Enum)` mixin | `class RunStatus(enum.StrEnum)` | Python 3.11 | Status / worker-status / event-type enums |
| `datetime.utcnow()` (naive, deprecated in 3.12) | `datetime.now(datetime.UTC)` — but prefer DB `func.now()` for persisted columns | Python 3.12 | All timestamps come from `server_default=func.now()` (PITFALL 21) |
| pydantic v1 `class Config` / `.dict()` / `@validator` | v2 `model_config = ConfigDict(...)` / `.model_dump()` / `@field_validator` | pydantic 2.0 | Every domain model |
| `typer.Option(False, "--json")` default-value style | `Annotated[bool, typer.Option("--json")]` (both still supported) | Typer 0.9+ | Optional stylistic choice for `status --json` |
| `freezegun` | `time-machine` (faster, C-based) | — | Phase 2 lease tests; minimal Phase 1 use |

**Deprecated / do not use:** `psycopg2`, `asyncpg`, `SQLModel`, `datetime.utcnow()`, `transitions` as a state source of truth, a native PG `ENUM` seeded with only the reachable subset of STATE-07, `structlog.testing.capture_logs` as the *only* redaction test (it bypasses processors).

**Pin drift noted this session:** `polyfactory` is now `3.3.0` and `time-machine` is now `3.5.0` — both a major ahead of the ranges implied in `STACK.md` (`>=2,<3` / `>=2`). Recommend the planner set `polyfactory>=3,<4` and `time-machine>=3,<4` in `pyproject.toml`. No API break relevant to Phase 1 usage.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The operator supplies two Neon connection strings: `DATABASE_URL` (pooled, `-pooler` host) for the app and `DATABASE_URL_DIRECT` (direct host) for Alembic. Implied by STACK.md/PITFALLS.md, not stated in CONTEXT.md. | Standard Stack, Pitfall 3, Code Examples 3 | If only one URL is available, Alembic DDL through the pooler can hang/fail; migration plan needs a different approach (e.g. a `NullPool` + `prepare_threshold` engine and accepting the risk, or a local PG for schema dev). |
| A2 | Docker is available on the dev/CI machine for `testcontainers`. **Not verified** — `docker` is absent from this research sandbox; no `psql`/`initdb` either. | Standard Stack (dev/test), Environment Availability, Validation Architecture | If no Docker: fall back to `pytest-postgresql` (needs local PG binaries) or point `db`/`integration` tests at a throwaway Neon branch via env var and `skipif` when unset. The plan must pick one and make it a Wave 0 task. |
| A3 | `runs.id` / `role_executions.id` / `run_events.id` are UUIDs (v4), app- or DB-generated (`gen_random_uuid()`); `run_events` additionally has a `BIGINT` identity `seq` for ordering. Spec says "run identity", not the type. | Architecture Patterns → Schema | A different id type (e.g. bigint) changes FK columns and the CLI's run-id argument shape; cheap to change now, an Alembic migration later. |
| A4 | The 40-hex classic-PAT redaction pattern is scoped to a "github-ish context" to avoid clobbering legitimate git SHAs in task text. Exact heuristic is tunable. | Pattern 5, Code Examples 4 | Too aggressive → mangles task text containing commit SHAs (D-18 says raw task text should persist as given); too loose → a bare classic PAT in prose leaks. Needs a test corpus. |
| A5 | `current_step` is a small integer ordinal stored **alongside** `current_role` (the identifier of record). STATE-02 says "current step"; PITFALL 20 says store an identifier not an index. | Architecture Patterns → Schema | If a later phase indexes `workflow.roles` by `current_step`, config edits during a pause misalign it — but Phase 3 owns the snapshot, and `current_role` is the authoritative pointer here. |
| A6 | The status column is `VARCHAR + CHECK` (`sa.Enum(..., native_enum=False)`) carrying all 10 STATE-07 values from migration 0001, not a native PG `ENUM`. | Pitfall 6, State of the Art | If a native PG enum is chosen instead, Phase 2+ additions are fine (all 10 defined now) but `ALTER TYPE` is still a hazard if the set ever grows. Low risk either way. |
| A7 | `CREATED → BA` and `BA → COMPLETED/FAILED` are **two** separate committed `advance()` calls (2 calls for the 1-role happy path). D-02 says "exactly one step" per call; this is the natural reading. | Pattern 1 | If the planner folds them into one `advance()` call, the mid-run kill window (SC2/SC4 test) shrinks to "inside one transaction" only — still valid but less demonstrative. Not a correctness risk. |
| A8 | The SC5 log-redaction test asserts against a real structlog sink (`StringIO`/file with the processor chain active), not `structlog.testing.capture_logs`. | Pitfall 5, Validation Architecture | If the test uses `capture_logs`, it passes while the real log file could still leak — a false-green on an unrecoverable-leak criterion. |
| A9 | `nyquist_validation` is enabled (config.json `workflow.nyquist_validation: true`) so the Validation Architecture section applies; `security_enforcement: true` at ASVS L1 so the Security Domain section applies. | Validation Architecture, Security Domain | Confirmed from `.planning/config.json` this session — low risk. |
| A10 | `GITHUB_TOKEN` is loaded by `Settings` in Phase 1 (even though unused) so `redact()` knows its literal value for D-16 exact-substitution. | Pattern 5 | If it is not loaded, a `GITHUB_TOKEN`-shaped value in task text is still caught by the D-15 pattern, but the exact-value guarantee (used by Phase 6/12 grep checks) does not cover it yet. |

## Open Questions

1. **Which Postgres does the test suite run against?**
   - What we know: `testcontainers` is the pinned first choice (`postgres:17-alpine`); `pytest-postgresql` is the documented Docker-free fallback; a Neon branch is the pre-merge-smoke option.
   - What's unclear: whether the dev/CI environment has Docker. It is absent in this research sandbox (no `docker`, no `psql`, no `initdb`).
   - Recommendation: make "stand up the test Postgres" an explicit Wave 0 task in the plan. Prefer `testcontainers`; if `docker info` fails on the target machine, fall back to `pytest-postgresql` with a documented local-PG-17 prerequisite, or `DATABASE_URL`-driven tests against a Neon branch with `pytest.mark.skipif` when unset. The `unit` marker (lifecycle, redaction, resolver, model validation) needs **no** database and must stay green regardless.

2. **`run_events.seq` type — `BIGSERIAL` vs `GENERATED ALWAYS AS IDENTITY`.**
   - What we know: ordering must be a DB-generated monotonic sequence, not a timestamp (PITFALL 21).
   - What's unclear: which of the two idioms; identity is the modern SQL-standard form, `BIGSERIAL` is the historical Postgres one. Functionally equivalent for Phase 1.
   - Recommendation: `sa.BigInteger` primary key with `autoincrement=True` (SQLAlchemy emits `GENERATED BY DEFAULT AS IDENTITY` on PG 17). Decide in the schema plan; trivially reversible.

3. **Does `create_run` go through `apply_transition`, or is it a sibling function?**
   - What we know: D-14 says "one redaction path"; ORCH-06 says "one mutation path" for "store result, transition state, create interaction, emit event".
   - What's unclear: whether the very first insert (`∅ → CREATED` + `RUN_CREATED`) must literally call `apply_transition` (which assumes a pre-existing row to `SELECT … FOR UPDATE`) or a dedicated `create_run` that shares the same redaction + single-transaction discipline.
   - Recommendation: a dedicated `create_run(session, task)` in `mutations.py` that (a) is in the same module, (b) uses one `with session.begin():`, (c) redacts the `RUN_CREATED` payload and the `normalized_task` (known-value-only per D-18) with the same `redact()`. It cannot use the `expected_status` guard (no row yet). Treat "one mutation path" as "one module, one transaction discipline, one redaction call", not "one function".

## Environment Availability

| Dependency | Required By | Available (research sandbox) | Version | Fallback |
|------------|------------|------------------------------|---------|----------|
| Python 3.12 | Everything | ✓ | 3.12.7 | — |
| uv | deps / lockfile / `[project.scripts]` | ✓ | 0.12.7 | pip + venv (slower, no Python pinning) |
| git | repo (already initialised) | ✓ | 2.39.5 | — |
| Neon Postgres (or any PG 17) | `runs`/`role_executions`/`run_events`, all `db`/`integration` tests, Alembic | ✗ (no `DATABASE_URL` set; no local PG) | — | Operator provisions a Neon project; supply `DATABASE_URL` + `DATABASE_URL_DIRECT` |
| Docker (for `testcontainers`) | `db` + `integration` test suites | ✗ (`docker` not on PATH) | — | `pytest-postgresql` (needs local `initdb`/`pg_ctl` — also ✗ here) **or** a Neon branch via env var with `skipif` |
| `psql` / `initdb` / `pg_ctl` | `pytest-postgresql` fallback | ✗ | — | Install `postgresql-client` + server, or use Docker/testcontainers, or Neon branch |

**Missing dependencies with no fallback:** a reachable Postgres 17 for the `db` / `integration` tiers — one of {Docker+testcontainers, local PG, Neon branch} **must** be established as a Wave 0 task before those tests can be written or run. The `unit` tier (pure functions) is unblocked.

**Missing dependencies with fallback:** the Postgres *provisioning method* is interchangeable — the plan should choose one and record it, not assume Docker.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — this section applies. VALIDATION.md is derived from it.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.x (+ `testcontainers[postgres]` 4.15 for `db`/`integration`; `polyfactory` 3.x for fixtures) |
| Config file | none yet — **Wave 0**: `[tool.pytest.ini_options]` in `pyproject.toml` (`testpaths=["tests"]`, `markers=["unit","db","integration","contract"]`) |
| Quick run command | `uv run pytest -m unit -q` |
| Full suite command | `uv run pytest -q` (requires the test Postgres — see Environment Availability) |

### Phase Requirements → Test Map

| SC / Req | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|--------------|
| **SC1** / INTAKE-01, ORCH-01, WORK-10, STATE-02/03/06 | `run text:"..."` → `runs` row, one `role_executions` (role=BA, worker=fake, attempt=1, COMPLETED), events `RUN_CREATED,ROLE_STARTED,ROLE_COMPLETED,RUN_COMPLETED`, status `COMPLETED`, exit 0 | integration | `pytest tests/integration/test_walking_skeleton.py::test_run_reaches_completed -x` | ❌ Wave 0 |
| **SC1** (failure arm) / D-10 | scripted `WorkerResult(FAILED)` → status `FAILED`, `ROLE_FAILED`+`RUN_FAILED`, exit 1 | db | `pytest tests/db/test_run_failure_path.py -x` | ❌ Wave 0 |
| **SC2** / STATE-08, D-02 | subprocess `run` killed after `CREATED→BA` commit; fresh `resume <id>` subprocess → `COMPLETED`, exit 0, attempt not reset, same run_id | integration | `pytest tests/integration/test_fresh_process_resume.py -x` | ❌ Wave 0 |
| **SC2** (fast variant) | `advance()` loop with a brand-new engine/`sessionmaker` per step → `COMPLETED`; assert no module-level mutable carryover | db | `pytest tests/db/test_resume_first_advance.py -x` | ❌ Wave 0 |
| **SC3** / STATE-06, D-11 | `status` reports state/role/attempt equal to `runs`+`role_executions` columns; unchanged after a bogus `run_events` row is inserted; `observability.status` does not import `events` | db + unit | `pytest tests/db/test_status_from_columns.py tests/unit/test_status_import_graph.py -x` | ❌ Wave 0 |
| **SC4** / ORCH-06 | `after_cursor_execute` raises after the `role_executions` write inside `apply_transition` → full ROLLBACK (status unchanged, 0 new events, result still NULL); then `advance` again → `COMPLETED` | db | `pytest tests/db/test_transition_atomic.py -x` | ❌ Wave 0 |
| **SC4** (pairing) / STATE-06 | after each `advance`, (status changed) ⇔ (≥1 matching `run_events` row); never a status change with 0 events, never an orphan event | db | `pytest tests/db/test_state_event_pairing.py -x` | ❌ Wave 0 |
| **SC5** / SEC-02, D-14..D-18 | end-to-end run with task text containing `postgres://u:p@h/db` + the live fake `DATABASE_URL`; grep every `run_events.payload`, `role_executions.result/error`, and the real log sink → 0 hits of the password / URI regex; `[redacted:` present | integration | `pytest tests/integration/test_secret_redaction_e2e.py -x` | ❌ Wave 0 |
| **SC5** (unit) | `redact()` per D-15 pattern + per D-16 exact value + D-18 patterns-off mode for `NormalizedTask` | unit | `pytest tests/unit/test_redaction.py -x` | ❌ Wave 0 |
| ORCH-05 / WORK-01/08 | `lifecycle.transition` pure (no DB) for every legal `(status,signal)`; illegal pairs raise | unit | `pytest tests/unit/test_lifecycle.py -x` | ❌ Wave 0 |
| WORK-03 | grep `src/dark_factory` outside `workers/`,`config/` for `"claude"/"copilot"/"hermes"` → none | unit | `pytest tests/unit/test_no_worker_name_leak.py -x` | ❌ Wave 0 |
| WORK-01/08/10 (QUAL-02 seam) | shared `CodingWorker` contract suite parametrized over `[FakeWorker(...)]`: status ∈ enum; `worker_session_id` present iff `capabilities().session_id`; `NEEDS_INPUT ⇒ questions` | contract | `pytest tests/contract/test_coding_worker_contract.py -x` | ❌ Wave 0 |
| INTAKE-04 | `classify()` does no I/O (monkeypatch `open`/`socket`/DB and assert unused), does not create a run; unknown prefix → `UnresolvableSourceError` | unit | `pytest tests/unit/test_resolver.py -x` | ❌ Wave 0 |
| INTAKE-05 | `text:` → `NormalizedTask`; `spec:`/`github:` → `SourceNotSupportedError` (exit 2, nothing persisted) | unit + integration | `pytest tests/unit/test_loaders.py tests/integration/test_unsupported_source_exit2.py -x` | ❌ Wave 0 |
| STATE-01 | Alembic `upgrade head` then `downgrade base` clean against a real PG; models match migration (`alembic check`) | db | `pytest tests/db/test_migrations.py -x` | ❌ Wave 0 |
| D-05 | exit code 0 / 1 / 2 for COMPLETED / FAILED / bad-invocation | integration | `pytest tests/integration/test_exit_codes.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -m unit -q` (pure, no DB — sub-second).
- **Per wave merge:** `uv run pytest -q` (full suite incl. `db`/`integration` against the test Postgres).
- **Phase gate:** full suite green + `alembic upgrade head`/`downgrade base` round-trips + the SC1–SC5 named tests all present and passing, before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths`, `markers` (`unit`/`db`/`integration`/`contract`)
- [ ] Test Postgres provisioning — pick one: `testcontainers` (needs Docker) | `pytest-postgresql` (needs local PG 17) | Neon branch via `DATABASE_URL` + `skipif`. **Blocking for `db`/`integration`.**
- [ ] `tests/conftest.py` — session-scoped `engine`/container fixture; `alembic upgrade head` helper; `db_session` fixture (`Session(bind=conn, join_transaction_mode="create_savepoint")` inside an outer rolled-back `conn.begin()`); a **separate** truncate-teardown fixture for cross-connection `integration` tests; `settings` override fixture (fake-shaped secrets); real-sink structlog capture fixture; `FakeWorker` factory + `polyfactory` model factories
- [ ] `tests/contract/test_coding_worker_contract.py` — parametrized `[FakeWorker]` now; Claude Code / Copilot / Hermes appended in Phases 7–8
- [ ] Test hook for the crash points — an env-var-driven `DARK_FACTORY_CRASH_AFTER` (or an injectable `after_cursor_execute` listener) used only by SC2/SC4 tests
- [ ] Framework install: `uv add --dev pytest testcontainers[postgres] pytest-postgresql polyfactory time-machine`

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high` (`.planning/config.json`). This section applies.

### Applicable ASVS Categories (L1)

| ASVS Category | Applies | Standard Control in Phase 1 |
|---------------|---------|-----------------------------|
| V2 Authentication | no | No user auth surface — single-operator local CLI; only DB credentials, held in `SecretStr` |
| V3 Session Management | no | No sessions (the `worker_session_id` is an opaque worker handle, not a security session) |
| V4 Access Control | no | No multi-user access model in Phase 1 |
| V5 Validation, Sanitization & Encoding | **yes** | Resolver prefix **allow-list** (`text:`/`spec:`/`github:` only); pydantic v2 validation of `NormalizedTask` / `WorkerResult` (`extra="forbid"`); Typer/Click arg parsing; **all SQL via SQLAlchemy Core/ORM parameters — no string-built SQL**; `text:` loader does not read files (no path traversal); `spec:` disabled |
| V6 Stored Cryptography | no | No crypto in Phase 1; `SecretStr` for in-memory secret hygiene only |
| V7 Error Handling & Logging | **yes** | `redact()` structlog processor on every log line; engine built from `SecretStr` parts, the URL is never echoed or logged; labeled `[redacted:*]` tokens; unexpected exceptions do not serialize config/context objects |
| V8 Data Protection | **yes** | `redact()` before every JSONB write (`run_events.payload`, `role_executions.result/error`); known-value scrub of `NormalizedTask`/`source_ref` (D-16/D-18); Neon holds state only — no artifact content, no secret material |
| V12 Files & Resources | minor | No file reads in Phase 1 (`text:` only); `spec:`/`github:` loaders raise before touching anything |
| V14 Configuration | **yes** | `pydantic-settings` from env/`.env`; pooled vs direct URL separation; secrets never reach `run_events`; `.env` git-ignored; `.env.example` documents names only |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret embedded in task text (`DATABASE_URL`-shaped value) persisted to `run_events` / `role_executions` / logs | Information Disclosure | `redact()` at the one mutation path + structlog processor, from the first persistence code (SEC-02, SC5) |
| SQL injection via task text flowing into a query | Tampering | SQLAlchemy Core/ORM parameterized statements only; zero f-string / `%`-built SQL; `ruff`/review guard |
| Connection string with password surfacing in a stack trace or crash log | Information Disclosure | Build the engine from `SecretStr.get_secret_value()` at the single call site; global `postgres://user:pass@` redaction pattern; never `echo`/`log` the URL |
| Log injection / forging via newlines in task text | Repudiation / Tampering | `structlog` `JSONRenderer` (values encoded); never build log messages by string concatenation of task text |
| Non-atomic write corrupts the audit trail (event without state, or vice versa) | Repudiation | Single-transaction `apply_transition` (ORCH-06, SC4) — the audit row and the state change share one commit |
| Worker-name branch leaks runtime-specific behavior into core | Tampering (integrity of the abstraction) | `WorkerRegistry` + `WorkerCapabilities` only; CI grep guard for `"claude"/"copilot"/"hermes"` outside `workers/` |
| (Deferred, establish the habit) subprocess inheriting `os.environ` | Elevation of Privilege | Not exercised in Phase 1 (FakeWorker is in-process); do not write `os.environ.copy()` helpers — Phase 6/7 build the explicit allowlist |

**Block-on-high check:** no `high`-severity ASVS-L1 gap identified for Phase 1 provided (a) `redact()` is wired at both points before any row is written, and (b) all SQL goes through SQLAlchemy. Both are plan tasks, not optional.

## Sources

### Primary (HIGH confidence)
- **PyPI JSON registry API** (`pypi.org/pypi/<pkg>/json`) — versions + upload dates verified 2026-09-07: sqlalchemy 2.0.52, alembic 1.19.2, psycopg 3.3.5, pydantic 2.13.5, pydantic-settings 2.15.0, typer 0.27.2, structlog 26.1.0, testcontainers 4.15.0, pytest-postgresql 9.1.0, polyfactory 3.3.0, time-machine 3.5.0.
- **Project `STACK.md` / `CLAUDE.md`** — pinned stack, version-compatibility matrix, "What NOT to Use", sync-vs-async decision, Neon pooled/direct guidance.
- **Project `ARCHITECTURE.md`** — resume-first `advance(run_id)`, the one mutation path (transactional outbox applied internally), checkpoint-not-replay, component responsibility table, amended §72 module layout.
- **Project `PITFALLS.md`** — Pitfalls 1–5, 21, 22 (non-atomic mutation, non-reconstructable state, transaction-across-subprocess, Neon connection handling, clock skew, Alembic/pooler); the "Looks Done But Isn't" checklist.
- **Project `PROJECT.md` / `REQUIREMENTS.md` / `ROADMAP.md`** — event catalog, STATE-07 enum, Phase 1 requirement text, five success criteria, cross-cutting invariants.
- **CONTEXT.md D-01…D-23 + DISCUSSION-LOG** — all binding user decisions for this phase.
- **`.planning/config.json`** — `nyquist_validation: true`, `security_enforcement: true`, `security_asvs_level: 1`.
- **Local environment probe** — `python 3.12.7`, `uv 0.12.7`, `git 2.39.5`; Docker / `psql` / `initdb` / `DATABASE_URL` **absent**.

### Secondary (MEDIUM confidence — cross-checked docs, not re-fetched in full this session)
- **SQLAlchemy 2.0 documentation** — `Session.begin()` transaction context manager; `Session(bind=connection, join_transaction_mode="create_savepoint")` test-isolation pattern; `session.get(..., with_for_update=True)`; Core `after_cursor_execute` event. `[CITED: docs.sqlalchemy.org/en/20/orm/session_transaction.html]`
- **psycopg 3 — "Prepared statements"** — `prepare_threshold=None` disables client prepared-statement caching; psycopg ≥ 3.2 supports prepared statements with PgBouncer ≥ 1.22. `[CITED: psycopg.org/psycopg3/docs/advanced/prepare.html]` — corroborated by SQLAlchemy GitHub Discussion #12522 and multiple PgBouncer-transaction-mode write-ups (WebSearch, 2026-09-07).
- **Neon docs** — "Choosing your connection method" (pooled for app traffic, direct/un-pooled for migrations); "Connection latency and timeouts" (5-min autosuspend, 300–800 ms cold start). `[CITED: neon.com/docs/connect/choose-connection]`, `[CITED: neon.com/docs/connect/connection-latency]`
- **structlog docs** — processor signature `(logger, method_name, event_dict) -> event_dict`; `configure(processors=[...])`; `contextvars.bind_contextvars`. `[CITED: www.structlog.org/en/stable/processors.html]`
- **Typer docs** — `typer.Exit(code=...)`, `typer.Option`, `Annotated` param style; Click vendored since 0.26. `[CITED: typer.tiangolo.com]`
- **testcontainers-python** — `PostgresContainer("postgres:17-alpine")`, `get_connection_url()`, session-scoped fixture pattern; `driver="psycopg"` for a `postgresql+psycopg://` URL. `[CITED: testcontainers.com/guides/getting-started-with-testcontainers-for-python]`

### Tertiary (LOW confidence — verify during implementation)
- Exact redaction regexes in §Pattern 5 / Code Examples 4 — starting points synthesised from D-15; the 40-hex classic-PAT heuristic in particular needs a test corpus `[ASSUMED]`.
- The two-`advance()`-calls-per-role granularity (A7) — a reading of D-02, not an explicit decision.
- `run_events.seq` idiom (`IDENTITY` vs `BIGSERIAL`) — Open Question 2.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pre-pinned by the project and re-verified against the PyPI registry this session; APIs are stable at these versions.
- Architecture / patterns (one mutation path, resume-first `advance`, redaction wiring): HIGH on the shape (it is dictated by ARCHITECTURE.md + the five success criteria + D-01…D-23), MEDIUM on the exact code skeletons.
- Schema column set: MEDIUM — reasoned from STATE-02/03/06 + D-19/D-20/D-22 + PITFALLS; id/enum/seq specifics are flagged as assumptions/open questions.
- Crash-injection test seam: MEDIUM — `after_cursor_execute` is a known-good mechanism but not prescribed by any source; alternatives documented.
- Pitfalls: HIGH — lifted from the project's own PITFALLS.md, which is cited to Neon docs + durable-execution literature.
- Environment availability: HIGH for what was probed (Docker/PG absent in this sandbox); the dev machine's real state is an open question.

**Research date:** 2026-09-07
**Valid until:** ~2026-10-07 for the stack versions (fast-moving minor releases; the pins have upper bounds so drift is contained); the architecture/pattern guidance is stable for the life of the milestone.
