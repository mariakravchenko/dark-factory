<!-- generated-by: gsd-doc-writer -->
# Testing

## Test framework and setup

Dark Factory uses **pytest** (`pytest>=9,<10`, currently `9.1.1`) as its sole
test framework — no `unittest`, no secondary runner. Supporting test-only
dependencies, all declared in the `dev` dependency group in `pyproject.toml`:

| Package | Purpose |
|---------|---------|
| `testcontainers[postgres]>=4.15,<5` | Ephemeral `postgres:17-alpine` container for the `db`/`integration` tiers when Docker is available |
| `pytest-postgresql>=9,<10` | Local `initdb`-backed Postgres 17 fallback when Docker is not available |
| `polyfactory>=3,<4` | pydantic-v2-native model factories (`NormalizedTask`, `WorkerResult`) used as test fixtures |
| `time-machine>=3,<4` | Deterministic clock control for lease-expiry and timestamp-dependent tests |
| `ruff>=0.16`, `mypy>=2.3` | Not test frameworks, but run alongside tests in the same CI job |

Install everything with `uv sync --all-extras --dev` (see
[docs/GETTING-STARTED.md](GETTING-STARTED.md)). No further setup step is
required to run the `unit` or `contract` tiers.

The `db` and `integration` tiers require a reachable **real PostgreSQL 17**
instance — this project never substitutes SQLite or a mock for the database.
`tests/conftest.py` resolves which backend to use via a probe ladder, tried
in order, and reports the chosen rung in pytest's session header
(`dark-factory test Postgres: ...`):

1. **testcontainers** — used automatically if `docker info` succeeds (spins
   up `postgres:17-alpine`).
2. **pytest-postgresql** — used if a local PostgreSQL 17 `initdb` is on
   `PATH` and Docker is unavailable.
3. **externally supplied** — set `DARK_FACTORY_TEST_DATABASE_URL` to a
   throwaway PostgreSQL 17 connection string if neither of the above is
   available.
4. If none of the three resolve, the fixture raises `pytest.UsageError`
   rather than silently degrading to a fake backend.

## Running tests

Run the full suite:

```bash
uv run pytest
```

Run a specific marker tier (see "Writing new tests" below for what each
marker means):

```bash
uv run pytest -q -m unit          # fast, no database or I/O
uv run pytest -q -m contract      # shared CodingWorker contract suite
uv run pytest -q -m db            # requires a real PostgreSQL 17
uv run pytest -q -m integration   # end-to-end CLI subprocess suites
```

Combine markers the same way CI does for its fast-fail step:

```bash
uv run pytest -q -m "unit or contract"
```

Run a single file or a single test:

```bash
uv run pytest tests/unit/test_domain_models.py
uv run pytest tests/db/test_four_role_pipeline.py::test_four_roles_complete_in_order
```

There is no configured watch-mode script (`pytest-watch` or similar is not a
dependency) — re-run `uv run pytest` manually, or use your editor's test
runner integration.

## Writing new tests

**File and function naming.** Test files live under `tests/` and are named
`test_*.py`; test functions are named `test_*`. There is no `*.spec.py` or
`*_test.py` variant in this codebase.

**Directory layout mirrors the marker tiers**, not the `src/` module tree:

| Directory | Marker | Contents |
|-----------|--------|----------|
| `tests/unit/` | `pytest.mark.unit` | Pure-function tests, no database, no subprocess |
| `tests/db/` | `pytest.mark.db` | Tests requiring a real PostgreSQL 17 (the `FakeWorker` orchestration suite — role transitions, artifact handoffs, pause/resume, etc.) |
| `tests/integration/` | `pytest.mark.integration` | End-to-end suites that drive the `dark-factory` CLI as a subprocess |
| `tests/contract/` | `pytest.mark.contract` | The shared `CodingWorker` contract suite, parametrized over every worker adapter (`FakeWorker`, `ClaudeCodeWorker`, `CopilotWorker`, `HermesWorker`) |
| `tests/support/` | — | Shared test helpers only (fake CLI generators, fake GitHub client, git repo fixtures) — not itself a collected test tier |

