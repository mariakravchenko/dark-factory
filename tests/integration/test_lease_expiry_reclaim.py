"""SC4: a killed owner's lease is safe from theft until the database clock passes
its expiry, and reclaimable immediately after.

Both halves must hold -- a lease stolen too early is as wrong as one that is
never reclaimable.

**First half -- not stolen before expiry.** A process is killed the instant
``CREATED -> BA`` commits (``DARK_FACTORY_CRASH_AFTER``), while it genuinely holds
an unexpired lease (a comfortably long TTL passed through the child environment).
A second process that tries to ``resume`` before that expiry gets nothing from
its claim, exits 0, and leaves the run's status, owner token, latest
role-execution row and event count all unchanged -- asserted field by field,
because this is the half that would silently pass if the claim predicate were
wrong in the permissive direction.

**Second half -- reclaimed after expiry.** Once ``force_lease_expiry`` ages the
lock past the server clock, a third process claims the run, continues from the
last committed step on the *same* attempt, reaches the terminal state, and the
audit trail carries no duplicate of the event the dead process already
committed.

**Honesty case.** The same reclaim after a genuinely short injected TTL and a
real elapsed wait, with no forcing update at all -- proof that the reclaim is
driven by the database clock passing the stored expiry rather than by the
forcing update being special.

The process-clock time-travel library in the dev dependencies is used nowhere in
this file. It patches only the *test process's* clock, whereas the stored
``lock_expires_at`` and every comparison against it are evaluated inside
PostgreSQL -- so time-travelling the test process would move nothing, and an
assertion built on it would be silently weaker than it looks (02-RESEARCH Pitfall
4). Expiry is reached here only two ways: a server-clock ``UPDATE`` (the fast
primary path) or a real elapsed wait against a short TTL (the honesty check).

No reaper, cron entry or sweeper participates in the reclaim: it happens lazily
on the next claim attempt and nowhere else, asserted structurally at the end.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    run_id_from_stdout,
    spawn,
)

pytestmark = pytest.mark.integration

_CRASH_AT_FIRST_TRANSITION = "CREATED_BA"
_LONG_TTL = 3600  # comfortably longer than this whole test
_SHORT_TTL = 2  # honesty check: a real wait outlasts this
_CHILD_TIMEOUT = 60

_EXPECTED_TERMINAL_TRAIL = [
    "RUN_CREATED",
    "ROLE_STARTED",
    "ROLE_COMPLETED",
    "RUN_COMPLETED",
]


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def _event_trail(engine: Engine, run_id: UUID) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )


def _latest_execution(session: Session, run_id: UUID) -> RoleExecution:
    row = session.scalar(
        select(RoleExecution)
        .where(RoleExecution.run_id == run_id)
        .order_by(
            RoleExecution.created_at.desc(),
            RoleExecution.attempt.desc(),
            RoleExecution.id.desc(),
        )
        .limit(1)
    )
    assert row is not None
    return row


def test_a_killed_owner_is_not_stolen_before_expiry_then_reclaimed_after_forcing(
    pg_url: str,
    engine: Engine,
    force_lease_expiry: Callable[[UUID], None],
    config_root: Path,
) -> None:
    runs_at_start = _count_runs(engine)

    # -- first process: dies the instant CREATED -> BA commits, holding a long lease --
    # A throwaway one-role [BA] config tree: this repo's own shipped
    # .dark-factory.yaml ships a real two-role pipeline whose BA declares
    # machine-artifact outputs the scripted/default worker here does not supply.
    p1 = spawn(
        ["run", "text:killed while holding an unexpired lease"],
        child_env(
            pg_url,
            crash_after=_CRASH_AT_FIRST_TRANSITION,
            lease_ttl_seconds=_LONG_TTL,
        ),
        cwd=config_root,
        timeout=_CHILD_TIMEOUT,
    )
    assert p1.returncode != 0, f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    assert "TimeoutExpired" not in (p1.stdout + p1.stderr)
    run_id = run_id_from_stdout(p1.stdout)

    # -- the committed intermediate state: BA, lease held, expiry in the server future --
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "BA"
        assert run.owner_token is not None
        assert run.lock_expires_at is not None
        server_now = session.scalar(select(func.now()))
        assert server_now is not None
        assert run.lock_expires_at > server_now

        snap_status = run.status.value
        snap_owner = run.owner_token
        snap_expiry = run.lock_expires_at
        latest = _latest_execution(session, run_id)
        snap_re = (latest.id, latest.status, latest.attempt, latest.result)
    snap_trail = _event_trail(engine, run_id)

    # -- second process, before the expiry: gets nothing, exits 0, touches nothing --
    p2 = spawn(
        ["resume", str(run_id)],
        child_env(pg_url, lease_ttl_seconds=_LONG_TTL),
        cwd=config_root,
        timeout=_CHILD_TIMEOUT,
    )
    assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"
    assert "is owned by another process" in p2.stderr
    assert "Traceback" not in p2.stderr

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == snap_status
        assert run.owner_token == snap_owner
        assert run.lock_expires_at == snap_expiry
        latest = _latest_execution(session, run_id)
        assert (latest.id, latest.status, latest.attempt, latest.result) == snap_re
    assert _event_trail(engine, run_id) == snap_trail

    # -- force the expiry past the server clock, then a third process reclaims --
    force_lease_expiry(run_id)
    p3 = spawn(
        ["resume", str(run_id)],
        child_env(pg_url, lease_ttl_seconds=_LONG_TTL),
        cwd=config_root,
        timeout=_CHILD_TIMEOUT,
    )
    assert p3.returncode == 0, f"stdout={p3.stdout!r}\nstderr={p3.stderr!r}"
    assert "BA → COMPLETED" in p3.stdout

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        # reaching a stop status clears the lease
        assert run.owner_token is None
        assert run.lock_expires_at is None
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        assert execs[0].id == snap_re[0]  # same row
        assert execs[0].attempt == snap_re[2]  # same attempt, never reset

    # the dead process had already committed ROLE_STARTED; it must appear once
    final_trail = _event_trail(engine, run_id)
    assert final_trail == _EXPECTED_TERMINAL_TRAIL
    assert final_trail.count("ROLE_STARTED") == 1

    # the whole test created exactly one run
    assert _count_runs(engine) == runs_at_start + 1


def test_the_reclaim_also_works_after_a_genuinely_elapsed_short_ttl_no_forcing(
    pg_url: str, engine: Engine, config_root: Path
) -> None:
    """The forced-expiry test above is the fast primary path; this is the honesty
    check. A short TTL through the child environment, a real wait a little longer
    than it, and a plain ``resume`` with no forcing update -- so the reclaim can
    only be driven by the database clock passing the stored ``lock_expires_at``.
    The wait is bounded and small so the file stays fast.
    """
    runs_at_start = _count_runs(engine)

    p1 = spawn(
        ["run", "text:short ttl, real wait, honest reclaim"],
        child_env(
            pg_url,
            crash_after=_CRASH_AT_FIRST_TRANSITION,
            lease_ttl_seconds=_SHORT_TTL,
            lease_heartbeat_seconds=1,
        ),
        cwd=config_root,
        timeout=_CHILD_TIMEOUT,
    )
    assert p1.returncode != 0, f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    run_id = run_id_from_stdout(p1.stdout)

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "BA"
        assert run.owner_token is not None

    # a real elapsed wait, comfortably past the 2 s TTL
    time.sleep(_SHORT_TTL + 2)

    p2 = spawn(
        ["resume", str(run_id)],
        child_env(pg_url),
        cwd=config_root,
        timeout=_CHILD_TIMEOUT,
    )
    assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"
    assert "BA → COMPLETED" in p2.stdout

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status.value == "COMPLETED"
        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        assert len(execs) == 1
        assert execs[0].attempt == 1

    assert _event_trail(engine, run_id) == _EXPECTED_TERMINAL_TRAIL
    assert _count_runs(engine) == runs_at_start + 1


_LAZY_EXPIRY_FORBIDDEN = (
    re.compile(r"\breaper\b", re.IGNORECASE),
    re.compile(r"\bsweeper\b", re.IGNORECASE),
    re.compile(r"APScheduler"),
    re.compile(r"BackgroundScheduler"),
    re.compile(r"\bcrontab\b", re.IGNORECASE),
    re.compile(r"pg_cron"),
    re.compile(r"\bcron\b", re.IGNORECASE),
)


def test_expiry_is_lazy_there_is_no_reaper_scheduler_or_sweeper() -> None:
    """The entire expiry mechanism is lazy evaluation on the next claim attempt.
    No background process, timer, cron entry or sweeper exists for it anywhere in
    the source tree -- that absence is what makes a crashed owner recoverable
    with no extra moving part."""
    src_root = REPO_ROOT / "src" / "dark_factory"
    offenders: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in _LAZY_EXPIRY_FORBIDDEN:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: /{pattern.pattern}/")
    assert not offenders, (
        "lease expiry must stay lazy (evaluated by the next claim); found "
        "scheduler/reaper/sweeper constructs: " + ", ".join(offenders)
    )
