<!-- generated-by: gsd-doc-writer -->
# Dark Factory

Dark Factory is a workflow-automation tool you install into **your own**
repository to run an automated software-delivery pipeline — **Business
Analyst → Architect → Developer → QA → an independent Quality Gate → PR** —
driven from a local CLI invocation or from GitHub Actions. Give it a task (a
plain-text description, a spec file, or a GitHub issue) and it drives that
task through each role, has an independent step verify the work before
anything ships, and opens the pull request only once both QA and the Quality
Gate agree it is good.

It persists every step to PostgreSQL, so a run survives a crash, a
laptop-to-CI handoff, or a multi-day wait on a human answer — any process on
any machine can pick a run back up from its last committed step, with
nothing carried over but the run id.

## Why this instead of just running an agent CLI

Pointing `claude` or `copilot` at a task directly gives you one long,
unsupervised agent session: there is no separation between the agent that
writes the code and the agent that checks it, no durable record of what
happened if the process dies partway through, and no clean way to hand a
paused task from your laptop to a CI runner. Dark Factory sits *around* the
agent CLIs rather than being one:

- **Separation of responsibility.** Dark Factory decides *what happens next*
  in the delivery lifecycle (which role runs, when to retry, when to publish);
  the AI agent assigned to each role decides *how* to do that role's
  engineering work. The outer pipeline is deterministic application code, not
  another LLM loop.
- **Independent verification before publishing.** A Developer's work is
  checked by QA, and QA's own PASS is checked again by a Quality Gate that
  runs project commands (tests, lint) independently. A pull request is opened
  only after **both** gates pass.
- **Durable, resumable runs.** A run's complete lifecycle state lives in Neon
  PostgreSQL. Any process, on any machine, can pick a run up from its last
  committed step — after a crash, a local-to-CI handoff, or a human who
  answers a clarifying question three days later.
- **Worker-agnostic roles.** Each role is assigned a worker (`claude-code`,
  `copilot`, `hermes`, or the in-process `fake` test worker) in a config file,
  not in code — reassigning a role to a different agent runtime is a YAML
  edit, never an `if worker == "claude"` branch in the orchestrator.

## Prerequisites

- **Python 3.12** (`requires-python = ">=3.12"`).
- **A Neon project running PostgreSQL 17** — this is Dark Factory's own
  run-state database, separate from anything your repository uses. Create it
  at Neon Console → New Project → select Postgres 17.
- **The repository you want Dark Factory to work on** — any existing git repo
  with a remote on GitHub. Dark Factory runs *inside* that repository, not
  the other way around.
- **Whichever worker-runtime CLI your roles will use** — `claude`, `copilot`,
  and/or `hermes` binaries on `PATH`, plus that runtime's own credential (see
  "Environment variables and secrets" below). The `fake` worker needs
  neither, and is the fastest way to prove the pipeline end-to-end with zero
  agent credentials.

## Install it into your own repository

Dark Factory is pip-installable and runs from inside the repository it is
automating, not from a checkout of Dark Factory's own source — but two
different setup paths have two different needs here:

- **In CI**, a job installs `dark-factory` from a git URL (`pip install
  "dark-factory @ git+https://github.com/<your-org>/dark-factory.git"`, or
  `pip install dark-factory` once it's published to PyPI) — **no checkout of
  this repository is ever needed.** "Finish a run in CI" below documents this
  path in full.
- **Locally**, getting a target repository fully set up still needs a
  one-time checkout of *this* repository, for two things that do not ship
  inside the installed package yet: Alembic's schema migrations, and
  `scripts/scaffold_target_repo.py`, the fast path for generating your
  target repository's config tree. There is currently no `dark-factory init`
  command that would make the checkout unnecessary — a deliberate, recorded
  deferral, not an oversight.

Nothing below becomes a permanent dependency of your repository: once your
repo's schema is applied and its config tree is scaffolded, every command
after that runs from *your* repo, using the installed package, never this
checkout.

```bash
# One-time: clone Dark Factory just to install it and borrow its tooling.
git clone https://github.com/mariakravchenko/dark-factory.git
cd dark-factory
uv tool install .
```

`dark-factory` is now a command on your `PATH`, from any directory.

See "Scaffold your repository's config tree" immediately below for
generating `.dark-factory.yaml`, the role YAMLs, instruction files,
`.env.example`, `.gitignore`, and both GitHub Actions workflows in *your*
repository.

```bash
# From here on, work happens in YOUR repository, not this one.
cd /path/to/your-repo
cp .env.example .env
```

Edit `.env` and set every variable "Environment variables and secrets" below
documents — at minimum `DATABASE_URL`, `DATABASE_URL_DIRECT`, and whichever
worker-runtime credential your scaffolded roles were assigned.

```bash
# Apply the schema to your Neon database. This still needs the dark-factory
# clone from the first step (migrations aren't packaged yet) — run it with
# your repo's .env active, pointed at your own DATABASE_URL_DIRECT.
cd /path/to/dark-factory  # the clone from step one
set -a; source /path/to/your-repo/.env; set +a
uv run alembic upgrade head
cd /path/to/your-repo

# Start a run from a plain-text task and drive it through the pipeline.
dark-factory run text:"add a health endpoint"
```

### Scaffold your repository's config tree

A standalone script in the Dark Factory checkout, `scripts/scaffold_target_repo.py`,
generates the files a target repository needs instead of hand-authoring them
— `.dark-factory.yaml`, the four role YAMLs, their instruction files,
`.env.example`, `.gitignore`, and two GitHub Actions workflows
(`resume.yml` and `run.yml`). It is a stopgap for this hand-authoring step,
not a replacement for the deferred `dark-factory init` command — that
decision stands. This script is a developer tool deliberately kept outside
the shipped package: it is **not** a `dark-factory` subcommand, is **not**
installed by `pip install dark-factory`, and therefore requires the checkout
from the section above to run.

```bash
uv run python scripts/scaffold_target_repo.py \
  --target /path/to/your-repo \
  --github-owner your-org \
  --github-repo your-repo

# Per-role worker overrides and a custom quality-gate command:
uv run python scripts/scaffold_target_repo.py \
  --target /path/to/your-repo \
  --github-owner your-org \
  --github-repo your-repo \
  --worker-architecture copilot \
  --quality-gate-command "make test"
```

It writes thirteen files into the target repository: `.dark-factory.yaml`
(the repo-behavior contract), the four role YAMLs under
`.dark-factory/roles/` (`BA.yaml`, `ARCHITECTURE.yaml`, `DEVELOPMENT.yaml`,
`QA.yaml`), the four instruction Markdown files under
`.dark-factory/instructions/` (copied from this repository's own set, with a
generated write-scope section appended), `.env.example` (the variable names
from "Environment variables and secrets" below, pre-filtered to the workers
your roles actually use), `.gitignore`, and the two GitHub Actions workflows
`.github/workflows/resume.yml` and `.github/workflows/run.yml`.

| Flag | Default | Purpose |
|------|---------|---------|
| `--target` | — (required) | Target repository root directory. |
| `--github-owner` | — (prompted interactively if omitted and stdin is a TTY; required otherwise) | Written into `.dark-factory.yaml`'s `repository.github_owner`. |
| `--github-repo` | — (prompted interactively if omitted and stdin is a TTY; required otherwise) | Written into `.dark-factory.yaml`'s `repository.github_repo`. |
| `--base-branch` | `main` | Written into `repository.base_branch`. |
| `--worker` | `claude-code` | Default worker for all four roles. Legal values: `claude-code`, `copilot`, `hermes`. |
| `--worker-ba` | unset (falls back to `--worker`) | Per-role worker override for `BA`. |
| `--worker-architecture` | unset (falls back to `--worker`) | Per-role worker override for `ARCHITECTURE`. |
| `--worker-development` | unset (falls back to `--worker`) | Per-role worker override for `DEVELOPMENT`. |
| `--worker-qa` | unset (falls back to `--worker`) | Per-role worker override for `QA`. |
| `--quality-gate-command` | this repo's own `uv run pytest -q` / `uv run ruff check .` pair | Repeatable — one `quality_gate.commands` entry per use; passing it at all replaces the default pair entirely. |
| `--install-source` | `dark-factory` | The `pip install "<value>"` target baked into the generated `resume.yml` / `run.yml` workflows. Pass a git-source string (e.g. `"dark-factory @ git+https://github.com/<your-org>/dark-factory.git"`) until the package is published to PyPI. |
| `--force` | off | Overwrite existing files instead of skipping them. |
| `--yes` | off | Suppress interactive prompting; requires `--github-owner` and `--github-repo` to already be set. |

The generated `run.yml` is a manual `workflow_dispatch` workflow with one
required `source` input, passed verbatim to `dark-factory run` — accepting
the same three source forms the local CLI accepts: a `text:`-prefixed
string, a `spec:`-prefixed file path, or a `github:`-prefixed issue number.
It is wired to the same Actions secrets the generated `resume.yml` uses, and
both generated workflows carry the identical three-key `permissions` block
— see "The reference workflow" below for exactly why each scope is
load-bearing.

Two things worth knowing before pointing it at a real repository: an
existing file in the target is left untouched unless you pass `--force`;
and the instruction files it writes are copied from this repository's own
`.dark-factory/instructions/`, with a generated write-scope section
appended so the prose matches what write-scope enforcement will actually
allow.

## Environment variables and secrets

Infrastructure credentials and process-level knobs live only in the
environment (`.env` or real environment variables), never in
`.dark-factory.yaml` — that two-tier split is deliberate, so a repo-behavior
config file can be committed with zero secret-handling review. See
"Configuration reference" below for the second tier.

Every field `Settings` (`src/dark_factory/config/settings.py`) declares, in
declaration order, by its uppercased environment-variable name:

| Variable | Required | Default | What it controls | Where to get it |
|----------|----------|---------|-------------------|------------------|
| `DATABASE_URL` | Required | — | The **pooled** Neon connection string (host contains `-pooler`), scheme rewritten to `postgresql+psycopg://`. Used by the application engine at runtime. | Neon Console → your project → Connection Details → the pooled connection string. |
| `DATABASE_URL_DIRECT` | Required | — | The **direct** (non-pooled) Neon connection string (host **without** `-pooler`), same scheme rewrite. **Alembic uses this one** — DDL and PgBouncer transaction pooling do not mix, so migrations through the pooled endpoint are unreliable. | Neon Console → Connection Details → disable connection pooling to reveal the direct host. |
| `DARK_FACTORY_GITHUB_TOKEN` | Optional | `None` | Dark Factory's own token for posting clarification comments and opening pull requests. Required once a run's source is a GitHub issue or its pipeline publishes. Deliberately not named `GITHUB_TOKEN`: that exact name is reserved by GitHub Actions for the ephemeral installation token it auto-injects into every job, so a repository secret cannot be created under it, and that installation token cannot call `GET /user` as a matter of platform rule. | GitHub: a classic PAT with `repo` scope, or a fine-grained PAT scoped to this repository with Contents (read/write), Issues (read/write), and Pull requests (read/write) permissions. |
| `LOG_LEVEL` | Optional | `INFO` | structlog output level. | Set it yourself — one of `CRITICAL`, `FATAL`, `ERROR`, `WARN`, `WARNING`, `INFO`, `DEBUG`, `NOTSET` (case-insensitive). |
| `LEASE_TTL_SECONDS` | Optional, **not a secret** | `900` | How long a claimed run stays owned without a renewal. After a hard crash the run is unclaimable until this elapses on the **database** clock — there is no earlier-steal escape hatch. | Set it yourself; the default is the genuine production value. |
| `LEASE_HEARTBEAT_SECONDS` | Optional, **not a secret** | `300` | How often the owning process pushes its lease expiry forward while a step runs. Must be strictly less than `LEASE_TTL_SECONDS`. | Set it yourself; one third of the TTL is the standard ratio, so two consecutive missed renewals still land inside the TTL. |
| `ANTHROPIC_API_KEY` | Optional | `None` | Credential for the `claude-code` worker adapter, shared by `hermes` (which has no dedicated credential of its own). Absence is harmless until a role actually tries to invoke one of those workers. | Anthropic Console — an API key for the account that will run these roles. |
| `COPILOT_GITHUB_TOKEN` | Optional | `None` | A worker's own authentication material for the `copilot` adapter, injected into the `copilot` subprocess only — never Dark Factory's own `DARK_FACTORY_GITHUB_TOKEN`. | GitHub: a fine-grained, **personal-account-owned** PAT carrying the `Copilot Requests` permission. A classic PAT (`ghp_*`) is rejected by the Copilot CLI. |
| `COPILOT_MODEL` | Optional | `None` | Model identifier passed to the `copilot` CLI. Unset uses the CLI's own default model. | Set it yourself if you want to pin a model. |
| `CLAUDE_MODEL` | Optional | `None` | Model identifier appended as `--model <value>` to every `claude` CLI invocation. Unset uses the CLI's own default model. | Set it yourself if you want to pin a model. |
| `WORKER_TIMEOUT_SECONDS` | Optional | `1800` | The single knob governing every worker subprocess call's timeout, in seconds. | Set it yourself; the default (30 minutes) is a deliberately generous estimate, not a measured figure. |

Settings loading **fails fast at startup** on:

- a `LOG_LEVEL` that is not one of the recognized Python logging level names
  listed above (case-insensitive);
- a `LEASE_TTL_SECONDS` that is not strictly positive;
- a `LEASE_HEARTBEAT_SECONDS` that is not strictly less than
  `LEASE_TTL_SECONDS`;
- a `WORKER_TIMEOUT_SECONDS` that is not strictly positive.

Worker credentials are the exception: an absent `ANTHROPIC_API_KEY` or
`COPILOT_GITHUB_TOKEN` surfaces only when a role actually invokes that
worker (a typed `MissingWorkerCredentialError`), never at process startup.

These are the same variable names a generated GitHub Actions workflow reads
as Actions secrets — see "The worker runtime" (under "Finish a run in CI"
below) for which secret each worker needs, mapped per role.

## Run a task

```bash
dark-factory run text:"add a health endpoint"
```

`run` prints the **run id on its own first line** (so a killed process is still
recoverable), then one line per state transition, then a short summary block:

```
54e1153f-4cb5-4e2f-92a8-dea95ba06846
CREATED → BA
BA → ARCHITECTURE
ARCHITECTURE → DEVELOPMENT
DEVELOPMENT → QA
QA → COMPLETED

run 54e1153f-4cb5-4e2f-92a8-dea95ba06846
  terminal state: COMPLETED
  last role:      QA
  attempt:        1
```

A partial run shows the id and only the transitions that committed — no
`terminal state: COMPLETED` line. The role sequence a run drives through comes
from `.dark-factory.yaml`'s `workflow.roles` list (`BA`, `ARCHITECTURE`,
`DEVELOPMENT`, `QA` by default). When the last configured role (QA) completes
with a PASS verdict, the orchestrator runs the independent Quality Gate and,
if it also passes, publishes the pull request — both as part of that same
`QA → COMPLETED` transition, recorded on the audit trail as
`QUALITY_GATE_STARTED` / `QUALITY_GATE_PASSED` and `PUBLISH_STARTED` /
`PR_CREATED` events (see `dark-factory events <run-id>`) rather than as
separate CLI transition lines. A Quality Gate failure bounces the run back to
the Developer instead, up to `quality_gate_max_iterations` times.

