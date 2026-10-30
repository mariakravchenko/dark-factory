<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide walks through running Dark Factory against **your own repository** —
not a checkout of Dark Factory itself. It consolidates the install, scaffold,
configure, migrate, and first-run steps into one path. For the full
`.dark-factory.yaml` / role-YAML schema reference, see
[docs/CONFIGURATION.md](CONFIGURATION.md). For how the pipeline and persistence
layer fit together, see [docs/ARCHITECTURE.md](ARCHITECTURE.md). For the CLI's
full command surface, pause/resume semantics, and exit-code contract, see the
main [README.md](../README.md).

## Prerequisites

- **Python 3.12** (`requires-python = ">=3.12"`).
- **[uv](https://docs.astral.sh/uv/)** — or an equivalent `pip`-based
  toolchain for your own repository.
- **A Neon project running PostgreSQL 17**, with a database Dark Factory will
  own. Create it at Neon Console → New Project → select Postgres 17. <!-- VERIFY: exact Neon Console navigation for project/database creation is a provider-console workflow that cannot be verified from this repository alone. -->
- **A GitHub repository** you intend to run Dark Factory against (this is
  the "target repository" referred to throughout this guide — it is a
  separate repository from Dark Factory's own).
- Whichever **worker runtime CLI** your roles will use — `claude`, `copilot`,
  and/or `hermes` binaries on `PATH`, plus that runtime's own credential (see
  the variable table in Step 3). The `fake` worker needs neither, and is the
  fastest way to prove the pipeline end-to-end with zero agent credentials.

## Step 1 — Get the `dark-factory` CLI

`dark-factory` is not yet published to PyPI, so the install source for now is
this repository's own git history rather than a package index — switch to
`pip install dark-factory` / `uv add dark-factory` once it ships.

Two of the steps below (scaffolding and applying the database schema) read
files — `scripts/scaffold_target_repo.py`, `.dark-factory/instructions/`,
`alembic.ini`, `migrations/` — that are **not** bundled into the installable
package (`[tool.hatch.build.targets.wheel] packages = ["src/dark_factory"]`
in `pyproject.toml` ships only the `dark_factory` Python package). Those two
steps always need a **checkout** of this repository, regardless of how your
target repository eventually installs `dark-factory` for day-to-day
`run`/`resume` calls. The simplest path covers both needs with one install:

```bash
# Clone a checkout of Dark Factory itself. This is where you'll run the
# scaffold script and the schema migration below.
git clone https://github.com/<your-org>/dark-factory.git
cd dark-factory
uv sync --all-extras --dev
```

`uv run dark-factory --help` now works from this checkout. Your target
repository separately declares `dark-factory` as its own dependency (for
example, in a GitHub Actions job that runs `dark-factory resume`) with:

```bash
# Inside your target repository's own toolchain:
uv add "dark-factory @ git+https://github.com/<your-org>/dark-factory.git"
# or, for a pip-based project:
pip install "dark-factory @ git+https://github.com/<your-org>/dark-factory.git"
```

## Step 2 — Scaffold your target repository's config

`scripts/scaffold_target_repo.py` is a standalone developer tool — it is
**not** a `dark-factory` subcommand and is **not** installed by `pip install
dark-factory` — so it is run from the Dark Factory checkout above, pointed
at your target repository's directory. It writes thirteen files into the
target: `.dark-factory.yaml`, the four role YAMLs under
`.dark-factory/roles/`, the four instruction Markdown files under
`.dark-factory/instructions/` (copied from this repository's own
instructions, with a generated write-scope section appended), `.env.example`,
`.github/workflows/resume.yml`, `.github/workflows/run.yml`, and
`.gitignore`.

```bash
# From the dark-factory checkout, pointed at your target repository:
uv run python scripts/scaffold_target_repo.py \
  --target /path/to/your-repo \
  --github-owner your-org \
  --github-repo your-repo
```

Useful flags (all from `scripts/scaffold_target_repo.py`'s own `argparse`
definition):

| Flag | Default | Purpose |
|------|---------|---------|
| `--target` | — (required) | Target repository root directory. |
| `--github-owner` / `--github-repo` | — (prompted interactively if omitted and stdin is a TTY; required otherwise) | Written into `.dark-factory.yaml`'s `repository.github_owner` / `github_repo`. |
| `--base-branch` | `main` | Written into `repository.base_branch`. |
| `--worker` | `claude-code` | Default worker for all four roles. Legal values: `claude-code`, `copilot`, `hermes`. |
| `--worker-ba`, `--worker-architecture`, `--worker-development`, `--worker-qa` | unset (falls back to `--worker`) | Per-role worker override. |
| `--quality-gate-command` | this repo's own `uv run pytest -q` / `uv run ruff check .` pair | Repeatable; one `quality_gate.commands` entry per use. |
| `--install-source` | `dark-factory` | The `pip install "<value>"` target baked into the generated `resume.yml` / `run.yml` workflows. Pass the git-source string from Step 1 here until the package is published. |
| `--force` | off | Overwrite existing files instead of skipping them. |
| `--yes` | off | Suppress interactive prompting; requires `--github-owner`/`--github-repo` to already be set. |

A realistic invocation that assigns a different worker to one role, picks a
custom quality-gate command, and points the generated workflows at a git
install source:

```bash
uv run python scripts/scaffold_target_repo.py \
  --target /path/to/your-repo \
  --github-owner your-org \
  --github-repo your-repo \
  --worker-architecture copilot \
  --quality-gate-command "make test" \
  --install-source "dark-factory @ git+https://github.com/<your-org>/dark-factory.git"
```

An existing file in the target is left untouched unless you pass `--force`
(the script prints `skipped (exists): <path>` for each one, plus which
`.gitignore` template entries an existing `.gitignore` is missing). See
[docs/CONFIGURATION.md](CONFIGURATION.md) for the full schema of the
`.dark-factory.yaml` and role-YAML files this step writes.

## Step 3 — Fill in `.env`

Copy the generated `.env.example` to `.env` inside your target repository and
fill in real values. `.env` is git-ignored by the generated `.gitignore`;
`.env.example` documents variable names only.

```bash
cd /path/to/your-repo
cp .env.example .env
```

Every variable `Settings` (`src/dark_factory/config/settings.py`) loads,
including the two worker credentials the scaffolded `.env.example` lists only
when a role is actually assigned that worker:

| Variable | Required | Default | What it's for | Where to get it |
|----------|----------|---------|----------------|------------------|
| `DATABASE_URL` | Required | — | The **pooled** Neon connection string (host contains `-pooler`), used by the application engine at runtime. Rewrite the scheme to `postgresql+psycopg://`. | Neon Console → your project → Connection Details → pooled connection string. |
| `DATABASE_URL_DIRECT` | Required | — | The **direct** (non-pooled) Neon connection string (host without `-pooler`). Alembic uses this one — DDL and PgBouncer transaction pooling do not mix. | Neon Console → Connection Details → disable connection pooling to reveal the direct host. |
| `GITHUB_TOKEN` | Optional | `None` | Dark Factory's own credential for posting clarification comments and opening pull requests. Required once a run's source is a GitHub issue or its pipeline publishes. | GitHub: a classic PAT with `repo` scope, or a fine-grained PAT scoped to this repository with Contents (read/write), Issues (read/write), and Pull requests (read/write) permissions. |
| `DISPATCH_GITHUB_TOKEN` | Optional | `None` | A separate, dispatch-only token the webhook receiver uses to trigger `resume.yml` via `workflow_dispatch` after a human's answer is recorded. Not needed for purely local runs. | GitHub: a fine-grained PAT scoped to this one target repository, with the `Actions: Read and write` permission only — no equivalent checkbox exists on the classic-token screen. |
| `GITHUB_WEBHOOK_SECRET` | Optional | `None` | Verifies inbound GitHub webhook deliveries at the webhook receiver before anything is parsed. Only needed for the optional webhook auto-resume path (Step 7). | A shared secret you choose yourself, then set identically on the repository's webhook (Settings → Webhooks → your webhook → Secret). |
| `ANTHROPIC_API_KEY` | Required only if a role uses `claude-code` or `hermes` | `None` | Credential for the `claude-code` worker adapter (and shared by `hermes`, which has no dedicated credential of its own). Its absence only surfaces as a typed `MissingWorkerCredentialError` when a role actually tries to invoke one of those workers. | Anthropic Console — an API key for the account that will run these roles. <!-- VERIFY: exact Anthropic Console URL/navigation for API key creation is an external-service workflow that cannot be verified from this repository alone. --> |
| `COPILOT_GITHUB_TOKEN` | Required only if a role uses `copilot` | `None` | A worker's own authentication material for the `copilot` adapter, injected into the `copilot` subprocess only — never Dark Factory's own `GITHUB_TOKEN`. | GitHub: a fine-grained, **personal-account-owned** PAT carrying the `Copilot Requests` permission. A classic PAT (`ghp_*`) is rejected by the Copilot CLI. |
| `LOG_LEVEL` | Optional | `INFO` | structlog output level. One of `CRITICAL`, `FATAL`, `ERROR`, `WARN`, `WARNING`, `INFO`, `DEBUG`, `NOTSET` (case-insensitive). An unrecognized value fails settings loading at startup. | Set it yourself; not fetched from anywhere. |
| `LEASE_TTL_SECONDS` | Optional, **not a secret** | `900` | Seconds a claimed run stays owned without a renewal before another process may pick it up after a crash. | Set it yourself; the default is the genuine production value. |
| `LEASE_HEARTBEAT_SECONDS` | Optional, **not a secret** | `300` | How often the owning process renews its lease while a step runs. Must be strictly less than `LEASE_TTL_SECONDS`, or settings loading fails at startup. | Set it yourself; one third of the TTL is the standard ratio. |
| `COPILOT_MODEL` | Optional | `None` | Model identifier passed to the `copilot` CLI. Unset uses the CLI's own default model. | Set it yourself if you want to pin a model. |
| `CLAUDE_MODEL` | Optional | `None` | Model identifier appended as `--model <value>` to every `claude` CLI invocation. Unset uses the CLI's own default model. | Set it yourself if you want to pin a model. |
| `WORKER_TIMEOUT_SECONDS` | Optional | `1800` | The single knob governing every worker subprocess call's timeout, in seconds. | Set it yourself; the default (30 minutes) is a deliberately generous estimate. |

See [docs/CONFIGURATION.md](CONFIGURATION.md) for the full `Settings`
validation rules (what fails process startup vs. what only surfaces later)
and the separate `.dark-factory.yaml` / role-YAML configuration surface.

## Step 4 — Apply the Neon database schema

Alembic's config (`alembic.ini`) and migration scripts (`migrations/`) live
at this repository's root and, like the scaffold script, are **not** part of
the installed `dark_factory` package — so this step also runs from the Dark
Factory checkout from Step 1, not from your target repository. Point its
`.env` at the **same** Neon database your target repository's `.env` and CI
secrets will use:

```bash
# From the dark-factory checkout:
cd dark-factory
cp .env.example .env   # if you haven't already; fill in DATABASE_URL_DIRECT
uv run alembic upgrade head
```

This is a one-time setup step against a given database, not something every
repository that runs `dark-factory` needs to repeat — the schema belongs to
the database `DATABASE_URL` / `DATABASE_URL_DIRECT` point at, not to any one
checkout.

## Step 5 — Run a first task and inspect it

From your target repository (with `dark-factory` installed per Step 1, its
`.dark-factory.yaml` / role YAMLs from Step 2, and `.env` filled in from
Step 3):

```bash
cd /path/to/your-repo
dark-factory run text:"add a health endpoint"
```

`run` prints the run id on its own first line, then one line per state
transition, then a summary block:

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

The default scaffold assigns `claude-code` to every role (`--worker
claude-code`), so this real run needs the `claude` binary on `PATH` and
`ANTHROPIC_API_KEY` set. For a zero-credential smoke test instead, change
one or more role YAMLs' `worker:` to `fake` and drive a scripted result with
the `DARK_FACTORY_FAKE_SCRIPT` environment variable (see README.md's "Pause
a run for a human" section for a worked example) — the pipeline, persistence,
and CLI behavior are identical either way.

Inspect any run by id, from any machine that can reach the same database:

```bash
dark-factory status 54e1153f-4cb5-4e2f-92a8-dea95ba06846
# or, for scripting:
dark-factory status 54e1153f-4cb5-4e2f-92a8-dea95ba06846 --json
```

`status` reports state, role history, artifacts, interactions, quality-gate
results, PR info, and transition history. `dark-factory runs` lists every run
if you don't already have an id; `dark-factory events <run-id>` prints the
full audit trail. See README.md's "The CLI surface" section for the complete
command reference, and its "Exit codes" table for how to interpret `run` /
`resume` from a wrapper script.

## Step 6 (optional) — Wire up the GitHub Actions workflows

The scaffold step already wrote two workflows into your target repository:
`.github/workflows/run.yml` (manual `workflow_dispatch`, takes a `source`
input and calls `dark-factory run`) and `.github/workflows/resume.yml`
(manual `workflow_dispatch`, takes a `run_id` input and calls `dark-factory
resume`). To use either from GitHub's Actions tab:

1. Commit and push the files Step 2 generated (`.dark-factory.yaml`, the role
   YAMLs, the instruction Markdown, `.env.example`, both workflow files, and
   `.gitignore`) — never commit `.env` itself.
2. In your target repository's GitHub settings, add the Actions secrets each
   generated workflow's `env:` block references: `DATABASE_URL`,
   `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`, and whichever worker credential
   your assigned workers need (`ANTHROPIC_API_KEY` and/or
   `COPILOT_GITHUB_TOKEN`, per the table in Step 3).
3. Each generated workflow has a commented-out "Install the worker runtime"
   step — uncomment it and fill in that runtime's own install command (e.g.
   for the `claude` binary), since Dark Factory neither ships nor verifies
   that install.
4. From the Actions tab, run `run` with a `source` value (`text:"..."`,
   `spec:<path>`, or `github:<owner>/<repo>#<n>`), or run `resume` with an
   existing run id.

Both workflows carry the same `contents: write` / `issues: write` /
`pull-requests: write` permissions block and `fetch-depth: 0` checkout —
README.md's "Finish a run in CI" section explains exactly why each of those
is load-bearing, including two real failure modes hit while proving this
path end-to-end.

## Step 7 (optional) — GitHub issue intake and webhook auto-resume

A run can also start from a GitHub issue (`dark-factory run
github:<owner>/<repo>#<n>`) and, when it pauses for a human, be resumed
automatically on a different machine once that human replies on the issue —
a webhook receiver records the answer and dispatches `resume.yml` for you,
using the `DISPATCH_GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET` from the table
in Step 3. This requires hosting the separate webhook receiver process
(installed via the `webhook` extra: `starlette` + `uvicorn`) and is covered
in full — including the webhook route, the dispatch credential's exact
scope, and the table of skip/fail outcomes when a dispatch doesn't fire — in
README.md's **"Finish a run in CI"** section. The manual fallback from any
machine, always, is `dark-factory resume <run_id>`.

## Common setup issues

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
  it for you.
- **A role fails with `MissingWorkerCredentialError`.** The credential
  environment variable for that role's assigned worker
  (`ANTHROPIC_API_KEY` for `claude-code`/`hermes`, `COPILOT_GITHUB_TOKEN` for
  `copilot`) isn't set in `.env`. This only surfaces when a role actually
  tries to invoke that worker, not at process startup.
- **The scaffold script exits with "instruction source file not found."**
  It copies instruction Markdown from *this repository's own*
  `.dark-factory/instructions/` directory, so it must be run from a Dark
  Factory checkout — not from an installed package, and not from your
  target repository.
- **`alembic upgrade head` or the scaffold script "can't find" the right
  files when run from your target repository.** Both commands belong to the
  Dark Factory checkout from Step 1, not your target repository — see the
  callout in Step 1 for why.

## Next steps

- [README.md](../README.md) — the full CLI surface, the pause/resume model,
  exit codes, the local-to-CI handoff, and the decisions baked into the
  schema.
- [docs/CONFIGURATION.md](CONFIGURATION.md) — the complete
  `.dark-factory.yaml` and role-YAML schema reference, plus every `Settings`
  field's validation rules.
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — how the pipeline, the durable
  state machine, and worker adapters fit together.
</content>
