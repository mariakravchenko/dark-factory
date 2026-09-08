"""Migration 0001 against a real PostgreSQL: table set, reversibility, no drift.

These assertions are the blocking gate for the rest of Phase 1 — no ``db`` or
``integration`` test in Plans 05-09 can run against an unmigrated database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import NullPool

from tests.conftest import _alembic_config

pytestmark = pytest.mark.db

EXPECTED_TABLES = {"runs", "role_executions", "run_events"}
FORBIDDEN_TABLES = {"human_interactions", "artifacts"}


@pytest.fixture
def direct_engine(pg_url: str) -> Engine:
    engine = create_engine(
        pg_url, poolclass=NullPool, connect_args={"prepare_threshold": None}
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_upgrade_head_creates_exactly_the_three_phase_one_tables(
    direct_engine: Engine,
) -> None:
    names = _table_names(direct_engine)
    assert names >= EXPECTED_TABLES
    assert not (FORBIDDEN_TABLES & names), (
        "Phase 1 must not create human_interactions (Phase 2) or artifacts (Phase 4)"
    )


def test_migration_round_trips_through_downgrade_and_back(
    pg_url: str, direct_engine: Engine
) -> None:
    from alembic import command

    cfg = _alembic_config(pg_url)

    command.downgrade(cfg, "base")
    after_downgrade = _table_names(direct_engine)
    assert not (EXPECTED_TABLES & after_downgrade), (
        "downgrade base must drop all three tables"
    )

    command.upgrade(cfg, "head")
    after_upgrade = _table_names(direct_engine)
    assert after_upgrade >= EXPECTED_TABLES


def test_alembic_check_reports_no_drift_between_orm_and_schema(pg_url: str) -> None:
    from alembic import command
    from alembic.util.exc import CommandError

    cfg = _alembic_config(pg_url)
    try:
        command.check(cfg)
    except CommandError as exc:  # pragma: no cover - only on real drift
        pytest.fail(f"alembic check detected ORM/schema drift: {exc}")


def test_run_events_has_the_composite_run_id_seq_index(direct_engine: Engine) -> None:
    indexes = inspect(direct_engine).get_indexes("run_events")
    composite = {tuple(ix["column_names"]) for ix in indexes}
    assert ("run_id", "seq") in composite
