<!-- generated-by: gsd-doc-writer -->
# Dark Factory

Dark Factory is a durable orchestration platform that runs a software-delivery
task through a managed pipeline of AI engineering roles — **Business Analyst →
Architect → Developer → QA → an independent Quality Gate → PR** — instead of
one unsupervised agent loop. Give it a task (a plain-text description, a spec
file, or a GitHub issue) and it drives that task through each role, has an
independent step verify the work before anything ships, and opens the pull
request only once both QA and the Quality Gate agree it is good — all while
persisting every step to PostgreSQL so the run survives a crash, a laptop-to-CI
handoff, or a multi-day wait on a human answer.

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
  committed step — after a crash, a local-to-CI handoff, a GitHub webhook, or
  a human who answers a clarifying question three days later.
- **Worker-agnostic roles.** Each role is assigned a worker (`claude-code`,
  `copilot`, `hermes`, or the in-process `fake` test worker) in a config file,
  not in code — reassigning a role to a different agent runtime is a YAML
  edit, never an `if worker == "claude"` branch in the orchestrator.

## The fastest way to get running

**See [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)** for prerequisites,
installation, and the first command that produces a real run against a Neon
database. The rest of this README is reference material: the full CLI
surface, the pause/resume model, the local-to-CI handoff, and the decisions
baked into the schema.

## Prerequisites

- **Python 3.12** (`requires-python = ">=3.12"`).
- **A Neon project running PostgreSQL 17** — this is Dark Factory's own
  run-state database, separate from anything your repository uses. Create it
  at Neon Console → New Project → select Postgres 17.
- **The repository you want Dark Factory to work on** — any existing git repo
  with a remote on GitHub. Dark Factory runs *inside* that repository, not
  the other way around.

## Install it into your own repository

Dark Factory is not yet published to PyPI, so getting it running has one
unavoidable one-time step: a clone of **this** repository, used only to (a)
install the CLI from source, and (b) borrow its schema migrations and its
`scripts/scaffold_target_repo.py` config generator — neither of which ships
inside the installed package yet. Nothing below becomes a permanent
dependency of your repository; once your repo is configured and its schema
applied, every command after that runs from *your* repo, not this one.

```bash
# One-time: clone Dark Factory just to install it and borrow its tooling.
git clone https://github.com/mariakravchenko/dark-factory.git
cd dark-factory
uv tool install .
```

`dark-factory` is now a command on your `PATH`, from any directory.

```bash
# Generate the config tree your repository needs — run from inside the
# dark-factory clone, pointed AT your repository.
python3 scripts/scaffold_target_repo.py \
  --target /path/to/your-repo \
  --github-owner your-org --github-repo your-repo
```

This writes `.dark-factory.yaml`, four role YAMLs, their instruction files,
`.env.example`, `.gitignore`, and two GitHub Actions workflows into
*your* repository. See [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) for
every flag (per-role worker overrides, custom quality-gate commands) and
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for what each generated file
means if you'd rather hand-author them instead.

```bash
# From here on, work happens in YOUR repository, not this one.
cd /path/to/your-repo
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
- **`GITHUB_TOKEN`** — Dark Factory's own token for posting clarification
  comments and opening pull requests. Required once a run's source is a
  GitHub issue or its pipeline includes publishing.
- **`DISPATCH_GITHUB_TOKEN`** — a separate, narrowly-scoped token the webhook
  receiver uses to dispatch a CI resume job (see "Finish a run in CI" below).
  Not needed for purely local runs.
- **A worker-runtime credential** (e.g. `ANTHROPIC_API_KEY` for `claude-code`)
  — whichever your scaffolded roles were assigned.

Two optional, **non-secret** variables tune the single-owner lease. Leave them
unset to take the production defaults; `.env.example` documents both in full.

| Variable | Default | Unit | What it controls |
|----------|---------|------|------------------|
| `LEASE_TTL_SECONDS` | `900` | seconds | How long a claimed run stays owned without a renewal. After a hard crash the run is unclaimable until this elapses on the database clock — there is no earlier-steal escape hatch. |
| `LEASE_HEARTBEAT_SECONDS` | `300` | seconds | How often the owning process pushes its lease expiry forward while a step runs. Must be strictly less than `LEASE_TTL_SECONDS` (settings loading fails otherwise); one third of the TTL is the standard ratio. |

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

## The CLI surface

| Command | Purpose |
|---------|---------|
| `dark-factory run <source>` | Start a run from a `text:"..."`, `spec:<path>`, or `github:<owner>/<repo>#<n>` source and drive it. |
| `dark-factory resume <run-id> [--answer "..."]` | Resume a run; with `--answer`, first records the answer to its open question. |
| `dark-factory status <run-id> [--json]` | The full report for one run: state, role history, artifacts, interactions, quality-gate results, PR info, and transition history. |
| `dark-factory events <run-id> [--json] [--type ...]` | The `run_events` audit trail for a run, in order, optionally filtered by event type (repeatable). |
| `dark-factory runs [--status ...]` | List every run, newest first, optionally filtered by status. The entry point when you don't already have a run id. |
| `dark-factory artifacts <run-id> [--show <artifact-id>]` | List a run's artifact references, or print one artifact's content read from the run's working branch via `git show`. |

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
your laptop. When the human replies on the GitHub issue, the webhook receiver
records the answer in Neon and then asks GitHub Actions to start a job that
resumes the run — a genuinely different machine, with nothing carried over but
the run id. The invariant holds throughout: **the trigger carries no lifecycle
logic; every entry point — the local CLI, the webhook receiver, a dispatched CI
job — reaches the same `advance(run_id)`.**

