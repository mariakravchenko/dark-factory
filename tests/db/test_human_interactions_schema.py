"""STATE-04 schema proof for ``human_interactions``, asserted against the **live**
PostgreSQL database (reflection + real INSERTs), not against ORM metadata.

Revision ``0003`` shape: the eight declared columns and their nullability, the
three-value ``interaction_status`` CHECK enforced by PostgreSQL (not the ORM),
the partial unique index that makes "at most one open question per run" a
database invariant, and both foreign keys. The two ``runs`` lease columns are
checked here for presence and nullability only.

Every deliberate violation runs in its own short transaction so it cannot poison
the rest of the test, and every fixture row is cleaned up (the ``cleanup_runs``
idiom from ``tests/db/test_transition_atomic.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

from dark_factory.domain.status import RunStatus
from dark_factory.persistence.models import Base, HumanInteraction, RoleExecution, Run

pytestmark = pytest.mark.db

_OWNED_TABLES = ["human_interactions", "role_executions", "run_events", "runs"]
_INTERACTION_COLUMNS = {
    "id",
    "run_id",
    "role_execution_id",
    "question",
    "answer",
    "status",
    "created_at",
    "answered_at",
}


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


def _seed_run_and_exec(
    engine: Engine,
    cleanup_runs: list[Any],
    *,
    status: RunStatus = RunStatus.BA,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert one ``runs`` row and one ``role_executions`` row; return their ids."""
    run_id = uuid.uuid4()
    role_execution_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(Run).values(
                id=run_id,
                source_kind="text",
                normalized_task={},
                workflow={"roles": ["BA"]},
                status=status,
            )
        )
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
    cleanup_runs.append(run_id)
    return run_id, role_execution_id


_INSERT_INTERACTION = sa.text(
    "INSERT INTO human_interactions"
    " (id, run_id, role_execution_id, question, answer, status, created_at)"
    " VALUES (gen_random_uuid(), :run_id, :role_execution_id, 'q', :answer,"
    " :status, now())"
)


# --------------------------------------------------------------------------- #
# human_interactions shape (STATE-04)
# --------------------------------------------------------------------------- #


def test_metadata_owns_exactly_the_four_tables() -> None:
    assert sorted(Base.metadata.tables) == _OWNED_TABLES


def test_human_interactions_has_the_eight_declared_columns_with_expected_nullability(
    engine: Engine,
) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("human_interactions")}
    assert set(cols) == _INTERACTION_COLUMNS
    for name in ("question", "status", "run_id", "role_execution_id", "created_at"):
        assert cols[name]["nullable"] is False, name
    for name in ("answer", "answered_at"):
        assert cols[name]["nullable"] is True, name


def test_runs_has_the_two_nullable_lease_columns(engine: Engine) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("runs")}
    assert "owner_token" in cols
    assert "lock_expires_at" in cols
    assert cols["owner_token"]["nullable"] is True
    assert cols["lock_expires_at"]["nullable"] is True


def test_status_accepts_each_of_the_three_declared_values(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    for status in ("WAITING", "ANSWERED", "CANCELLED"):
        run_id, role_execution_id = _seed_run_and_exec(engine, cleanup_runs)
        with engine.begin() as conn:
            conn.execute(
                _INSERT_INTERACTION,
                {
                    "run_id": run_id,
                    "role_execution_id": role_execution_id,
                    "answer": None,
                    "status": status,
                },
            )


def test_status_rejects_a_fourth_undeclared_value_at_the_database(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, role_execution_id = _seed_run_and_exec(engine, cleanup_runs)
    # A fourth value that fits the VARCHAR(16) width, so the rejection can only
    # come from the CHECK constraint, not from string truncation.
    with pytest.raises(IntegrityError) as excinfo, engine.begin() as conn:
        conn.execute(
            _INSERT_INTERACTION,
            {
                "run_id": run_id,
                "role_execution_id": role_execution_id,
                "answer": None,
                "status": "PENDING",
            },
        )
    assert "interaction_status" in str(excinfo.value)


def test_partial_unique_index_rejects_a_second_waiting_but_allows_a_second_answered(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, role_execution_id = _seed_run_and_exec(engine, cleanup_runs)
    params = {
        "run_id": run_id,
        "role_execution_id": role_execution_id,
        "answer": None,
        "status": "WAITING",
    }
    with engine.begin() as conn:
        conn.execute(_INSERT_INTERACTION, params)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(_INSERT_INTERACTION, params)

    # A second row for the same run that is not WAITING is outside the partial
    # index and must be accepted — the index is genuinely partial.
    with engine.begin() as conn:
        conn.execute(
            _INSERT_INTERACTION,
            {**params, "status": "ANSWERED", "answer": "an answer"},
        )


def test_a_nonexistent_run_id_is_rejected_by_the_foreign_key(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            _INSERT_INTERACTION,
            {
                "run_id": uuid.uuid4(),
                "role_execution_id": uuid.uuid4(),
                "answer": None,
                "status": "WAITING",
            },
        )
