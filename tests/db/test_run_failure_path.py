"""The FAILED terminal arm, driven in-process against real PostgreSQL (D-05, D-10).

A ``FakeWorker`` scripted to return a FAILED :class:`WorkerResult` drives the run
to ``FAILED`` with ``current_role`` retained, persists ROLE_FAILED + RUN_FAILED,
stores the failure detail in ``role_executions.error``, and updates the single
attempt row in place -- the failure never creates a second attempt.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = pytest.mark.db

SessionFactory = Callable[[], Session]
RegistryBuilder = Callable[[list[WorkerResult]], Any]


def _drive_failing_run(
    session_factory: SessionFactory, registry_builder: RegistryBuilder
) -> Any:
    run_id = start_run("text:make this fail", session_factory=session_factory)
    registry = registry_builder(
        [
            WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="analysis could not be completed",
                error="boom-detail-42",
            )
        ]
    )
    final = drive(run_id, session_factory=session_factory, registry=registry)
    assert final is RunStatus.FAILED
    return run_id


def test_failed_result_drives_run_to_failed_with_role_retained(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED
        assert run.current_role == "BA"
    finally:
        session.close()


def test_failure_arm_persists_role_failed_and_run_failed_events(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        event_types = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    finally:
        session.close()

    assert event_types == [
        "RUN_CREATED",
        "ROLE_STARTED",
        "ROLE_FAILED",
        "RUN_FAILED",
    ]


def test_failure_updates_the_one_attempt_row_in_place_with_error_detail(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
    finally:
        session.close()

    assert len(execs) == 1
    (execution,) = execs
    assert execution.attempt == 1
    assert execution.status == "FAILED"
    assert execution.result is None
    assert execution.error is not None
    assert "boom-detail-42" in json.dumps(execution.error)


def test_failure_arm_is_two_committed_advance_steps(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        event_count = session.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
    finally:
        session.close()

    # RUN_CREATED (create_run) + ROLE_STARTED (CREATED->BA) + ROLE_FAILED +
    # RUN_FAILED (BA->FAILED): the one-role failure path is two advance steps.
    assert event_count == 4


def test_failed_run_keeps_its_current_step(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.current_step == 0
    finally:
        session.close()


def test_role_started_is_recorded_before_the_failure_events(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
    use_fake_secrets: object,
) -> None:
    run_id = _drive_failing_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        ordered = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    finally:
        session.close()

    assert ordered.index("ROLE_STARTED") < ordered.index("ROLE_FAILED")
    assert ordered.index("ROLE_FAILED") < ordered.index("RUN_FAILED")
