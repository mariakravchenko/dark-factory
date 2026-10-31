<!-- generated-by: gsd-doc-writer -->
# Configuration

Dark Factory has two distinct configuration surfaces, and the project is
deliberate about keeping them separate:

1. **Infrastructure settings** (`.env` / environment variables, loaded by
   `Settings` in `src/dark_factory/config/settings.py`) — credentials and
   process-level knobs. These never reach a worker subprocess except through
   an explicit per-worker allowlist, and the resolved `Settings` object is the
   single source of truth `redact()` uses to scrub secret values from logs,
   events, and artifacts.
2. **Repo behaviour config** (`.dark-factory.yaml` + `.dark-factory/roles/*.yaml`,
   loaded by `load_effective_config()` in `src/dark_factory/config/loader.py`)
   — the ordered role pipeline, each role's worker/tools/permissions, the
   quality-gate commands, retry limits, and publishing policy. This is
   repo-controlled, validated with `extra="forbid"` Pydantic models, and
   resolved into one JSON-serialisable **effective-config snapshot** at
   `start_run` time. Editing these files after a run has started never
   changes that run — every resume replays the snapshot taken when the run
   was created, never a live re-read of the files.

## Environment Variables

Copy `.env.example` to `.env` and fill in real values. `.env` is git-ignored
(see `.gitignore`); `.env.example` documents variable **names** only, with
every value a visibly-fake placeholder.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Required | — | The **pooled** Neon connection string (host contains `-pooler`), scheme `postgresql+psycopg://`. Used by the application engine at runtime. |
| `DATABASE_URL_DIRECT` | Required | — | The **direct** (non-pooled) Neon connection string. Used only by Alembic — DDL and PgBouncer transaction pooling do not mix. |
| `LOG_LEVEL` | Optional | `INFO` | structlog output level. One of `CRITICAL`, `FATAL`, `ERROR`, `WARN`, `WARNING`, `INFO`, `DEBUG`, `NOTSET` (case-insensitive; normalized to upper case). An unrecognized value fails settings loading at startup. |
| `LEASE_TTL_SECONDS` | Optional | `900` | Seconds a claimed run stays owned without a renewal (single-owner execution). Not a secret — this is the genuine production default. Must be strictly positive. |
| `LEASE_HEARTBEAT_SECONDS` | Optional | `300` | Seconds between the owning process's lease-expiry renewals while a role step is in flight. Must be strictly **less than** `LEASE_TTL_SECONDS`, or settings loading fails at startup. One third of the TTL is the standard ratio, chosen so two consecutive missed renewals still land inside the TTL. |
| `GITHUB_TOKEN` | Optional | `None` | Dark Factory's own GitHub credential, used for its own comment/PR creation. Loaded even when unused so the redaction layer knows its literal value for exact-substring scrubbing. Never passed to a worker subprocess. |

The following additional settings are declared on `Settings` but are **not**
listed in `.env.example`; set them as plain environment variables (or add
them to `.env`) when the corresponding feature is used.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Optional | `None` | Credential for the `claude-code` worker adapter (and shared by the `hermes` adapter, which has no dedicated credential of its own). Its absence is harmless until a role actually tries to invoke one of those workers, at which point the adapter raises a typed `MissingWorkerCredentialError` rather than spawning anything. |
| `COPILOT_GITHUB_TOKEN` | Optional | `None` | A worker's own authentication material for the `copilot` adapter — injected into the `copilot` subprocess only, never Dark Factory's own GitHub credential. The GitHub Copilot CLI requires a fine-grained, personal-account-owned PAT carrying the `Copilot Requests` permission; a classic PAT (`ghp_*`) is rejected by the CLI. |
| `COPILOT_MODEL` | Optional | `None` | Model identifier passed to the `copilot` CLI. Unset means the CLI's own default model is used. |
| `CLAUDE_MODEL` | Optional | `None` | Model identifier appended as `--model <value>` to every `claude` CLI invocation by the `claude-code` worker. Unset means the CLI's own default model is used. |
| `WORKER_TIMEOUT_SECONDS` | Optional | `1800` | The single knob governing every worker subprocess call's timeout, in seconds. Must be strictly positive. 1800s (30 minutes) is a deliberately generous estimate, not a measured figure. |

<!-- VERIFY: Creating a Neon project and locating the pooled vs. direct connection strings (Neon Console → Connection Details) is a Neon-console workflow that cannot be verified from this repository alone. -->

### Required vs. optional at startup

`Settings` (`src/dark_factory/config/settings.py`) fails process startup
immediately if `DATABASE_URL` or `DATABASE_URL_DIRECT` is missing — both are
declared as plain `SecretStr` with no default. Every other field is either
`SecretStr | None = None` or carries a numeric/string default, so a
`fake`-worker-only pipeline needs no credential beyond the two database URLs.
Two `model_validator` checks run after all fields load and raise `ValueError`
(surfacing as a settings-construction error) if:

