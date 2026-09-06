# Stack Research

**Domain:** Durable, resumable Python orchestration platform (CLI-first) that coordinates external AI engineering-agent CLIs through a fixed role pipeline, persisting full run lifecycle state in Neon PostgreSQL and publishing GitHub PRs
**Researched:** 2026-09-06
**Confidence:** HIGH on library selection and current versions (verified against the PyPI registry API); MEDIUM on the sync-vs-async and durable-execution judgement calls (cross-referenced vendor docs + community guidance, no single authoritative source)

---

## TL;DR (the load-bearing decisions)

1. **Sync, not async.** This is the highest-leverage decision. The orchestrator is a CLI process that handles **one run at a time** and spends its wall-clock time blocked on multi-minute agent-CLI subprocesses, `git push`, and GitHub API calls — not on database concurrency. Async buys nothing here and costs a lot (function coloring, harder pytest, asyncpg/PgBouncer prepared-statement pain). Use a **synchronous SQLAlchemy 2.0 engine + psycopg 3**. Revisit only if a long-lived multi-tenant webhook service is added later — and even then, run it as a separate thin process.
2. **No durable-workflow engine.** Hand-roll an explicit enum state machine whose authoritative state lives in Neon. Enforce "two processes never run the same run" with a **conditional `UPDATE ... WHERE` claim + `SELECT ... FOR UPDATE`** (optionally `pg_advisory_xact_lock`). Temporal / Prefect / Celery are explicitly overkill and violate the "no separate orchestration/lock service" constraint.
3. **Shell out to `git`**, talk to GitHub through **`githubkit`**, invoke agent CLIs through **stdlib `subprocess`** with an explicit `env` allowlist (the security boundary).
4. **Tooling:** `uv` + `ruff` + `mypy` + `pytest` + `testcontainers`, `src/` layout, Python 3.12.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.12 (baseline `>=3.12`) | Language runtime | 3.12 is the current well-supported baseline; every library below supports it. Avoids the `>=3.11`-only floor that `pygit2` would impose, and gets `tomllib`, faster startup, better error messages. 3.13 works too but 3.12 maximizes wheel availability. |
| **Typer** | 0.27.2 | CLI framework for `run \| resume \| status \| runs \| artifacts \| events` | Type-hint-driven command definitions map 1:1 onto the six subcommands with almost no boilerplate; sub-`typer.Typer()` groups model `runs`/`artifacts`/`events` sub-namespaces cleanly. Bundles Rich for `status` tables and tracebacks, ships shell completion. Since 0.26 it **vendors Click** — no separate Click pin, no version skew. Backed by the FastAPI org, actively released. |
| **SQLAlchemy** | 2.0.52 (pin `>=2.0.40,<2.1`) | ORM + Core for the `runs`, `role_executions`, `human_interactions`, `artifacts`, `run_events` tables | Named in the spec. 2.0 typed ORM (`Mapped[...]` / `mapped_column`) gives mypy-checked models, first-class `JSONB`, `SELECT ... FOR UPDATE` / `.with_for_update()`, and portable-but-not-leaky Postgres access. **Use the synchronous API.** 2.1 is in RC as of 2026-09 — stay on 2.0.x until 2.1 is final, the upgrade is uneventful. |
| **psycopg (v3)** | 3.3.5 (pin `>=3.2,<4`) | PostgreSQL driver behind SQLAlchemy (`postgresql+psycopg://`) | psycopg2 (2.9.x) is maintenance-only — no new features. psycopg3 is faster, far more memory-efficient, has a cleaner pipeline/prepared-statement model, and — critically for Neon — **v3.2+ negotiates protocol-level prepared statements through PgBouncer 1.22+**. One driver serves both the sync engine and any future async edge. |
| **Alembic** | 1.19.2 | Schema migrations | The migration tool for SQLAlchemy; named in the spec. Autogenerate from the 2.0 models. **Run migrations against Neon's direct (un-pooled) endpoint**, not the `-pooler` host — DDL + PgBouncer transaction pooling do not mix. |
| **Neon PostgreSQL** | managed (PG 17) | Durable run state, metadata, audit trail | Given. Treat as plain Postgres: `DATABASE_URL` only, no `neon`-specific imports. Two connection strings in config: pooled (`...-pooler.neon.tech`, for the app) and direct (for Alembic). |
| **pydantic** | 2.13.5 (pin `>=2.9,<3`) | Domain models that cross a boundary: `NormalizedTask`, `WorkerResult`, `WorkerCapabilities`, `RoleContext`, `ArtifactReference`, role/`.dark-factory.yaml` config schemas, JSONB payload shapes | v2 is the standard for validated boundary data. Validate agent-CLI JSON output, YAML config, and JSONB columns on the way in; serialize events on the way out. Keep pydantic models **separate from** SQLAlchemy ORM classes (do not use SQLModel — see "What NOT to Use"). |
| **pydantic-settings** | 2.15.0 | Load + validate `DATABASE_URL`, `GITHUB_TOKEN`, worker credentials, log level from env / `.env` | Purpose-built for typed settings with env precedence. This object is the single choke point for infrastructure secrets — it is what you deliberately **do not** pass into worker subprocess environments. Use `SecretStr` fields so secrets don't render in logs/reprs. |
| **PyYAML** | 6.0.3 | Parse `.dark-factory.yaml` and `.dark-factory/roles/*.yaml` | Config is read-only at runtime, so `yaml.safe_load` into pydantic models is all that's needed. No comment round-tripping requirement → no `ruamel.yaml`. |
| **githubkit** | 0.16.1 | GitHub REST + GraphQL + webhook payloads: read issue/comments, create branch refs, open PRs, post/ingest clarification comments, parse `issue_comment` webhooks | Fully typed, auto-generated from the OpenAPI spec (always current), built on `httpx`, sync **and** async from one client, optional Pydantic validation of **webhook events** and responses, built-in pagination + retry, GitHub App / PAT / OAuth auth. The webhook model classes remove hand-written event parsing. |
| **git (CLI)** | system `git >=2.40` via `subprocess` | Branch creation, worktree/clean-tree checks, staging, commit, push, diff collection | The `git` CLI is the ground truth, supports `git worktree` for isolated run checkouts, needs no native build, and you already own robust subprocess infrastructure for the agent CLIs. Wrap it in one thin `GitClient` module with structured errors. |
| **subprocess (stdlib)** | 3.12 | Invoke `claude`, `copilot`, `hermes` non-interactively; run quality-gate commands | No dependency does this better. `Popen` with `args` list (never `shell=True`), explicit `env=` allowlist (**the credential boundary**), `cwd=` the run worktree, `start_new_session=True` for process-group kill on timeout, capture stdout/stderr, parse `--output-format json`. |
| **uv** | 0.12.10 | Dependency resolution, lockfile, virtualenv, Python version pinning, packaging | The de-facto standard in 2025-2026. `uv.lock` + PEP 621 `pyproject.toml`, 10-100x faster than pip/Poetry, manages the Python toolchain itself, `uv run` / `uv build` / `uv publish`. One tool replaces pip + pip-tools + pipx + pyenv + Poetry. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **rich** | 15.0.0 | `status`/`runs` tables, trees, progress, colored diffs | Comes transitively via Typer; use directly for the `status <run>` render (per-role pipeline, attempts, artifacts, interactions). |
| **structlog** | 26.1.0 | Structured, JSON-capable logging with a **secret-redaction processor** and `run_id`/`role`/`attempt` context binding | From day one — the spec requires secrets never appear in logs and that a run be reconstructable. A redaction processor + bound context is the cheapest way to satisfy both. |
| **tenacity** | 9.1.4 | Bounded retry/backoff for GitHub API calls, `git push`, transient DB errors (Neon cold-start) | Wrap only *idempotent* external calls. Do **not** use it for QA↔Developer or quality-gate retry loops — those are orchestration logic with persisted attempt counts, not transient-fault retries. |
| **polyfactory** | latest 2.x | Build `WorkerResult` / `NormalizedTask` / ORM-row fixtures in tests | pydantic-v2-native factory library (same maintainers as Litestar). Cleaner than `factory_boy` for pydantic. Use for test data; hand-write `FakeWorker` itself. |
| **pytest-httpx** or **respx** | latest | Stub GitHub HTTP in unit tests (githubkit rides on httpx) | Adapter/integration tests for `CopilotWorker` etc. still shell out for real; use HTTP stubbing for GitHub-integration unit tests only. |
| **time-machine** | latest | Deterministic tests for lease expiry / `WAITING_HUMAN` timeouts / event timestamps | Faster and less intrusive than `freezegun`. |
| **mcp** (official SDK) | 2.1.1 | Optional MCP tool-transport adapter in `tools/` | Only if/when a worker consumes tools over MCP. `package == mcp`, repo `modelcontextprotocol/python-sdk`. The orchestrator must never import it on a core path. |
| **GitPython** | 3.1.61 | Optional ergonomic wrapper for *read* porcelain (`repo.head.commit.hexsha`, dirty check) | Optional. If the thin `subprocess` `GitClient` covers needs, skip it. Never use it for push/commit policy — Dark Factory owns those via explicit commands. |
| **httpx** | 0.28.1 | Direct HTTP for the (small) set of calls githubkit doesn't cover, or a minimal webhook receiver | Transitive via githubkit; use directly only for a tiny `POST /webhook` handler if you don't want a full web framework. |
| **transitions** | 0.9.3 | Optional: declaratively express the legal run-state / role-pipeline transition graph and guard conditions | Optional and non-load-bearing. The authoritative state is a Postgres column; `transitions` can validate "is this transition legal?" in memory but must not own persistence or concurrency. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Env + deps + lock + build | `uv sync --all-extras --dev`; commit `uv.lock`. `uv run dark-factory ...` in CI. |
| **ruff** | 0.16.6 — lint **and** format | Replaces flake8 + isort + black + pyupgrade + most of pylint. `ruff check` + `ruff format` in pre-commit and CI. Enable `I`, `UP`, `B`, `SIM`, `RUF`, `ASYNC` rule sets. |
| **mypy** | 2.3.1 — static typing | Run in `--strict`. SQLAlchemy 2.0 + pydantic v2 + githubkit are all fully typed, so strict is realistic. `plugins = ["pydantic.mypy"]`. |
| **pytest** | 9.1.1 — test runner | `testpaths = ["tests"]`, markers for `unit` / `integration` (real agent CLIs) / `db`. |
| **testcontainers[postgres]** | 4.15.0 — ephemeral Postgres for tests | Session-scoped `postgres:17-alpine` container (~3 s once), per-test transaction+SAVEPOINT rollback for isolation. Best production parity (Neon *is* real Postgres). |
| **pytest-postgresql** | 9.1.0 — Docker-free alternative | Use when the dev/CI box has a local Postgres and can't run Docker-in-Docker. Needs `initdb`/`pg_ctl` on PATH. |
| **pytest-asyncio** | 1.4.0 — only if async is introduced | Not needed for the recommended all-sync design. Add only if a future async webhook edge lands. |
| **pre-commit** | latest | `ruff`, `ruff-format`, `mypy`, `uv lock --check`, end-of-file/trailing-whitespace. |
| **GitHub Actions** | CI | Lint + type + unit on every push; `integration` job gated on availability of `claude`/`copilot`/`hermes` credentials; optional pre-merge smoke against a **Neon branch**. |

