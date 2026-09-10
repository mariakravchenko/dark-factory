"""SC4: a crash injected between the sub-writes of a transition rolls the whole
transition back, and the run is still resumable afterwards.

The seam is a SQLAlchemy ``after_cursor_execute`` listener that raises the first
time a chosen statement of the transition goes over the wire. The failure lands
*inside* ``apply_transition``'s ``with session.begin()`` block -- after at least
one statement has executed and before COMMIT -- which is the exact window SC4 is
about. The injection point is parametrized over the ``role_executions`` write and
the ``runs`` update so the guarantee is shown to be a property of the
transaction, not an accident of statement ordering.

RESEARCH documents two weaker seams and both are worse here: patching
``Session.commit`` to raise proves the database's all-or-nothing behaviour
rather than this code's use of it, and a real ``SIGKILL`` cannot be aimed
between two statements -- which is why it is used for SC2 in Task 1 and not here.

The listener is registered and removed inside each test body, and every
post-crash assertion reads through a session opened *after* removal, so the
listener can never leak into another test in the shared session-scoped engine.

Rows here are really committed (a real crash leaves real rows behind); the
``cleanup_runs`` fixture deletes them at teardown.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import advance, drive, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.config import DEFAULT_TEST_SNAPSHOT

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_COMPLETED = WorkerResult(
    status=WorkerResultStatus.COMPLETED,
    summary="BA analysis complete",
    worker_session_id="fake-sc4",
)

# Statement prefixes (upper-cased, left-stripped) that identify each sub-write of
# the BA -> COMPLETED transition.
_INJECTION_POINTS = {
    "role_executions_write": "UPDATE ROLE_EXECUTIONS",
    "runs_update": "UPDATE RUNS",
}


class _InjectedCrash(RuntimeError):
    """Distinctive exception raised by the mid-transaction statement listener."""


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    """A production-shaped session factory: a fresh ``Session`` on the real engine
    per call, committing for real (``NullPool`` discards the connection on close,
    so an ``after_cursor_execute`` failure cannot poison a later test)."""

    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _snapshot(session_factory: SessionFactory, run_id: Any) -> dict[str, Any]:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(RoleExecution.attempt.desc())
            .limit(1)
        )
        event_count = session.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
        return {
            "status": run.status,
            "event_count": event_count,
            "latest_result": latest.result if latest is not None else None,
            "latest_re_status": latest.status if latest is not None else None,
        }
    finally:
        session.close()


def _ba_execution_count(session_factory: SessionFactory, run_id: Any) -> int:
    session = session_factory()
    try:
        total = session.scalar(
            select(func.count())
            .select_from(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
        )
        assert total is not None
        return total
    finally:
        session.close()


@pytest.mark.parametrize("injection_point", list(_INJECTION_POINTS))
def test_crash_between_subwrites_rolls_back_whole_and_stays_resumable(
    injection_point: str,
    engine: Engine,
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[[list[WorkerResult]], Any],
    cleanup_runs: list[Any],
) -> None:
    target_prefix = _INJECTION_POINTS[injection_point]
    registry = fake_worker_registry([_COMPLETED])

    # -- committed baseline: a run at BA, one attempt row, a known event count --
    run_id = start_run(
        "text:prove the transition is atomic",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)
    assert (
        advance(run_id, session_factory=real_session_factory, registry=registry)
        is RunStatus.BA
    )
    baseline = _snapshot(real_session_factory, run_id)
    assert baseline["status"] is RunStatus.BA
    assert baseline["latest_result"] is None

    # -- arm the mid-transaction crash on the chosen sub-write --
    fired = {"n": 0}

    def boom(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if fired["n"] == 0 and statement.lstrip().upper().startswith(target_prefix):
            fired["n"] = 1
            raise _InjectedCrash(target_prefix)

    event.listen(engine, "after_cursor_execute", boom)
    try:
        with pytest.raises(_InjectedCrash):
            advance(run_id, session_factory=real_session_factory, registry=registry)
    finally:
        event.remove(engine, "after_cursor_execute", boom)

    assert fired["n"] == 1, f"the {injection_point} statement never went over the wire"

    # -- the invariant, read through a session opened after listener removal --
    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA  # runs.status unchanged
    assert after["event_count"] == baseline["event_count"]  # no event without state
    assert after["latest_result"] is None  # the role-execution write rolled back
    assert after["latest_re_status"] == baseline["latest_re_status"]

    # -- and still resumable: crash consistency means resumable, not merely intact --
    final = drive(run_id, session_factory=real_session_factory, registry=registry)
    assert final is RunStatus.COMPLETED
    assert _ba_execution_count(real_session_factory, run_id) == 1  # no phantom attempt
