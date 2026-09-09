"""STATE-04 / HITL-07 / HITL-08 schema proof, asserted against the **live**
PostgreSQL database (reflection + real INSERTs and conditional UPDATEs), not
against ORM metadata.

Two concerns share this module:

1. **``human_interactions`` shape** (revision ``0003``) — the eight declared
   columns and their nullability, the three-value ``interaction_status`` CHECK
   enforced by PostgreSQL (not the ORM), the partial unique index that makes "at
   most one open question per run" a database invariant, and both foreign keys.

2. **The ``runs`` lease columns behave as a database-clock lease** — before any
   ``orchestrator/lease.py`` exists. Claim-don't-check is shown as a single
   ``UPDATE ... RETURNING`` statement: one process wins, a concurrent claim gets
   zero rows, a forced-past expiry makes the run claimable again, a terminal run
   is never claimable, and the expiry value is proven to be computed on the
   server by comparing it against a separately selected ``now()``.

Every deliberate violation runs in its own short transaction so it cannot poison
the rest of the test, and every fixture row is cleaned up (the ``cleanup_runs``
idiom from ``tests/db/test_transition_atomic.py``). No reading of the Python
process wall clock appears anywhere in this file — every expiry value and every
expiry comparison is a SQL expression over the server clock, so the lease
assertions live entirely in the database's clock domain.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
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


def _claim(
    conn: Any, run_id: uuid.UUID, token: uuid.UUID, ttl_seconds: int
) -> list[Any]:
    """The whole of claim-don't-check as one statement: no application-side check
    between reading ownership and taking it. Both the expiry value written and
    the expiry test in the WHERE are ``func.now()`` — one clock domain, the
    server's."""
    stmt = (
        sa.update(Run)
        .where(
            Run.id == run_id,
            Run.status.notin_([RunStatus.COMPLETED, RunStatus.FAILED]),
            sa.or_(Run.owner_token.is_(None), Run.lock_expires_at < sa.func.now()),
        )
        .values(
            owner_token=token,
            lock_expires_at=sa.func.now() + timedelta(seconds=ttl_seconds),
            updated_at=sa.func.now(),
        )
        .returning(Run.id)
    )
    return list(conn.execute(stmt).fetchall())


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


# --------------------------------------------------------------------------- #
# runs lease columns behave as a database-clock lease (HITL-07, HITL-08)
# --------------------------------------------------------------------------- #


def test_a_fresh_run_has_null_in_both_lease_columns(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, _ = _seed_run_and_exec(engine, cleanup_runs)
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(Run.owner_token, Run.lock_expires_at).where(Run.id == run_id)
        ).one()
    assert row.owner_token is None
    assert row.lock_expires_at is None


def test_first_claim_wins_and_an_immediate_second_claim_gets_zero_rows(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, _ = _seed_run_and_exec(engine, cleanup_runs)
    first_token = uuid.uuid4()
    second_token = uuid.uuid4()

    with engine.begin() as conn:
        first = _claim(conn, run_id, first_token, ttl_seconds=900)
    with engine.begin() as conn:
        second = _claim(conn, run_id, second_token, ttl_seconds=900)

    assert len(first) == 1
    assert second == []

    with engine.begin() as conn:
        owner = conn.execute(
            sa.select(Run.owner_token).where(Run.id == run_id)
        ).scalar_one()
    assert owner == first_token


def test_a_forced_past_expiry_makes_the_run_claimable_again(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, _ = _seed_run_and_exec(engine, cleanup_runs)
    first_token = uuid.uuid4()
    third_token = uuid.uuid4()

    with engine.begin() as conn:
        assert len(_claim(conn, run_id, first_token, ttl_seconds=900)) == 1

    # Force expiry with a server-clock-relative UPDATE (time-machine cannot move
    # the PostgreSQL clock).
    with engine.begin() as conn:
        conn.execute(
            sa.update(Run)
            .where(Run.id == run_id)
            .values(lock_expires_at=sa.func.now() - timedelta(seconds=1))
        )

    with engine.begin() as conn:
        reclaimed = _claim(conn, run_id, third_token, ttl_seconds=900)
    assert len(reclaimed) == 1

    with engine.begin() as conn:
        owner = conn.execute(
            sa.select(Run.owner_token).where(Run.id == run_id)
        ).scalar_one()
    assert owner == third_token


def test_lock_expires_at_is_computed_on_the_server_not_in_the_test_process(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, _ = _seed_run_and_exec(engine, cleanup_runs)
    ttl_seconds = 2

    with engine.begin() as conn:
        assert len(_claim(conn, run_id, uuid.uuid4(), ttl_seconds=ttl_seconds)) == 1

    with engine.begin() as conn:
        lock_expires_at = conn.execute(
            sa.select(Run.lock_expires_at).where(Run.id == run_id)
        ).scalar_one()
        server_now = conn.execute(sa.select(sa.func.now())).scalar_one()

    delta_seconds = (lock_expires_at - server_now).total_seconds()
    # Strictly in the future, and by approximately the TTL (server_now is taken a
    # moment after the claim, so the gap is a little under ttl_seconds).
    assert 0 < delta_seconds <= ttl_seconds + 1


def test_a_terminal_run_is_never_claimable(
    engine: Engine, cleanup_runs: list[Any]
) -> None:
    run_id, _ = _seed_run_and_exec(engine, cleanup_runs, status=RunStatus.COMPLETED)
    with engine.begin() as conn:
        rows = _claim(conn, run_id, uuid.uuid4(), ttl_seconds=900)
    assert rows == []

    with engine.begin() as conn:
        owner = conn.execute(
            sa.select(Run.owner_token).where(Run.id == run_id)
        ).scalar_one()
    assert owner is None
