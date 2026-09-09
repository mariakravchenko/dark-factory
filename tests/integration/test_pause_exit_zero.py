"""SC1: a role whose worker returns ``NEEDS_INPUT`` pauses the run.

A real ``dark-factory run`` process is spawned with a two-element fake script --
a ``NEEDS_INPUT`` result carrying a distinctive question and a worker session id,
then a ``COMPLETED`` result. The process must exit 0 with a transition line into
``WAITING_HUMAN`` on stdout.

Then, in a session opened *after* the process has exited, all of SC1 is asserted
as one block, because the failure mode this guards is the pause path forgetting
exactly one of the five writes and leaving a run that is unresumable for a
reason nobody can see:

1. ``runs.status`` is ``WAITING_HUMAN`` and ``runs.current_role`` is retained;
2. both lease columns (``owner_token`` / ``lock_expires_at``) are NULL -- the
   pause is a stop status, so ``apply_transition`` cleared the lease atomically
   with the state change;
3. the latest ``role_executions`` row carries the ``NEEDS_INPUT`` result and the
   worker session id, has status marker ``WAITING_HUMAN`` and its original
   attempt number;
4. exactly one ``human_interactions`` row exists for the run, ``WAITING`` with a
   non-empty question bound to that role-execution row;
5. the audit trail ends with ``QUESTION_CREATED`` then ``RUN_PAUSED``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn

pytestmark = pytest.mark.integration

_QUESTION = "Which database should the health endpoint report on -- primary or replica?"
_SESSION_ID = "fake-needs-input-tracer-001"

_SCRIPT = [
    {
        "status": "NEEDS_INPUT",
        "summary": "need a decision before I can proceed",
        "questions": [_QUESTION],
        "worker_session_id": _SESSION_ID,
    },
    {
        "status": "COMPLETED",
        "summary": "done",
        "worker_session_id": _SESSION_ID,
    },
]


def test_run_pauses_persists_all_five_writes_releases_the_lease_and_exits_zero(
    pg_url: str, engine: Engine
) -> None:
    proc = spawn(
        ["run", "text:pause for a human decision"],
        child_env(pg_url, fake_script=_SCRIPT),
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert "BA → WAITING_HUMAN" in proc.stdout, proc.stdout
    run_id = run_id_from_stdout(proc.stdout)

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        # (1) status + retained role
        assert run.status.value == "WAITING_HUMAN"
        assert run.current_role == "BA"
        # (2) lease released atomically with the pause
        assert run.owner_token is None
        assert run.lock_expires_at is None

        # (3) the latest role-execution row
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        (re_row,) = execs
        assert re_row.status == "WAITING_HUMAN"
        assert re_row.attempt == 1
        assert re_row.worker_session_id == _SESSION_ID
        previous = WorkerResult.model_validate(re_row.result)
        assert previous.status is WorkerResultStatus.NEEDS_INPUT
        assert previous.questions == [_QUESTION]

        # (4) exactly one WAITING interaction, bound to that row
        interactions = list(
            session.scalars(
                select(HumanInteraction).where(HumanInteraction.run_id == run_id)
            )
        )
        assert len(interactions) == 1
        (interaction,) = interactions
        assert interaction.status.value == "WAITING"
        assert interaction.question.strip() != ""
        assert _QUESTION in interaction.question
        assert interaction.role_execution_id == re_row.id
        assert interaction.answer is None
        assert interaction.answered_at is None

        # (5) the audit trail ends QUESTION_CREATED -> RUN_PAUSED
        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert events[-2:] == ["QUESTION_CREATED", "RUN_PAUSED"]
