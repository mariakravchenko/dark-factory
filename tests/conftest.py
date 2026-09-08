"""Shared test fixtures for Dark Factory.

The single load-bearing decision made here is *how a real PostgreSQL 17 is
reached*. `01-RESEARCH.md` § "Environment Availability" found Docker, `initdb`
and `DATABASE_URL` all absent on the probed machine, so this file does not
assume a backend — it walks a probe ladder and takes the first rung that
works:

    1. testcontainers        -- a responsive Docker daemon (`docker info` == 0)
    2. pytest-postgresql     -- a local PostgreSQL 17 `initdb` on PATH
    3. externally supplied   -- DARK_FACTORY_TEST_DATABASE_URL (throwaway PG 17)
    4. (no rung 4)           -- stop and fail; never degrade to SQLite or a mock

The selected rung is echoed into pytest's session header (`pytest_report_header`)
so a future reader of any test run knows which backend produced it.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

_REPO_ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Provisioning probe ladder
# --------------------------------------------------------------------------- #

_RUNG_LABELS = {
    "testcontainers": "testcontainers (postgres:17-alpine via Docker)",
    "pytest-postgresql": "pytest-postgresql (local initdb 17)",
    "external": "externally supplied Postgres via DARK_FACTORY_TEST_DATABASE_URL",
    "none": "NONE — no reachable PostgreSQL 17",
}

_rung_cache: str | None = None


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _initdb_17_available() -> bool:
    try:
        result = subprocess.run(
            ["initdb", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(re.search(r"\b17(\.\d+)?\b", result.stdout))


def _select_rung() -> str:
    """Return the ladder rung key, memoised for the whole session."""
    global _rung_cache
    if _rung_cache is not None:
        return _rung_cache
    if _docker_available():
        _rung_cache = "testcontainers"
    elif _initdb_17_available():
        _rung_cache = "pytest-postgresql"
    elif os.environ.get("DARK_FACTORY_TEST_DATABASE_URL"):
        _rung_cache = "external"
    else:
        _rung_cache = "none"
    return _rung_cache


def _to_psycopg3_url(url: str) -> str:
    """Normalise any PostgreSQL URL onto the `postgresql+psycopg://` (v3) scheme."""
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def pytest_report_header(config: pytest.Config) -> str:
    """Record which Postgres provisioning rung this run will use."""
    return f"dark-factory test Postgres: {_RUNG_LABELS[_select_rung()]}"


# --------------------------------------------------------------------------- #
# Connection-layer fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def pg_url(request: pytest.FixtureRequest) -> Iterator[str]:
    """A `postgresql+psycopg://` URL for a real PostgreSQL 17, resolved by the ladder."""
    rung = _select_rung()

    if rung == "testcontainers":
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:17-alpine", driver="psycopg") as container:
            yield _to_psycopg3_url(container.get_connection_url())
        return

    if rung == "pytest-postgresql":
        connection = request.getfixturevalue("postgresql")
        params = connection.info
        password = params.password or ""
        yield _to_psycopg3_url(
            f"postgresql://{params.user}:{password}@{params.host}:{params.port}/{params.dbname}"
        )
        return

    if rung == "external":
        raw = os.environ["DARK_FACTORY_TEST_DATABASE_URL"]
        yield _to_psycopg3_url(raw)
        return

    raise pytest.UsageError(
        "No PostgreSQL 17 is reachable: Docker is absent, there is no local "
        "PostgreSQL 17 `initdb`, and DARK_FACTORY_TEST_DATABASE_URL is unset. "
        "The db/integration tiers require a real PostgreSQL 17 — SQLite and "
        "mocks are not acceptable substitutes (see 01-RESEARCH.md)."
    )


@pytest.fixture(scope="session")
def engine(pg_url: str) -> Iterator[Engine]:
    """Session-scoped engine tuned for a short-lived CLI against Neon's PgBouncer pooler."""
    eng = create_engine(
        pg_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
        future=True,
    )
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A per-test Session wrapped in an outer transaction that is always rolled back.

    Uses SQLAlchemy 2.0's native ``join_transaction_mode="create_savepoint"`` —
    the old ``after_transaction_end`` savepoint-restart event recipe is obsolete.
    """
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


# --------------------------------------------------------------------------- #
# Alembic upgrade hook (Plan 04)
# --------------------------------------------------------------------------- #


def _alembic_config(url: str) -> Config:
    """An Alembic ``Config`` pinned to this repo, with the URL injected in
    memory so no connection string is ever written to a file."""
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema_at_head(request: pytest.FixtureRequest) -> Iterator[None]:
    """Bring the provisioned database to ``head`` once before any ``db`` or
    ``integration`` test runs, so a fresh checkout produces a green suite with
    no manual migration step.

    Skipped entirely when the collected session contains no ``db`` /
    ``integration`` test — a ``pytest -m unit`` run never touches PostgreSQL and
    must not force the provisioning ladder to resolve.
    """
    wants_database = any(
        item.get_closest_marker("db") or item.get_closest_marker("integration")
        for item in request.session.items
    )
    if not wants_database:
        yield
        return

    from alembic import command

    url = request.getfixturevalue("pg_url")
    command.upgrade(_alembic_config(url), "head")
    yield


# --------------------------------------------------------------------------- #
# Extension points — filled in by later plans, declared here so their shape is
# visible from the start. Do NOT wire these up before their plan.
# --------------------------------------------------------------------------- #
#
# Plan 03 — settings override fixture:
#   A fixture yielding a `Settings` instance built from fake-shaped secrets
#   (SecretStr placeholders) so redaction has known literal values to scrub
#   without any real credential entering the test process.
#
# Plan 03 — real-sink structlog capture fixture:
#   A fixture that attaches the *production* structlog processor chain to a
#   StringIO / temp-file sink (NOT structlog.testing.capture_logs) so the
#   SC5 redaction assertion runs against a real sink.
#
# Plan 05 — FakeWorker factory:
#   A fixture returning a builder for `FakeWorker` seeded with a scripted list
#   of `WorkerResult`s, plus polyfactory model factories for `WorkerResult` /
#   `NormalizedTask` / ORM rows.