`dark-factory resume <run-id>` runs the identical drive loop from a brand-new
process; on an already-terminal run it prints the id and the summary block and
adds no transition lines.

### The CLI surface

| Command | Purpose |
|---------|---------|
| `dark-factory run <source>` | Start a run from a `text:"..."`, `spec:<path>`, or `github:<owner>/<repo>#<n>` source and drive it. |
| `dark-factory resume <run-id> [--answer "..."]` | Resume a run; with `--answer`, first records the answer to its open question. |
| `dark-factory status <run-id> [--json]` | The full report for one run: state, role history, artifacts, interactions, quality-gate results, PR info, and transition history. |
| `dark-factory events <run-id> [--json] [--type ...]` | The `run_events` audit trail for a run, in order, optionally filtered by event type (repeatable). |
| `dark-factory runs [--status ...]` | List every run, newest first, optionally filtered by status. The entry point when you don't already have a run id. |
| `dark-factory artifacts <run-id> [--show <artifact-id>]` | List a run's artifact references, or print one artifact's content read from the run's working branch via `git show`. Artifacts are references, not content: the `artifacts` table records only metadata (id, type, path, checksum) — the actual content lives on the filesystem under `.dark-factory/runs/<run-id>/`, travels between machines by being committed to a `.dark-factory/` path on the run's working branch, and is excluded from the published PR diff. |

