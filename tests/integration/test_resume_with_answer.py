"""SC2: a brand-new process resumes a paused run with ``resume --answer``.

The first process pauses on a scripted ``NEEDS_INPUT`` result (as in
``test_pause_exit_zero``). A second, entirely separate process -- its environment
carries nothing from the first but the database URL -- runs
``resume <run-id> --answer "<distinctive answer>"`` and drives the same run to a
terminal state:

* it exits 0 and the run reaches ``COMPLETED``;
* the ``human_interactions`` row is ``ANSWERED`` with the stored answer and an
  ``answered_at`` timestamp;
* the ``role_executions`` row is the *same* row with the *same* attempt number;
* the total number of ``runs`` rows is unchanged across the whole cycle;
* the audit trail contains ``HUMAN_ANSWER_RECEIVED`` immediately followed by
  ``RUN_RESUMED``.

Two negative cases run as separate subprocess invocations: ``resume --answer``
against a run that is not waiting exits 2 with "not waiting" on stderr, and a
second ``resume --answer`` for the same pause also exits 2 -- the answer is
accept-once.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import TERMINAL_STATUSES
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from tests.support.subprocess_runner import child_env, run_id_from_stdout, spawn

pytestmark = pytest.mark.integration

_QUESTION = "Which database?"
_ANSWER = "Use the primary Postgres cluster"
_SESSION_ID = "fake-resume-tracer-001"

_PAUSE_SCRIPT = [
    {
        "status": "NEEDS_INPUT",
        "questions": [_QUESTION],
        "worker_session_id": _SESSION_ID,
    },
]
_RESUME_SCRIPT = [
    {
        "status": "COMPLETED",
        "summary": "resumed and finished",
        "worker_session_id": _SESSION_ID,
    },
]


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def _pause_a_run(pg_url: str, cwd: Path) -> UUID:
    proc = spawn(
        ["run", "text:pause then resume with an answer"],
        child_env(pg_url, fake_script=_PAUSE_SCRIPT),
        cwd=cwd,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert "BA → WAITING_HUMAN" in proc.stdout, proc.stdout
    return run_id_from_stdout(proc.stdout)


def test_a_fresh_process_resumes_the_same_run_and_attempt_with_an_answer(
    pg_url: str, engine: Engine, config_root: Path
) -> None:
    # A throwaway one-role [BA] config tree: this repo's own shipped
    # .dark-factory.yaml ships a real two-role pipeline whose BA declares
    # machine-artifact outputs the scripted resume result does not supply.
    run_id = _pause_a_run(pg_url, config_root)

    with Session(engine) as session:
        re_before = session.scalar(
            select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert re_before is not None
        re_id_before = re_before.id
        attempt_before = re_before.attempt
    runs_before = _count_runs(engine)

    resume_env = child_env(pg_url, fake_script=_RESUME_SCRIPT)
    assert "DARK_FACTORY_CRASH_AFTER" not in resume_env
    resume_proc = spawn(
        ["resume", str(run_id), "--answer", _ANSWER], resume_env, cwd=config_root
    )
    assert resume_proc.returncode == 0, (
        f"stdout={resume_proc.stdout!r}\nstderr={resume_proc.stderr!r}"
    )

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status in TERMINAL_STATUSES
        assert run.status.value == "COMPLETED"

        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        (re_after,) = execs
        assert re_after.id == re_id_before
        assert re_after.attempt == attempt_before

        interaction = session.scalar(
            select(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )
        assert interaction is not None
        assert interaction.status.value == "ANSWERED"
        assert interaction.answer is not None
        assert _ANSWER in interaction.answer
        assert interaction.answered_at is not None

        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert "HUMAN_ANSWER_RECEIVED" in events
        received = events.index("HUMAN_ANSWER_RECEIVED")
        assert events[received + 1] == "RUN_RESUMED"

    assert _count_runs(engine) == runs_before


def test_resume_answer_against_a_non_waiting_run_exits_two(
    pg_url: str, config_root: Path
) -> None:
    proc = spawn(
        ["run", "text:this run just completes"], child_env(pg_url), cwd=config_root
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    run_id = run_id_from_stdout(proc.stdout)

    bad = spawn(
        ["resume", str(run_id), "--answer", "too late"],
        child_env(pg_url),
        cwd=config_root,
    )
    assert bad.returncode == 2, f"stdout={bad.stdout!r}\nstderr={bad.stderr!r}"
    assert "not waiting" in bad.stderr
    assert "Traceback" not in bad.stderr


def test_a_second_answer_for_the_same_pause_is_rejected(
    pg_url: str, config_root: Path
) -> None:
    run_id = _pause_a_run(pg_url, config_root)

    first = spawn(
        ["resume", str(run_id), "--answer", _ANSWER],
        child_env(pg_url, fake_script=_RESUME_SCRIPT),
        cwd=config_root,
    )
    assert first.returncode == 0, f"stdout={first.stdout!r}\nstderr={first.stderr!r}"

    second = spawn(
        ["resume", str(run_id), "--answer", "answering again"],
        child_env(pg_url, fake_script=_RESUME_SCRIPT),
        cwd=config_root,
    )
    assert second.returncode == 2, f"stdout={second.stdout!r}\nstderr={second.stderr!r}"
    assert "not waiting" in second.stderr