### The deployment model

Dark Factory is a pip-installable package. A deployer does **not** clone or
check out Dark Factory's own repository. Instead:

1. Install `dark-factory` as a dependency inside your own repository's own
   toolchain (`uv add dark-factory` once published, or the equivalent for
   your package manager).
2. Hand-author `.dark-factory.yaml` and `.dark-factory/roles/*.yaml` in your
   own repository, modelled on the ones this repository ships.
3. Add one small `resume.yml` workflow to your own repository (below).
4. Give your webhook receiver a `DISPATCH_GITHUB_TOKEN` (below).
5. Make your roles' assigned worker runtime available wherever
   `dark-factory resume` runs — a credential alone does not satisfy this; see
   "The worker runtime" below.

There is currently no `dark-factory init` command to scaffold steps 2 and 3 —
a deliberate, recorded deferral, not an oversight.

#### Scaffolding steps 2 and 3

A standalone script in this repository, `scripts/scaffold_target_repo.py`,
generates the files steps 2 and 3 above describe hand-authoring — the repo
config (`.dark-factory.yaml`), the four role YAMLs, the four instruction
files, `.env.example`, the `resume.yml` workflow, and `.gitignore` — plus a
second generated workflow, `run.yml`, that starts a run in CI the same way
the resume one finishes one. It is a stopgap for this hand-authoring step,
not a replacement for the deferred `dark-factory init` command — that
decision stands.

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

The generated `run.yml` is a manual `workflow_dispatch` workflow with one
required `source` input, passed verbatim to `dark-factory run` — accepting
the same three source forms the local CLI accepts: a `text:`-prefixed
string, a `spec:`-prefixed file path, or a `github:`-prefixed issue number.
It is wired to the same Actions secrets the generated `resume.yml` uses,
and both generated workflows carry the identical three-key `permissions`
block:

- `contents: write` — a run commits and pushes each role's work, and
  `actions/checkout`'s persisted credential is scoped by this block, so it
  is what stands between that push and a 403.
- `issues: write` — the job hands the reserved Actions auto-token to
  `dark-factory` as `GITHUB_TOKEN`, and that token's REST authority is
  scoped by this same block; Dark Factory posts its own clarification
  comment on the issue when a run pauses `WAITING_HUMAN` (and reads the
  issue when the source is `github:`-prefixed).
- `pull-requests: write` — publication after QA PASS and an independent
  Quality Gate PASS creates the pull request through the API, which this
  scope authorizes.

The scope stops there deliberately: `actions: write` is absent because the
only workflow-dispatch call Dark Factory makes happens in the webhook
receiver, on the separate `DISPATCH_GITHUB_TOKEN`, never inside these jobs.

Two things worth knowing before pointing it at a real repository: an
existing file in the target is left untouched unless you pass `--force`;
and the instruction files it writes are copied from this repository's own
`.dark-factory/instructions/`, with a generated write-scope section
appended so the prose matches what write-scope enforcement will actually
allow.

This script is a developer tool deliberately kept outside the shipped
package — it is **not** a `dark-factory` subcommand, is **not** installed
by `pip install dark-factory`, and therefore requires a checkout of this
repository to run. That is the one place the deployment model's "you do
not clone Dark Factory's own repository" premise above does not hold.

### The full flow

1. Locally, `dark-factory run github:<owner>/<repo>#<n>` creates and drives
   the run; it may pause `WAITING_HUMAN` with a clarifying comment on the
   issue.
2. The human replies on the issue.
3. GitHub delivers an `issue_comment` webhook to the receiver's
   `/webhooks/github` route; it verifies the signature, resolves the reply to
   its pending interaction and records the answer.
4. The receiver reads the run's own persisted `repository.github_owner` /
   `github_repo` and asks GitHub to dispatch `resume.yml` on that repository,
   carrying the run id as input.
