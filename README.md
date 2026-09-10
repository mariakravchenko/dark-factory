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

Two optional, **non-secret** variables tune the single-owner lease (Phase 2).
Leave them unset to take the production defaults; `.env.example` documents both
in full.

| Variable | Default | Unit | What it controls |
|----------|---------|------|------------------|
| `LEASE_TTL_SECONDS` | `900` | seconds | How long a claimed run stays owned without a renewal. After a hard crash the run is unclaimable until this elapses on the database clock — there is no earlier-steal escape hatch in this phase. |
| `LEASE_HEARTBEAT_SECONDS` | `300` | seconds | How often the owning process pushes its lease expiry forward while a step runs. Must be strictly less than `LEASE_TTL_SECONDS` (settings loading fails otherwise); one third of the TTL is the standard ratio. |

The `900` / `300` production values are inherited from the roadmap's Open
Decision 2. The pause/resume and heartbeat **mechanism** is proven in the test
suite at short injected TTLs; confirming the real-scale numbers against a live
Neon endpoint is a pending operator smoke check (a crashed run being unclaimable
for up to ~15 minutes is the trade-off being confirmed).

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
| `0` | The run stopped **cleanly waiting for a human** (`WAITING_HUMAN`) — the process did exactly what it was asked to and there is nothing to retry. |
| `0` | **Another process owns the run** and this one declined to act — it printed `run <id> is owned by another process; exiting without changes` on stderr and changed nothing. This is a normal outcome of two processes touching one run, not a fault. |
| `1` | The run reached `FAILED` — a real, persisted terminal delivery failure. |
| `2` | Bad invocation or an orchestration error where **nothing new was persisted** — unresolvable input, unknown run id, bad UUID, config/validation error, answering a run that is not waiting, a lost lease. |

The two extra `0` cases are the ones a wrapper script is most likely to
misread: a clean pause and a declined ownership race are **successes**. Only `1`
(persisted `FAILED`) and `2` (nothing advanced) are failures.

## Pause a run for a human, then resume it (Phase 2)

A role can stop mid-run to ask the operator a question. The run goes to
`WAITING_HUMAN`, the owning process releases its lease and exits `0`, and any
later process — on any machine sharing the database — answers the question and
carries the run to a terminal state.

Every command below was run as written against a real Neon database; the output
shown is what the process actually printed.

### 1. Make a run pause

In the walking skeleton the worker is `FakeWorker`, so a `NEEDS_INPUT` result is
produced with the `DARK_FACTORY_FAKE_SCRIPT` environment variable — a JSON array
of scripted worker results. The first asks a question; the second (used after
the answer) completes.

```bash
DARK_FACTORY_FAKE_SCRIPT='[
  {"status":"NEEDS_INPUT","summary":"need a decision before I can proceed",
   "questions":["Which database should the health endpoint report on -- primary or replica?"],
   "worker_session_id":"fake-operator-walkthrough-001"},
  {"status":"COMPLETED","summary":"done","worker_session_id":"fake-operator-walkthrough-001"}
]' uv run dark-factory run text:"add a health endpoint"
```

```
e9de8336-56f6-4ce8-be34-9914d67ed3eb
CREATED → BA
BA → WAITING_HUMAN

run e9de8336-56f6-4ce8-be34-9914d67ed3eb
  terminal state: WAITING_HUMAN
  last role:      BA
  attempt:        1
```

Exit code `0`. The run id is on the first line. The `terminal state:` label in
the summary block is the generic "where the drive loop stopped" line — here it
stopped at `WAITING_HUMAN`, which is a pause, not a terminal state.

### 2. See that the run is waiting, and for what

```bash
uv run dark-factory status e9de8336-56f6-4ce8-be34-9914d67ed3eb
```

```
run_id: e9de8336-56f6-4ce8-be34-9914d67ed3eb
source_kind: text
source_ref: -
status: WAITING_HUMAN
current_role: BA
current_step: 0
latest_attempt: 1
created_at: 2026-09-10T08:14:52.308996Z
updated_at: 2026-09-10T08:15:02.556575Z
base_branch: -
working_branch: -
```

`status: WAITING_HUMAN` on `current_role: BA` tells you the run is paused and
which role asked. The **question text** itself is persisted on the
`human_interactions` row; there is no dedicated CLI surface for it yet (operator
question intake over GitHub comments arrives in Phase 10). Until then, read it
with the project's own session:

```bash
uv run python -c "
from uuid import UUID
from sqlalchemy import select
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import HumanInteraction
with new_session() as s:
    q = s.scalar(select(HumanInteraction).where(
        HumanInteraction.run_id == UUID('e9de8336-56f6-4ce8-be34-9914d67ed3eb')))
    print(q.status.value, '|', q.question)
"
```

```
WAITING | Which database should the health endpoint report on -- primary or replica?
```

### 3. Resume with an answer, from a different shell

Nothing from the original process is needed — only the run id and the database.
Open a new shell (no `DARK_FACTORY_FAKE_SCRIPT` set) and:

```bash
uv run dark-factory resume e9de8336-56f6-4ce8-be34-9914d67ed3eb \
  --answer "Report on the primary Postgres cluster"
```

```
e9de8336-56f6-4ce8-be34-9914d67ed3eb
BA → COMPLETED

run e9de8336-56f6-4ce8-be34-9914d67ed3eb
  terminal state: COMPLETED
  last role:      BA
  attempt:        1
```

Exit code `0`. `resume` also writes one `run.resumed` info line to **stderr**
(structured JSON); it does not touch the stdout contract above. The run
continues on the **same role execution and attempt** — it is not a new run. A
second `resume --answer` for the same pause exits `2` with `not waiting` on
stderr: the answer is accept-once.

### 4. Two processes touching the same run at once

While one process owns a run (it holds the lease), a second `resume` on the same
run does not wait and does not fail — it declines:

```bash
uv run dark-factory resume ff7a698c-72ec-44ee-91fa-cb1fe88e4a5b --answer "primary"
```

```
ff7a698c-72ec-44ee-91fa-cb1fe88e4a5b
run ff7a698c-72ec-44ee-91fa-cb1fe88e4a5b is owned by another process; exiting without changes
```

Exit code `0`, nothing changed. This is the normal result of a race, **not an
error** — a wrapper script that retries or alerts on it is retrying pointlessly.

### 5. When a process is killed while it owns a run

A hard-killed owner never releases its lease. Nothing else can claim that run
until its `lock_expires_at` passes — `LEASE_TTL_SECONDS` (default `900`) after
its last heartbeat, measured on the **database** clock. After that, any process
`resume`s it from the last committed step. This phase has no command to force an
earlier steal.

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

_(Human pause/resume and the Postgres single-owner lease **were** added in
Phase 2 — see the walkthrough above and the section below.)_

## What Phase 2 deliberately does not do

Pause, resume and single-owner execution are in place; the following is
deliberately still out:

- **No forced lease steal.** There is no command to take another process's lease
  before it expires — a crashed owner's run waits out `LEASE_TTL_SECONDS`.
- **No way to cancel a waiting run.** `WAITING_HUMAN` is left until it is
  answered; there is no `cancel`. (`CANCELLED` exists in the schema as an inert
  value, written nowhere yet.)
- **No per-question answering.** A pause carries **all** of the role's questions
  as one block, and `--answer` supplies one answer for that block.
- **No non-command-line answer intake.** The only way in is
  `resume <run-id> --answer "..."`. Answering via GitHub comment arrives in
  Phase 10; picking a paused run up on a *different machine* is Phase 11.

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