- `lease_ttl_seconds` is not strictly positive, or
- `lease_heartbeat_seconds` is not strictly less than `lease_ttl_seconds`.

A third validator rejects a `worker_timeout_seconds` that is not strictly
positive. A fourth (`field_validator` on `log_level`) rejects any value that
is not a recognized Python-logging level name.

### Secret handling

Every `SecretStr`-typed field on `Settings` is walked by
`known_secret_values()` and registered with the redaction layer by its live
value (not by name) — so any credential added to `Settings` in the future is
covered automatically, provided it is declared as `SecretStr`. Values shorter
than 8 characters are skipped (to avoid a trivially short secret turning
redaction into indiscriminate scrubbing). No module may log, echo, format, or
interpolate a `Settings` value directly.

## `.dark-factory.yaml`

The repo-behaviour contract, validated by `RepoConfig`
(`src/dark_factory/config/repo_config.py`) with every model `frozen=True` and
`extra="forbid"` — an unrecognized or invented key fails validation at load
time rather than being silently dropped. Parsed with `yaml.safe_load` only.

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

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `version` | int | `1` | Schema version of the document. |
| `repository.base_branch` | string | `"main"` | The target repo's base branch for new runs. |
| `repository.github_owner` | string \| null | `null` | GitHub owner of the target repository; used for GitHub-sourced intake and publishing. Repos that use neither need no change. |
| `repository.github_repo` | string \| null | `null` | GitHub repository name, paired with `github_owner`. Read from config only — never from a CLI locator — so a crafted locator can never redirect a fetch at another repository. |
| `workflow.roles` | list of strings | — (required, min 1 entry) | The ordered pipeline. Each entry must be one of the role-shaped `RunStatus` values: `BA`, `ARCHITECTURE`, `DEVELOPMENT`, `QA`, `VERIFYING`, `PUBLISHING`. A human label or typo is rejected at load time. |
| `roles_dir` | string | `".dark-factory/roles"` | Directory (relative to the repo root) containing one `<ROLE_NAME>.yaml` file per entry in `workflow.roles`. Resolved and checked against path escape — a `roles_dir` that resolves outside the repo root is rejected. |
| `quality_gate.commands` | list of strings | `[]` | Shell commands run as the independent quality gate after QA passes. Stored in the effective-config snapshot; executed by the orchestrator's quality-gate step. |
| `retry.qa_developer_max_iterations` | int (>= 0) | `3` | Maximum QA → Developer feedback-loop bounces before the run fails. |
| `retry.quality_gate_max_iterations` | int (>= 0) | `2` | Maximum quality-gate → Developer feedback-loop bounces before the run fails. |
| `publishing.create_pr` | bool | `true` | Gates PR creation. Publishing (PR creation) only ever happens after QA PASS *and* independent quality-gate PASS, regardless of this flag's value. |

This file is read once per run, at creation, inside `start_run` — the
resolved effective-config snapshot is persisted on the run row and is what
every resume replays. Editing `.dark-factory.yaml` never changes an
already-created run. No secrets belong in this file; infrastructure
credentials live in `.env` / `Settings` exclusively.

## `.dark-factory/roles/*.yaml`

