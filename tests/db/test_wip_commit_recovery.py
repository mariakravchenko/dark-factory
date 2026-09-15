"""SC3's recovery half (GIT-01, GIT-02, D-05, D-06, D-07): a role that leaves
the worktree dirty is recovered on the next role's entry -- the WIP commit,
its persisted SHA, the ``WIP_COMMIT_CREATED`` audit event, the clean worktree
afterwards, and the A-05-05 regression guard that a mid-attempt ``patch``
write never clears a ``RESUMING`` attempt's persisted ``result``.

Follows the in-process db-test idiom of ``tests/db/test_artifact_handoff.py``
/ ``tests/db/test_run_owns_a_worktree.py``: a two-role config tree built by
``config_root_factory`` (already git-initialised and, since this plan,
already listing ``ensure_clean_worktree`` in every shipped role's
``before:``), a per-test ``WorkerRegistry`` wrapping a small worker, explicit
step-by-step ``advance()`` calls (rather than ``drive()``) so the test can
dirty the worktree at the exact point between "BA completed" and
"ARCHITECTURE's before-hook fires" (mirroring
``tests/db/test_run_owns_a_worktree.py::test_two_role_run_creates_and_reuses_one_worktree``'s
step-by-step ``advance()`` sequence), and a teardown that deletes every
fixture row and force-removes any worktree the test created.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.events.catalog import EventType
from dark_factory.git.client import run_git
from dark_factory.git.lifecycle import WIP_COMMIT_SUBJECT_PREFIX
from dark_factory.git.worktree import (
    remove_worktree,
    working_branch_name,
    worktree_path,
)
from dark_factory.orchestrator.lease import run_lease
from dark_factory.orchestrator.runner import _persist_wip_commit, advance, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.persistence.mutations import (
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
)
from dark_factory.persistence.repositories import load_run_state
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_UNSET = object()


class _RecoveryProbingWorker(CodingWorker):
    """Delegates to a real :class:`FakeWorker`, but on the ARCHITECTURE call
    reads ``role_executions.wip_commit_sha`` straight from the database
    (through its own connection, not the test's) to prove the recovery SHA
    was already committed to Neon **before** this call happened."""

    def __init__(self, script: list[WorkerResult], engine: Engine, run_id: Any) -> None:
        self._inner = FakeWorker(script)
        self._engine = engine
        self._run_id = run_id
        self.wip_sha_observed_at_architecture_call: str | object | None = _UNSET

    def execute(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        if role == "ARCHITECTURE":
            with Session(self._engine) as session:
                row = session.scalars(
                    sa.select(RoleExecution).where(
                        RoleExecution.run_id == self._run_id,
                        RoleExecution.role == "ARCHITECTURE",
                    )
                ).one()
                self.wip_sha_observed_at_architecture_call = row.wip_commit_sha
        return self._inner.execute(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._inner.resume(context, previous, answer)

    def capabilities(self) -> WorkerCapabilities:
        return self._inner.capabilities()


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[tuple[Any, Path]]]:
    entries: list[tuple[Any, Path]] = []
    yield entries
    ids = [run_id for run_id, _root in entries]
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


def test_dirty_worktree_is_recovered_on_the_next_roles_entry(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("BA", "ARCHITECTURE"))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:a dirty worktree is recovered at the next role's entry",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    work_dir = worktree_path(root, run_id)
    working_branch = working_branch_name(run_id)
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="ba done",
            worker_session_id="fake-ba-recovery",
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="architecture done",
            worker_session_id="fake-architecture-recovery",
        ),
    ]
    worker = _RecoveryProbingWorker(script, engine, run_id)
    registry = _registry(worker)

    # Step 1: CREATED -> BA (enter first role). No worktree yet.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.BA

    # Step 2: run BA's worker -> transitions to ARCHITECTURE. The worktree now
    # exists, freshly created and clean -- BA's own before-hook (a clean
    # entry) wrote no recovery commit and no WIP_COMMIT_CREATED event.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE
    assert work_dir.is_dir()

    with Session(engine) as session:
        ba_row = session.scalars(
            sa.select(RoleExecution).where(
                RoleExecution.run_id == run_id, RoleExecution.role == "BA"
            )
        ).one()
        assert ba_row.wip_commit_sha is None
        wip_events_after_ba = session.scalars(
            sa.select(RunEvent).where(
                RunEvent.run_id == run_id,
                RunEvent.type == EventType.WIP_COMMIT_CREATED.value,
            )
        ).all()
        assert wip_events_after_ba == []

    head_before_dirtying = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()

    # Dirty the worktree exactly as a worker that edited and stopped would
    # have: a modified tracked file AND a brand-new untracked file.
    (work_dir / "README.md").write_text(
        "# throwaway test repository\n\nleft dirty by a simulated worker\n",
        encoding="utf-8",
    )
    (work_dir / "new_untracked_file.txt").write_text(
        "content a stopped worker never committed\n", encoding="utf-8"
    )

    # Step 3: enter ARCHITECTURE (insert its role_executions row). No git
    # side effect -- _enter_role never touches the worktree.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE

    dirty_status_before_recovery = run_git(
        ["status", "--porcelain=v1", "--untracked-files=all"], cwd=work_dir
    ).stdout
    assert dirty_status_before_recovery.strip() != ""

    # Step 4: run ARCHITECTURE's worker. Its before-hook (ensure_clean_worktree,
    # now listed on every shipped/config_root_factory role) finds the
    # worktree dirty, recovers it with one commit, persists the SHA on the
    # recovering attempt with a WIP_COMMIT_CREATED event BEFORE the worker is
    # called, then runs the worker to completion. ARCHITECTURE is this run's
    # terminal role, so reaching COMPLETED also fires 05-03 Task 3's own
    # cleanup (recover-then-remove): its final wip_commit_if_dirty pass finds
    # nothing left dirty (the before-hook already recovered everything at
    # entry, so this stays a single recovery commit, not two), and then the
    # worktree itself is removed -- so every assertion below reads the
    # recovery commit from the branch via `root`, never via `work_dir`,
    # which no longer exists once this call returns (D-04, D-09, D-11).
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.COMPLETED

    # -- the worktree is gone: 05-03 Task 3's COMPLETED cleanup removed it,
    # -- proven through git's own bookkeeping in the main repository -------
    assert not work_dir.exists()
    porcelain = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert str(work_dir) not in porcelain

    # -- exactly one recovery commit, containing both changes, read from the
    # -- branch in the main repository rather than the now-removed worktree --
    log = (
        run_git(
            ["log", "--format=%H %s", f"{head_before_dirtying}..{working_branch}"],
            cwd=root,
        )
        .stdout.strip()
        .splitlines()
    )
    assert len(log) == 1, f"expected exactly one recovery commit, got: {log}"
    recovery_sha, recovery_subject = log[0].split(" ", 1)
    assert recovery_subject.startswith(WIP_COMMIT_SUBJECT_PREFIX)
    assert "ARCHITECTURE" in recovery_subject
    show = run_git(["show", "--stat", "--format=", recovery_sha], cwd=root).stdout
    assert "README.md" in show
    assert "new_untracked_file.txt" in show

    # -- the worker observed the SHA already persisted before it was called --
    assert worker.wip_sha_observed_at_architecture_call == recovery_sha

    # -- the recovering attempt's final row still carries the same SHA -------
    with Session(engine) as session:
        architecture_row = session.scalars(
            sa.select(RoleExecution).where(
                RoleExecution.run_id == run_id, RoleExecution.role == "ARCHITECTURE"
            )
        ).one()
        assert architecture_row.status == "COMPLETED"
        assert architecture_row.wip_commit_sha == recovery_sha

        # -- exactly one WIP_COMMIT_CREATED row, naming role/attempt/commit --
        wip_events = session.scalars(
            sa.select(RunEvent).where(
                RunEvent.run_id == run_id,
                RunEvent.type == EventType.WIP_COMMIT_CREATED.value,
            )
        ).all()
        assert len(wip_events) == 1
        wip_event = wip_events[0]
        assert wip_event.role_execution_id == architecture_row.id
        assert wip_event.payload["role"] == "ARCHITECTURE"
        assert wip_event.payload["commit"] == recovery_sha
        assert wip_event.payload["attempt"] == architecture_row.attempt


def test_patch_mode_write_does_not_clear_a_resuming_attempts_persisted_result(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
) -> None:
    """A-05-05's regression guard, the single most valuable assertion in this
    file: a ``patch``-mode write (the shape ``_persist_wip_commit`` issues)
    never nulls a ``RESUMING`` attempt's persisted ``NEEDS_INPUT`` ``result``
    -- the column a resume reads back to reconstruct ``previous``."""
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:a patch write must not clear a resuming attempt's result",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    needs_input_result = WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        questions=["which database?"],
        worker_session_id="fake-resuming-001",
    ).model_dump(mode="json")

    # Directly construct a RESUMING BA attempt whose persisted result is a
    # NEEDS_INPUT WorkerResult payload -- the shape a real pause leaves.
    with real_session_factory() as session:
        apply_transition(
            session,
            run_id=run_id,
            expected_status=RunStatus.CREATED,
            next_status=RunStatus.BA,
            next_current_role="BA",
            next_current_step=0,
            role_execution=RoleExecutionWrite(
                mode="insert",
                role="BA",
                worker="fake",
                status="RESUMING",
                result=needs_input_result,
            ),
            events=[
                EventWrite(
                    type=EventType.ROLE_STARTED,
                    payload={"role": "BA", "worker": "fake"},
                )
            ],
        )

    with real_session_factory() as session:
        state = load_run_state(session, run_id)
    assert state is not None
    latest = state.latest_execution
    assert latest is not None
    assert latest.status == "RESUMING"
    assert latest.result == needs_input_result
    assert latest.wip_commit_sha is None

    sha = "deadbeef" * 5  # a 40-character placeholder SHA
    with run_lease(run_id, session_factory=real_session_factory) as lease:
        _persist_wip_commit(run_id, state, latest, real_session_factory, lease, sha=sha)

    with real_session_factory() as session:
        after = load_run_state(session, run_id)
    assert after is not None
    after_latest = after.latest_execution
    assert after_latest is not None
    assert after_latest.status == "RESUMING"
    assert after_latest.result == needs_input_result  # byte-identical, not nulled
    assert after_latest.wip_commit_sha == sha
