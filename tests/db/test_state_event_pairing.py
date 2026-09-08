"""The state-change <-> audit-row pairing, asserted across every ``advance`` in a
run, for both terminal arms (SC4's companion structural property, T-01-04).

Driven step by step rather than through ``drive`` so the status and the
``run_events`` count can be snapshotted around each ``advance``:

* every call that changed the status added **at least one** ``run_events`` row;
* every call that did not change the status added **none**.

The pairing is asserted in both directions -- never an exact per-step count. The
entry step emits one event and the completion step emits two; hard-coding those
numbers would make the test brittle against a legitimate event-catalog addition
in a later phase while proving nothing extra.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import advance, start_run
from dark_factory.persistence.models import Run, RunEvent

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_ARM_SCRIPTS = {
    "completed": WorkerResult(
        status=WorkerResultStatus.COMPLETED,
        summary="BA analysis complete",
        worker_session_id="fake-pairing",
    ),
    "failed": WorkerResult(
        status=WorkerResultStatus.FAILED,
        summary="BA analysis could not be completed",
        error="stop here",
    ),
}
_ARM_TERMINAL = {
    "completed": RunStatus.COMPLETED,
    "failed": RunStatus.FAILED,
}


def _status_and_events(
    session_factory: SessionFactory, run_id: Any
) -> tuple[RunStatus, int]:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        count = session.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
        assert count is not None
        return run.status, count
    finally:
        session.close()


@pytest.mark.parametrize("arm", list(_ARM_SCRIPTS))
def test_every_status_change_is_paired_with_at_least_one_event(
    arm: str,
    advance_session_factory: SessionFactory,
    fake_worker_registry: Callable[[list[WorkerResult]], Any],
) -> None:
    registry = fake_worker_registry([_ARM_SCRIPTS[arm]])
    run_id = start_run(
        "text:pair every state change with an audit row",
        session_factory=advance_session_factory,
    )

    saw_change = False
    saw_noop = False
    prev_status, prev_events = _status_and_events(advance_session_factory, run_id)

    # Two real steps (CREATED->BA, BA->terminal) then terminal no-ops.
    for _ in range(6):
        new_status = advance(
            run_id, session_factory=advance_session_factory, registry=registry
        )
        _, new_events = _status_and_events(advance_session_factory, run_id)
        delta = new_events - prev_events

        if new_status != prev_status:
            assert delta >= 1, (
                f"{prev_status.value} -> {new_status.value} added no run_events row"
            )
            saw_change = True
        else:
            assert delta == 0, (
                f"a no-op advance in {new_status.value} wrote {delta} event(s)"
            )
            saw_noop = True

        prev_status, prev_events = new_status, new_events

    assert saw_change and saw_noop
    assert prev_status is _ARM_TERMINAL[arm]


def test_a_freshly_created_run_has_exactly_its_run_created_row_and_no_orphans(
    advance_session_factory: SessionFactory,
) -> None:
    run_id = start_run(
        "text:just created, never advanced", session_factory=advance_session_factory
    )
    session = advance_session_factory()
    try:
        orphan_events = session.scalar(
            select(func.count())
            .select_from(RunEvent)
            .outerjoin(Run, Run.id == RunEvent.run_id)
            .where(Run.id.is_(None))
        )
        assert orphan_events == 0  # no run_events row without a run

        types = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.CREATED
        assert types == ["RUN_CREATED"]  # its one state change, its one event
    finally:
        session.close()