---

## Installation

```bash
# Project init (uv, src layout, Python 3.12)
uv init --package --python 3.12 dark-factory
cd dark-factory

# Core runtime
uv add \
  "typer>=0.27,<1" \
  "sqlalchemy>=2.0.40,<2.1" \
  "psycopg[binary,pool]>=3.2,<4" \
  "alembic>=1.19,<2" \
  "pydantic>=2.9,<3" \
  "pydantic-settings>=2.7,<3" \
  "pyyaml>=6,<7" \
  "githubkit>=0.16,<1" \
  "structlog>=25,<27" \
  "tenacity>=9,<10" \
  "rich>=14"

# Optional extras
uv add --optional mcp   "mcp>=2,<3"
uv add --optional git   "GitPython>=3.1,<4"

# Dev + test
uv add --dev \
  "ruff>=0.16" \
  "mypy>=2.3" \
  "pytest>=9,<10" \
  "testcontainers[postgres]>=4.15,<5" \
  "pytest-postgresql>=9,<10" \
  "polyfactory>=2,<3" \
  "pytest-httpx>=0.35" \
  "time-machine>=2" \
  "pre-commit>=4"
```

> `psycopg[binary]` for dev speed; switch to the pure `psycopg` + system libpq (or `psycopg[c]`) for production builds. `psycopg[pool]` is only needed if you use psycopg's own pool instead of SQLAlchemy's — you won't, but it's harmless.

