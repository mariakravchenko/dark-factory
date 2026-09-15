"""The ``role_executions.wip_commit_sha`` schema proof (Plan 05-02 Task 2),
asserted against the **live** PostgreSQL database -- reflection via
``inspect(engine)`` and real INSERT/UPDATE statements in their own short
transactions -- not against ORM metadata, exactly as
``tests/db/test_human_interactions_schema.py`` proves the ``0003`` shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, inspect

from dark_factory.domain.status import RunStatus
from dark_factory.persistence.models import RoleExecution, Run

pytestmark = pytest.mark.db


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _seed_run(engine: Engine, cleanup_runs: list[Any]) -> uuid.UUID:
    run_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(Run).values(
                id=run_id,
                source_kind="text",
                normalized_task={},
                workflow={"roles": ["BA"]},
                status=RunStatus.BA,
            )
        )
    cleanup_runs.append(run_id)
    return run_id


def test_wip_commit_sha_column_exists_is_nullable_and_is_a_string_type(
    engine: Engine,
) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("role_executions")}
    assert "wip_commit_sha" in cols
    assert cols["wip_commit_sha"]["nullable"] is True
    assert isinstance(cols["wip_commit_sha"]["type"], sa.String)


def test_inserting_without_wip_commit_sha_yields_null(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    role_execution_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(RoleExecution).values(
                id=role_execution_id,
                run_id=run_id,
                role="BA",
                worker="fake",
                status="RUNNING",
                attempt=1,
            )
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(RoleExecution.wip_commit_sha).where(
                RoleExecution.id == role_execution_id
            )
        ).scalar_one()
    assert value is None


def test_inserting_a_forty_char_sha_round_trips_byte_for_byte(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    role_execution_id = uuid.uuid4()
    sha = "a" * 40
    with engine.begin() as conn:
        conn.execute(
            sa.insert(RoleExecution).values(
                id=role_execution_id,
                run_id=run_id,
                role="BA",
                worker="fake",
                status="RUNNING",
                attempt=1,
                wip_commit_sha=sha,
            )
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(RoleExecution.wip_commit_sha).where(
                RoleExecution.id == role_execution_id
            )
        ).scalar_one()
    assert value == sha


def test_updating_from_null_to_a_sha_and_back_to_null_both_work(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    role_execution_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(RoleExecution).values(
                id=role_execution_id,
                run_id=run_id,
                role="BA",
                worker="fake",
                status="RUNNING",
                attempt=1,
            )
        )

    sha = "b" * 40
    with engine.begin() as conn:
        conn.execute(
            sa.update(RoleExecution)
            .where(RoleExecution.id == role_execution_id)
            .values(wip_commit_sha=sha)
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(RoleExecution.wip_commit_sha).where(
                RoleExecution.id == role_execution_id
            )
        ).scalar_one()
    assert value == sha

    with engine.begin() as conn:
        conn.execute(
            sa.update(RoleExecution)
            .where(RoleExecution.id == role_execution_id)
            .values(wip_commit_sha=None)
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(RoleExecution.wip_commit_sha).where(
                RoleExecution.id == role_execution_id
            )
        ).scalar_one()
    assert value is None
