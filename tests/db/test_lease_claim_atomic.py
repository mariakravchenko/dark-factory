"""HITL-07 at the statement level: N concurrent claims against one run yield
exactly one token.

Mutual exclusion here is a property of the single conditional
``UPDATE ... RETURNING`` inside :func:`dark_factory.orchestrator.lease.claim_lease`
-- not of anything in Python. Sixteen threads, each with its **own** ``Session``
(a ``Session`` is not thread-safe, and a shared one would prove nothing about two
processes anyway), call the real ``claim_lease`` against one unowned run; exactly
one comes back with a token and fifteen come back with nothing, and the run's
stored ``owner_token`` equals that one token.

The same assertions hold for a run whose ``lock_expires_at`` has been forced into
the past -- an expired lease is claimable by exactly one *new* owner, not by all
of them, and the winning token differs from the first round's. A run in a
terminal status is claimable by nobody, even while unowned. Renewal and release
are token-fenced: only the owning token moves or clears the lease, and a token
that was never issued changes the row not at all.

Every fixture row is deleted at teardown (the ``cleanup_runs`` idiom from
``tests/db/test_transition_atomic.py``). No process wall clock is read anywhere
in this file -- every expiry value and every expiry comparison lives inside
``claim_lease`` / ``renew_lease`` as a server-clock SQL expression.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.lease import claim_lease, release_lease, renew_lease
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from tests.support.config import DEFAULT_TEST_SNAPSHOT

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

_THREADS = 16
_TTL = 900

SessionFactory = Callable[[], Session]


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    """A production-shaped session factory: a fresh ``Session`` on the real engine
    per call, committing for real (``NullPool`` discards the connection on close).
    One per thread -- never shared."""

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


def _claim_from_n_threads(
    factory: SessionFactory, run_id: uuid.UUID, *, n: int = _THREADS
) -> list[uuid.UUID]:
    """Start ``n`` threads that each open their own session, rendezvous on a
    barrier to maximise overlap, then call the real ``claim_lease`` once. Return
    the list of non-``None`` tokens handed out."""
    results: list[uuid.UUID | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker() -> None:
        session = factory()
        try:
            barrier.wait(timeout=15)
            token = claim_lease(session, run_id, ttl_seconds=_TTL)
        finally:
            session.close()
        with lock:
            results.append(token)

    threads = [threading.Thread(target=worker, name=f"claimer-{i}") for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a claim thread hung"

    assert len(results) == n
    return [token for token in results if token is not None]


def test_sixteen_concurrent_claims_on_one_unowned_run_yield_exactly_one_token(
    real_session_factory: SessionFactory, cleanup_runs: list[Any]
) -> None:
    run_id = start_run(
        "text:only one owner",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    tokens = _claim_from_n_threads(real_session_factory, run_id)
    assert len(tokens) == 1

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.owner_token == tokens[0]
        server_now = session.scalar(select(func.now()))
        assert server_now is not None
        assert run.lock_expires_at is not None
        assert run.lock_expires_at > server_now


def test_a_forced_expired_run_is_reclaimed_by_exactly_one_new_owner(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    force_lease_expiry: Callable[[uuid.UUID], None],
) -> None:
    run_id = start_run(
        "text:expired then reclaimed once",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    first_round = _claim_from_n_threads(real_session_factory, run_id)
    assert len(first_round) == 1

    force_lease_expiry(run_id)

    second_round = _claim_from_n_threads(real_session_factory, run_id)
    assert len(second_round) == 1
    # an expired lease is claimable by exactly one *new* owner
    assert second_round[0] != first_round[0]

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.owner_token == second_round[0]


def test_a_terminal_run_is_claimable_by_nobody_even_while_unowned(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    fake_worker_registry: Callable[..., Any],
) -> None:
    run_id = start_run(
        "text:this run completes",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    registry = fake_worker_registry(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="done",
                worker_session_id="fake-lease-atomic",
            )
        ]
    )
    final = drive(run_id, session_factory=real_session_factory, registry=registry)
    assert final is RunStatus.COMPLETED

    tokens = _claim_from_n_threads(real_session_factory, run_id)
    assert tokens == []

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.owner_token is None
        assert run.lock_expires_at is None


def test_renewal_moves_the_lease_only_for_the_owning_token(
    real_session_factory: SessionFactory, cleanup_runs: list[Any]
) -> None:
    run_id = start_run(
        "text:renew fencing",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    with real_session_factory() as session:
        token = claim_lease(session, run_id, ttl_seconds=_TTL)
    assert token is not None

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        expiry_after_claim = run.lock_expires_at
    assert expiry_after_claim is not None

    # a renewal with the winning token returns True and pushes the expiry forward
    with real_session_factory() as session:
        assert renew_lease(session, run_id, token, ttl_seconds=_TTL) is True

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.lock_expires_at is not None
        assert run.lock_expires_at >= expiry_after_claim
        after_good_renew = (run.owner_token, run.lock_expires_at, run.updated_at)

    # a renewal with a token that was never issued returns False and changes nothing
    stranger = uuid.uuid4()
    with real_session_factory() as session:
        assert renew_lease(session, run_id, stranger, ttl_seconds=_TTL) is False

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert (
            run.owner_token,
            run.lock_expires_at,
            run.updated_at,
        ) == after_good_renew


def test_release_clears_the_lease_only_for_the_owning_token_then_a_fresh_claim_wins(
    real_session_factory: SessionFactory, cleanup_runs: list[Any]
) -> None:
    run_id = start_run(
        "text:release fencing",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    with real_session_factory() as session:
        token = claim_lease(session, run_id, ttl_seconds=_TTL)
    assert token is not None

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        before_bad_release = (run.owner_token, run.lock_expires_at, run.updated_at)

    # a release attempted with a non-owning token changes nothing
    stranger = uuid.uuid4()
    with real_session_factory() as session:
        release_lease(session, run_id, stranger)
    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert (
            run.owner_token,
            run.lock_expires_at,
            run.updated_at,
        ) == before_bad_release

    # a release with the winning token nulls both columns
    with real_session_factory() as session:
        release_lease(session, run_id, token)
    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.owner_token is None
        assert run.lock_expires_at is None

    # and a fresh claim then succeeds immediately, with a different token
    with real_session_factory() as session:
        again = claim_lease(session, run_id, ttl_seconds=_TTL)
    assert again is not None
    assert again != token
