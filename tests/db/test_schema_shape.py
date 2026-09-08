"""Column-level guarantees of migration 0001, asserted against the **live**
PostgreSQL database (through the ORM models and raw SQL) rather than against
metadata.

Every test runs inside the ``db_session`` fixture's outer transaction, which is
rolled back afterwards, so nothing here persists.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = pytest.mark.db

_TEN_STATUS_VALUES = [member.value for member in RunStatus]


def _new_run(session: Session, **overrides: object) -> Run:
    kwargs: dict[str, object] = {
        "source_kind": "text",
        "normalized_task": {},
        "workflow": {"roles": ["BA"]},
        "status": RunStatus.CREATED,
    }
    kwargs.update(overrides)
    run = Run(**kwargs)
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def test_status_accepts_every_one_of_the_ten_run_status_values(
    db_session: Session,
) -> None:
    for value in _TEN_STATUS_VALUES:
        savepoint = db_session.begin_nested()
        db_session.execute(
            text(
                "INSERT INTO runs (id, source_kind, normalized_task, workflow, status)"
                " VALUES (gen_random_uuid(), 'text', '{}'::jsonb, '{}'::jsonb, :status)"
            ),
            {"status": value},
        )
        savepoint.rollback()


def test_status_rejects_a_value_outside_the_ten_member_set(db_session: Session) -> None:
    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO runs (id, source_kind, normalized_task, workflow, status)"
                " VALUES (gen_random_uuid(), 'text', '{}'::jsonb, '{}'::jsonb,"
                " 'NOT_A_REAL_STATUS')"
            )
        )


def test_iteration_counters_default_to_zero_when_omitted(db_session: Session) -> None:
    run = _new_run(db_session)
    assert run.qa_developer_iterations == 0
    assert run.quality_gate_iterations == 0


def test_iteration_counters_are_not_null(db_session: Session) -> None:
    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO runs (id, source_kind, normalized_task, workflow, status,"
                " qa_developer_iterations) VALUES (gen_random_uuid(), 'text',"
                " '{}'::jsonb, '{}'::jsonb, 'CREATED', NULL)"
            )
        )


def test_branch_columns_insert_as_null_when_omitted(db_session: Session) -> None:
    run = _new_run(db_session)
    assert run.base_branch is None
    assert run.working_branch is None


def test_timestamps_are_server_populated_and_timezone_aware(
    db_session: Session,
) -> None:
    run = _new_run(db_session)
    assert isinstance(run.created_at, datetime)
    assert isinstance(run.updated_at, datetime)
    assert run.created_at.tzinfo is not None
    assert run.updated_at.tzinfo is not None


def test_role_execution_result_jsonb_preserves_every_scalar_type(
    db_session: Session,
) -> None:
    run = _new_run(db_session)
    payload = {
        "an_int": 7,
        "a_float": 1.5,
        "a_bool": True,
        "a_null": None,
        "nested": {"list": [1, 2, {"deep": "value"}]},
    }
    role_execution = RoleExecution(
        run_id=run.id,
        role="BA",
        worker="fake",
        status="RUNNING",
        attempt=1,
        result=payload,
    )
    db_session.add(role_execution)
    db_session.flush()
    db_session.expire(role_execution)

    read_back = role_execution.result
    assert read_back == payload
    assert isinstance(read_back["an_int"], int)
    assert not isinstance(read_back["an_int"], bool)
    assert isinstance(read_back["a_float"], float)
    assert read_back["a_bool"] is True
    assert read_back["a_null"] is None
    assert read_back["nested"]["list"][2]["deep"] == "value"


def test_role_execution_attempt_starts_at_one(db_session: Session) -> None:
    run = _new_run(db_session)
    role_execution = RoleExecution(
        run_id=run.id, role="BA", worker="fake", status="RUNNING", attempt=1
    )
    db_session.add(role_execution)
    db_session.flush()
    db_session.refresh(role_execution)
    assert role_execution.attempt == 1


def test_run_events_seq_is_strictly_increasing_within_one_transaction(
    db_session: Session,
) -> None:
    run = _new_run(db_session)
    first = RunEvent(run_id=run.id, type="ROLE_STARTED", payload={})
    second = RunEvent(run_id=run.id, type="ROLE_COMPLETED", payload={})
    db_session.add_all([first, second])
    db_session.flush()
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.seq is not None
    assert second.seq > first.seq


def test_normalized_task_round_trips_a_100kb_body_unchanged(
    db_session: Session,
) -> None:
    big_body = "x" * 100_000
    task = {"title": "big", "body": big_body}
    run = _new_run(db_session, normalized_task=task)
    db_session.expire(run)
    assert run.normalized_task == task
    assert len(run.normalized_task["body"]) == 100_000