`status` and `events` render as text tables/panels by default; `--json` emits
a single parseable JSON object/array for scripting — the same field set in
both modes (`run_id`, `source_kind`, `source_ref`, `status`, `current_role`,
`current_step`, `latest_attempt`, `created_at`, `updated_at`, `base_branch`,
`working_branch`, plus `pr_number` / `pr_url` / `published_commit_sha`).

```bash
dark-factory status 54e1153f-4cb5-4e2f-92a8-dea95ba06846 --json
```

`base_branch` and `working_branch` are populated once a run creates its
isolated git worktree (step 2 of the pipeline onward); a `text:`-sourced run
with no repository context leaves them `null`.

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

## Pause a run for a human, then resume it

A role can stop mid-run to ask the operator a question. The run goes to
`WAITING_HUMAN`, the owning process releases its lease and exits `0`, and any
later process — on any machine sharing the database — answers the question and
carries the run to a terminal state.

Every command below was run as written against a real Neon database; the output
shown is what the process actually printed.

### 1. Make a run pause

Against the `fake` worker a `NEEDS_INPUT` result is produced with the
`DARK_FACTORY_FAKE_SCRIPT` environment variable — a JSON array of scripted
worker results. The first asks a question; the second (used after the answer)
completes.

```bash
DARK_FACTORY_FAKE_SCRIPT='[
  {"status":"NEEDS_INPUT","summary":"need a decision before I can proceed",
   "questions":["Which database should the health endpoint report on -- primary or replica?"],
   "worker_session_id":"fake-operator-walkthrough-001"},
  {"status":"COMPLETED","summary":"done","worker_session_id":"fake-operator-walkthrough-001"}
]' dark-factory run text:"add a health endpoint"
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
dark-factory status e9de8336-56f6-4ce8-be34-9914d67ed3eb
```

`status: WAITING_HUMAN` on `current_role: BA` tells you the run is paused and
which role asked. The question text itself is part of the report's
interactions section (and is also readable straight off the
`human_interactions` row). GitHub-sourced runs get the same question posted
as a clarification comment on the originating issue — see "Finish a run in
CI" below.

### 3. Resume with an answer, from a different shell

Nothing from the original process is needed — only the run id and the database.
Open a new shell (no `DARK_FACTORY_FAKE_SCRIPT` set) and:

