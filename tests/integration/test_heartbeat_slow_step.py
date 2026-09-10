"""SC5: a role step that runs far longer than the lease TTL keeps its lease.

While the worker call is in flight the owner's daemon heartbeat keeps pushing
``runs.lock_expires_at`` forward, so a competing process's claim ``UPDATE`` keeps
matching zero rows for the whole duration of the step. This is the validation the
roadmap's Open Decision 2 asked for: the shipped defaults are a 900 s TTL and a
300 s heartbeat, and the note on that decision is that the *ratio*
(heartbeat ~= TTL/3), not the absolute value, is what transfers. This file
injects a short TTL and a short heartbeat that keep that ratio and proves it
behaves as claimed, in seconds rather than minutes.

The plan's illustrative values were a 2 s TTL and a 1 s heartbeat. Against the
operator's *remote* Neon endpoint one heartbeat renewal round-trip (open a
session, one ``UPDATE ... RETURNING``, commit, close) measures ~1.4-1.6 s, so a
1 s interval plus a ~1.5 s renewal leaves the 2 s TTL with no margin and a
competitor polling every 0.5 s eventually claims in the gap. The injected values
here are therefore a 6 s TTL and a 2 s heartbeat -- the same TTL/3 ratio, scaled
so ``interval + renewal_latency`` (~3.5 s) sits comfortably inside the TTL. The
step is still more than three times the TTL. The production 300 s / 900 s
defaults have a ~1.5 s renewal inside a 300 s interval and are unaffected; this
scaling is an endpoint-latency accommodation, mirrored on 02-04's 4 s -> 15 s
slow-step adjustment, and is a data point for the plan's production-TTL
``<human-check>``.

Two real operating-system processes sharing only PostgreSQL. An in-process
simulation shares module state, a warm engine and an identity map and could pass
while the real thing fails -- single-owner execution is precisely a claim about
what two processes can observe of each other.

The renewal is proved to be *periodic* -- the recorded expiry strictly increases
several times across the step -- not a single push at claim time. The
release-on-exception path is proved separately and in-process: a ``run_lease``
whose body raises must leave the run immediately claimable, never held for the
remainder of the TTL by a heartbeat thread that outlived its owner's decision.

"Slow" and "dead" are deliberately not distinguished: liveness *is* a freshly
pushed expiry and an owner proves it by renewing. The lease path contains no
process-identity check, no probe of another backend's activity and no
step-duration heuristic -- asserted structurally at the end so a future
contributor who reaches for a liveness probe trips something.
"""

from __future__ import annotations

import itertools
import re
import subprocess
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.orchestrator.lease import claim_lease, run_lease
from dark_factory.orchestrator.runner import start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.config import DEFAULT_TEST_SNAPSHOT
from tests.support.subprocess_runner import (
    REPO_ROOT,
    child_env,
    popen,
    run_id_from_stdout,
    spawn,
    wait_for,
)

pytestmark = pytest.mark.integration

SessionFactory = Callable[[], Session]

# Open Decision 2's TTL/3 ratio, scaled up so one ~1.5 s renewal round-trip plus
# the interval sits well inside the TTL against the remote endpoint (see module
# docstring). The step below is more than three times the TTL.
_TTL_SECONDS = 6
_HEARTBEAT_SECONDS = 2

# A step window comfortably wider than one cold-starting competitor's
# time-to-claim against the shared remote endpoint (~4-5 s per subprocess, see
# 02-04-SUMMARY). The heartbeat's correctness is proved by the advancing expiry,
# not by this number; it only has to outlast the competitors' startup.
_SLOW_STEP_MS = 20000
_CHILD_TIMEOUT = 150

# Competitors are launched only in the first stretch of the step so that even a
# slow cold start reaches ``claim_lease`` while the owner still genuinely holds
# the lease -- never in the tail, where the run may already be terminal. Spaced
# out so the row-lock contention of their claim ``UPDATE``s does not starve the
# owner's heartbeat renewal.
_COMPETITOR_LAUNCH_WINDOW_S = 10.0
_COMPETITOR_INTERVAL_S = 1.5
_MAX_COMPETITORS = 6

