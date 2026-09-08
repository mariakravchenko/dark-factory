"""``advance`` on a terminal run is a proven zero-write no-op (D-05 idempotency).

Take a run to each terminal state, snapshot the ``runs`` row, the
``role_executions`` rows and the ``run_events`` count, call ``advance`` twice
more, and assert every snapshot is byte-for-byte unchanged and the returned
status is the same terminal value both times. This is what makes ``resume`` safe
to run repeatedly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import advance, drive, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = pytest.mark.db

SessionFactory = Callable[[], Session]
RegistryBuilder = Callable[[list[WorkerResult]], Any]

_SCRIPTS = {
    RunStatus.COMPLETED: WorkerResult(
        status=WorkerResultStatus.COMPLETED,
        summary="done",
        worker_session_id="fake-terminal",
    ),
    RunStatus.FAILED: WorkerResult(
        status=WorkerResultStatus.FAILED,
        summary="not done",
        error="stop here",
    ),
}


def _snapshot(session_factory: SessionFactory, run_id: Any) -> dict[str, Any]:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        execs = list(
            session.scalars(
                select(RoleExecution)
                .where(RoleExecution.run_id == run_id)
                .order_by(RoleExecution.attempt)
            )
        )
        event_count = session.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
        return {
            "status": run.status,
            "current_role": run.current_role,
            "updated_at": run.updated_at,
            "executions": [
                (e.id, e.status, e.attempt, e.updated_at, e.result, e.error)
                for e in execs
            ],
            "event_count": event_count,
        }
    finally:
        session.close()


@pytest.mark.parametrize("terminal", [RunStatus.COMPLETED, RunStatus.FAILED])
def test_advance_on_terminal_run_writes_nothing_and_returns_the_same_status(
    terminal: RunStatus,
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = start_run(
        "text:take me to a terminal state", session_factory=advance_session_factory
    )
    registry = fake_worker_registry([_SCRIPTS[terminal]])
    assert (
        drive(run_id, session_factory=advance_session_factory, registry=registry)
        is terminal
    )

    before = _snapshot(advance_session_factory, run_id)

    first = advance(run_id, session_factory=advance_session_factory, registry=registry)
    second = advance(run_id, session_factory=advance_session_factory, registry=registry)

    assert first is terminal
    assert second is terminal
    assert _snapshot(advance_session_factory, run_id) == before


def test_repeated_advance_on_a_completed_run_adds_no_events(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = start_run(
        "text:finish then poke it again", session_factory=advance_session_factory
    )
    registry = fake_worker_registry([_SCRIPTS[RunStatus.COMPLETED]])
    assert (
        drive(run_id, session_factory=advance_session_factory, registry=registry)
        is RunStatus.COMPLETED
    )

    def _event_count() -> int | None:
        session = advance_session_factory()
        try:
            return session.scalar(
                select(func.count())
                .select_from(RunEvent)
                .where(RunEvent.run_id == run_id)
            )
        finally:
            session.close()

    before = _event_count()
    for _ in range(3):
        assert (
            advance(run_id, session_factory=advance_session_factory, registry=registry)
            is RunStatus.COMPLETED
        )
    assert _event_count() == before == 4