```bash
dark-factory resume e9de8336-56f6-4ce8-be34-9914d67ed3eb \
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
dark-factory resume ff7a698c-72ec-44ee-91fa-cb1fe88e4a5b --answer "primary"
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
`resume`s it from the last committed step. There is no command to force an
earlier steal.

## Finish a run in CI — the local → CI handoff

### What this is

A run that pauses for a human on your laptop does not have to be resumed on
your laptop. When the human replies on the GitHub issue, dispatching a small
CI workflow resumes the run on a genuinely different machine, with nothing
carried over but the run id. The invariant holds throughout: **the trigger
carries no lifecycle logic; every entry point — the local CLI, a dispatched
CI job — reaches the same `advance(run_id)`.**

In CI, the job installs `dark-factory` as a dependency — no checkout of Dark
Factory's own repository, ever (see "Install it into your own repository"
above). It needs your target repository's `.dark-factory.yaml` and
`.dark-factory/roles/*.yaml` already committed, the `resume.yml` workflow
below added to `.github/workflows/`, and the worker runtime your roles are
assigned to available on the runner — a credential alone does not satisfy
this; see "The worker runtime" below.

#### Scaffolding `resume.yml` and `run.yml`

Both generated workflows come from the same scaffold step described in
"Scaffold your repository's config tree" above — `resume.yml` (the reference
block below) and its sibling `run.yml`, which starts a run in CI the same
way `resume.yml` finishes one.

### The full flow

1. Locally, `dark-factory run github:<owner>/<repo>#<n>` creates and drives
   the run; it may pause `WAITING_HUMAN` with a clarifying comment on the
   issue.
2. The human replies on the issue.
3. The human runs `gh workflow run resume.yml -f run_id=<id> -f
   answer=<text>` against the target repository — or any external script
   does, since the dispatch itself carries no Dark Factory logic.
4. A fresh GitHub Actions runner checks out the repository, installs
   `dark-factory` and runs `dark-factory resume <run_id> --answer <text>`,
   which records the answer and re-materializes everything from Neon plus a
   fresh git worktree. `--answer` may be omitted to simply re-drive a run
   that is not currently waiting on a human — that is what the optional
   `answer` input buys.
5. The run reaches `COMPLETED` (possibly publishing a PR) or pauses again,
   and the loop repeats from step 2. The human's answer is recorded durably
   by `dark-factory resume --answer` itself, and a run can always be resumed
   again from any machine with `dark-factory resume <run_id>`.

### The reference workflow

Copy the block below into your own repository at
`.github/workflows/resume.yml`. Dark Factory **neither ships nor validates**
this file — it is a reference, and you own it. The sentinel comments
bracketing it are load-bearing: a test in this repository extracts this
exact block by those sentinels and asserts it still parses and still
declares the inputs the documented `gh workflow run` command passes, so
their spelling must not change.

<!-- resume-workflow-reference: begin -->
```yaml
name: resume

"on":
  workflow_dispatch:
    inputs:
      run_id:
        description: "The Dark Factory run id to resume"
        required: true
        type: string
      answer:
        description: "Answer to the run's open human question (omit to just re-drive)"
        required: false
        type: string

# contents: push each role's work back to origin. issues: post the
# clarification comment when a run pauses WAITING_HUMAN. pull-requests:
# open the PR after QA PASS and Quality Gate PASS.
permissions:
  contents: write
  issues: write
  pull-requests: write

jobs:
  resume:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install dark-factory
        run: pip install "dark-factory @ git+https://github.com/<your-org>/dark-factory.git"

      # - name: Install the worker runtime
      #   # Required whenever a role is assigned to a worker that shells out
      #   # to a CLI binary -- see "The worker runtime" below for the binary
      #   # name your roles need on PATH. The install command itself comes
      #   # from that runtime's own documentation: Dark Factory neither
      #   # ships nor verifies it.
      #   run: <install your worker runtime's CLI here, per its own docs>

      - name: Resume the run
        run: |
          if [ -n "$RUN_ANSWER" ]; then
            dark-factory resume "$RUN_ID" --answer "$RUN_ANSWER"
          else
            dark-factory resume "$RUN_ID"
          fi
        env:
          RUN_ID: ${{ inputs.run_id }}
          RUN_ANSWER: ${{ inputs.answer }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          DATABASE_URL_DIRECT: ${{ secrets.DATABASE_URL_DIRECT }}
          DARK_FACTORY_GITHUB_TOKEN: ${{ secrets.DARK_FACTORY_GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```
<!-- resume-workflow-reference: end -->

The trigger key is quoted (`"on":`) for the same reason this repository's own
`ci.yml` quotes it: YAML 1.1 parses a bare `on:` as the boolean `True`. There
is no `if:` anywhere in this workflow, no matrix, no second job — the
workflow is a trigger, and a trigger that grows a branch on run state has
started deciding what happens next, which is the one thing it must not do.

`permissions: contents: write` is load-bearing, not generous-by-default:
this job resumes a role that commits and pushes its own work back to
`origin`, and `actions/checkout`'s default credential setup (left at its own
default, `persist-credentials: true`) is scoped by exactly this
`permissions` block — so it is the one thing standing between "the push
Dark Factory performs after a role completes" and a 403. It also covers a
less obvious half: the git-worktree reconstruction that re-checks out a
run's branch when resuming on a machine that never created it (the
local-laptop-pause, CI-resume handoff this whole section is about) has no
credential channel of its own; it relies entirely on whatever checkout
already configured. Scope this down to `read` and the *push* fails loudly
("Write access to repository not granted"); try to route around that by
disabling `persist-credentials` instead of widening `permissions`, and the
*fetch* fails silently instead — git has no other credential to fall back
on, so the worktree reconstructs empty off the base branch, and the role
that resumes next can't find the previous role's artifacts at all. Both
failure modes were hit, in exactly this order, while proving this
cross-machine resume capability for real.

The other two scopes are bounded just as tightly to the job's own REST
calls. `issues: write` gives the job authority to post the clarification
comment when a role needs input and the run pauses `WAITING_HUMAN` — step 1
of the full flow above, and the thing that makes the whole pause/resume loop
legible to the human waiting on it. Omit it and that comment call 403s the
moment the first role needs input. `pull-requests: write` gives the job
authority to open the PR after QA PASS and Quality Gate PASS — the one
publication the whole policy gates on; omit it and that create-PR call 403s
instead. The job's token stops there: it carries no `actions` scope, because
nothing in Dark Factory dispatches a workflow at all — the dispatch is a
human action using the human's own `gh` credentials, outside any job's
token. As with `contents`, an absent scope here surfaces as a 403 from the
GitHub API, not as a git-level error.

`fetch-depth: 0` on the checkout step is the third thing this same proof hit
before a role genuinely completed end to end. `actions/checkout`'s default
(`1`) fetches only the tip of the default branch — too shallow for the PR
diff collection (a merge-base, triple-dot diff against `main`, run from the
quality gate's after-hook) to find any common ancestor once `main` has moved
on since the run's branch forked from it, which it reliably has by the time
a role finishes. The failure there is `fatal: main...dark-factory/run-<id>:
no merge base` — full history is what a merge-base computation needs; any
fixed shallow depth just relocates the same failure further out.

The install step names a git source rather than a package index, because
`dark-factory` is not yet published to PyPI — switch to `pip install
dark-factory` (or `uv add dark-factory`) once it ships.

The Actions secrets this job needs: `DATABASE_URL` / `DATABASE_URL_DIRECT`
(the same Neon connection strings your local `.env` uses),
`DARK_FACTORY_GITHUB_TOKEN` (for the comment/PR operations Dark Factory
performs on your behalf — a repository secret you create yourself, named
deliberately unlike GitHub's own reserved `GITHUB_TOKEN`), and whichever
worker credential your roles' assigned worker needs (e.g.
`ANTHROPIC_API_KEY` for `claude-code`).

The step's exit code is the same contract the CLI documents above: `0` for a
run that reached a clean terminal state — including a fresh `WAITING_HUMAN`
pause, since the loop simply goes round again — `1` for a persisted `FAILED`,
`2` for a bad invocation such as an unknown run id. A red Actions run here
means `1` or `2`, never `0`.

### The worker runtime

Dark Factory does not implement a coding agent; the worker adapter assigned to
a role spawns that runtime's own CLI as a subprocess inside the job, and the
binary must already be on `PATH` there. A missing binary surfaces as a
`FAILED` role execution whose recorded error names the missing binary — that
is the text to search for if a resumed run fails immediately after the
install step.

Every worker this repository registers, the binary its adapter shells out
to, and the credential environment variable it reads:

| `worker:` value | Binary required on `PATH` | Credential environment variable |
|---|---|---|
| `claude-code` | `claude` | `ANTHROPIC_API_KEY` |
| `copilot` | `copilot` | `COPILOT_GITHUB_TOKEN` |
| `hermes` | `hermes` | `ANTHROPIC_API_KEY` — shared with `claude-code`; Hermes has no dedicated credential of its own |

(`fake`, the fourth registered worker, needs neither a binary nor a
credential — it scripts its results in-process, which is exactly how the
`db`-tier suite runs in CI with no agent credentials configured at all.)

## Configuration reference

A target repository's behavior is declared in `.dark-factory.yaml` at its
root, read once per run at creation time; the resolved snapshot is what every
resume replays, so editing it never changes an in-flight run.

```yaml
version: 1

repository:
  base_branch: main
  github_owner: your-org
  github_repo: your-repo

workflow:
  roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]

roles_dir: .dark-factory/roles

quality_gate:
  commands:
    - "uv run pytest -q"
    - "uv run ruff check ."

retry:
  qa_developer_max_iterations: 3
  quality_gate_max_iterations: 2

publishing:
  create_pr: true
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `version` | int | `1` | Schema version of the document. |
| `repository` | mapping | `{}` | The target repo's Git conventions — see the three keys below. |
| `base_branch` | string | `"main"` | The target repo's base branch for new runs. |
| `github_owner` | string \| null | `null` | GitHub owner of the target repository; used for GitHub-sourced intake and publishing. Repos that use neither need no change. |
| `github_repo` | string \| null | `null` | GitHub repository name, paired with `github_owner`. Read from config only — never from a CLI locator — so a crafted locator can never redirect a fetch at another repository. |
| `workflow` | mapping | — (required) | The ordered role pipeline — see `roles` below. |
| `roles` | list of strings | — (required, min 1 entry) | The ordered pipeline. Each entry must be one of the role-shaped `RunStatus` values: `BA`, `ARCHITECTURE`, `DEVELOPMENT`, `QA`, `VERIFYING`, `PUBLISHING`. A human label or typo is rejected at load time. |
| `roles_dir` | string | `".dark-factory/roles"` | Directory (relative to the repo root) containing one `<ROLE_NAME>.yaml` file per entry in `workflow.roles`. Resolved and checked against path escape — a `roles_dir` that resolves outside the repo root is rejected. |
| `quality_gate` | mapping | `{}` | The independent quality-gate commands — see `commands` below. |
| `commands` | list of strings | `[]` | Shell commands run as the independent quality gate after QA passes. Stored in the effective-config snapshot; executed by the orchestrator's quality-gate step. |
| `retry` | mapping | `{}` | Feedback-loop iteration caps — see the two keys below. |
| `qa_developer_max_iterations` | int (>= 0) | `3` | Maximum QA → Developer feedback-loop bounces before the run fails. |
| `quality_gate_max_iterations` | int (>= 0) | `2` | Maximum quality-gate → Developer feedback-loop bounces before the run fails. |
| `publishing` | mapping | `{}` | The PR-creation switch — see `create_pr` below. |
| `create_pr` | bool | `true` | Gates PR creation. Publishing (PR creation) only ever happens after QA PASS *and* independent quality-gate PASS, regardless of this flag's value. |

Each entry in `workflow.roles` points at a `<name>.yaml` file in `roles_dir`
(`BA.yaml`, `ARCHITECTURE.yaml`, `DEVELOPMENT.yaml`, `QA.yaml` in this
repository's own `.dark-factory/roles/`) that declares, per role: its
assigned `worker`, its `instructions` file, the `tools` it may invoke, its
`permissions.write_scope` (which repository paths it may change — empty
means read-only), and its `inputs` / `outputs` artifact contract with the
adjacent roles.

`quality_gate.commands` are the independent checks the Quality Gate role runs
against the Developer's own work after QA passes — failing either loop
(`qa_developer_max_iterations` / `quality_gate_max_iterations`) sends the run
back to the Developer rather than publishing. `publishing.create_pr: true` is
the switch that gates PR creation on both PASS results; it never fires on
either one alone.

No secrets live in this file — infrastructure credentials (`DATABASE_URL`,
`DARK_FACTORY_GITHUB_TOKEN`, worker credentials) are environment-only,
loaded by `pydantic-settings` and never written into run config, artifacts,
or logs.

### `.dark-factory/roles/*.yaml`

One file per entry in `workflow.roles`, named `<ROLE_NAME>.yaml` and located
under the directory named by `roles_dir`. Validated by `RoleDefinition`,
also `frozen=True` and `extra="forbid"`. The scaffold script writes these
as a starting point — every field is a plain YAML value you can hand-edit
at any time; there's no code to touch.

```yaml
name: DEVELOPMENT
worker: claude-code
instructions: ../instructions/development.md

tools:
  [repo.read, repo.search, repo.write, repo.write_tests, shell.execute, artifacts.read, artifacts.write]
permissions:
  write_scope: ["src/**"]

before: [ensure_clean_worktree]
after: [collect_diff]

inputs: [design.md, constraints.json]
optional_inputs: [verdict.json, quality_gate.json]
outputs: [implementation_summary.json]
examples: []
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | — (required) | Must match the `workflow.roles` entry whose file this is, or config loading fails. |
| `worker` | string | — (required) | Must be a name registered on the worker registry: `fake`, `claude-code`, `copilot`, or `hermes`. Validated by exact-name membership, never dynamic lookup. Reassigning a role to a different worker is a config-only change — the orchestrator never branches on worker identity. |
| `instructions` | string (path) | — (required) | Path to the role's instruction Markdown, resolved relative to the role YAML's own directory, must stay under the repo root (no `..` escape), and is capped at 64 KiB when inlined into the snapshot. |
| `tools` | list of strings | `[]` | Capability names this role may invoke, validated by exact-name membership against the tool registry: `artifacts.read`, `artifacts.write`, `repo.read`, `repo.search`, `repo.write`, `repo.write_tests`, `shell.execute`. A capability not in this list is denied before it runs, regardless of what is registered. |
| `permissions` | mapping | `{}` | The role's write-scope grant — see `write_scope` below. |
| `write_scope` | list of glob patterns | `[]` (zero tolerance) | Filesystem glob patterns (matched with `fnmatch.fnmatchcase`, not `pathlib`) a role's write-capable tool invocations must stay within. **An empty or absent list means zero tolerance, not "unrestricted"** — every path is a violation when the list is empty. Any changed path outside the declared patterns is reverted and fails the role. |
| `before` | list of strings | `[]` | Action names run before the role's worker is invoked, validated against the action registry: `ensure_clean_worktree` is the only one meant to be role-configurable today — it recovers a dirty worktree onto the current branch; a role YAML that omits it forgoes that recovery. |
| `after` | list of strings | `[]` | Action names run after the role's worker returns. `collect_diff` (git-only; writes the PR-bound diff) is listed only on roles that can change repository source (`DEVELOPMENT`, `QA`). |
| `inputs` | list of strings | `[]` | Artifact filenames this role requires as input, resolved by declared filename (not pipeline adjacency). Config loading / role execution fails if a declared input cannot be resolved. |
| `optional_inputs` | list of strings | `[]` | Artifact filenames resolved leniently — simply omitted from the role's context when absent, never an error. Used for feedback-loop artifacts (`verdict.json`, `quality_gate.json`) that don't exist on a role's first attempt. |
| `outputs` | list of strings | `[]` | Artifact filenames this role is expected to produce. |
| `examples` | list of strings | `[]` | Reserved for future few-shot example references; currently unused by any shipped role. |

### Shipped roles

The four roles below are **generated starting examples**, not fixed
defaults — `scripts/scaffold_target_repo.py` writes them as plain YAML
files directly in your repo, and every field (`worker`, `write_scope`,
`inputs`, `outputs`, `tools`, `instructions`) is yours to edit afterward
with no code change required. Every role defaults to the `claude-code`
worker (`DEFAULT_WORKER`) at generation time — override per-role with
`--worker-ba` / `--worker-architecture` / `--worker-development` /
`--worker-qa`, or just hand-edit the generated `.dark-factory/roles/*.yaml`
later.

| Role | Worker (default) | `write_scope` | Inputs | Outputs |
|------|-------------------|---------------|--------|---------|
| `BA` | `claude-code` | `[]` (read-only) | — | `requirements.md`, `acceptance_criteria.json` |
| `ARCHITECTURE` | `claude-code` | `[]` (read-only) | `acceptance_criteria.json` | `design.md`, `constraints.json` |
| `DEVELOPMENT` | `claude-code` | `["src/**"]` | `design.md`, `constraints.json` (optional: `verdict.json`, `quality_gate.json`) | `implementation_summary.json` |
| `QA` | `claude-code` | `["tests/**"]` | `acceptance_criteria.json`, `implementation_summary.json` | `test_report.json`, `verdict.json` |

Any role can be reassigned to any worker (`fake`, `claude-code`, `copilot`,
`hermes`) with zero orchestrator code change — this repository's own
`.dark-factory/roles/*.yaml` proves it by deliberately running each of its
four roles on a different worker.

`QA` deliberately has no `repo.write` grant — it may write tests, never
production source, which is the "cannot publish" half of its permission
boundary.

**`write_scope` only governs your repository's source tree** (`src/**`,
`tests/**`, etc.) — a role whose `write_scope` is `[]`, like `BA` and
`ARCHITECTURE` above, still writes its declared `outputs` normally. Those
go to a completely separate location, the run's own gitignored
`.dark-factory/runs/<run_id>/artifacts/<role>/` tree, gated by the
`artifacts.write` tool grant instead — an independent enforcement path from
`write_scope`. "Read-only" above means "cannot touch your source code," not
"produces no output."

### Instruction files

Each role's instruction Markdown lives alongside the role YAML under
`.dark-factory/instructions/` (`ba.md`, `architecture.md`,
`development.md`, `qa.md` in this repository's own tree). A role YAML's
`instructions` path is resolved relative to that role YAML's own directory,
must resolve under the repository root, and must be a real file — the
scaffold copies these from this repository's own set, with a generated
write-scope section appended so the prose matches what write-scope
enforcement will actually allow.

## Troubleshooting

- **`alembic upgrade head` fails or hangs.** Confirm `DATABASE_URL_DIRECT` is
  the **non-pooled** host (no `-pooler` in the hostname) — DDL against the
  pooled endpoint is unreliable because DDL and PgBouncer transaction pooling
  do not mix.
- **Settings fail to load with a `lease_heartbeat_seconds` error.** Your
  `.env` has `LEASE_HEARTBEAT_SECONDS` set greater than or equal to
  `LEASE_TTL_SECONDS`. It must be strictly less, or the heartbeat can never
  fire often enough to keep the lease alive.
- **A role fails immediately with an error naming a missing binary.** The
  worker assigned to that role (`claude`, `copilot`, or `hermes`) is not on
  `PATH` wherever `dark-factory run`/`resume` executed. Install that
  runtime's own CLI per its own docs — Dark Factory never ships or installs
  it for you. See "The worker runtime" above for which binary each worker
  needs.
- **A role fails with `MissingWorkerCredentialError`.** The credential
  environment variable for that role's assigned worker
  (`ANTHROPIC_API_KEY` for `claude-code`/`hermes`, `COPILOT_GITHUB_TOKEN` for
  `copilot`) isn't set in `.env`. This only surfaces when a role actually
  tries to invoke that worker, not at process startup — see "Environment
  variables and secrets" above.
- **The scaffold script exits with "instruction source file not found."**
  It copies instruction Markdown from *this repository's own*
  `.dark-factory/instructions/` directory, so it must be run from a Dark
  Factory checkout — not from an installed package, and not from your
  target repository.
- **`alembic upgrade head` or the scaffold script "can't find" the right
  files when run from your target repository.** Both commands belong to the
  Dark Factory checkout (see "Install it into your own repository" above),
  not your target repository.

## Contributing to Dark Factory itself

Everything above is for someone *using* Dark Factory to drive a delivery run
against their own repository. If you want to work on Dark Factory itself
instead, stop here — the rest of this section is for you.

```bash
git clone https://github.com/mariakravchenko/dark-factory.git
cd dark-factory
uv sync --all-extras --dev
```

The quality gates, in the order `.github/workflows/ci.yml` runs them:

| Command | What it does |
|---------|--------------|
| `uv run ruff check .` | Lint. |
| `uv run ruff format --check .` | Verify formatting without rewriting files. |
| `uv run mypy src/dark_factory` | Strict static type check of the package. |
| `uv run pytest -q -m "unit or contract"` | Fast tiers — pure functions plus the shared `CodingWorker` contract suite. |
| `uv run pytest -q -m db` | The `FakeWorker` orchestration suite against a real PostgreSQL 17. |
| `uv run pytest -q -m integration` | End-to-end CLI-as-subprocess suites. |

The four pytest markers (`pyproject.toml`'s `[tool.pytest.ini_options]`
`markers` list):

- `unit` — fast, pure-function tests with no database or I/O. The everyday
  inner loop: `uv run pytest -m unit`.
- `db` — tests that require a reachable PostgreSQL 17 instance:
  `uv run pytest -m db`.
- `integration` — end-to-end tests that drive the CLI as a subprocess.
- `contract` — the shared `CodingWorker` contract suite, parametrized over
  worker adapters: `uv run pytest -m "unit or contract"` for the combined
  fast-tier command.

The `db` and `integration` tiers need a real PostgreSQL 17, resolved by
`tests/conftest.py`'s probe ladder in order: **testcontainers** (a
responsive Docker daemon), then **pytest-postgresql** (a local `initdb` on
`PATH`), then an externally supplied `DARK_FACTORY_TEST_DATABASE_URL`. There
is no SQLite or mock fallback.

Commit convention is **Conventional Commits** — `type(scope): subject`.
