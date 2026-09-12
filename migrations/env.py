"""Alembic environment for Dark Factory (Plan 01-04).

Two rules are load-bearing here:

1. **No committed URL.** ``alembic.ini`` leaves ``sqlalchemy.url`` blank. This
   module resolves the connection string at runtime, preferring
   ``DATABASE_URL_DIRECT`` — Neon's **direct, non-pooled** endpoint — because DDL
   through PgBouncer transaction pooling misbehaves. It falls back to
   ``DATABASE_URL`` and then to ``DARK_FACTORY_TEST_DATABASE_URL`` (the test
   path), and raises a clear error if none is set. A caller may also inject the
   URL by pre-setting ``sqlalchemy.url`` on the Alembic config (the test
   conftest does this); an explicitly-set value wins.

2. **``target_metadata = Base.metadata``**, so ``alembic revision --autogenerate``
   and ``alembic check`` compare against the ORM models and the two cannot drift
   apart silently.

Only the five tables Dark Factory owns — ``runs``, ``role_executions``,
``run_events``, ``human_interactions`` and ``artifacts`` — are in scope. The
test database is a shared throwaway instance that may hold unrelated tables;
``include_name`` keeps autogenerate (and ``alembic check``) from proposing to
drop them, and keeps ``human_interactions`` / ``artifacts`` from being proposed
for drop.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from dark_factory.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The tables this project owns. Everything else in the target database is out of
# scope for autogenerate / `alembic check`.
_OWNED_TABLES = {
    "runs",
    "role_executions",
    "run_events",
    "human_interactions",
    "artifacts",
}

_PSYCOPG_SCHEME = "postgresql+psycopg://"
_LEGACY_SCHEMES = ("postgresql+psycopg2://", "postgresql://", "postgres://")

# Resolution order for the DDL connection string. DATABASE_URL_DIRECT first: DDL
# must not travel through Neon's -pooler host.
_URL_ENV_VARS = (
    "DATABASE_URL_DIRECT",
    "DATABASE_URL",
    "DARK_FACTORY_TEST_DATABASE_URL",
)


def _normalise_scheme(url: str) -> str:
    for legacy in _LEGACY_SCHEMES:
        if url.startswith(legacy):
            return _PSYCOPG_SCHEME + url[len(legacy) :]
    return url


def _resolve_url() -> str:
    injected = config.get_main_option("sqlalchemy.url")
    if injected:
        return _normalise_scheme(injected)
    for name in _URL_ENV_VARS:
        raw = os.environ.get(name)
        if raw:
            return _normalise_scheme(raw)
    raise RuntimeError(
        "Alembic has no database URL. Set the direct (non-pooled) endpoint as "
        + _URL_ENV_VARS[0]
        + " for DDL, or "
        + ", ".join(_URL_ENV_VARS[1:])
        + " as a fallback. Never point Alembic at a -pooler host."
    )


def _include_name(name: str | None, type_: str, parent_names: dict[str, str]) -> bool:
    if type_ == "table":
        return name in _OWNED_TABLES
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        _resolve_url(),
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
