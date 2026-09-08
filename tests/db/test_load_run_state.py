"""`load_run_state` — reconstruct the whole run from columns into a detached,
frozen value object; never touch ``run_events`` (Plan 01-05, Task 2 — STATE-06,
STATE-08).
"""

from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence.models import RunEvent
from dark_factory.persistence.mutations import (
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)
from dark_factory.persistence.repositories import RunState, load_run_state

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]


def _task() -> NormalizedTask:
    return NormalizedTask(
        source_kind="text",
        source_ref=None,
        title="t",
        body="the body",
        metadata={"k": "v"},
    )


def _run_at_ba(db_session: Session) -> uuid.UUID:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})
    apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.CREATED,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="insert", role="BA", worker="fake", status="RUNNING"
        ),
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={})],
    )
    return run_id


def test_reconstructs_every_phase_one_resume_value(db_session: Session) -> None:
    run_id = _run_at_ba(db_session)

    state = load_run_state(db_session, run_id)
    assert isinstance(state, RunState)
    assert state.run_id == run_id
    assert state.status is RunStatus.BA
    assert state.current_role == "BA"
    assert state.current_step == 0
    assert isinstance(state.normalized_task, NormalizedTask)
    assert state.normalized_task.body == "the body"
    assert state.workflow == {"roles": ["BA"]}
    assert state.qa_developer_iterations == 0
    assert state.quality_gate_iterations == 0
    assert state.latest_execution is not None
    assert state.latest_execution.role == "BA"
    assert state.latest_execution.worker == "fake"
    assert state.latest_execution.status == "RUNNING"
    assert state.latest_execution.attempt == 1


def test_unknown_run_id_returns_none(db_session: Session) -> None:
    assert load_run_state(db_session, uuid.uuid4()) is None


def test_run_with_no_role_execution_has_none_latest(db_session: Session) -> None:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})
    state = load_run_state(db_session, run_id)
    assert state is not None
    assert state.status is RunStatus.CREATED
    assert state.latest_execution is None


def test_run_state_survives_the_producing_session_being_closed(
    db_session: Session,
) -> None:
    run_id = _run_at_ba(db_session)
    state = load_run_state(db_session, run_id)
    assert state is not None

    db_session.close()

    # no lazy-load, no DetachedInstanceError — every field is a plain value
    assert state.normalized_task.body == "the body"
    assert state.workflow["roles"] == ["BA"]
    assert state.latest_execution is not None
    assert state.latest_execution.attempt == 1


def test_two_independent_sessions_return_equal_state(db_session: Session) -> None:
    run_id = _run_at_ba(db_session)

    first = load_run_state(db_session, run_id)
    other = Session(bind=db_session.connection())
    try:
        second = load_run_state(other, run_id)
    finally:
        other.close()

    assert first == second


def test_load_run_state_never_queries_run_events(db_session: Session) -> None:
    run_id = _run_at_ba(db_session)
    before = load_run_state(db_session, run_id)

    db_session.add(
        RunEvent(run_id=run_id, type="ROLE_FAILED", payload={"bogus": True})
    )
    db_session.flush()
    after = load_run_state(db_session, run_id)

    assert before == after


def test_repositories_module_imports_nothing_from_events() -> None:
    from dark_factory.persistence import repositories

    src = inspect.getsource(repositories)
    assert "dark_factory.events" not in src
