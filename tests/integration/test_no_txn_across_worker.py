"""HITL-08: no database transaction is ever *held open* while the worker call runs.

Proved from the server's own activity view, not by reading the source. While a
deliberately slow ``FakeWorker`` is mid-call in a real ``dark-factory`` process,
no backend belonging to this application has a transaction that has been open for
more than a few seconds. This is why a slow step needs a heartbeat rather than a
held lock: ownership is a lease column with a database-clock expiry, not a row
lock held for the duration of the step.

The engine names itself ``dark-factory`` to PostgreSQL via ``connect_args``
(plan 02-02); the test's own connection is deliberately unlabelled, so the
activity-view filter counts the application's backends and never the test's own.
The runner closes its read session before calling the worker and opens the write
session only for the commit, so during the worker call there is typically no
``dark-factory`` backend at all. The heartbeat renews on its own session with a
sub-second ``with session.begin(): UPDATE ...`` per beat; against the remote
endpoint the commit round-trip of one such beat can be caught as a *transient*
``idle in transaction`` (the plan anticipates this -- "may be non-zero only
transiently"), so the assertion is on a transaction that has *lingered*: a
transaction genuinely spanning the multi-second worker call would show an
``xact_start`` many seconds in the past, a renewal beat never does.

A cheap positive companion assertion sits beside it: the session handed to each
mutation helper is not inside a transaction once the helper returns -- the same
invariant stated the other way round.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from dark_factory.persistence.mutations import (
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)
from tests.support.subprocess_runner import (
    child_env,
    popen,
    run_id_from_stdout,
    wait_for,
)

pytestmark = pytest.mark.integration

# Wide enough that the worker call is unambiguously in flight for many samples.
# The 6 s / 2 s lease keeps Open Decision 2's TTL/3 ratio while leaving margin for
# the remote endpoint's ~1.5 s renewal round-trip (see test_heartbeat_slow_step).
_SLOW_STEP_MS = 12000
_TTL_SECONDS = 6
_HEARTBEAT_SECONDS = 2
_CHILD_TIMEOUT = 120

_COMPLETED_ONCE = [
    {
        "status": "COMPLETED",
        "summary": "the slow step",
        "worker_session_id": "fake-no-txn-001",
    }
]

# A "lingering" transaction is one held open across the worker call -- exactly
# the T-02-27 threat. A heartbeat renewal beat is sub-second, so a transaction
# whose ``xact_start`` is older than this is not a beat: it is a transaction that
# has spanned real work. Run from the test's own unlabelled connection, which is
# therefore never itself counted.
_LINGER_SECONDS = 3

_LINGERING_TXN_OF_THIS_APP = sa.text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE application_name = 'dark-factory' "
    "AND state LIKE 'idle in transaction%' "
    "AND xact_start < now() - (:linger * interval '1 second')"
)

# The raw count, for the narrative: transient beats may show here.
_IDLE_IN_TXN_OF_THIS_APP = sa.text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE application_name = 'dark-factory' "
    "AND state LIKE 'idle in transaction%'"
)


def _lingering_txn_count(engine: Engine) -> int:
    with engine.connect() as conn:
        value = conn.execute(
            _LINGERING_TXN_OF_THIS_APP, {"linger": _LINGER_SECONDS}
        ).scalar_one()
    return int(value)


def _idle_in_txn_count(engine: Engine) -> int:
    with engine.connect() as conn:
        value = conn.execute(_IDLE_IN_TXN_OF_THIS_APP).scalar_one()
    return int(value)


def _owned_and_running(engine: Engine, run_id: UUID) -> Callable[[], bool]:
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


def test_zero_backends_of_this_application_are_idle_in_transaction_during_the_call(
    pg_url: str, engine: Engine
) -> None:
    owner = popen(
        ["run", "text:no transaction may span the worker call"],
        child_env(
            pg_url,
            fake_script=_COMPLETED_ONCE,
            fake_sleep_ms=_SLOW_STEP_MS,
            lease_ttl_seconds=_TTL_SECONDS,
            lease_heartbeat_seconds=_HEARTBEAT_SECONDS,
        ),
    )
    try:
        assert owner.stdout is not None
        first_line = owner.stdout.readline()
        run_id = run_id_from_stdout(first_line)

        wait_for(_owned_and_running(engine, run_id), timeout=40)

        lingering: list[int] = []
        raw: list[int] = []
        deadline = time.monotonic() + _SLOW_STEP_MS / 1000 + 30
        while owner.poll() is None and time.monotonic() < deadline:
            lingering.append(_lingering_txn_count(engine))
            raw.append(_idle_in_txn_count(engine))
            time.sleep(0.2)

        won = _drain(owner, first_line=first_line)
    finally:
        if owner.poll() is None:
            owner.kill()

    assert won.returncode == 0, f"stdout={won.stdout!r}\nstderr={won.stderr!r}"
    assert "BA → COMPLETED" in won.stdout
    assert "Traceback" not in won.stderr

    # sampled repeatedly across the worker call: no transaction of this
    # application has stayed open across the step -- every sample is zero. The
    # raw idle-in-transaction series is kept only for the failure narrative;
    # transient beats there are a heartbeat commit round-trip, not a held lock.
    assert len(lingering) >= 5, f"only {len(lingering)} samples taken during the call"
    assert all(count == 0 for count in lingering), (
        f"a dark-factory transaction lingered > {_LINGER_SECONDS}s during the "
        f"worker call: lingering={lingering} raw_idle_in_txn={raw}"
    )


@pytest.mark.usefixtures("use_fake_secrets")
def test_a_session_handed_to_a_mutation_helper_is_not_in_a_transaction_afterwards(
    engine: Engine,
) -> None:
    """The invariant stated positively, and it costs nothing to check: both
    ``create_run`` and ``apply_transition`` open exactly one ``with
    session.begin()`` block and make no explicit commit, so the session they are
    handed is out of its transaction the moment they return."""
    session = Session(bind=engine, expire_on_commit=False)
    run_id: UUID | None = None
    try:
        task = NormalizedTask(source_kind="text", source_ref=None, title="t", body="b")
        run_id = create_run(session, task=task, workflow={"roles": ["BA"]})
        assert not session.in_transaction()

        apply_transition(
            session,
            run_id=run_id,
            expected_status=RunStatus.CREATED,
            next_status=RunStatus.BA,
            next_current_role="BA",
            next_current_step=0,
            role_execution=RoleExecutionWrite(
                mode="insert", role="BA", worker="fake", status="RUNNING"
            ),
            events=[EventWrite(type=EventType.ROLE_STARTED, payload={"role": "BA"})],
        )
        assert not session.in_transaction()
    finally:
        session.rollback()
        session.close()
        if run_id is not None:
            with engine.begin() as conn:
                conn.execute(sa.delete(RunEvent).where(RunEvent.run_id == run_id))
                conn.execute(
                    sa.delete(RoleExecution).where(RoleExecution.run_id == run_id)
                )
                conn.execute(sa.delete(Run).where(Run.id == run_id))
