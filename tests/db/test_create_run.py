"""`create_run` — one transaction, one commit, redaction inside (Plan 01-05, Task 1).

Every test runs inside the rolled-back ``db_session`` outer transaction.
``use_fake_secrets`` swaps ``mutations.get_settings`` for a ``Settings`` built
from obviously-fake credentials, so ``known_secret_values()`` returns a known map
without any real secret entering the test process.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence import mutations
from dark_factory.persistence.models import Run, RunEvent
from dark_factory.persistence.mutations import create_run

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]


def _task(**over: object) -> NormalizedTask:
    kw: dict[str, object] = {
        "source_kind": "text",
        "source_ref": None,
        "title": "t",
        "body": "do the thing",
        "metadata": {},
    }
    kw.update(over)
    return NormalizedTask(**kw)


def test_create_run_inserts_created_row_and_one_run_created_event(
    db_session: Session,
) -> None:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})

    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.status is RunStatus.CREATED
    assert run.current_role is None
    assert run.current_step is None
    assert run.workflow == {"roles": ["BA"]}

    events = db_session.scalars(select(RunEvent).where(RunEvent.run_id == run_id)).all()
    assert [e.type for e in events] == [EventType.RUN_CREATED.value]


def test_create_run_returns_a_uuid_that_resolves_to_a_row(db_session: Session) -> None:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})
    assert db_session.get(Run, run_id) is not None


def test_mutations_module_never_calls_session_commit() -> None:
    src = inspect.getsource(mutations)
    assert "session.commit(" not in src


def test_create_run_leaves_both_iteration_counters_at_zero(db_session: Session) -> None:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})
    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.qa_developer_iterations == 0
    assert run.quality_gate_iterations == 0


def test_persisted_task_text_scrubs_known_value_only_not_generic_uri_talk(
    db_session: Session, fake_settings: Settings
) -> None:
    live = fake_settings.database_url.get_secret_value()
    run_id = create_run(
        db_session,
        task=_task(
            body=f"use {live} to connect; note that postgresql:// URIs are fine to discuss"
        ),
        workflow={"roles": ["BA"]},
    )

    run = db_session.get(Run, run_id)
    assert run is not None
    stored = run.normalized_task["body"]
    assert live not in stored
    assert "[redacted:database_url]" in stored
    # D-18: generic connection-string wording is NOT pattern-scrubbed in task text
    assert "postgresql:// URIs are fine to discuss" in stored


def test_run_created_event_payload_is_pattern_redacted(db_session: Session) -> None:
    run_id = create_run(
        db_session,
        task=_task(source_ref="postgresql+psycopg://user:hunter2@host:5432/db"),
        workflow={"roles": ["BA"]},
    )

    ev = db_session.scalars(select(RunEvent).where(RunEvent.run_id == run_id)).one()
    assert "hunter2" not in str(ev.payload)
    assert "redacted" in str(ev.payload)