---

## Sync vs Async — the explicit call

**Recommendation: fully synchronous core. No `asyncio` in the orchestrator, persistence, worker, git, or GitHub layers.**

Why sync wins for *this* workload:

| Factor | This system | Implication |
|--------|-------------|-------------|
| Concurrency per process | Exactly one run advancing at a time | No event loop benefit; a connection pool of 5 is plenty |
| Where wall-clock time goes | Multi-minute agent-CLI subprocesses, `git push`, CI, human waits (minutes-to-days, handled by *process exit* + resume) | Blocking I/O is already "free" — the process is meant to exit, not hold connections |
| Scaling model | Run more processes (local + CI + webhook worker), each owning different runs via DB claim | Horizontal by process, not by coroutine |
| Testing | `FakeWorker` + testcontainers + transaction rollback | Sync tests are dramatically simpler; no `pytest-asyncio`, no loop-scope foot-guns |
| Driver/pooler risk | Neon = PgBouncer transaction pooling | `asyncpg` + PgBouncer is a known prepared-statement hazard; sync psycopg3 sidesteps most of it |
| Team cognitive load | Portfolio project, small surface | "Colored functions" tax every call site for zero throughput gain |

**When you would reconsider:** a single always-on process that must service hundreds of concurrent GitHub webhooks with sub-second latency. Even then the right move is a **separate** thin async (or threaded) receiver that just writes an interaction row and enqueues a claim — the durable orchestrator stays sync. Do not async-ify the core to serve the edge.

