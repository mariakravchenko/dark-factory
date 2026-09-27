"""`load_run_state` — reconstruct the whole run from columns into a detached,
frozen value object; never touch ``run_events`` (Plan 01-05, Task 2 — STATE-06,
STATE-08).
"""

from __future__ import annotations

import inspect
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence.models import HumanInteraction, Run, RunEvent
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
    # Phase 10 (plan 10-06, GIT-03/GIT-04): a freshly seeded run has
    # published nothing and has no open question -- all four new fields are
    # None.
    assert state.pr_number is None
    assert state.pr_url is None
    assert state.published_commit_sha is None
    assert state.pending_clarification_comment_id is None


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

    db_session.add(RunEvent(run_id=run_id, type="ROLE_FAILED", payload={"bogus": True}))
    db_session.flush()
    after = load_run_state(db_session, run_id)

    assert before == after


def test_repositories_module_imports_nothing_from_events() -> None:
    from dark_factory.persistence import repositories

    src = inspect.getsource(repositories)
    assert "dark_factory.events" not in src


# --------------------------------------------------------------------------- #
# Phase 10 (plan 10-06, GIT-03/GIT-04): the three publish-identifier columns
# and pending_clarification_comment_id.
# --------------------------------------------------------------------------- #


def test_load_run_state_reads_back_the_three_publish_identifiers_verbatim(
    db_session: Session,
) -> None:
    run_id = _run_at_ba(db_session)
    sha = "e" * 40
    db_session.execute(
        sa.update(Run)
        .where(Run.id == run_id)
        .values(
            pr_number=42,
            pr_url="https://example.invalid/pr/42",
            published_commit_sha=sha,
        )
    )
    db_session.flush()

    state = load_run_state(db_session, run_id)

    assert state is not None
    assert state.pr_number == 42
    assert state.pr_url == "https://example.invalid/pr/42"
    assert state.published_commit_sha == sha


def test_pending_clarification_comment_id_reads_from_a_waiting_row_but_not_an_answered_one(
    db_session: Session,
) -> None:
    run_id = _run_at_ba(db_session)
    latest = load_run_state(db_session, run_id)
    assert latest is not None
    assert latest.latest_execution is not None
    role_execution_id = latest.latest_execution.id

    db_session.add(
        HumanInteraction(
            run_id=run_id,
            role_execution_id=role_execution_id,
            question="what should the endpoint be named?",
            status=InteractionStatus.WAITING,
            clarification_comment_id=4503599627370496,
        )
    )
    db_session.flush()

    waiting_state = load_run_state(db_session, run_id)
    assert waiting_state is not None
    assert waiting_state.pending_clarification_comment_id == 4503599627370496

    db_session.execute(
        sa.update(HumanInteraction)
        .where(HumanInteraction.role_execution_id == role_execution_id)
        .values(answer="call it /health", status=InteractionStatus.ANSWERED)
    )
    db_session.flush()

    answered_state = load_run_state(db_session, run_id)
    assert answered_state is not None
    assert answered_state.pending_clarification_comment_id is None
    # ``pending_answer`` becomes populated the moment the row is answered --
    # the exact sibling behavior this field always had.
    assert answered_state.pending_answer == "call it /health"
