"""SC3: two real processes race the same run -- exactly one executes the step,
the other exits 0 cleanly without changing status and without duplicating work.

Two operating-system processes sharing only PostgreSQL. An in-process simulation
would share module state, a warm engine and an identity map and could pass while
the real thing fails; single-owner execution is precisely a claim about what two
processes can observe of each other.

**Scenario 1 -- deterministic loser.** The first process runs a deliberately
slow step (``DARK_FACTORY_FAKE_SLEEP_MS``) long enough that it is unambiguously
still inside the worker call, holding the lease, by the time the second process
-- itself a fresh interpreter that must cold-start and open its own connections
-- reaches its claim. Synchronisation onto "the first child is inside the role
with the lease held" is by polling the database through the shared ``wait_for``
helper, never a fixed sleep; the slow step's duration is only a generous upper
bound on the loser's time-to-claim, not a timing assertion. The second process
runs ``resume``, loses the claim, prints the CLI's owned-by-another-process
notice on stderr, and exits 0 without writing. After the race the run has exactly
one ROLE_COMPLETED event and exactly one BA role-execution row at attempt 1.

**Scenario 2 -- tight race.** Both processes start back-to-back against a freshly
created, not-yet-advanced run, with no slow step. Either may win, so the
assertions are on the invariants -- at most one advanced, exactly one
ROLE_COMPLETED event, exactly one BA row at attempt 1, neither process exited
non-zero -- never on which process won; pinning the winner would assert a
scheduling accident.

Every child carries a bounded timeout so a hang fails loudly rather than stalling
the suite.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.orchestrator.runner import start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.subprocess_runner import (
    child_env,
    popen,
    run_id_from_stdout,
    spawn,
    wait_for,
)

pytestmark = pytest.mark.integration

# A generous upper bound on how long the losing child needs to cold-start a fresh
# interpreter, open its connections and reach ``claim_lease`` -- not a timing
# assertion. The winner is synchronised on an observable database condition, not
# on this number; it only has to outlast the loser's startup.
_SLOW_STEP_MS = 15000
_CHILD_TIMEOUT = 60
_COMPLETED_ONCE = [
    {
        "status": "COMPLETED",
        "summary": "did the one step",
        "worker_session_id": "fake-race-001",
    }
]


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def _role_held(engine: Engine, run_id: UUID) -> Callable[[], bool]:
    def predicate() -> bool:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is None:
                return False
            return run.status.value == "BA" and run.owner_token is not None

    predicate.__name__ = f"run {run_id} inside BA with the lease held"
    return predicate


def _drain(
    proc: subprocess.Popen[str], *, first_line: str = ""
) -> subprocess.CompletedProcess[str]:
    out, err = proc.communicate(timeout=_CHILD_TIMEOUT)
    return subprocess.CompletedProcess(
        proc.args, proc.returncode or 0, first_line + out, err
    )


def _ba_rows(session: Session, run_id: UUID) -> list[RoleExecution]:
    return list(
        session.scalars(
            select(RoleExecution).where(
                RoleExecution.run_id == run_id, RoleExecution.role == "BA"
            )
        )
    )


def _role_completed_events(session: Session, run_id: UUID) -> list[str]:
    return list(
        session.scalars(
            select(RunEvent.type).where(
                RunEvent.run_id == run_id, RunEvent.type == "ROLE_COMPLETED"
            )
        )
    )


def test_two_processes_race_one_advances_the_other_exits_zero_without_writing(
    pg_url: str, engine: Engine
) -> None:
    p1 = popen(
        ["run", "text:only one of us may execute this step"],
        child_env(pg_url, fake_script=_COMPLETED_ONCE, fake_sleep_ms=_SLOW_STEP_MS),
    )
    try:
        assert p1.stdout is not None
        first_line = p1.stdout.readline()
        run_id = run_id_from_stdout(first_line)

        # wait until the first child genuinely holds the lease inside the role
        wait_for(_role_held(engine, run_id), timeout=20)

        runs_before_loser = _count_runs(engine)
        # the second process runs while the first is still mid-step
        loser = spawn(
            ["resume", str(run_id)], child_env(pg_url), timeout=_CHILD_TIMEOUT
        )
        runs_after_loser = _count_runs(engine)

        winner = _drain(p1, first_line=first_line)
    finally:
        if p1.poll() is None:
            p1.kill()

    assert winner.returncode == 0, f"stdout={winner.stdout!r}\nstderr={winner.stderr!r}"
    assert loser.returncode == 0, f"stdout={loser.stdout!r}\nstderr={loser.stderr!r}"

    # exactly one printed a transition line for the step
    assert "BA → COMPLETED" in winner.stdout
    assert "→" not in loser.stdout

    # the loser named the owning process on stderr, with no traceback either side
    assert "is owned by another process" in loser.stderr
    assert "Traceback" not in loser.stderr
    assert "Traceback" not in winner.stderr

    # the loser mutated nothing while it ran
    assert runs_after_loser == runs_before_loser

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        ba_rows = _ba_rows(session, run_id)
        assert len(ba_rows) == 1
        assert ba_rows[0].attempt == 1
        assert len(_role_completed_events(session, run_id)) == 1

    assert _count_runs(engine) == runs_before_loser


def test_a_tight_race_from_creation_still_yields_one_execution(
    pg_url: str, engine: Engine
) -> None:
    def _factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    run_id = start_run("text:tight race with no slow step", session_factory=_factory)
    runs_before = _count_runs(engine)

    a = popen(["resume", str(run_id)], child_env(pg_url))
    b = popen(["resume", str(run_id)], child_env(pg_url))
    try:
        ra = _drain(a)
        rb = _drain(b)
    finally:
        for proc in (a, b):
            if proc.poll() is None:
                proc.kill()

    assert ra.returncode == 0, f"stdout={ra.stdout!r}\nstderr={ra.stderr!r}"
    assert rb.returncode == 0, f"stdout={rb.stdout!r}\nstderr={rb.stderr!r}"
    assert "Traceback" not in ra.stderr
    assert "Traceback" not in rb.stderr

    # at most one advanced -- assert on the invariant, not on which one won
    advanced = ["BA → COMPLETED" in ra.stdout, "BA → COMPLETED" in rb.stdout]
    assert advanced.count(True) <= 1

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        ba_rows = _ba_rows(session, run_id)
        assert len(ba_rows) == 1
        assert ba_rows[0].attempt == 1
        assert len(_role_completed_events(session, run_id)) == 1

    assert _count_runs(engine) == runs_before