`psycopg` v3 is chosen partly because it gives you a **free async escape hatch** later (`AsyncConnection`) without swapping drivers.

---

## Durable execution & concurrency — build, don't buy

**Recommendation: hand-rolled explicit state machine + Postgres locking. No workflow engine, no lock service.**

State model (already in the spec): a `runs.status` enum (`CREATED, BA, ARCHITECTURE, DEVELOPMENT, QA, VERIFYING, PUBLISHING, COMPLETED, WAITING_HUMAN, FAILED`) plus `current_role` / `current_step`, `role_executions` for attempts, and an append-only `run_events` audit log from which the whole run is reconstructable.

**"Two processes must not execute the same run" — pick one, all satisfy the "no distributed-lock service" constraint:**

1. **Conditional-UPDATE lease (recommended primary).** Claim a run atomically:
   ```sql
   UPDATE runs
      SET owner_token = :token,
          lease_expires_at = now() + interval '15 minutes',
          updated_at = now()
    WHERE id = :run_id
      AND status NOT IN ('COMPLETED','FAILED')
      AND (owner_token IS NULL OR lease_expires_at < now())
   RETURNING id;
   ```
   Zero rows returned → someone else owns it; exit. Renew the lease on each step; clear it on pause/finish. Survives crashes (lease simply expires). This is the canonical pattern and needs no extra infrastructure.
2. **`SELECT ... FOR UPDATE` (use *inside* each state-advancing transaction).** `session.get(Run, run_id, with_for_update={"nowait": True})` (or `.with_for_update(skip_locked=True)` when a poller scans for claimable runs) so the read-modify-write of `status` is serialized at the row level.
3. **`pg_advisory_xact_lock(hashtext(run_id::text))`** as a coarser alternative to serialize all work for one run for the duration of a transaction — handy if step logic touches several tables.

Combine 1 (ownership across the whole run) + 2 (correctness of each transition). Advisory locks optional.

**Why not Temporal / Prefect / Celery / DBOS:**

- **Temporal** (`temporalio` 1.32.0) delivers durable execution but requires operating a Temporal cluster (or paying for Cloud) and a worker fleet — a whole second orchestration system. The spec explicitly rules out "a separate CI orchestration implementation" and "a distributed-lock service"; a Temporal cluster is squarely in that spirit. Its value shows up when workflows escape the DB boundary or need multi-tenant isolation — not here.
- **Prefect / Dagster / Airflow** are arbitrary-DAG engines. The spec explicitly excludes "a generic arbitrary-DAG workflow engine" — the pipeline is a fixed ordered role list with two known feedback edges (QA→Developer, Quality-Gate→Developer).
- **Celery / RQ / APScheduler** need a broker and turn "resume" into "schedule a job." Resume here is triggered by an external event (CLI, CI step, webhook) that calls back into the same deterministic entrypoint. A broker adds a moving part with nothing to do.
- **DBOS** is the closest philosophical match (durable execution *inside* Postgres) and worth knowing about, but it's a heavier framework commitment and decorator model than a ~5-table hand-rolled machine needs, and it wants to own your transaction/checkpoint semantics. For this scope, direct SQLAlchemy + the lease pattern is less magic and fully inspectable — which is the point ("if the orchestrator cannot explain where a run is, it cannot resume it").

