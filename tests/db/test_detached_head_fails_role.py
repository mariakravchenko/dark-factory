"""SC3's detached-HEAD half (D-08): a role entered on a detached HEAD reaches
``FAILED`` without its worker ever being called, in exactly the Phase 4
D-09 failure shape (``tests/db/test_artifact_schema_violation_fails_role.py``)
-- never a new failure vocabulary -- and the run's worktree survives the
failure for post-mortem inspection (D-04's failure arm).

Follows the in-process db-test idiom of ``tests/db/test_run_owns_a_worktree.py``:
a two-role config tree, explicit step-by-step ``advance()`` calls so the test
can detach the worktree's ``HEAD`` at the exact point between "BA completed"
and "ARCHITECTURE's before-hook fires", and a teardown that force-removes any
worktree the test created.
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
from dark_factory.git.worktree import remove_worktree, worktree_path
from dark_factory.orchestrator.runner import advance, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]


class _CountingWorker(CodingWorker):
    """Delegates to a real :class:`FakeWorker`, counting ``execute()`` calls
    so the test can assert the count is unchanged across the failing
    ``advance`` -- distinguishing "failed before the worker" from "failed
    because of the worker" (D-08)."""

    def __init__(self, script: list[WorkerResult]) -> None:
        self._inner = FakeWorker(script)
        self.execute_call_count = 0

    def execute(self, context: object) -> WorkerResult:
        self.execute_call_count += 1
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


def test_a_detached_head_fails_the_role_and_the_run_without_calling_the_worker(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("BA", "ARCHITECTURE"))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:a detached HEAD fails the role before the worker runs",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    work_dir = worktree_path(root, run_id)
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="ba done",
            worker_session_id="fake-ba-detached",
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="architecture done -- never reached",
            worker_session_id="fake-architecture-detached",
        ),
    ]
    worker = _CountingWorker(script)
    registry = _registry(worker)

    # Step 1: CREATED -> BA (enter first role). No worktree yet.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.BA

    # Step 2: run BA's worker -> transitions to ARCHITECTURE, creates the
    # worktree.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE
    assert work_dir.is_dir()
    assert worker.execute_call_count == 1

    # Detach the worktree's HEAD directly -- a state the platform cannot
    # reason about, simulating an operator (or a crashed prior process) that
    # left the checkout on a bare commit rather than a branch.
    sha = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()
    run_git(["checkout", "-q", sha], cwd=work_dir)
    head_ref_before = run_git(["symbolic-ref", "-q", "HEAD"], cwd=work_dir, check=False)
    assert head_ref_before.returncode != 0  # genuinely detached

    # Step 3: enter ARCHITECTURE (insert its role_executions row). No git
    # side effect -- _enter_role never touches the worktree.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE

    # Step 4: ARCHITECTURE's before-hook (ensure_clean_worktree) finds the
    # detached HEAD and fails the role and the run -- the worker is never
    # invoked.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.FAILED

    # -- the worker was never called for ARCHITECTURE ------------------------
    assert worker.execute_call_count == 1

    with Session(engine) as session:
        architecture_row = session.scalars(
            sa.select(RoleExecution).where(
                RoleExecution.run_id == run_id, RoleExecution.role == "ARCHITECTURE"
            )
        ).one()
        assert architecture_row.status == "FAILED"
        assert architecture_row.result is None
        assert architecture_row.error is not None
        assert str(work_dir) in str(architecture_row.error)
        assert sha in str(architecture_row.error)
        assert architecture_row.wip_commit_sha is None

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED
        assert run.owner_token is None

        event_types = session.scalars(
            sa.select(RunEvent.type)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq)
        ).all()
        assert "ROLE_FAILED" in event_types
        assert "RUN_FAILED" in event_types
        role_failed_idx = event_types.index("ROLE_FAILED")
        run_failed_idx = event_types.index("RUN_FAILED")
        assert run_failed_idx == role_failed_idx + 1

        wip_events = session.scalars(
            sa.select(RunEvent).where(
                RunEvent.run_id == run_id,
                RunEvent.type == EventType.WIP_COMMIT_CREATED.value,
            )
        ).all()
        assert wip_events == []

    # -- D-04's failure arm: the worktree survives, still detached ----------
    assert work_dir.is_dir()
    head_ref_after = run_git(["symbolic-ref", "-q", "HEAD"], cwd=work_dir, check=False)
    assert head_ref_after.returncode != 0
    assert run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip() == sha
