"""``advance`` is a proven zero-write no-op on a **stopped** run.

This file now covers two distinct no-op classes:

* **terminal** (``COMPLETED`` / ``FAILED``) — the run will never advance again.
* **waiting** (``WAITING_HUMAN``) — the run *will* advance, but only once an
  answer exists; until then ``advance`` must write nothing and must not reach
  the worker.

Conflating the two is exactly the mistake that ``STOP_STATUSES`` and
``TERMINAL_STATUSES`` being separate constants prevents: a run that waits must
not be treated as finished, and a run that waits must not quietly re-run its
role with no answer (RESEARCH Pitfall 7).

In every case: snapshot the ``runs`` row, the ``role_executions`` rows and the
``run_events`` count, act, and assert every snapshot is byte-for-byte unchanged
and the returned status is the same stop value.
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
from tests.support.config import DEFAULT_TEST_SNAPSHOT

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
        "text:take me to a terminal state",
        session_factory=advance_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
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
        "text:finish then poke it again",
        session_factory=advance_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
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


# --------------------------------------------------------------------------- #
# WAITING_HUMAN — the *other* no-op class: the run will advance, but only once
# an answer exists. Until then advance() must write nothing and must not reach
# the worker at all.
# --------------------------------------------------------------------------- #

_NEEDS_INPUT = WorkerResult(
    status=WorkerResultStatus.NEEDS_INPUT,
    questions=["which database?"],
    worker_session_id="fake-waiting",
)


def _pause_a_run(
    session_factory: SessionFactory, registry_builder: RegistryBuilder
) -> Any:
    run_id = start_run(
        "text:pause on a question",
        session_factory=session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    pausing_registry = registry_builder([_NEEDS_INPUT])
    assert (
        drive(run_id, session_factory=session_factory, registry=pausing_registry)
        is RunStatus.WAITING_HUMAN
    )
    return run_id


def test_advance_on_a_waiting_run_writes_nothing_and_never_calls_the_worker(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _pause_a_run(advance_session_factory, fake_worker_registry)

    before = _snapshot(advance_session_factory, run_id)

    # A registry whose worker raises on *any* call: "the worker was not invoked"
    # is then proven by the absence of an exception, not by inspection.
    exploding = fake_worker_registry([])
    status = advance(
        run_id, session_factory=advance_session_factory, registry=exploding
    )

    assert status is RunStatus.WAITING_HUMAN
    assert _snapshot(advance_session_factory, run_id) == before


def test_drive_that_reaches_waiting_stops_there_rather_than_looping(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = start_run(
        "text:reach waiting and stop",
        session_factory=advance_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    # Script has a COMPLETED after the NEEDS_INPUT: drive must NOT consume it.
    registry = fake_worker_registry(
        [
            _NEEDS_INPUT,
            WorkerResult(status=WorkerResultStatus.COMPLETED, summary="unreached"),
        ]
    )
    assert (
        drive(run_id, session_factory=advance_session_factory, registry=registry)
        is RunStatus.WAITING_HUMAN
    )
    snap = _snapshot(advance_session_factory, run_id)
    assert snap["status"] is RunStatus.WAITING_HUMAN
    assert len(snap["executions"]) == 1


def test_drive_starting_from_waiting_returns_immediately_without_advancing(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _pause_a_run(advance_session_factory, fake_worker_registry)

    before = _snapshot(advance_session_factory, run_id)

    exploding = fake_worker_registry([])
    assert (
        drive(run_id, session_factory=advance_session_factory, registry=exploding)
        is RunStatus.WAITING_HUMAN
    )
    assert _snapshot(advance_session_factory, run_id) == before