**Idempotency (spec requirement)** is handled the same hand-rolled way: persist `branch`, `commit_sha`, `pr_number`, `pr_url`, `clarification_comment_id`; every publish/comment step checks the persisted identifier first and no-ops if present.

---

## Invoking the agent CLIs

| Concern | Approach |
|---------|----------|
| Spawn | `subprocess.Popen([...], cwd=worktree, env=role_env, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True, start_new_session=True)` |
| **Credential boundary** | `role_env` is built from scratch: `PATH`, `HOME`, a temp `XDG_*`, plus only the *worker's own* auth var (e.g. `ANTHROPIC_API_KEY` / `GITHUB_TOKEN` scoped for Copilot). Never `os.environ.copy()`. `DATABASE_URL` and Dark Factory's `GITHUB_TOKEN` are never present. |
| Non-interactive invocation | **Claude Code:** `claude -p "<prompt>" --output-format json` (or `stream-json` for live events) → parse `result`, `session_id`, `total_cost_usd`; permissions via `--allowedTools` / `--permission-mode`, `--dangerously-skip-permissions` only inside a sandboxed worktree. **Copilot CLI:** `copilot -p "<prompt>" --no-ask-user --allow-tool 'shell(pytest)' --allow-tool write --model <pin>` (prefer narrow `--allow-tool` over `--allow-all-tools`). **Hermes:** `hermes chat -q "<prompt>"` / `--oneshot` print mode — no PTY/tmux needed; avoid its interactive mode. |
| Structured output | Prefer each CLI's JSON/stream-JSON mode; fall back to writing an agreed artifact file (`implementation_summary.json`, `verdict.json`) into `.dark-factory/runs/<id>/artifacts/<role>/` and reading that. `WorkerResult` normalizes all three. |
| Session / resume handle | Store the opaque `worker_session_id` (Claude `session_id`, etc.) on `role_executions`. `worker.resume()` uses native `--resume <id>` when `WorkerCapabilities.native_resume` is true, else reconstructs context and re-invokes. |
| Timeout / hang | `Popen.communicate(timeout=...)`; on `TimeoutExpired` kill the whole process group (`os.killpg`). Record as a `FAILED` attempt with captured partial output. |
| No PTY unless forced | Do not adopt `pexpect` globally. If one runtime genuinely needs a TTY, isolate that in its adapter only. |
| Retry | Orchestration-level (persisted attempt counts + retry limits from repo config), *not* `tenacity`. |

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Typer 0.27 | **Click 8.5** directly | You want zero magic / full control over parsing, or you dislike the `Annotated` parameter style. Click is the engine Typer sits on; dropping to it later is cheap. |
| Typer | **argparse** (stdlib) | Only if a hard "no third-party CLI dependency" rule exists. You lose Rich output, completion, and type-driven validation. |
| Sync SQLAlchemy + psycopg3 | **Async SQLAlchemy + psycopg3 async** | A single long-lived process must handle high-concurrency webhook traffic itself. Even then, prefer a separate receiver process. |
| psycopg3 | **psycopg2-binary** | An existing codebase already standardized on psycopg2. Not this greenfield. |
| psycopg3 | **asyncpg** | Pure-async, no PgBouncer in the path, raw throughput critical. Neon's transaction pooler makes asyncpg's prepared-statement handling a liability; avoid. |
| githubkit | **PyGithub 2.10** | Team already knows PyGithub and doesn't need webhook models or GraphQL. Conservative, mature, but only partially typed and REST-only. |
| githubkit | **gidgethub** | You want a tiny async-only sans-I/O core and will hand-model responses. Lower level than needed. |
| githubkit | **raw `httpx`** | Only for the 1-2 endpoints a library genuinely lacks. Rebuilding auth/pagination/retry/types by hand is wasted effort. |
| `git` via subprocess | **GitPython 3.1** | You want Pythonic porcelain for *reads* and accept the extra dep. Fine as a thin convenience layer; keep write/PR policy in explicit commands. |
| `git` via subprocess | **pygit2 (libgit2)** | You need in-process performance for thousands of git ops. Costs a native build and libgit2/pygit2 version coupling — not worth it for a handful of ops per run. |
| PyYAML | **ruamel.yaml 0.19** | You must *write back* YAML preserving comments/formatting (e.g. a `dark-factory init` that edits an existing file). Not needed for read-only config load. |
| Hand-rolled FSM + Postgres locks | **`transitions` 0.9** | You want a declarative transition table with entry/exit callbacks and are fine keeping persistence separate. Acceptable as a modeling aid; never as the source of truth. |
| Hand-rolled durability | **DBOS Transact** | You want library-level durable-execution decorators and are happy to let it own checkpoint semantics inside Postgres, and the team will standardize on it. Reasonable future migration target; more framework than this scope needs now. |
| Hand-rolled durability | **Temporal** | Workflows grow beyond the DB boundary, need signals/timers at scale, multi-tenant isolation, or a dedicated ops team already runs a cluster. |
| testcontainers | **pytest-postgresql** | CI/dev cannot run Docker; a local Postgres with `initdb` is available. |
| testcontainers | **Neon branch per CI run** | Pre-merge smoke / migration-compatibility checks against the real provider. Too slow/rate-limited for the inner unit loop. |
| uv | **Poetry** | Team standard is Poetry and the speed/lockfile gains don't justify migration. For greenfield, uv is the current default. |
| uv | **pip + pip-tools + venv** | Ultra-minimal, no new tool. Slower, more manual, no integrated Python-version management. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Airflow / Prefect / Dagster / Luigi / Celery-canvas** | Arbitrary-DAG engines; spec explicitly excludes "a generic arbitrary-DAG workflow engine." The pipeline is a fixed ordered role list with two feedback edges. | Deterministic Python loop over `workflow.roles` + explicit transition functions |
| **Temporal / Cadence** | Requires a separate orchestration cluster + worker fleet; against the spec's "no separate CI orchestrator / no distributed-lock service" intent; value is for out-of-DB, multi-tenant, high-scale workflows | Hand-rolled enum FSM + Neon lease/`FOR UPDATE` |
| **Redis / etcd / ZooKeeper / Consul for locking** | A separate distributed-lock service — explicitly out of scope | `UPDATE ... WHERE owner_token IS NULL`, `SELECT ... FOR UPDATE`, `pg_advisory_xact_lock` |
| **Celery / RQ / Dramatiq / APScheduler** | Need a broker; "resume" here is an externally-triggered call into a deterministic entrypoint, not a scheduled job | CLI / CI step / webhook handler invokes the same orchestrator function; DB claim decides ownership |
| **SQLModel** | Fuses pydantic + SQLAlchemy into one class; lags SQLAlchemy 2.0 features, and the "one model for API + DB" idea breaks down exactly where this project needs divergence (JSONB payloads, secret handling, event serialization) | SQLAlchemy 2.0 typed ORM classes **and** separate pydantic v2 models; convert explicitly |
| **asyncpg** | Async-only; prepared-statement handling clashes with Neon's PgBouncer transaction pooling; forces async coloring for no throughput gain here | psycopg 3 (sync now, async-capable later) |
| **psycopg2** | Maintenance-only, no new features, weaker prepared-statement/pipeline story, no native async path | psycopg 3 |
| **PyMiniRacer / quickjs / any embedded JS runtime for actions** | Spec explicitly excludes "an embedded JavaScript/scripting runtime for actions" | `ActionRegistry` of plain Python callables referenced by name in config |
| **Storing artifact *content* in Neon (JSONB/bytea blobs)** | Spec: "do not turn Neon into a document store." Bloats rows, slows the audit log, complicates backups | Filesystem `.dark-factory/runs/<id>/...` holds content; Neon stores `ArtifactReference` metadata (id, path, type, checksum) |
| **`os.environ.copy()` when spawning workers** | Leaks `DATABASE_URL`, `GITHUB_TOKEN`, worker creds into agent processes — a spec-level security violation | Construct `env` explicitly from an allowlist per role |
| **`shell=True` in subprocess** | Command injection surface from task text / repo-derived strings | `Popen([...])` with an argument list |
| **`transitions` (or any lib) as the state *source of truth*** | In-memory FSM state can't survive `kill -9`; durability + observability are the same requirement | Authoritative `status` column in Neon; library at most validates legality |
| **pygit2** | Native libgit2 build + tight version coupling for ~10 git ops per run | Shell out to `git` |
| **SQLModel/`databases`/`encode/orm`** | Thin, less-maintained abstractions over a moving SQLAlchemy target | SQLAlchemy 2.0 directly |

