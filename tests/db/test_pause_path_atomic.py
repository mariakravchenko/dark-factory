"""HITL-02 (atomicity half): the pause transition and the answer transition are
each all-or-nothing under a crash injected between their sub-writes.

The recipe is ``tests/db/test_transition_atomic.py``'s, unchanged in spirit: a
SQLAlchemy ``after_cursor_execute`` listener raises the first time a chosen
statement of the transition goes over the wire, so the failure lands *inside*
``apply_transition``'s single ``with session.begin()`` block -- after at least
one sub-write has executed and before COMMIT. The rollback under test is the
**database's**, not the application's: what is proved is that all five writes of
the pause (the role-execution update, the interaction insert, the runs update
and the two audit events) really are inside one transaction block. Move any of
them outside it and a crash at that seam would leave a half-paused run -- a run
whose status says "waiting" with no recorded question -- and one of these tests
would fail loudly.

The injection-point map extends the Phase-1 file's ``UPDATE ROLE_EXECUTIONS`` /
``UPDATE RUNS`` prefixes with the interaction insert (``INSERT INTO
HUMAN_INTERACTIONS``, pause) and the interaction update (``UPDATE
HUMAN_INTERACTIONS``, answer). The ``UPDATE RUNS`` prefix is qualified with
``STATUS`` so it matches the lifecycle write and not the lease's own ``UPDATE
runs`` -- ``claim_lease`` / ``renew_lease`` / ``release_lease`` touch only
``owner_token`` / ``lock_expires_at`` / ``updated_at`` and never ``status``.

Real commits; ``cleanup_runs`` deletes every fixture row at teardown.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import advance, drive, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_QUESTION = "primary or replica?"
_ANSWER = "use the primary cluster"
_SESSION_ID = "fake-atomic-pause-001"

_NEEDS_INPUT = WorkerResult(
    status=WorkerResultStatus.NEEDS_INPUT,
    summary="need a decision",
    questions=[_QUESTION],
    worker_session_id=_SESSION_ID,
)
_COMPLETED = WorkerResult(
    status=WorkerResultStatus.COMPLETED,
    summary="done",
    worker_session_id=_SESSION_ID,
)

# (upper-cased, left-stripped statement prefix, required substring or None).
_PAUSE_INJECTION_POINTS: dict[str, tuple[str, str | None]] = {
    "role_execution_update": ("UPDATE ROLE_EXECUTIONS", None),
    "interaction_insert": ("INSERT INTO HUMAN_INTERACTIONS", None),
    "runs_update": ("UPDATE RUNS", "STATUS"),
}
_ANSWER_INJECTION_POINTS: dict[str, tuple[str, str | None]] = {
    "role_execution_update": ("UPDATE ROLE_EXECUTIONS", None),
    "interaction_update": ("UPDATE HUMAN_INTERACTIONS", None),
    "runs_update": ("UPDATE RUNS", "STATUS"),
}


class _InjectedCrash(RuntimeError):
    """Distinctive exception raised by the mid-transaction statement listener."""


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
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
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _arm(
    engine: Engine, prefix: str, must_contain: str | None
) -> tuple[dict[str, int], Callable[..., None]]:
    """Register an ``after_cursor_execute`` listener that raises the first time a
    statement matching ``prefix`` (and containing ``must_contain`` if given) goes
    over the wire. Returns the fire-count dict and the listener for removal."""
    fired = {"n": 0}

    def boom(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if fired["n"]:
            return
        upper = statement.lstrip().upper()
        if upper.startswith(prefix) and (must_contain is None or must_contain in upper):
            fired["n"] = 1
            raise _InjectedCrash(prefix)

    event.listen(engine, "after_cursor_execute", boom)
    return fired, boom


def _snapshot(factory: SessionFactory, run_id: UUID) -> dict[str, Any]:
    session = factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(
                RoleExecution.created_at.desc(),
                RoleExecution.attempt.desc(),
                RoleExecution.id.desc(),
            )
            .limit(1)
        )
        interactions = list(
            session.scalars(
                select(HumanInteraction).where(HumanInteraction.run_id == run_id)
            )
        )
        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        return {
            "status": run.status,
            "events": events,
            "interaction_count": len(interactions),
            "interaction_status": (
                interactions[0].status.value if interactions else None
            ),
            "interaction_answer": interactions[0].answer if interactions else None,
            "re": None
            if latest is None
            else (
                str(latest.id),
                latest.status,
                latest.attempt,
                latest.result,
                latest.error,
            ),
        }
    finally:
        session.close()


def _run_at_ba(
    factory: SessionFactory,
    registry_builder: Callable[..., Any],
    cleanup: list[Any],
) -> UUID:
    run_id = start_run("text:atomic pause proof", session_factory=factory)
    cleanup.append(run_id)
    status = advance(
        run_id, session_factory=factory, registry=registry_builder([_COMPLETED])
    )
    assert status is RunStatus.BA
    return run_id


def _pause_cleanly(
    run_id: UUID, factory: SessionFactory, registry_builder: Callable[..., Any]
) -> None:
    status = advance(
        run_id, session_factory=factory, registry=registry_builder([_NEEDS_INPUT])
    )
    assert status is RunStatus.WAITING_HUMAN


def _ba_attempt(factory: SessionFactory, run_id: UUID) -> int:
    session = factory()
    try:
        rows = list(
            session.scalars(
                select(RoleExecution).where(
                    RoleExecution.run_id == run_id, RoleExecution.role == "BA"
                )
            )
        )
        assert len(rows) == 1
        return rows[0].attempt
    finally:
        session.close()


@pytest.mark.parametrize("point", list(_PAUSE_INJECTION_POINTS))
def test_a_crash_between_the_pause_sub_writes_leaves_the_run_unpaused(
    point: str,
    engine: Engine,
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[..., Any],
    cleanup_runs: list[Any],
) -> None:
    prefix, must_contain = _PAUSE_INJECTION_POINTS[point]
    run_id = _run_at_ba(real_session_factory, fake_worker_registry, cleanup_runs)
    baseline = _snapshot(real_session_factory, run_id)
    assert baseline["status"] is RunStatus.BA

    fired, boom = _arm(engine, prefix, must_contain)
    try:
        with pytest.raises(_InjectedCrash):
            advance(
                run_id,
                session_factory=real_session_factory,
                registry=fake_worker_registry([_NEEDS_INPUT]),
            )
    finally:
        event.remove(engine, "after_cursor_execute", boom)
    assert fired["n"] == 1, f"the {point} statement never went over the wire"

    # -- all-or-nothing: the pause left none of its five writes --
    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA
    assert after["interaction_count"] == 0
    assert "QUESTION_CREATED" not in after["events"]
    assert "RUN_PAUSED" not in after["events"]
    assert after["events"] == baseline["events"]
    assert after["re"] == baseline["re"]  # role-execution row untouched

    # -- still resumable, and the eventual outcome matches the no-crash run --
    _pause_cleanly(run_id, real_session_factory, fake_worker_registry)
    resumed = submit_answer(run_id, _ANSWER, session_factory=real_session_factory)
    assert resumed is RunStatus.BA
    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_COMPLETED]),
    )
    assert final is RunStatus.COMPLETED
    assert _ba_attempt(real_session_factory, run_id) == baseline["re"][2]


@pytest.mark.parametrize("point", list(_ANSWER_INJECTION_POINTS))
def test_a_crash_between_the_answer_sub_writes_leaves_the_run_waiting(
    point: str,
    engine: Engine,
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[..., Any],
    cleanup_runs: list[Any],
) -> None:
    prefix, must_contain = _ANSWER_INJECTION_POINTS[point]
    run_id = _run_at_ba(real_session_factory, fake_worker_registry, cleanup_runs)
    _pause_cleanly(run_id, real_session_factory, fake_worker_registry)
    baseline = _snapshot(real_session_factory, run_id)
    assert baseline["status"] is RunStatus.WAITING_HUMAN
    assert baseline["interaction_count"] == 1

    fired, boom = _arm(engine, prefix, must_contain)
    try:
        with pytest.raises(_InjectedCrash):
            submit_answer(run_id, _ANSWER, session_factory=real_session_factory)
    finally:
        event.remove(engine, "after_cursor_execute", boom)
    assert fired["n"] == 1, f"the {point} statement never went over the wire"

    # -- all-or-nothing: the run is still fully waiting, the answer left nothing --
    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.WAITING_HUMAN
    assert after["interaction_status"] == "WAITING"
    assert after["interaction_answer"] is None
    assert "HUMAN_ANSWER_RECEIVED" not in after["events"]
    assert "RUN_RESUMED" not in after["events"]
    assert after["events"] == baseline["events"]
    assert after["re"] == baseline["re"]

    # -- a failed attempt left a state a retry can act on --
    resumed = submit_answer(run_id, _ANSWER, session_factory=real_session_factory)
    assert resumed is RunStatus.BA
    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_COMPLETED]),
    )
    assert final is RunStatus.COMPLETED
    assert _ba_attempt(real_session_factory, run_id) == baseline["re"][2]