_COMPLETED_ONCE = [
    {
        "status": "COMPLETED",
        "summary": "the one slow step",
        "worker_session_id": "fake-heartbeat-001",
    }
]


class _Boom(RuntimeError):
    """Distinctive exception raised inside a ``run_lease`` body."""


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    """A production-shaped session factory: a fresh ``Session`` on the real engine
    per call, committing for real (``NullPool`` discards the connection on
    close)."""

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
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _run_row(engine: Engine, run_id: UUID) -> tuple[str, Any, datetime | None]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run.status.value, run.owner_token, run.lock_expires_at


def _event_types(engine: Engine, run_id: UUID) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )


def _ba_rows(engine: Engine, run_id: UUID) -> list[RoleExecution]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(RoleExecution).where(
                    RoleExecution.run_id == run_id, RoleExecution.role == "BA"
                )
            )
        )


def _owned_and_running(engine: Engine, run_id: UUID) -> Callable[[], bool]:
    def predicate() -> bool:
        status, token, _ = _run_row(engine, run_id)
        return status == "BA" and token is not None

    predicate.__name__ = f"run {run_id} inside BA with the lease held"
    return predicate


def _drain(
    proc: subprocess.Popen[str], *, first_line: str = ""
) -> subprocess.CompletedProcess[str]:
    out, err = proc.communicate(timeout=_CHILD_TIMEOUT)
    return subprocess.CompletedProcess(
        proc.args, proc.returncode or 0, first_line + out, err
    )


def test_a_slow_step_keeps_its_lease_and_the_expiry_advances_repeatedly(
    pg_url: str, engine: Engine
) -> None:
    owner = popen(
        ["run", "text:a step three times longer than its lease ttl"],
        child_env(
            pg_url,
            fake_script=_COMPLETED_ONCE,
            fake_sleep_ms=_SLOW_STEP_MS,
            lease_ttl_seconds=_TTL_SECONDS,
            lease_heartbeat_seconds=_HEARTBEAT_SECONDS,
        ),
    )
    competitors: list[subprocess.Popen[str]] = []
    try:
        assert owner.stdout is not None
        first_line = owner.stdout.readline()
        run_id = run_id_from_stdout(first_line)

        # the observable moment the owner is inside the step, holding the lease
        wait_for(_owned_and_running(engine, run_id), timeout=40)

        # Sample the lease only while the step is genuinely in flight (status BA).
        # The instant it commits BA -> COMPLETED the lease columns are cleared, and
        # there is a brief window before the process exits; those post-step rows
        # are not part of this measurement.
        samples: list[tuple[str, Any, datetime | None]] = []
        step_start = time.monotonic()
        next_competitor_at = step_start
        deadline = step_start + _SLOW_STEP_MS / 1000 + 40
        while owner.poll() is None and time.monotonic() < deadline:
            observation = _run_row(engine, run_id)
            if observation[0] != "BA":
                break
            samples.append(observation)
            now = time.monotonic()
            if (
                now >= next_competitor_at
                and now - step_start < _COMPETITOR_LAUNCH_WINDOW_S
                and len(competitors) < _MAX_COMPETITORS
                and observation[1] is not None
            ):
                competitors.append(popen(["resume", str(run_id)], child_env(pg_url)))
                next_competitor_at = now + _COMPETITOR_INTERVAL_S
            time.sleep(0.25)

        won = _drain(owner, first_line=first_line)
    finally:
        for proc in (owner, *competitors):
            if proc.poll() is None:
                proc.kill()

    # -- the owner completed its own step and exited cleanly --
    assert won.returncode == 0, f"stdout={won.stdout!r}\nstderr={won.stderr!r}"
    assert "BA → COMPLETED" in won.stdout
    assert "Traceback" not in won.stderr

    expiries = [expiry for (_, _, expiry) in samples]
    tokens = [token for (_, token, _) in samples]
    statuses = [status for (status, _, _) in samples]

    assert len(samples) >= 8, f"only {len(samples)} samples taken during the step"
    assert all(e is not None for e in expiries)
    # non-decreasing, and strictly increasing at least three times -> the renewal
    # is periodic, not a single push at claim time
    pairs = list(itertools.pairwise(expiries))
    assert all(b >= a for a, b in pairs), expiries
    strict_increases = sum(1 for a, b in pairs if b > a)
    assert strict_increases >= 3, (
        f"lock expiry advanced only {strict_increases}x during a "
        f"{_SLOW_STEP_MS / 1000:.0f}s step: {expiries}"
    )

    # -- the owner token never changed while the step was in flight --
    assert all(token is not None for token in tokens)
    assert len(set(tokens)) == 1, tokens
    assert set(statuses) == {"BA"}, statuses

    # -- every competitor that raced the step lost cleanly and wrote nothing --
    assert len(competitors) >= 3, f"only {len(competitors)} competitors launched"
    drained = [_drain(proc) for proc in competitors]
    for competitor in drained:
        assert competitor.returncode == 0, (
            f"stdout={competitor.stdout!r}\nstderr={competitor.stderr!r}"
        )
        assert "is owned by another process" in competitor.stderr
        assert "Traceback" not in competitor.stderr
        assert "→" not in competitor.stdout

    # -- exactly one execution of the step: no competitor ever got in --
    ba_rows = _ba_rows(engine, run_id)
    assert len(ba_rows) == 1
    assert ba_rows[0].attempt == 1
    assert _event_types(engine, run_id).count("ROLE_COMPLETED") == 1

    # -- reaching COMPLETED cleared both lease columns rather than leaving them
    #    to expire, so a process started now claims immediately --
    status, token, expiry = _run_row(engine, run_id)
    assert status == "COMPLETED"
    assert token is None
    assert expiry is None

    after = spawn(["resume", str(run_id)], child_env(pg_url), timeout=_CHILD_TIMEOUT)
    assert after.returncode == 0, f"stdout={after.stdout!r}\nstderr={after.stderr!r}"
    assert "Traceback" not in after.stderr