Each test module declares its tier with a module-level `pytestmark`, e.g.:

```python
pytestmark = pytest.mark.unit
```

or, for a `db` test that also needs a shared fixture:

```python
pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]
```

`tests/unit/test_qual01_ci_coverage.py` structurally asserts every module
mapped to the `db` tier actually carries this marker — a module without it
is silently never selected by `-m db` in CI, so always set `pytestmark`
before adding assertions.

**Shared fixtures** live in `tests/conftest.py`. The most commonly reused
ones:

- `engine` / `db_session` — a real PostgreSQL 17 `Engine`/`Session`, provisioned per the probe ladder described above.
- `fake_settings` / `use_fake_secrets` — a `Settings` instance with safe test credentials, so secret-redaction tests have known literal values to assert against.
- `normalized_task_factory` / `worker_result_factory` — `polyfactory` factories for `NormalizedTask` and `WorkerResult`.
- `git_repo_root` / `config_root` / `config_root_factory` — temp git repos and `.dark-factory.yaml`/`roles/*.yaml` trees for config-driven tests.
- `_no_real_agent_binary_spawn` (autouse) — a tripwire that fails any test that attempts to spawn a real `claude`/`copilot`/`hermes` binary, so a test can never accidentally shell out to a live agent.

**Avoid a live AI call in tests.** Never drive a test against the real
`claude`, `copilot`, or `hermes` CLI. Use `dark_factory.workers.fake.FakeWorker`
(a scripted, in-process `CodingWorker` with no external AI call) for
orchestration tests, or the generated fake-CLI scripts in
`tests/support/fake_claude_cli.py` / `fake_copilot_cli.py` / `fake_hermes_cli.py`
for subprocess-level adapter tests. The three real-adapter suites that do
exist — `tests/integration/test_claude_code_live.py`,
`test_copilot_live.py`, `test_hermes_live.py` — are guarded by a module-level
`skipif` from `tests/support/live_runtime.py` that checks for the binary on
`PATH` and its credential in `Settings`, and must stay reported as a named
skip (never excluded from collection) so they start running automatically
the day a real credential and binary are available.

## Coverage requirements

No coverage tool (`pytest-cov`, `coverage.py`, `.nycrc`, `c8`) is configured
in this project, and no `--cov` flag appears in `pyproject.toml` or
`.github/workflows/ci.yml`. There is no enforced minimum coverage threshold.

Instead of a blanket coverage percentage, `QUAL-01` (in
`.planning/REQUIREMENTS.md`) is enforced by a scenario-to-module map asserted
in `tests/unit/test_qual01_ci_coverage.py`: role transitions, artifact
handoffs, pause/resume, QA rejection, Developer retries, quality-gate
retries, failure limits, and publishing must each be traceable to a specific
`tests/db/` module that carries the `db` marker and is actually selected by
a CI step. If you add a new orchestration scenario, extend that map rather
than relying on an aggregate coverage number.

## CI integration

Tests run in `.github/workflows/ci.yml` on every push to any branch and on
every pull request, in two jobs:

**`quality`** (timeout 30 minutes) — runs on every push/PR:
1. `uv run ruff check .` — lint
2. `uv run mypy src/dark_factory` — type check
3. `uv run pytest -q tests/unit/test_no_worker_name_leak.py` — the worker-name leak guard (QUAL-04)
4. `uv run pytest -q -m "unit or contract"` — unit and contract tiers
5. `uv run pytest -q -m db` (timeout 20 minutes) — the database tier, against a `postgres:17-alpine` container provisioned by the hosted runner's Docker daemon

**`integration`** (timeout 60 minutes) — runs after `quality` succeeds
(`needs: quality`):
1. `uv run pytest -q -m integration` — the full integration tier, including the three skip-guarded live-adapter suites, which report as named skips on a runner with no agent-CLI credentials rather than being excluded from the selector.

Both jobs install dependencies with `uv sync --all-extras --dev --frozen`
against Python 3.12.
