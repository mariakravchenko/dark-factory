"""SC1 / TRIG-04 / HITL-06 (D-06): a run paused by one real ``dark-factory``
operating-system process is finished by a second, entirely separate one that
shares only PostgreSQL -- after the first process's worktree and its
untracked artifact tree have both been deleted from disk.

Two real operating-system processes are the whole point. An in-process
simulation shares module state, a warm SQLAlchemy engine and an identity map
and could pass while the real cross-machine claim failed -- the claim under
test is specifically that *nothing* carries over between the two processes.
The child environment for every spawned process is built exclusively from
``tests.support.subprocess_runner.child_env``'s explicit allowlist, never
``os.environ.copy()`` (CLAUDE.md's credential boundary).

**Deliberate marker deviation (11-RESEARCH.md Pitfall 1, 11-CONTEXT.md
D-05/D-06).** Every existing test in this repository that spawns
``dark-factory`` as a real OS subprocess lives under ``tests/integration/``
and carries ``pytest.mark.integration`` -- a tier ``ci.yml`` deliberately
never runs, because some ``integration`` tests need live agent-CLI
credentials the hosted runner does not have. This module needs only
PostgreSQL and ``FakeWorker`` -- never agent-CLI credentials -- so per D-05
("the ``db``-tier test suite (**and the cross-machine proof below**) runs in
``ci.yml``") it is marked ``db``, not ``integration``, and lives under
``tests/db/`` rather than ``tests/integration/``. Marking it ``integration``
would mean it silently never runs in CI while the plan's checklist says
"done" -- precisely the failure mode this deviation exists to avoid.

**A second, documented deviation from the plan's literal recipe: how the
worktree is deleted (D-06's "erase every local trace" step).** The plan's
own wording suggested a plain ``shutil.rmtree`` on the worktree directory.
Verified empirically against a real git repository before writing this
test: a bare ``rm -rf`` on a ``git worktree add``-created directory leaves
git's own administrative registration behind (``git worktree list`` still
shows it, marked ``prunable``), and a *same-repository* reconstruction
attempt (``git worktree add`` for the same branch at a new path -- exactly
what ``ensure_worktree``'s path 2 does) then fails with "fatal: '<branch>'
is already used by worktree at '<stale-path>'". A genuinely fresh CI
checkout would never hit this -- it starts with zero worktree
registrations -- so a bare ``rm -rf`` here would make the test fail for a
git-administrative-locking reason unrelated to the actual SC1 claim. This
module instead calls the production :func:`~dark_factory.git.worktree.remove_worktree`
helper (``force=True``) while the directory still exists, which removes the
directory *and* deregisters it in one git call -- the same mechanism a real
``COMPLETED`` cleanup already uses in production (D-04) -- and is the
faithful proof: "no worktree present, and git's own bookkeeping agrees."

**A third, documented deviation: where "the worktree exists again" is
observed.** ``orchestrator/runner.py``'s ``_cleanup_run_worktree`` removes a
run's worktree unconditionally the instant the run reaches ``COMPLETED``
(D-04) -- there is no configuration flag or run shape that skips this. For
a one-role pipeline (this module's own ``config_root``), that means the
worktree that ``ensure_worktree`` rebuilds during the resumed step is
*removed again*, synchronously, before the resuming CLI process ever exits
-- so asserting the worktree exists *after* ``p2`` returns would always be
false, no matter how faithfully reconstruction actually happened. This
module instead arms the resumed step with ``DARK_FACTORY_FAKE_SLEEP_MS``
(``fake_sleep_ms``, an existing, shipped test-only knob) and observes the
worktree's existence *while the resumed process is still in flight* --
after ``ensure_worktree`` has rebuilt it and before the worker call
(deliberately slowed down) returns and triggers the terminal cleanup. This
is a *stronger* proof of reconstruction than a post-exit filesystem check
would have been: it catches the worktree the moment it is rebuilt from the
persisted ``base_branch``/``working_branch`` columns plus git, rather than
merely inferring reconstruction happened from indirect evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.git.worktree import remove_worktree, worktree_path
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.subprocess_runner import (
    child_env,
    popen,
    run_id_from_stdout,
    spawn,
    wait_for,
)

pytestmark = pytest.mark.db

SessionFactory = Callable[[], Session]

# A one-element script whose single element pauses the run -- the mapping's
# keys must match `WorkerResult` exactly, since `FakeWorker` validates each
# element of `DARK_FACTORY_FAKE_SCRIPT` through `WorkerResult.model_validate`.
_QUESTION = "should the release proceed today?"
_PAUSE_SCRIPT: list[dict[str, Any]] = [
    {
        "status": "NEEDS_INPUT",
        "summary": "need a human decision before finishing",
        "questions": [_QUESTION],
    }
]
_ANSWER = "yes, proceed"

# Long enough that a remote-Neon round trip or two ahead of it cannot exhaust
# the window before this test's `wait_for` observes the rebuilt worktree; see
# the module docstring's third deviation note.
_RESUME_SLEEP_MS = 3000
_CHILD_TIMEOUT = 90


def _count_runs(engine: Engine) -> int:
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(Run))
        assert total is not None
        return total


def _run_status(engine: Engine, run_id: UUID) -> RunStatus:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run.status


def _role_executions_count(engine: Engine, run_id: UUID) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(RoleExecution)
                .where(RoleExecution.run_id == run_id)
            )
            or 0
        )


def _the_role_execution(engine: Engine, run_id: UUID) -> RoleExecution:
    with Session(engine) as session:
        row = session.scalar(
            select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert row is not None
        return row


def _the_interaction(engine: Engine, run_id: UUID) -> HumanInteraction | None:
    with Session(engine) as session:
        return session.scalar(
            select(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )


def _event_types(engine: Engine, run_id: UUID) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def _true_default_registry() -> WorkerRegistry:
    """A registry whose ``"fake"`` factory hands back a plain, unscripted
    ``FakeWorker`` -- the true D-10 default (a fresh ``COMPLETED`` result,
    artifact-aware only when ``context.outputs`` is non-empty). Mirrors what
    a *fresh subprocess* with no ``DARK_FACTORY_FAKE_SCRIPT`` in its
    environment resolves to, so the in-process control run's resumed step is
    genuinely comparable to the two-process run's resumed step."""
    registry = WorkerRegistry()
    registry.register("fake", FakeWorker)
    return registry


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[tuple[UUID, Path]]]:
    """Yields a list the test appends ``(run_id, repo_root)`` pairs to.

    Teardown deletes every DB row for each run id *and* force-removes any
    worktree left on disk for it -- a failing assertion mid-test must not
    strand a worktree or rows for the next test (the idiom
    ``tests/db/test_run_owns_a_worktree.py`` already uses).
    """
    entries: list[tuple[UUID, Path]] = []
    yield entries
    ids = [entry[0] for entry in entries]
    if ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(ArtifactReference).where(ArtifactReference.run_id.in_(ids))
            )
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))
    for run_id, root in entries:
        remove_worktree(root, run_id, force=True)