def test_a_lease_context_whose_body_raises_releases_the_lease_immediately(
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    """The direct test for the hostage-taking failure mode. A heartbeat thread
    that outlived its owner's decision would keep the run unclaimable for the
    life of the process, and the symptom is a run that merely looks slow. Uses
    the *default* 900 s TTL deliberately: a fresh claim can only succeed here if
    ``run_lease.__exit__`` actually released, not because a short TTL lapsed."""
    run_id = start_run(
        "text:the lease body raises",
        session_factory=real_session_factory,
        snapshot=DEFAULT_TEST_SNAPSHOT,
    )
    cleanup_runs.append(run_id)

    with (
        pytest.raises(_Boom),
        run_lease(run_id, session_factory=real_session_factory),
    ):
        raise _Boom()

    # both lease columns are null straight away
    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.owner_token is None
        assert run.lock_expires_at is None

    # and a fresh claim wins at once -- only possible if the release ran
    with real_session_factory() as session:
        token = claim_lease(session, run_id, ttl_seconds=900)
    assert token is not None


_LIVENESS_PROBE_FORBIDDEN = (
    re.compile(r"pg_stat_activity"),
    re.compile(r"os\.getpid"),
    re.compile(r"os\.getppid"),
    re.compile(r"\bpsutil\b"),
    re.compile(r"SIGKILL"),
)


def test_the_lease_path_never_probes_another_process_for_liveness() -> None:
    """Liveness *is* a freshly pushed expiry -- an owner proves it by renewing.
    There is no process-identity check, no activity probe of another backend and
    no is-this-step-slow heuristic anywhere in the lease path. This mirrors the
    plan's grep-style structural assertion so the invariant is enforced, not
    merely described."""
    text = (REPO_ROOT / "src" / "dark_factory" / "orchestrator" / "lease.py").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    offenders = [
        pattern.pattern for pattern in _LIVENESS_PROBE_FORBIDDEN if pattern.search(code)
    ]
    assert not offenders, (
        "the lease path must not distinguish a slow owner from a dead one; "
        f"found liveness-probe constructs: {offenders}"
    )
