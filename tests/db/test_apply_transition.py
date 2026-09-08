"""`apply_transition` — one transaction, redaction-at-write, the ``expected_status``
guard and in-transaction ``attempt`` computation, proven against real PostgreSQL
(Plan 01-05, Task 1).

The ``db_session`` fixture runs in ``join_transaction_mode="create_savepoint"``.
Back-to-back ``with session.begin():`` blocks are fine, but a *bare* read
(``session.get`` / ``session.scalars``) autobegins a transaction that must be
released with ``session.rollback()`` before the next mutation opens its own
``session.begin()``. Every test below follows that rule.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence import mutations
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from dark_factory.persistence.mutations import (
    ConcurrentTransition,
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]


class _Boom(RuntimeError):
    pass


def _task() -> NormalizedTask:
    return NormalizedTask(
        source_kind="text", source_ref=None, title="t", body="b", metadata={}
    )


def _created_run(db_session: Session) -> object:
    return create_run(db_session, task=_task(), workflow={"roles": ["BA"]})


def _start_ba(
    db_session: Session, run_id: object, *, worker: str = "fake"
) -> RunStatus:
    return apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.CREATED,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="insert", role="BA", worker=worker, status="RUNNING"
        ),
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={"role": "BA"})],
    )


def test_happy_transition_writes_role_execution_columns_and_events(
    db_session: Session,
) -> None:
    run_id = _created_run(db_session)
    new_status = _start_ba(db_session, run_id)

    assert new_status is RunStatus.BA
    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.status is RunStatus.BA
    assert run.current_role == "BA"
    assert run.current_step == 0

    re_rows = db_session.scalars(
        select(RoleExecution).where(RoleExecution.run_id == run_id)
    ).all()
    assert len(re_rows) == 1
    assert re_rows[0].attempt == 1

    types = db_session.scalars(
        select(RunEvent.type).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    ).all()
    assert types == [EventType.RUN_CREATED.value, EventType.ROLE_STARTED.value]


def test_stale_expected_status_raises_concurrent_transition_and_writes_nothing(
    db_session: Session,
) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)

    before_events = db_session.scalars(
        select(RunEvent.id).where(RunEvent.run_id == run_id)
    ).all()
    before_re = db_session.scalars(
        select(RoleExecution.id).where(RoleExecution.run_id == run_id)
    ).all()
    db_session.rollback()

    with pytest.raises(ConcurrentTransition):
        apply_transition(
            db_session,
            run_id=run_id,
            expected_status=RunStatus.CREATED,  # stale — the run is BA now
            next_status=RunStatus.COMPLETED,
            next_current_role="BA",
            next_current_step=0,
            role_execution=None,
            events=[EventWrite(type=EventType.RUN_COMPLETED, payload={})],
        )
    db_session.rollback()

    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.status is RunStatus.BA
    assert (
        db_session.scalars(select(RunEvent.id).where(RunEvent.run_id == run_id)).all()
        == before_events
    )
    assert (
        db_session.scalars(
            select(RoleExecution.id).where(RoleExecution.run_id == run_id)
        ).all()
        == before_re
    )


def test_status_change_with_empty_events_is_rejected_without_side_effects(
    db_session: Session,
) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)

    with pytest.raises(ValueError):
        apply_transition(
            db_session,
            run_id=run_id,
            expected_status=RunStatus.BA,
            next_status=RunStatus.COMPLETED,
            next_current_role="BA",
            next_current_step=0,
            role_execution=None,
            events=[],
        )
    db_session.rollback()

    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.status is RunStatus.BA


def test_exception_between_subwrites_rolls_back_every_table(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)
    re_id = db_session.scalars(
        select(RoleExecution.id).where(RoleExecution.run_id == run_id)
    ).one()
    db_session.rollback()

    real_redact = mutations.redact

    def flaky(value: object, **kw: object) -> object:
        if isinstance(value, dict) and value.get("_boom"):
            raise _Boom
        return real_redact(value, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(mutations, "redact", flaky)

    with pytest.raises(_Boom):
        apply_transition(
            db_session,
            run_id=run_id,
            expected_status=RunStatus.BA,
            next_status=RunStatus.COMPLETED,
            next_current_role="BA",
            next_current_step=0,
            role_execution=RoleExecutionWrite(
                mode="update",
                id=re_id,
                role="BA",
                worker="fake",
                status="COMPLETED",
                result={"summary": "done"},
            ),
            events=[
                EventWrite(type=EventType.ROLE_COMPLETED, payload={"ok": True}),
                EventWrite(type=EventType.RUN_COMPLETED, payload={"_boom": True}),
            ],
        )
    db_session.rollback()

    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.status is RunStatus.BA
    re_row = db_session.get(RoleExecution, re_id)
    assert re_row is not None
    assert re_row.result is None
    types = db_session.scalars(
        select(RunEvent.type).where(RunEvent.run_id == run_id)
    ).all()
    assert EventType.ROLE_COMPLETED.value not in types
    assert EventType.RUN_COMPLETED.value not in types


def test_second_insert_for_same_run_and_role_gets_attempt_two(
    db_session: Session,
) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)
    apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="insert", role="BA", worker="fake", status="RUNNING"
        ),
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={})],
    )

    attempts = sorted(
        db_session.scalars(
            select(RoleExecution.attempt).where(RoleExecution.run_id == run_id)
        ).all()
    )
    assert attempts == [1, 2]


def test_role_execution_result_uri_is_stored_redacted(db_session: Session) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)
    re_id = db_session.scalars(
        select(RoleExecution.id).where(RoleExecution.run_id == run_id)
    ).one()
    db_session.rollback()

    apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.COMPLETED,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="update",
            id=re_id,
            role="BA",
            worker="fake",
            status="COMPLETED",
            result={"conn": "postgresql+psycopg://user:hunter2@host:5432/db"},
        ),
        events=[
            EventWrite(type=EventType.ROLE_COMPLETED, payload={}),
            EventWrite(type=EventType.RUN_COMPLETED, payload={}),
        ],
    )

    re_row = db_session.get(RoleExecution, re_id)
    assert re_row is not None
    assert "hunter2" not in str(re_row.result)
    assert "[redacted:database_url]" in str(re_row.result)


def test_event_payload_known_secret_value_is_stored_redacted(
    db_session: Session, fake_settings: Settings
) -> None:
    run_id = _created_run(db_session)
    live = fake_settings.database_url.get_secret_value()
    _start_ba(db_session, run_id)

    apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.COMPLETED,
        next_current_role="BA",
        next_current_step=0,
        role_execution=None,
        events=[
            EventWrite(
                type=EventType.RUN_COMPLETED, payload={"note": f"db lives at {live}"}
            )
        ],
    )

    ev = db_session.scalars(
        select(RunEvent).where(
            RunEvent.run_id == run_id, RunEvent.type == EventType.RUN_COMPLETED.value
        )
    ).one()
    assert live not in str(ev.payload)
    assert "[redacted:" in str(ev.payload)


def test_counter_increments_touch_only_the_named_counter(db_session: Session) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)

    apply_transition(
        db_session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=None,
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={})],
        counter_increments={"qa_developer_iterations": 1},
    )

    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.qa_developer_iterations == 1
    assert run.quality_gate_iterations == 0


def test_empty_counter_map_leaves_both_counters_untouched(db_session: Session) -> None:
    run_id = _created_run(db_session)
    _start_ba(db_session, run_id)
    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.qa_developer_iterations == 0
    assert run.quality_gate_iterations == 0