def test_a_run_paused_by_one_process_is_finished_by_another_with_nothing_carried_over(
    pg_url: str,
    engine: Engine,
    config_root: Path,
    cleanup_runs: list[tuple[UUID, Path]],
) -> None:
    """The SC1 proof, in five phases with assertions between each -- see the
    module docstring for the two documented deviations from the plan's
    literal recipe (how the worktree is deleted, and where "exists again" is
    observed)."""
    # -- Phase 1: pause --
    p1 = spawn(
        ["run", "text:finish me somewhere else"],
        child_env(pg_url, fake_script=_PAUSE_SCRIPT),
        cwd=config_root,
    )
    assert p1.returncode == 0, f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    assert "TimeoutExpired" not in (p1.stdout + p1.stderr)
    run_id = run_id_from_stdout(p1.stdout)
    cleanup_runs.append((run_id, config_root))

    # -- Phase 2: the committed pause --
    assert _run_status(engine, run_id) is RunStatus.WAITING_HUMAN
    assert _role_executions_count(engine, run_id) == 1
    role_before = _the_role_execution(engine, run_id)
    captured_role_execution_id = role_before.id
    captured_attempt = role_before.attempt
    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.WAITING

    # -- Phase 3: erase every local trace --
    # Simulates a CI runner's fresh checkout: it has the repository's
    # committed `.dark-factory/` configuration but has never seen this
    # run's worktree or its untracked artifact output. `remove_worktree`
    # (not a bare `shutil.rmtree`) is what actually removes both the
    # directory and git's own worktree registration in one call -- see the
    # module docstring's second deviation note for why a bare `rm -rf`
    # would fail this test for the wrong reason.
    worktree_dir = worktree_path(config_root, run_id)
    artifact_dir = run_root(config_root, run_id)
    removed = remove_worktree(config_root, run_id, force=True)
    assert removed, f"expected a worktree to remove at {worktree_dir}"
    assert not worktree_dir.exists()
    # The real run tree in this architecture nests *inside* the worktree
    # (`run_root(work_dir, run_id)`, never `run_root(config_root, run_id)`),
    # so this second path was never populated for this one-role pipeline --
    # asserting its absence is honest, if not load-bearing here. Recorded in
    # 11-03-SUMMARY.md per the plan's own request for this finding.
    assert not artifact_dir.exists()

    # -- Phase 4: resume from a genuinely separate process --
    resume_env = child_env(pg_url, fake_sleep_ms=_RESUME_SLEEP_MS)
    assert "DARK_FACTORY_FAKE_SCRIPT" not in resume_env
    assert "DARK_FACTORY_CRASH_AFTER" not in resume_env
    runs_before_resume = _count_runs(engine)

    resume_proc = popen(
        ["resume", str(run_id), "--answer", _ANSWER],
        resume_env,
        cwd=config_root,
    )
    stdout = ""
    stderr = ""
    try:
        assert resume_proc.stdout is not None
        first_line = resume_proc.stdout.readline()
        assert run_id_from_stdout(first_line) == run_id

        def _worktree_rebuilt() -> bool:
            return worktree_path(config_root, run_id).exists()

        # Raises TimeoutError naming the predicate if the resumed process
        # never rebuilds the worktree within the window -- a loud failure,
        # not a silent false negative.
        wait_for(_worktree_rebuilt, timeout=60)
        # TRIG-04: reconstructed from the persisted base_branch/working_branch
        # columns plus git -- observed while the (deliberately slowed-down)
        # resumed step is still in flight, never carried over from process A
        # (whose own worktree we just deleted in Phase 3).
        rebuilt = worktree_path(config_root, run_id)
        assert rebuilt.exists()
        assert (rebuilt / ".git").exists()

        stdout, stderr = resume_proc.communicate(timeout=_CHILD_TIMEOUT)
        stdout = first_line + stdout
    finally:
        if resume_proc.poll() is None:
            resume_proc.kill()
            leftover_out, leftover_err = resume_proc.communicate(timeout=10)
            stdout += leftover_out
            stderr += leftover_err

    assert resume_proc.returncode == 0, f"stdout={stdout!r}\nstderr={stderr!r}"
    assert "TimeoutExpired" not in (stdout + stderr)

    # -- Phase 5: the claim --
    assert _run_status(engine, run_id) is RunStatus.COMPLETED
    assert _count_runs(engine) == runs_before_resume
    assert _role_executions_count(engine, run_id) == 1
    role_after = _the_role_execution(engine, run_id)
    assert role_after.id == captured_role_execution_id
    assert role_after.attempt == captured_attempt
    interaction_after = _the_interaction(engine, run_id)
    assert interaction_after is not None
    assert interaction_after.status is InteractionStatus.ANSWERED
    assert interaction_after.answer == _ANSWER
    # D-04: a COMPLETED run's worktree is removed again, unconditionally,
    # the instant the terminal transition commits -- see the module
    # docstring's third deviation note. The durable record survives on the
    # run's working branch; only the ephemeral worktree filesystem copy is
    # gone, exactly as production intends.
    assert not worktree_path(config_root, run_id).exists()


