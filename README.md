# Dark Factory

Dark Factory is a durable software-delivery orchestration platform for AI
engineering agents: it coordinates a single development task through specialized
engineering roles — Business Analyst → Architect → Developer → QA → Quality Gate
→ PR — where each role is performed by an external AI agent runtime. The
responsibility boundary is deliberate: **Dark Factory decides *what happens
next*; the engineering agent decides *how* to do the engineering work.** The
outer delivery lifecycle stays under deterministic application control, and the
complete lifecycle state of a run lives in PostgreSQL (Neon), so any process on
any machine can resume exactly where a previous one stopped. **Phase 1 (the
walking skeleton) delivers the durable-run tracer:** `dark-factory run
text:"..."` creates a run, drives it through one role with a `FakeWorker` (no AI,
no GitHub, no git, no quality gate), and any brand-new process can pick that run
up from its last committed step and carry it to a terminal state — with a
redacted audit trail throughout.

## Prerequisites

- **Python 3.12** (`requires-python = ">=3.12"`).
- **[uv](https://docs.astral.sh/uv/)** — dependency resolution, lockfile,
  virtualenv and Python-version management.
- **A Neon project running PostgreSQL 17** with a database for Dark Factory.
  Create it at Neon Console → New Project → select Postgres 17.

## Run the walking skeleton against a real Neon project

Every command below is paste-able as written.

```bash
# 1. Configuration. Copy the reference file and fill in the two connection strings.
cp .env.example .env
```

Edit `.env` and set:

- **`DATABASE_URL`** — the **pooled** Neon connection string. In the Neon
  Console, open your project → Connection Details → select the pooled string
  (its host contains `-pooler`). Rewrite the scheme to `postgresql+psycopg://`.
  This is what the application engine uses at runtime.
- **`DATABASE_URL_DIRECT`** — the **direct** (non-pooled) Neon connection string.
  In Connection Details, disable connection pooling to reveal it (host **without**
  `-pooler`). Rewrite the scheme to `postgresql+psycopg://`. **Alembic uses this
  one** because DDL and PgBouncer transaction pooling do not mix — running
  migrations through the pooled endpoint is unreliable.

```bash
# 2. Install the pinned dependency set into a project virtualenv.
uv sync --all-extras --dev

# 3. Apply the schema (creates runs, role_executions, run_events). Uses
#    DATABASE_URL_DIRECT.
uv run alembic upgrade head

# 4. Start a run from a plain-text task and drive it to a terminal state.
uv run dark-factory run text:"add a health endpoint"
```

`run` prints the **run id on its own first line** (so a killed process is still
recoverable), then one line per state transition, then a short summary block:

```
54e1153f-4cb5-4e2f-92a8-dea95ba06846
CREATED → BA
BA → COMPLETED

run 54e1153f-4cb5-4e2f-92a8-dea95ba06846
  terminal state: COMPLETED
  last role:      BA
  attempt:        1
```

A partial run shows the id and only the transitions that committed — no
`terminal state: COMPLETED` line.

```bash
# 5. Inspect where the run is. Position is read from state columns, never from
#    the event log.
uv run dark-factory status 54e1153f-4cb5-4e2f-92a8-dea95ba06846
```

```
run_id: 54e1153f-4cb5-4e2f-92a8-dea95ba06846
source_kind: text
source_ref: -
status: COMPLETED
current_role: BA
current_step: 0
latest_attempt: 1
created_at: 2026-09-08T13:01:25.921585Z
updated_at: 2026-09-08T13:01:34.669417Z
base_branch: -
working_branch: -
```

`base_branch` and `working_branch` are `-` (null) — they exist in the schema
from the first migration but are not used until Phase 5 (see below).

```bash
# 6. The same fields as one JSON object (what the later CI phases consume).
uv run dark-factory status 54e1153f-4cb5-4e2f-92a8-dea95ba06846 --json
```

```
{"run_id": "54e1153f-4cb5-4e2f-92a8-dea95ba06846", "source_kind": "text", "source_ref": null, "status": "COMPLETED", "current_role": "BA", "current_step": 0, "latest_attempt": 1, "created_at": "2026-09-08T13:01:25.921585Z", "updated_at": "2026-09-08T13:01:34.669417Z", "base_branch": null, "working_branch": null}
```

`dark-factory resume <run-id>` runs the identical drive loop from a brand-new
process; on an already-terminal run it prints the id and the summary block and
adds no transition lines.

### Exit codes (`run` / `resume`)

| Code | Meaning |
|------|---------|
| `0` | The run reached `COMPLETED`. |
| `1` | The run reached `FAILED` — a real, persisted terminal delivery failure. |
| `2` | Bad invocation — unresolvable input, unknown run id, config/validation error. **Nothing was persisted or advanced.** |

## Running the tests

Dark Factory does not assume a database backend. `tests/conftest.py` walks a
**provisioning probe ladder** and takes the first rung that works:

1. **testcontainers** — a responsive Docker daemon (`postgres:17-alpine`);
2. **pytest-postgresql** — a local PostgreSQL 17 `initdb` on `PATH`;
3. **externally supplied** — a throwaway PostgreSQL 17+ reachable through the
   `DARK_FACTORY_TEST_DATABASE_URL` environment variable (set it in the
   git-ignored `.env`);
4. no rung 4 — the ladder stops and fails rather than degrading to SQLite or a
   mock.

The selected rung is echoed into pytest's session header. For rung 1 you need
Docker; for rung 2 a local `initdb`; for rung 3 nothing but the env var pointing
at a scratch database. `alembic upgrade head` is applied automatically before any
`db` / `integration` test.

Marker tiers:

| Marker | What it covers |
|--------|----------------|
| `unit` | Fast pure-function tests — no database, no I/O. |
| `db` | Tests that need a reachable PostgreSQL. |
| `integration` | End-to-end tests that drive the CLI / a full run against PostgreSQL. |
| `contract` | The shared `CodingWorker` contract suite, parametrized over worker adapters. |

```bash
# Quick inner loop — no database needed:
uv run pytest -m unit

# The whole suite across every tier (needs a reachable PostgreSQL):
uv run pytest
```

## What Phase 1 deliberately does not do

So a reader does not mistake absence for oversight — none of the following is in
the walking skeleton:

- **No real agent runtime.** `FakeWorker` is the only worker (Claude Code arrives
  in Phase 7; Copilot and Hermes in Phase 8).
- **No GitHub** in any form — no issue intake, no clarification comments, no PR
  publishing, no webhooks (Phase 10).
- **No git worktree, no working branch, no `git` invocation at all** (Phase 5).
- **No independent quality gate** and no bounded feedback loops (Phase 9).
- **No configuration file** — the one-role pipeline is a hardcoded Python
  default; `.dark-factory.yaml` and role YAML arrive in Phase 3.
- **No human pause and resume** — `WAITING_HUMAN`, `resume --answer "..."` and
  safe process release are Phase 2.
- **No concurrency lease** — the Postgres single-owner lease / heartbeat is
  Phase 2.

## Decisions recorded here, enforced later

Three schema-shaping decisions were made now so a later phase does not
re-litigate them from an empty schema:

- **`base_branch` and `working_branch`** exist as **nullable columns** on `runs`
  from the first migration (`0001_walking_skeleton`) and stay unused until
  **Phase 5**.
- **`qa_developer_iterations` and `quality_gate_iterations`** exist as **non-null,
  zero-default integer columns** on `runs`. They are incremented only through the
  one mutation path and are **enforced in Phase 9** — never derived by folding
  `run_events` or counting `role_executions` rows.
- **Artifacts are references, not content.** The future `artifacts` table
  (Phase 4) will hold artifact *references* only — `id`, `run_id`,
  `role_execution_id`, `type`, `path`, `checksum`, `metadata`, `created_at` —
  **never artifact content**. Content lives on the filesystem under
  `.dark-factory/runs/<run-id>/` and, from **Phase 5**, travels between machines
  by being committed to a `.dark-factory/` path on the run's working branch,
  excluded from the published diff. **Phase 1 creates no `artifacts` table by
  design.**

## Development

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src/dark_factory
uv run pytest -m unit
```
