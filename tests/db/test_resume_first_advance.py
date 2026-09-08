"""The no-carryover proof: ``advance`` reconstructs the run from columns on every
call and retains nothing between calls (STATE-08, RESEARCH Pattern 1).

This is the in-process, fast counterpart to Task 1's subprocess test. Task 1
proves the property once across a real process boundary; this proves it on every
step cheaply, and it is the test that will catch a cached connection or a warm
identity map quietly becoming load-bearing in a later phase.

One run is driven through a single shared engine. A second, identically created
run is driven while a brand-new engine and sessionmaker are constructed
immediately before each ``advance`` call and the previous engine is disposed. If
anything carried across an ``advance`` -- a connection, an identity map, a
module-level object -- the two drives would diverge.

Rows are really committed; ``cleanup_runs`` drops them at teardown.
"""

from __future__ import annotations

import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import dark_factory.orchestrator.runner as runner_module
from dark_factory.domain.status import STOP_STATUSES, RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import advance, run_state, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_SOURCE = "text:reconstruct me from columns every single step"
_COMPLETED = WorkerResult(
    status=WorkerResultStatus.COMPLETED,
    summary="BA analysis complete",
    worker_session_id="fake-nocarry",
)

# Volatile columns that legitimately differ between two runs of the same task.
_VOLATILE_COLUMNS = {"id", "created_at", "updated_at"}


@pytest.fixture
def cleanup_runs(pg_url: str) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        eng = _fresh_engine(pg_url)
        try:
            with eng.begin() as conn:
                conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
                conn.execute(
                    sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids))
                )
                conn.execute(sa.delete(Run).where(Run.id.in_(ids)))
        finally:
            eng.dispose()


def _fresh_engine(pg_url: str) -> Engine:
    """An engine shaped exactly like the production one (engine.py)."""
    return create_engine(
        pg_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
        future=True,
    )


def _factory_for(engine: Engine) -> SessionFactory:
    maker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return lambda: maker()


def _run_columns(session_factory: SessionFactory, run_id: Any) -> dict[str, Any]:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        return {
            column.key: getattr(run, column.key)
            for column in Run.__table__.columns
            if column.key not in _VOLATILE_COLUMNS
        }
    finally:
        session.close()


def _event_types(session_factory: SessionFactory, run_id: Any) -> list[str]:
    session = session_factory()
    try:
        return list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    finally:
        session.close()


def _public_attr_identities(module: types.ModuleType) -> dict[str, int]:
    return {
        name: id(value)
        for name, value in vars(module).items()
        if not name.startswith("_")
    }


def _drive_with_shared_engine(
    pg_url: str, registry: Any
) -> tuple[Any, RunStatus, int, dict[str, Any], list[str]]:
    engine = _fresh_engine(pg_url)
    try:
        session_factory = _factory_for(engine)
        run_id = start_run(_SOURCE, session_factory=session_factory)
        state = run_state(run_id, session_factory=session_factory)
        assert state is not None
        status = state.status
        steps = 0
        while status not in STOP_STATUSES:
            status = advance(run_id, session_factory=session_factory, registry=registry)
            steps += 1
        return (
            run_id,
            status,
            steps,
            _run_columns(session_factory, run_id),
            _event_types(session_factory, run_id),
        )
    finally:
        engine.dispose()


def _drive_with_a_fresh_engine_per_step(
    pg_url: str, registry: Any
) -> tuple[Any, RunStatus, int, dict[str, Any], list[str]]:
    engine = _fresh_engine(pg_url)
    try:
        run_id = start_run(_SOURCE, session_factory=_factory_for(engine))
        state = run_state(run_id, session_factory=_factory_for(engine))
        assert state is not None
        status = state.status
        steps = 0
        while status not in STOP_STATUSES:
            next_engine = _fresh_engine(pg_url)
            engine.dispose()
            engine = next_engine
            status = advance(
                run_id,
                session_factory=_factory_for(engine),
                registry=registry,
            )
            steps += 1
        return (
            run_id,
            status,
            steps,
            _run_columns(_factory_for(engine), run_id),
            _event_types(_factory_for(engine), run_id),
        )
    finally:
        engine.dispose()


def test_a_fresh_engine_per_step_is_indistinguishable_from_a_shared_engine(
    pg_url: str,
    fake_worker_registry: Callable[[list[WorkerResult]], Any],
    cleanup_runs: list[Any],
) -> None:
    before = _public_attr_identities(runner_module)

    shared_id, shared_status, shared_steps, shared_cols, shared_types = (
        _drive_with_shared_engine(pg_url, fake_worker_registry([_COMPLETED]))
    )
    cleanup_runs.append(shared_id)

    fresh_id, fresh_status, fresh_steps, fresh_cols, fresh_types = (
        _drive_with_a_fresh_engine_per_step(pg_url, fake_worker_registry([_COMPLETED]))
    )
    cleanup_runs.append(fresh_id)

    after = _public_attr_identities(runner_module)

    assert shared_status is RunStatus.COMPLETED
    assert fresh_status is RunStatus.COMPLETED
    assert shared_steps == fresh_steps == 2
    assert shared_cols == fresh_cols  # field by field, ids/timestamps excluded
    assert (
        shared_types
        == fresh_types
        == [
            "RUN_CREATED",
            "ROLE_STARTED",
            "ROLE_COMPLETED",
            "RUN_COMPLETED",
        ]
    )
    # nothing at module scope in the orchestrator changed across a full drive
    assert before == after


def test_orchestrator_module_exposes_no_mutable_public_state(
    pg_url: str,
    fake_worker_registry: Callable[[list[WorkerResult]], Any],
    cleanup_runs: list[Any],
) -> None:
    """A full drive must not mutate any module-level object in the orchestrator,
    and there must be no mutable public container for a later step to lean on."""
    mutable_public = {
        name: value
        for name, value in vars(runner_module).items()
        if not name.startswith("_") and isinstance(value, list | dict | set | bytearray)
    }
    assert mutable_public == {}, f"mutable module-level public state: {mutable_public}"

    before = _public_attr_identities(runner_module)
    run_id, status, _, _, _ = _drive_with_shared_engine(
        pg_url, fake_worker_registry([_COMPLETED])
    )
    cleanup_runs.append(run_id)
    assert status is RunStatus.COMPLETED
    assert _public_attr_identities(runner_module) == before