5. A fresh GitHub Actions runner checks out the repository, installs
   `dark-factory` and runs `dark-factory resume <run_id>`, which
   re-materializes everything from Neon plus a fresh git worktree.
6. The run reaches `COMPLETED` (possibly publishing a PR) or pauses again,
   and the loop repeats from step 2.

### The reference workflow

Copy the block below into your own repository at
`.github/workflows/resume.yml`. Dark Factory **neither ships nor validates**
this file — it is a reference, and you own it. The sentinel comments
bracketing it are load-bearing: a test in this repository extracts this
exact block by those sentinels and asserts it still parses and still says
what the dispatcher sends, so their spelling must not change.

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
        run: dark-factory resume "${{ inputs.run_id }}"
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          DATABASE_URL_DIRECT: ${{ secrets.DATABASE_URL_DIRECT }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
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
the only `actions`-scoped call is dispatching this very workflow, made by the
webhook receiver on the separate `DISPATCH_GITHUB_TOKEN` — see "The dispatch
credential" below. As with `contents`, an absent scope here surfaces as a
403 from the GitHub API, not as a git-level error.

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
(the same Neon connection strings your local `.env` uses), `GITHUB_TOKEN`
(for the comment/PR operations Dark Factory performs on your behalf), and
whichever worker credential your roles' assigned worker needs (e.g.
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

This table says nothing about `DISPATCH_GITHUB_TOKEN`; that credential
belongs to the webhook receiver that dispatches this job, not to the job
itself, and is documented in its own subsection next.

### The dispatch credential

Provision a **fine-grained** personal access token, scoped to the one target
repository, with the `Actions: Read and write` permission — nothing else.
That permission name — `actions: write` — is the fine-grained token's own
label and has **no equivalent checkbox on the classic-token creation
screen**; a classic token needs the much broader `repo` scope instead, which
works but grants far more than this call needs. Use a classic token only as a
documented fallback if a fine-grained token is unavailable to you.

Set the result as `DISPATCH_GITHUB_TOKEN` — matching `.env.example` exactly —
on whatever process hosts your webhook receiver. It is a third credential,
deliberately separate from `GITHUB_TOKEN` (comment/PR operations) and
`GITHUB_WEBHOOK_SECRET` (verifying inbound deliveries): one field per
credential purpose, so "did the infrastructure credential ever reach
somewhere it should not" stays answerable from the field name alone.

### When the resume does not fire

| Outcome | Log event | Detail |
|---|---|---|
| Dispatched | `webhook.dispatch.requested` | The `workflow_dispatch` call succeeded. |
| Skipped — repository not configured | `webhook.dispatch.skipped` (`reason=repository_not_configured`) | The run's persisted `workflow["repository"]` has no `github_owner`/`github_repo`/`base_branch` — ordinary for a `text:`-sourced run. |
| Skipped — no dispatch token | `webhook.dispatch.skipped` (`reason=dispatch_github_token_not_configured`) | This receiver process has no `DISPATCH_GITHUB_TOKEN` configured. |
| Failed | `webhook.dispatch.failed` | The `workflow_dispatch` API call itself raised (a real GitHub error). |

In every one of these cases the human's answer is already durably recorded —
a missing dispatch delays the resume, it never loses the answer. The manual
fallback from any machine, always, is `dark-factory resume <run_id>`.

## Configuration reference

A target repository's behavior is declared in `.dark-factory.yaml` at its
root, read once per run at creation time; the resolved snapshot is what every
resume replays, so editing this file never changes an in-flight run.

```yaml
version: 1

repository:
  base_branch: main

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
`GITHUB_TOKEN`, worker credentials) are environment-only, loaded by
`pydantic-settings` and never written into run config, artifacts, or logs.

## Decisions baked into the schema

A few schema-shaping decisions are worth knowing before reading the
persistence layer:

- **`base_branch` and `working_branch`** are nullable columns on `runs` —
  populated once a run opens its isolated git worktree, left `null` for a
  `text:`-sourced run with no repository context.
- **`qa_developer_iterations` and `quality_gate_iterations`** are non-null,
  zero-default integer columns on `runs`, incremented only through one
  mutation path — never derived by folding `run_events` or counting
  `role_executions` rows.
- **Artifacts are references, not content.** The `artifacts` table holds
  artifact *references* only — `id`, `run_id`, `role_execution_id`, `type`,
  `path`, `checksum`, `metadata`, `created_at` — **never artifact content**.
  Content lives on the filesystem under `.dark-factory/runs/<run-id>/` and
  travels between machines by being committed to a `.dark-factory/` path on
  the run's working branch, excluded from the published diff.

</content>
