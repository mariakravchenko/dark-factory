<!-- generated-by: gsd-doc-writer -->
# Development

This is the contributor-facing guide to working *on* Dark Factory itself — cloning
the repository, running its own lint/type/test gates, and the conventions its commit
history follows. It is not about using Dark Factory to drive a delivery run against
some other project; for that, see [README.md](../README.md).

## Local setup

Dark Factory is a `src/`-layout Python 3.12 package managed with
[uv](https://docs.astral.sh/uv/). There is no separate "dev install" step beyond
pulling in the optional extras and the dev dependency group.

```bash
# 1. Clone and enter the repository.
git clone <repository-url>
cd dark-factory

# 2. Install the full dependency set: runtime + the mcp extra + dev tools
#    (ruff, mypy, pytest, testcontainers, polyfactory, time-machine).
uv sync --all-extras --dev

# 3. Configuration for a working local run (optional for pure lint/type/unit work).
cp .env.example .env
# then fill in DATABASE_URL / DATABASE_URL_DIRECT as described in
# docs/CONFIGURATION.md and the root README.
```

`uv sync --all-extras --dev` creates/updates the project's `.venv` and installs from
the committed `uv.lock`, so every contributor and CI resolve to the exact same
versions. Prefix every command below with `uv run` (or activate `.venv` yourself) —
there is no global install.

The `mcp` optional-dependency extra is structurally isolated from the orchestrator
core: `tests/unit/test_no_mcp_import_in_core.py` asserts that uninstalling it still
leaves the core importable and functional. `--all-extras` pulls it in for local
development so the full test suite can run, but it is not required to work on the
core orchestrator.

## Build / check commands

There is no compiled build step — `src/dark_factory` is pure Python, packaged with
Hatchling (`[tool.hatch.build.targets.wheel]` in `pyproject.toml`). The commands below
are the full set of quality gates, in the order `.github/workflows/ci.yml` runs them.

| Command | What it does |
|---------|--------------|
| `uv sync --all-extras --dev --frozen` | Install the exact locked dependency set (CI uses `--frozen`; drop it locally to let `uv` update the lock). |
| `uv run ruff check .` | Lint (import order, pyupgrade, bugbear, simplify, Ruff-specific rules — see Code style below). |
| `uv run ruff format --check .` | Verify formatting without rewriting files; drop `--check` to apply formatting. |
| `uv run mypy src/dark_factory` | Strict static type check of the package (not `tests/`). |
| `uv run pytest -m unit` | Fast tier — pure functions, no database, no subprocess. The everyday inner loop. |
| `uv run pytest -m "unit or contract"` | Adds the shared `CodingWorker` contract suite, parametrized across worker adapters. |
| `uv run pytest -m db` | The `FakeWorker` orchestration suite against a real PostgreSQL 17 — see "Running the database tier" below. |
| `uv run pytest -m integration` | End-to-end CLI-as-subprocess suites, including the three live-runtime suites that self-skip when `claude`/`copilot`/`hermes` aren't on `PATH`. |
| `uv run pytest` | Every tier in one run (needs a reachable PostgreSQL). |
| `uv run alembic upgrade head` | Apply migrations — run against `DATABASE_URL_DIRECT`, never the pooled endpoint. |

### Running the database tier locally

`tests/conftest.py` never assumes a backend is present — it walks a probe ladder and
uses the first rung that works, logging which one it picked into pytest's session
header:

1. **testcontainers** — a responsive Docker daemon (`docker info` exits `0`); spins up
   an ephemeral `postgres:17-alpine` container per session.
2. **pytest-postgresql** — a local PostgreSQL 17 `initdb` on `PATH`.
3. **externally supplied** — set `DARK_FACTORY_TEST_DATABASE_URL` to a throwaway
   PostgreSQL 17 instance.
4. Otherwise the `db` and `integration` tiers fail outright — there is no SQLite or
   mock fallback, so a false green is not possible.

Pick whichever rung matches your machine; no extra flags are needed — the fixtures
detect it automatically.

## Code style

- **Ruff** (`ruff.toml` config lives in `pyproject.toml`'s `[tool.ruff]` /
  `[tool.ruff.lint]`) is both the linter and the formatter — there is no separate
  Black/isort/flake8 setup. The enabled rule sets are `I` (import sorting), `UP`
  (pyupgrade), `B` (bugbear), `SIM` (simplify), `RUF` (Ruff-specific). Target version
  is `py312`. `.planning/` and `.claude/` are excluded from formatting/linting — they
  hold planning prose, not project source.
  Run: `uv run ruff check .` and `uv run ruff format --check .` (drop `--check` to
  auto-fix formatting).
- **mypy** runs in `--strict` mode (`[tool.mypy]` in `pyproject.toml`) with the
  `pydantic.mypy` plugin enabled, scoped to `src/dark_factory` (test code is not
  type-checked in CI).
  Run: `uv run mypy src/dark_factory`.
- There is no `.editorconfig` or `.pre-commit-config.yaml` committed to the
  repository — `ruff` and `mypy` are run manually or via CI, not via a pre-commit hook.
- CI enforces all of the above: see `.github/workflows/ci.yml`'s `quality` job, which
  runs lint, types, a dedicated worker-name-leak guard test
  (`tests/unit/test_no_worker_name_leak.py`), then the unit/contract and `db` tiers in
  sequence, failing fast before any container is pulled.

## Branch and commit conventions

No `CONTRIBUTING.md` or branch-naming policy is committed to this repository. In
practice the project's own commit history follows **Conventional Commits** —
`type(scope): subject`, with types observed in the log including `feat`, `fix`,
`docs`, `test`, `chore`, and `ci`. Follow that pattern for new commits
(e.g. `fix(worker-registry): reject unknown worker names`).

Note that branches named `dark-factory/run-<uuid>` you may see in `git branch -a` are
**not** human development branches — they are working branches Dark Factory's own
orchestrator creates per delivery run (see `docs/ARCHITECTURE.md`), unrelated to how a
contributor should branch for a code change against this repository.

## PR process

There is no `.github/PULL_REQUEST_TEMPLATE.md` or `.github/ISSUE_TEMPLATE/` in this
repository, and no separate human-facing review checklist beyond CI itself. In
practice:

- Every push and pull request triggers `.github/workflows/ci.yml`'s `quality` job
  (lint, types, worker-name-leak guard, unit/contract tier, `db` tier) and its
  `integration` job (full CLI-as-subprocess suites), gated to run only after `quality`
  passes.
- A change is mergeable once both CI jobs are green — there is no additional manual
  sign-off step encoded in the repository.
- The `integration` job runs a plain `-m integration` selector rather than a curated
  subset: the three live-runtime suites (`test_claude_code_live.py`,
  `test_copilot_live.py`, `test_hermes_live.py`) self-skip when the corresponding CLI
  binary isn't on the runner's `PATH`, so no credentials need to be provisioned for
  the job to go green.
- `pyproject.toml`'s pytest markers (`unit`, `db`, `integration`, `contract`) are the
  project's test-tier taxonomy; a new test should carry exactly one of them.

## Next steps

- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — component boundaries and the
  `advance(run_id)` state-machine design.
- [docs/CONFIGURATION.md](CONFIGURATION.md) — every environment variable and
  `.dark-factory.yaml` setting.
- [README.md](../README.md) — the full CLI surface, pause/resume model, and the
  local-to-CI handoff.
