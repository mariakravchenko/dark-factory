"""SC3 / STATE-06 / D-11: ``read_status`` reads a run's position from state
columns alone, and its output is provably invariant under a vandalised
``run_events`` table.

The centrepiece is the event-log vandalism sequence: capture the whole
:class:`RunView`, then insert a bogus event, then delete every event for the run,
then rewrite an event's type to an unrecognised string, asserting after each that
the ``RunView`` still compares equal to the first capture. If any of those could
move a single field of what ``status`` reports, the append-only audit log would
silently be the control state and the checkpoint design would be a fiction.

Driven in-process against the provisioned PostgreSQL via ``advance_session_factory``
(the Plan 05 rolled-back-outer-transaction discipline, as a repeatable factory).
"""

from __future__ import annotations

import functools
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import NULL_MARKER, RunView
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.events.redaction import redact
from dark_factory.observability.status import UnknownRunError, read_status
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]
RegistryBuilder = Callable[[list[WorkerResult]], Any]

_EXPECTED_FIELDS = {
    "run_id",
    "source_kind",
    "source_ref",
    "status",
    "current_role",
    "current_step",
    "latest_attempt",
    "created_at",
    "updated_at",
    "base_branch",
    "working_branch",
}


def _completed_run(
    session_factory: SessionFactory, registry_builder: RegistryBuilder
) -> uuid.UUID:
    run_id = start_run("text:where is this run", session_factory=session_factory)
    registry = registry_builder(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="BA analysis complete",
                worker_session_id="fake-status",
            )
        ]
    )
    final = drive(run_id, session_factory=session_factory, registry=registry)
    assert final is RunStatus.COMPLETED
    return run_id


def _table_counts(session_factory: SessionFactory) -> dict[str, int]:
    session = session_factory()
    try:
        return {
            "runs": session.scalar(select(func.count()).select_from(Run)) or 0,
            "role_executions": session.scalar(
                select(func.count()).select_from(RoleExecution)
            )
            or 0,
            "run_events": session.scalar(select(func.count()).select_from(RunEvent))
            or 0,
        }
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# position is read from columns
# --------------------------------------------------------------------------- #


def test_reports_status_role_and_attempt_from_columns(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)

    view = read_status(run_id, session_factory=advance_session_factory)

    assert isinstance(view, RunView)
    assert view.run_id == run_id
    assert view.status is RunStatus.COMPLETED
    assert view.current_role == "BA"
    assert view.latest_attempt == 1
    assert view.source_kind == "text"


def test_unknown_run_id_raises_unknown_run_error(
    advance_session_factory: SessionFactory,
) -> None:
    with pytest.raises(UnknownRunError):
        read_status(uuid.uuid4(), session_factory=advance_session_factory)


def test_run_with_no_role_execution_yet_reports_null_role_and_attempt(
    advance_session_factory: SessionFactory,
) -> None:
    run_id = start_run(
        "text:just created, never advanced", session_factory=advance_session_factory
    )

    view = read_status(run_id, session_factory=advance_session_factory)

    assert view.status is RunStatus.CREATED
    assert view.current_role is None
    assert view.current_step is None
    assert view.latest_attempt is None


def test_runview_exposes_the_full_d12_field_set(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)
    view = read_status(run_id, session_factory=advance_session_factory)

    assert set(type(view).model_fields) == _EXPECTED_FIELDS


# --------------------------------------------------------------------------- #
# invariance under a vandalised event log (the SC3 centrepiece)
# --------------------------------------------------------------------------- #


def test_runview_survives_insert_delete_and_corruption_of_run_events(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)
    baseline = read_status(run_id, session_factory=advance_session_factory)

    # 1. an arbitrary extra event
    session = advance_session_factory()
    try:
        session.add(
            RunEvent(run_id=run_id, type="TOTALLY_BOGUS", payload={"injected": True})
        )
        session.commit()
    finally:
        session.close()
    assert read_status(run_id, session_factory=advance_session_factory) == baseline

    # 2. every event for the run deleted
    session = advance_session_factory()
    try:
        session.execute(delete(RunEvent).where(RunEvent.run_id == run_id))
        session.commit()
    finally:
        session.close()
    assert read_status(run_id, session_factory=advance_session_factory) == baseline

    # 3. re-insert one row and corrupt its type to an unrecognised string
    session = advance_session_factory()
    try:
        session.add(RunEvent(run_id=run_id, type="NONSENSE_NOT_IN_CATALOG", payload={}))
        session.commit()
    finally:
        session.close()
    assert read_status(run_id, session_factory=advance_session_factory) == baseline


def test_runview_correct_with_a_completely_empty_event_log(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        session.execute(delete(RunEvent).where(RunEvent.run_id == run_id))
        session.commit()
    finally:
        session.close()

    view = read_status(run_id, session_factory=advance_session_factory)
    assert view.status is RunStatus.COMPLETED
    assert view.current_role == "BA"
    assert view.latest_attempt == 1


# --------------------------------------------------------------------------- #
# the read model writes nothing
# --------------------------------------------------------------------------- #


def test_read_status_performs_no_write(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)

    session = advance_session_factory()
    try:
        updated_at_before = session.get(Run, run_id).updated_at  # type: ignore[union-attr]
    finally:
        session.close()
    counts_before = _table_counts(advance_session_factory)

    for _ in range(3):
        read_status(run_id, session_factory=advance_session_factory)

    session = advance_session_factory()
    try:
        updated_at_after = session.get(Run, run_id).updated_at  # type: ignore[union-attr]
    finally:
        session.close()
    counts_after = _table_counts(advance_session_factory)

    assert updated_at_after == updated_at_before
    assert counts_after == counts_before


# --------------------------------------------------------------------------- #
# rendering: field list shape + source redaction in both modes
# --------------------------------------------------------------------------- #


def test_as_text_renders_one_line_per_field_including_the_branch_fields(
    advance_session_factory: SessionFactory,
    fake_worker_registry: RegistryBuilder,
) -> None:
    run_id = _completed_run(advance_session_factory, fake_worker_registry)
    view = read_status(run_id, session_factory=advance_session_factory)

    lines = view.as_text().splitlines()
    assert len(lines) == len(_EXPECTED_FIELDS)
    keys = {line.split(":", 1)[0] for line in lines}
    assert keys == _EXPECTED_FIELDS
    assert all(re.match(r"^\w+: ", line) for line in lines)
    # base_branch / working_branch are shown even though null until Phase 5
    assert f"base_branch: {NULL_MARKER}" in lines
    assert f"working_branch: {NULL_MARKER}" in lines


def test_source_reference_is_redacted_in_both_render_modes(
    advance_session_factory: SessionFactory,
) -> None:
    run_id = uuid.uuid4()
    session = advance_session_factory()
    try:
        session.add(
            Run(
                id=run_id,
                source_kind="text",
                source_ref="postgresql://u:sup3rsecretpw@db.example:5432/prod",
                normalized_task={"source_kind": "text", "body": "x"},
                workflow={"roles": ["BA"]},
                status=RunStatus.CREATED,
                current_role=None,
                current_step=None,
            )
        )
        session.commit()
    finally:
        session.close()

    view = read_status(run_id, session_factory=advance_session_factory)
    redactor = functools.partial(redact, known_secrets={})

    text = view.as_text(redactor=redactor)
    payload = view.as_json(redactor=redactor)

    assert "sup3rsecretpw" not in text
    assert "sup3rsecretpw" not in payload
    assert "[redacted:database_url]" in text
    assert '"source_ref": "[redacted:database_url]"' in payload
