"""A lease lost mid-step aborts the step, persists nothing, and is refused at
the commit -- fenced by the owner token on the already-locked ``runs`` row, not
only by the in-memory ``Event`` that races the worker call returning (RESEARCH
Pitfall 2). This completes the HITL-07 story with the mid-step-loss case.

Two guards, each independently sufficient:

* the **in-memory flag** (`LeaseHandle.lease_lost`) -- checked immediately after
  the worker call returns, so the abort happens before any write is attempted;
* the **commit-time token fence** -- `apply_transition` compares
  `expected_owner_token` against the already-locked ``runs`` row and raises
  `LeaseLost` when it differs, so a lease loss the flag missed still cannot
  produce a write.

A later refactor that removes one guard should fail exactly one test here while
the other still shows the run protected. The lease-loss failure is a distinct
type from `ConcurrentTransition` -- "someone took my lease" and "someone moved
the run past the status I expected" are different recovery paths. And because the
discarded step wrote nothing, it is proven re-runnable on the *same* attempt: the
outcome is indistinguishable from the step never having started.

Real commits against real PostgreSQL; ``cleanup_runs`` deletes every fixture row
at teardown (the idiom from ``tests/db/test_transition_atomic.py``).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.events.catalog import EventType
from dark_factory.orchestrator.lease import LeaseHandle, claim_lease, run_lease
from dark_factory.orchestrator.runner import _advance_once, advance, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from dark_factory.persistence.mutations import (
    ConcurrentTransition,
    EventWrite,
    LeaseLost,
    RoleExecutionWrite,
    apply_transition,
)
from dark_factory.workflows.pipeline import DEFAULT_PIPELINE
from tests.support.config import DEFAULT_TEST_SNAPSHOT

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_COMPLETED = WorkerResult(
    status=WorkerResultStatus.COMPLETED,
    summary="BA analysis complete",
    worker_session_id="fake-lease-lost-001",
)


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    """A fresh ``Session`` on the real engine per call, committing for real
    (``NullPool`` discards the connection on close). Never shared across
    threads."""

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


def _snapshot(factory: SessionFactory, run_id: UUID) -> dict[str, Any]:
    session = factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(RoleExecution.attempt.desc())
            .limit(1)
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
            "owner_token": run.owner_token,
            "events": events,
            "re": None
            if latest is None
            else (
                latest.id,
                latest.status,
                latest.attempt,
                latest.result,
                latest.error,
                latest.worker_session_id,
                latest.updated_at,
            ),
        }
    finally:
        session.close()


def _overwrite_owner_token(
    factory: SessionFactory, run_id: UUID, token: UUID | None = None
) -> UUID:
    """The database-level equivalent of another process having taken the lease:
    a fresh owner token and a fresh (server-clock) expiry, exactly as a real
    competing ``claim_lease`` would leave the row."""
    new_token = token or uuid4()
    session = factory()
    try:
        with session.begin():
            session.execute(
                sa.update(Run)
                .where(Run.id == run_id)
                .values(
                    owner_token=new_token,
                    lock_expires_at=sa.text("now() + interval '900 seconds'"),
                )
            )
    finally:
        session.close()
    return new_token


def _clear_lease(factory: SessionFactory, run_id: UUID) -> None:
    session = factory()
    try:
        with session.begin():
            session.execute(
                sa.update(Run)
                .where(Run.id == run_id)
                .values(owner_token=None, lock_expires_at=None)
            )
    finally:
        session.close()


def _run_at_ba(factory: SessionFactory, cleanup: list[Any], registry: Any) -> UUID:
    """A committed run parked at BA with one RUNNING role-execution row and the
    lease released (``advance`` claims and releases per call)."""
    run_id = start_run(
        "text:lease lost mid step",
        session_factory=factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup.append(run_id)
    assert advance(run_id, session_factory=factory, registry=registry) is RunStatus.BA
    return run_id


def _claim(factory: SessionFactory, run_id: UUID) -> UUID:
    session = factory()
    try:
        token = claim_lease(session, run_id, ttl_seconds=900)
    finally:
        session.close()
    assert token is not None
    return token


def _completed_update(re_id: UUID) -> RoleExecutionWrite:
    return RoleExecutionWrite(
        mode="update",
        id=re_id,
        role="BA",
        worker="fake",
        status="COMPLETED",
        worker_session_id=_COMPLETED.worker_session_id,
        result=_COMPLETED.model_dump(mode="json"),
    )


_TERMINAL_EVENTS = [
    EventWrite(type=EventType.ROLE_COMPLETED, payload={"role": "BA"}),
    EventWrite(type=EventType.RUN_COMPLETED, payload={"role": "BA"}),
]


# --------------------------------------------------------------------------- #
# The fence, directly against ``apply_transition``
# --------------------------------------------------------------------------- #


def test_a_transition_with_a_non_matching_owner_token_raises_lease_lost_writes_nothing(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)

    # another process takes the lease
    _overwrite_owner_token(real_session_factory, run_id)
    before = _snapshot(real_session_factory, run_id)
    assert before["re"] is not None
    re_id = before["re"][0]

    session = real_session_factory()
    try:
        with pytest.raises(LeaseLost) as excinfo:
            apply_transition(
                session,
                run_id=run_id,
                expected_status=RunStatus.BA,  # exactly what the caller expected
                next_status=RunStatus.COMPLETED,
                next_current_role=None,
                next_current_step=None,
                role_execution=_completed_update(re_id),
                events=_TERMINAL_EVENTS,
                expected_owner_token=my_token,
            )
    finally:
        session.close()
    assert not isinstance(excinfo.value, ConcurrentTransition)

    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA
    assert after["events"] == before["events"]
    assert after["re"] == before["re"]


def test_lease_lost_is_a_distinct_error_type_from_concurrent_transition(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    assert not issubclass(LeaseLost, ConcurrentTransition)
    assert not issubclass(ConcurrentTransition, LeaseLost)

    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)
    re_id = _snapshot(real_session_factory, run_id)["re"][0]

    # token wrong, status right -> LeaseLost (and not a ConcurrentTransition)
    _overwrite_owner_token(real_session_factory, run_id)
    session = real_session_factory()
    try:
        with pytest.raises(LeaseLost) as lease_lost:
            apply_transition(
                session,
                run_id=run_id,
                expected_status=RunStatus.BA,
                next_status=RunStatus.COMPLETED,
                next_current_role=None,
                next_current_step=None,
                role_execution=_completed_update(re_id),
                events=_TERMINAL_EVENTS,
                expected_owner_token=my_token,
            )
    finally:
        session.close()
    assert not isinstance(lease_lost.value, ConcurrentTransition)

    # status wrong -> ConcurrentTransition (and not a LeaseLost)
    session = real_session_factory()
    try:
        with pytest.raises(ConcurrentTransition) as concurrent:
            apply_transition(
                session,
                run_id=run_id,
                expected_status=RunStatus.CREATED,  # stale -- the run is BA
                next_status=RunStatus.COMPLETED,
                next_current_role=None,
                next_current_step=None,
                events=[EventWrite(type=EventType.RUN_COMPLETED, payload={})],
                expected_owner_token=my_token,
            )
    finally:
        session.close()
    assert not isinstance(concurrent.value, LeaseLost)


def test_the_fence_holds_when_the_expected_status_is_exactly_right(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    """Pitfall 2 directly: the in-memory flag races the worker call returning, so
    the commit must be independently protected. Here the status is exactly what
    the caller expected -- the only thing that fails is the token -- and every
    field of the latest role-execution row is asserted unchanged."""
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)
    _overwrite_owner_token(real_session_factory, run_id)

    session = real_session_factory()
    try:
        run = session.get(Run, run_id)
        # the caller's expected status genuinely holds -- only the token is wrong
        assert run is not None
        assert run.status is RunStatus.BA
        latest = session.scalar(
            select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert latest is not None
        pre = (
            latest.status,
            latest.result,
            latest.error,
            latest.worker_session_id,
            latest.updated_at,
        )
        re_id = latest.id
        event_count = session.scalar(
            select(sa.func.count())
            .select_from(RunEvent)
            .where(RunEvent.run_id == run_id)
        )
    finally:
        session.close()

    session = real_session_factory()
    try:
        with pytest.raises(LeaseLost):
            apply_transition(
                session,
                run_id=run_id,
                expected_status=RunStatus.BA,
                next_status=RunStatus.COMPLETED,
                next_current_role=None,
                next_current_step=None,
                role_execution=_completed_update(re_id),
                events=_TERMINAL_EVENTS,
                expected_owner_token=my_token,
            )
    finally:
        session.close()

    session = real_session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None and run.status is RunStatus.BA
        latest = session.scalar(
            select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert latest is not None
        assert (
            latest.status,
            latest.result,
            latest.error,
            latest.worker_session_id,
            latest.updated_at,
        ) == pre
        assert (
            session.scalar(
                select(sa.func.count())
                .select_from(RunEvent)
                .where(RunEvent.run_id == run_id)
            )
            == event_count
        )
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# The abort, through the runner
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("use_lease_settings")
def test_a_lease_taken_while_the_worker_call_is_in_flight_aborts_persists_nothing(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    """The realistic path: a real ``run_lease`` under the short (2 s / 1 s) lease
    settings with its genuine daemon heartbeat, a worker whose call is slow
    enough to be interrupted, and the run's owner token overwritten from another
    session while the call is in flight. The heartbeat's next renewal matches no
    row, sets the flag, and the step aborts through the runner with nothing
    written."""
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    before = _snapshot(real_session_factory, run_id)

    def steal_mid_step() -> None:
        # the lease is already claimed by the time this runs; overwrite it while
        # the worker call is in flight
        time.sleep(0.8)
        _overwrite_owner_token(real_session_factory, run_id)

    thief = threading.Thread(target=steal_mid_step, name="lease-thief")
    with run_lease(run_id, session_factory=real_session_factory) as handle:
        thief.start()
        with pytest.raises(LeaseLost):
            _advance_once(
                run_id,
                session_factory=real_session_factory,
                registry=fake_worker_registry([_COMPLETED], sleep_ms=4000),
                pipeline=DEFAULT_PIPELINE,
                lease=handle,
            )
    thief.join()

    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA
    assert after["events"] == before["events"]
    assert after["re"] == before["re"]
    # the heartbeat noticed the loss, not only the commit-time fence
    assert handle.lease_lost.is_set()


def test_the_in_memory_flag_alone_aborts_the_step_before_any_write(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    """Flag set, token still matches the row. The abort must happen on the flag
    alone, before ``apply_transition`` is ever called -- so removing the
    commit-time fence would still leave this test green."""
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)
    before = _snapshot(real_session_factory, run_id)

    lost = threading.Event()
    lost.set()
    handle = LeaseHandle(token=my_token, lease_lost=lost)  # token NOT disturbed

    with pytest.raises(LeaseLost):
        _advance_once(
            run_id,
            session_factory=real_session_factory,
            registry=fake_worker_registry([_COMPLETED]),
            pipeline=DEFAULT_PIPELINE,
            lease=handle,
        )

    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA
    assert after["events"] == before["events"]
    assert after["re"] == before["re"]
    assert after["owner_token"] == my_token  # only the flag forced the abort


def test_the_token_fence_alone_aborts_when_the_in_memory_flag_is_missed(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    """Flag clear, token no longer matches. The abort must happen on the fence
    alone, inside ``apply_transition`` -- so removing the in-memory check would
    still leave this test green."""
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)
    _overwrite_owner_token(real_session_factory, run_id)
    before = _snapshot(real_session_factory, run_id)

    handle = LeaseHandle(token=my_token, lease_lost=threading.Event())  # never set

    with pytest.raises(LeaseLost):
        _advance_once(
            run_id,
            session_factory=real_session_factory,
            registry=fake_worker_registry([_COMPLETED]),
            pipeline=DEFAULT_PIPELINE,
            lease=handle,
        )

    after = _snapshot(real_session_factory, run_id)
    assert after["status"] is RunStatus.BA
    assert after["events"] == before["events"]
    assert after["re"] == before["re"]


def test_after_an_abort_the_discarded_step_re_runs_on_the_same_attempt(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    """The whole reason for preferring an abort over a partial write: a discarded
    step is idempotent. After the abort, a fresh claim runs the step again on the
    same attempt number, leaving exactly one role-execution row for the role and
    exactly one completion event."""
    run_id = _run_at_ba(
        real_session_factory, cleanup_runs, fake_worker_registry([_COMPLETED])
    )
    my_token = _claim(real_session_factory, run_id)
    _overwrite_owner_token(real_session_factory, run_id)

    handle = LeaseHandle(token=my_token, lease_lost=threading.Event())
    with pytest.raises(LeaseLost):
        _advance_once(
            run_id,
            session_factory=real_session_factory,
            registry=fake_worker_registry([_COMPLETED]),
            pipeline=DEFAULT_PIPELINE,
            lease=handle,
        )

    # the thief goes away; the run is claimable again
    _clear_lease(real_session_factory, run_id)

    final = advance(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_COMPLETED]),
    )
    assert final is RunStatus.COMPLETED

    session = real_session_factory()
    try:
        ba_rows = list(
            session.scalars(
                select(RoleExecution).where(
                    RoleExecution.run_id == run_id, RoleExecution.role == "BA"
                )
            )
        )
        assert len(ba_rows) == 1
        assert ba_rows[0].attempt == 1  # same attempt, never reset or duplicated

        completion_events = list(
            session.scalars(
                select(RunEvent.type).where(
                    RunEvent.run_id == run_id, RunEvent.type == "ROLE_COMPLETED"
                )
            )
        )
        assert len(completion_events) == 1
    finally:
        session.close()