---

## Stack Patterns by Variant

**If a persistent GitHub-webhook service is added later:**
- Add a *separate* small process (FastAPI or a bare `httpx`/`starlette` handler) that verifies the webhook signature, writes/updates a `human_interactions` row, and either sets the run claimable or spawns `dark-factory resume`.
- Keep it sync (WSGI + threadpool) unless load genuinely demands async; either way it does not import the orchestrator's step logic — it only nudges state.
- The orchestrator core stays 100% synchronous.

**If Docker is unavailable in CI:**
- Swap `testcontainers` for `pytest-postgresql` (needs `postgresql` + `initdb` on the runner).
- Keep one nightly job that runs the migration + a smoke test against a real **Neon branch** to catch provider-specific drift.

**If only Claude Code is available for early milestones (Copilot/Hermes creds not yet provisioned):**
- Build `ClaudeCodeWorker` + `FakeWorker` first; `CopilotWorker` / `HermesWorker` implement the same `CodingWorker` contract and are covered by their own integration suites, skipped via pytest markers when creds are absent.
- `WorkerCapabilities` already encodes the differences (native resume, session id, structured output, non-interactive) so the orchestrator needs no per-worker branching.

**If artifact volume grows large / multi-machine filesystem sharing is needed:**
- Swap the filesystem artifact store behind the existing `artifacts.read/write` tool + `ArtifactReference` abstraction for S3-compatible object storage.
- Neon still holds only references — no schema change.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| SQLAlchemy 2.0.52 | psycopg 3.3.x | URL scheme `postgresql+psycopg://` (NOT `postgresql+psycopg2://`). `postgresql+psycopg` = v3. |
| SQLAlchemy 2.0.x | Alembic 1.19.x | Matched majors; `alembic init` templates target 2.0. Point `sqlalchemy.url` / `env.py` at Neon's **direct** endpoint for DDL. |
| psycopg 3.2+ | PgBouncer 1.22+ (Neon pooler) | Needed for protocol-level prepared statements through transaction pooling. Still safest: `connect_args={"prepare_threshold": None}` on the pooled engine, and/or `?prepare_threshold=0` — measure, then relax. |
| SQLAlchemy engine (Neon) | `pool_pre_ping=True`, modest `pool_size` (e.g. 5), `pool_recycle=300` | Neon scale-to-zero / pooler can drop idle connections; pre-ping avoids stale-connection errors on resume after a long human wait. |
| Typer 0.27.x | Click 8.5 (vendored) | Do **not** add a separate `click` dependency or pin — Typer vendors it since 0.26. If you import `click` directly, use `typer.main.get_command` / the re-exported surface. |
| pydantic 2.13.x | pydantic-settings 2.15.x | Same v2 line; keep both `>=2.9,<3`. |
| githubkit 0.16.x | httpx 0.28.x, pydantic 2.x | githubkit pulls a compatible httpx; let it resolve. Webhook models are pydantic v2. |
| mcp 2.1.x | Python `>=3.10`, pydantic 2.x, anyio | Optional extra; isolate so its anyio/async surface never leaks into the sync core. |
| testcontainers 4.15.x | Docker Engine / Podman, `postgres:17-alpine` | Match the image major to Neon's Postgres major (17). |
| mypy 2.3.x + `pydantic.mypy` plugin | pydantic 2.13.x | Enable the plugin; SQLAlchemy 2.0 needs no plugin (native `Mapped[...]` typing). |
| Python 3.12 | everything above | `pygit2` would force `>=3.11`; not using it keeps the floor flexible. All other deps allow `>=3.10`. |