One file per entry in `workflow.roles`, named `<ROLE_NAME>.yaml` and located
under the directory named by `roles_dir`. Validated by `RoleDefinition`
(`src/dark_factory/config/loader.py`), also `frozen=True` and
`extra="forbid"`.

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
| `worker` | string | — (required) | Must be a name registered on `WorkerRegistry.default_registry` (`src/dark_factory/workers/registry.py`): `fake`, `claude-code`, `copilot`, or `hermes`. Validated by exact-name membership, never dynamic lookup. Reassigning a role to a different worker is a config-only change — the orchestrator never branches on worker identity. |
| `instructions` | string (path) | — (required) | Path to the role's instruction Markdown, resolved relative to the role YAML's own directory, must stay under the repo root (no `..` escape), and is capped at 64 KiB when inlined into the snapshot. |
| `tools` | list of strings | `[]` | Capability names this role may invoke, validated by exact-name membership against `ToolRegistry.default_registry` (`src/dark_factory/tools/registry.py`): `artifacts.read`, `artifacts.write`, `repo.read`, `repo.search`, `repo.write`, `repo.write_tests`, `shell.execute`. A capability not in this list is denied before it runs, regardless of what is registered. |
| `permissions.write_scope` | list of glob patterns | `[]` (zero tolerance) | Filesystem glob patterns (matched with `fnmatch.fnmatchcase`, not `pathlib`) a role's write-capable tool invocations must stay within. **An empty list means zero tolerance, not "unrestricted"** — every path is a violation when the list is empty. Any changed path outside the declared patterns is reverted and fails the role. |
| `before` | list of strings | `[]` | Action names run before the role's worker is invoked, validated against the action registry (`src/dark_factory/actions/builtins.py`): `ensure_clean_worktree` is the only one meant to be role-configurable today — it recovers a dirty worktree onto the current branch; a role YAML that omits it forgoes that recovery. `prepare_role_context` and `store_role_artifacts` are permanent no-ops kept only for backward compatibility with older role YAMLs. |
| `after` | list of strings | `[]` | Action names run after the role's worker returns. `collect_diff` (git-only; writes the PR-bound diff) is listed only on roles that can change repository source (`DEVELOPMENT`, `QA`). `collect_test_results` is a permanent no-op — the quality gate is orchestrator-inline code, not a role-configurable hook. |
| `inputs` | list of strings | `[]` | Artifact filenames this role requires as input, resolved by declared filename (not pipeline adjacency). Config loading / role execution fails if a declared input cannot be resolved. |
| `optional_inputs` | list of strings | `[]` | Artifact filenames resolved leniently — simply omitted from the role's context when absent, never an error. Used for feedback-loop artifacts (`verdict.json`, `quality_gate.json`) that don't exist on a role's first attempt. |
| `outputs` | list of strings | `[]` | Artifact filenames this role is expected to produce. |
| `examples` | list of strings | `[]` | Reserved for future few-shot example references; currently unused by any shipped role. |

### Shipped roles

| Role | Worker | Tools | `write_scope` | Inputs | Outputs |
|------|--------|-------|---------------|--------|---------|
| `BA` | `fake` | `repo.read`, `repo.search`, `artifacts.read`, `artifacts.write` | `[]` (read-only) | — | `requirements.md`, `acceptance_criteria.json` |
| `ARCHITECTURE` | `copilot` | `repo.read`, `repo.search`, `artifacts.read`, `artifacts.write` | `[]` (read-only) | `acceptance_criteria.json` | `design.md`, `constraints.json` |
| `DEVELOPMENT` | `claude-code` | `repo.read`, `repo.search`, `repo.write`, `repo.write_tests`, `shell.execute`, `artifacts.read`, `artifacts.write` | `["src/**"]` | `design.md`, `constraints.json` (optional: `verdict.json`, `quality_gate.json`) | `implementation_summary.json` |
| `QA` | `hermes` | `repo.read`, `repo.search`, `repo.write_tests`, `shell.execute`, `artifacts.read`, `artifacts.write` | `["tests/**"]` | `acceptance_criteria.json`, `implementation_summary.json` | `test_report.json`, `verdict.json` |

`QA` deliberately has no `repo.write` grant — it may write tests, never
production source, which is the "cannot publish" half of its permission
boundary. Instruction Markdown for each role lives alongside the role YAML
under `.dark-factory/instructions/` (`ba.md`, `architecture.md`,
`development.md`, `qa.md`).

## Config file format summary

| File | Format | Location | Purpose |
|------|--------|----------|---------|
| `.env` | dotenv (`KEY=value`) | repo root (git-ignored) | Infrastructure credentials and process knobs, loaded by `pydantic-settings`. |
| `.dark-factory.yaml` | YAML | repo root | Repo-behaviour contract: pipeline, quality gate, retry limits, publishing policy. |
| `.dark-factory/roles/<ROLE>.yaml` | YAML | `roles_dir` (default `.dark-factory/roles`) | One role's worker, tool grants, write scope, hooks, and artifact contract. |
| `.dark-factory/instructions/<role>.md` | Markdown | referenced by each role's `instructions` field | The prompt text handed to that role's worker. |

## Per-environment overrides

`pydantic-settings` loads `.env` from the current working directory by
default (`env_file=".env"` in `SettingsConfigDict`); any variable already
present in the process environment takes precedence over the file. There is
no built-in `.env.development` / `.env.production` convention in this
codebase today — set environment-specific values either in a different
`.env` file per checkout/worktree, or via the deployment platform's own
environment-variable mechanism.

<!-- VERIFY: GitHub Actions secrets configuration (Settings → Secrets and variables → Actions on the GitHub repository) and any production secret-manager setup are platform-console workflows that cannot be verified from this repository alone. -->

The repository's own CI workflow (`.github/workflows/ci.yml`) sets no
`DATABASE_URL`-style secrets at all — it runs the test suite against an
ephemeral `testcontainers` Postgres instance. `README.md` documents a
separate, reference-only `resume.yml` workflow (not committed to this
repository, meant to be copied into a deployment repo) that reads
`DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`, and
`ANTHROPIC_API_KEY` from GitHub Actions secrets to resume a paused run on a
fresh runner.