@pytest.mark.usefixtures("use_fake_secrets")
def test_the_two_process_run_and_a_single_process_run_are_indistinguishable(
    pg_url: str,
    engine: Engine,
    config_root: Path,
    cleanup_runs: list[tuple[UUID, Path]],
    fake_worker_registry: Callable[..., Any],
    real_session_factory: SessionFactory,
) -> None:
    """SC2 (behavioural half; Task 2's AST guard proves the structural half):
    a second, independent two-process run and an in-process single-process
    control run of the identical configuration reach the identical terminal
    status and the identical ordered ``run_events`` type sequence -- the
    process boundary changes nothing about what the orchestrator does,
    because there is no CI-only code path for it to take.

    This run is deliberately independent of the SC1 test above (a fresh
    ``config_root``-scoped run, no worktree deletion) -- the property under
    test here is process-boundary-invariance, not no-carryover, so the two
    proofs stay decoupled and each is collectible/runnable on its own.
    """
    # -- the two-process run --
    p1 = spawn(
        ["run", "text:compare a two-process run against a single-process run"],
        child_env(pg_url, fake_script=_PAUSE_SCRIPT),
        cwd=config_root,
    )
    assert p1.returncode == 0, f"stdout={p1.stdout!r}\nstderr={p1.stderr!r}"
    two_process_run_id = run_id_from_stdout(p1.stdout)
    cleanup_runs.append((two_process_run_id, config_root))

    p2 = spawn(
        ["resume", str(two_process_run_id), "--answer", _ANSWER],
        child_env(pg_url),
        cwd=config_root,
    )
    assert p2.returncode == 0, f"stdout={p2.stdout!r}\nstderr={p2.stderr!r}"

    two_process_status = _run_status(engine, two_process_run_id)
    two_process_events = _event_types(engine, two_process_run_id)
    assert two_process_status is RunStatus.COMPLETED

    # -- the in-process, single-process control run of the identical config --
    snapshot = load_effective_config(config_root)
    control_run_id = start_run(
        "text:compare a two-process run against a single-process run",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((control_run_id, config_root))

    control_needs_input = WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a human decision before finishing",
        questions=[_QUESTION],
        worker_session_id="fake-control-pause",
    )
    paused = drive(
        control_run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([control_needs_input]),
        repo_root=config_root,
    )
    assert paused is RunStatus.WAITING_HUMAN

    submit_answer(
        control_run_id, _ANSWER, session_factory=real_session_factory
    )
    # The resumed step uses the true, unscripted default -- mirroring the
    # two-process run's own resumed step, whose environment carries no
    # `DARK_FACTORY_FAKE_SCRIPT` either (see `_true_default_registry`).
    final = drive(
        control_run_id,
        session_factory=real_session_factory,
        registry=_true_default_registry(),
        repo_root=config_root,
    )
    assert final is RunStatus.COMPLETED

    control_events = _event_types(engine, control_run_id)
    assert control_events == two_process_events
    assert _run_status(engine, control_run_id) == two_process_status