---

## Suggested Project Layout (`src/`)

```
dark-factory/
  pyproject.toml            # PEP 621, [project.scripts] dark-factory = "dark_factory.cli:app"
  uv.lock
  alembic.ini
  migrations/               # Alembic env + versions
  src/dark_factory/
    cli.py                  # Typer app: run|resume|status|runs|artifacts|events
    config/                 # pydantic-settings + YAML schema loaders
    orchestrator/           # deterministic pipeline driver + transition functions
    workflows/              # workflow definition loading (workflow.roles)
    roles/                  # role executor(s), role config models
    workers/               # CodingWorker contract, registry, ClaudeCode/Copilot/Hermes/FakeWorker
    tools/                  # ToolRegistry + optional MCP transport adapter
    actions/                # ActionRegistry (prepare_role_context, collect_diff, ...)
    input/                  # source detection + NormalizedTask
    context/                # ContextBuilder -> RoleContext
    artifacts/              # filesystem store + ArtifactReference
    quality/                # QA + independent quality-gate runner
    persistence/            # SQLAlchemy models, session factory, repositories, lease/lock helpers
    integrations/           # githubkit-backed GitHub client, git subprocess client
    events/                 # run_events append + reconstruction
  tests/
    unit/  integration/  conftest.py   # testcontainers fixture, FakeWorker, polyfactory factories
```

