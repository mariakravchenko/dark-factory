"""The ``runs.published_commit_sha`` / ``human_interactions.clarification_comment_id``
/ ``human_interactions.github_comment_id`` schema proof (Phase 10, plan 10-06,
migration ``0006``), asserted against the **live** PostgreSQL database --
reflection via ``inspect(engine)`` and real INSERT/UPDATE statements in their
own short transactions -- not against ORM metadata, exactly as
``tests/db/test_role_executions_wip_commit_sha_schema.py`` proves the ``0005``
shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, inspect

from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.persistence.models import HumanInteraction, RoleExecution, Run

pytestmark = pytest.mark.db

# The GIT-04 64-bit precision edge: 2^52, comfortably above the 32-bit
# ceiling (2^31 - 1) an ``sa.Integer`` column would have silently
# overflowed/truncated.
_LARGE_COMMENT_ID = 4503599627370496


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
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


def _seed_role_execution(engine: Engine, run_id: uuid.UUID) -> uuid.UUID:
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
    return role_execution_id


# --------------------------------------------------------------------------- #
# runs.published_commit_sha
# --------------------------------------------------------------------------- #


def test_published_commit_sha_column_exists_is_nullable_and_is_a_string_type(
    engine: Engine,
) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("runs")}
    assert "published_commit_sha" in cols
    assert cols["published_commit_sha"]["nullable"] is True
    assert isinstance(cols["published_commit_sha"]["type"], sa.String)


def test_inserting_a_run_without_published_commit_sha_yields_null(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(Run.published_commit_sha).where(Run.id == run_id)
        ).scalar_one()
    assert value is None


def test_inserting_a_forty_char_sha_round_trips_byte_for_byte(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    sha = "c" * 40
    with engine.begin() as conn:
        conn.execute(
            sa.update(Run).where(Run.id == run_id).values(published_commit_sha=sha)
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(Run.published_commit_sha).where(Run.id == run_id)
        ).scalar_one()
    assert value == sha


def test_updating_published_commit_sha_from_null_to_a_sha_and_back_to_null_both_work(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    sha = "d" * 40
    with engine.begin() as conn:
        conn.execute(
            sa.update(Run).where(Run.id == run_id).values(published_commit_sha=sha)
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(Run.published_commit_sha).where(Run.id == run_id)
        ).scalar_one()
    assert value == sha

    with engine.begin() as conn:
        conn.execute(
            sa.update(Run).where(Run.id == run_id).values(published_commit_sha=None)
        )
    with engine.begin() as conn:
        value = conn.execute(
            sa.select(Run.published_commit_sha).where(Run.id == run_id)
        ).scalar_one()
    assert value is None


# --------------------------------------------------------------------------- #
# human_interactions.clarification_comment_id / github_comment_id
# --------------------------------------------------------------------------- #


def test_comment_id_columns_exist_are_nullable_and_are_biginteger_type(
    engine: Engine,
) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("human_interactions")}
    for name in ("clarification_comment_id", "github_comment_id"):
        assert name in cols
        assert cols[name]["nullable"] is True
        assert isinstance(cols[name]["type"], sa.BigInteger)


def test_inserting_without_comment_ids_yields_null_for_both(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id = _seed_run(engine, cleanup_runs)
    role_execution_id = _seed_role_execution(engine, run_id)
    interaction_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(HumanInteraction).values(
                id=interaction_id,
                run_id=run_id,
                role_execution_id=role_execution_id,
                question="what should the endpoint be named?",
                status=InteractionStatus.WAITING,
            )
        )
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(
                HumanInteraction.clarification_comment_id,
                HumanInteraction.github_comment_id,
            ).where(HumanInteraction.id == interaction_id)
        ).one()
    assert row.clarification_comment_id is None
    assert row.github_comment_id is None


def test_a_64_bit_comment_id_round_trips_through_both_columns_as_the_exact_integer(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    """GIT-04 precision edge, made mechanical: 2^52 is well above the 32-bit
    ceiling an ``sa.Integer`` column would silently truncate/overflow."""
    run_id = _seed_run(engine, cleanup_runs)
    role_execution_id = _seed_role_execution(engine, run_id)
    interaction_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(HumanInteraction).values(
                id=interaction_id,
                run_id=run_id,
                role_execution_id=role_execution_id,
                question="what should the endpoint be named?",
                status=InteractionStatus.WAITING,
                clarification_comment_id=_LARGE_COMMENT_ID,
            )
        )
        conn.execute(
            sa.update(HumanInteraction)
            .where(HumanInteraction.id == interaction_id)
            .values(
                answer="call it /health",
                status=InteractionStatus.ANSWERED,
                github_comment_id=_LARGE_COMMENT_ID,
            )
        )
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(
                HumanInteraction.clarification_comment_id,
                HumanInteraction.github_comment_id,
            ).where(HumanInteraction.id == interaction_id)
        ).one()
    assert row.clarification_comment_id == _LARGE_COMMENT_ID
    assert isinstance(row.clarification_comment_id, int)
    assert row.github_comment_id == _LARGE_COMMENT_ID
    assert isinstance(row.github_comment_id, int)