`src/` layout (not flat) so tests run against the installed package, catching packaging/import bugs early — standard for a tool meant to be `pip install`-ed and run as a console script.

---

## Sources

- **PyPI JSON registry API** (`pypi.org/pypi/<pkg>/json`) — verified current versions on 2026-09-06: typer 0.27.2, click 8.5.0, SQLAlchemy 2.0.52 (2.1 in RC), alembic 1.19.2, psycopg 3.3.5, psycopg2-binary 2.9.12, pydantic 2.13.5, pydantic-settings 2.15.0, githubkit 0.16.1, PyGithub 2.10.0, mcp 2.1.1, PyYAML 6.0.3, ruamel.yaml 0.19.1, transitions 0.9.3, temporalio 1.32.0, GitPython 3.1.61, pygit2 1.20.0, testcontainers 4.15.0, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-postgresql 9.1.0, ruff 0.16.6, mypy 2.3.1, uv 0.12.10, httpx 0.28.1, structlog 26.1.0, tenacity 9.1.4 — confidence HIGH (canonical registry).
- **SQLAlchemy 2.0 asyncio docs** + community guidance (docs.sqlalchemy.org, GitHub discussions #5923 / #10344) — "commit to sync or async, don't mix"; async only pays off for high-concurrency servers — confidence MEDIUM.
- **psycopg3 docs — "Differences from psycopg2"** and Tiger Data / Spherex benchmarks — psycopg3 perf + memory advantages, psycopg2 is maintenance-only — confidence MEDIUM.
- **Neon docs — "Connection pooling"** and **Neon blog — "PgBouncer: the one with prepared statements"**; psycopg3 prepared-statements doc — pooled `-pooler` host, transaction pooling, psycopg3 3.2 + PgBouncer 1.22, `prepare_threshold=None` — confidence MEDIUM.
- **githubkit README + docs** (github.com/yanyongyu/githubkit) — fully typed, REST+GraphQL+webhooks, sync/async, Pydantic webhook models, pagination/retry — confidence MEDIUM.
- **Claude Code headless docs** (docs.claude.com / community guides) — `-p/--print`, `--output-format json|stream-json`, `session_id`, `--resume`, `--allowedTools`, `--permission-mode` — confidence MEDIUM.
- **GitHub Docs — "Copilot CLI programmatic reference" / "Running Copilot CLI programmatically"** — `-p`, `--no-ask-user`, `--allow-tool 'shell(...)'`, `--allow-all-tools`, `--model` — confidence MEDIUM.
- **NousResearch Hermes Agent CLI docs** (hermes-agent.nousresearch.com, github.com/NousResearch/hermes-agent) — `hermes chat -q` / `--oneshot` non-interactive print mode, no PTY — confidence MEDIUM.
- **Temporal vs DBOS / state-machine comparisons** (temporal.io blog, tiarebalbi.com "DBOS vs Temporal", HackerNoon practical guide) — Temporal needs a cluster; DB-backed is lower friction for small single-Postgres teams — confidence MEDIUM.
- **testcontainers-python docs** + Docker guide, pytest-postgresql PyPI — container startup ~3 s, session-scoped fixture pattern; pytest-postgresql needs local Postgres — confidence MEDIUM.
- **uv docs / ecosystem coverage** — lockfile, PEP 621, Python management, speed vs pip/Poetry — confidence MEDIUM.

---
*Stack research for: durable CLI-first Python orchestration of external AI engineering-agent CLIs on Neon PostgreSQL*
*Researched: 2026-09-06*
