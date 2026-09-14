"""The phase tracer: a run persists its own working branch at creation, and
every role of the run executes inside a real, reused git worktree (GIT-01,
D-01, D-02, D-03, D-15).

Follows the in-process db-test idiom of ``tests/db/test_artifact_handoff.py``:
a config tree built by ``config_root_factory`` (git-initialised since this
plan), ``start_run`` with the resolved snapshot, a per-test ``WorkerRegistry``
injected with a small worker that writes its own artifact files (mimicking a
real worker, which writes files before reporting them), ``drive``/``advance``
against the config tree's ``repo_root``, and a teardown that both deletes the
run's DB rows and force-removes any worktree the test created so a failing
assertion cannot leave a stale worktree behind for the next test.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.git import GitCommandError, WorktreePathError
from dark_factory.git.client import run_git
from dark_factory.git.worktree import (
    ensure_worktree,
    remove_worktree,
    working_branch_name,
    worktree_path,
)
from dark_factory.orchestrator.runner import advance, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import write_role_artifacts

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]


class _ArtifactWritingWorker(CodingWorker):
    """A ``COMPLETED``-only worker that writes one artifact file per call
    (mimicking a real worker, which writes its own files before returning a
    result naming them) into a precomputed run root, then returns a matching
    :class:`WorkerResult`.

    ``run_dir`` is computed by the test from :func:`worktree_path` /
    :func:`~dark_factory.artifacts.paths.run_root` *before* driving the run
    -- a pure path computation, not a filesystem read -- so it is available
    up front even though the worktree itself does not exist on disk until
    the orchestrator's own ``ensure_worktree`` call creates it, which always
    happens before this worker is ever invoked.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role is not None
        refs = write_role_artifacts(self._run_dir, role, {"note.txt": f"{role} ok"})
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{role} done",
            worker_session_id=f"fake-{role}",
            artifacts=refs,
        )

    def execute(self, context: object) -> WorkerResult:
        return self._record(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._record(context)

    def capabilities(self) -> WorkerCapabilities:
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )


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
    """Yields a list the test appends ``(run_id, repo_root)`` pairs to.

    Teardown removes every DB row for each run id *and* force-removes any
    worktree left on disk for it -- a failing assertion mid-test must not
    leave a stale worktree for the next test to trip over.
    """
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


def test_branch_columns_persisted_before_any_git_command(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
) -> None:
    """``create_run`` writes ``base_branch`` / ``working_branch`` in the same
    transaction as the ``CREATED`` row -- proven here by asserting the
    columns *before* ``drive`` (and therefore before any git command) ever
    runs."""
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:branch columns persisted at creation",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    with real_session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.base_branch == "main"
        assert run.working_branch == working_branch_name(run_id)

    # No worktree exists yet -- the columns were written with zero git
    # side effects.
    assert not worktree_path(root, run_id).exists()


def test_two_role_run_creates_and_reuses_one_worktree(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
) -> None:
    """The full SC1 tracer: a two-role run creates exactly one worktree
    checked out on its persisted working branch, both roles execute inside
    it, the second role's entry reuses the worktree with no second
    ``git worktree add`` (an unchanged branch ``HEAD`` SHA and an unchanged
    worktree count prove it), and the run tree ends up under the worktree,
    never under the main checkout."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE"))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:two roles share one worktree",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    branch = working_branch_name(run_id)
    work_dir = worktree_path(root, run_id)
    run_dir = run_root(work_dir, run_id)
    worker = _ArtifactWritingWorker(run_dir)
    registry = _registry(worker)

    # Step 1: CREATED -> BA (enter first role). No worktree yet.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.BA
    assert not work_dir.exists()

    # Step 2: run BA's worker -> transitions to ARCHITECTURE. This is the
    # FIRST ensure_worktree call: creates the worktree.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE
    assert work_dir.is_dir()
    assert (work_dir / ".git").exists()

    porcelain_after_creation = run_git(
        ["worktree", "list", "--porcelain"], cwd=root
    ).stdout
    assert f"worktree {work_dir}" in porcelain_after_creation
    assert f"refs/heads/{branch}" in porcelain_after_creation

    head_ref = run_git(["symbolic-ref", "-q", "HEAD"], cwd=work_dir).stdout.strip()
    assert head_ref == f"refs/heads/{branch}"

    sha_after_creation = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()

    # Step 3: enter ARCHITECTURE (insert its role_executions row). No
    # worktree call at all.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.ARCHITECTURE

    # Step 4: run ARCHITECTURE's worker -> COMPLETED. This is the SECOND
    # ensure_worktree call for this run: must reuse, not recreate.
    status = advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert status is RunStatus.COMPLETED

    porcelain_after_reuse = run_git(
        ["worktree", "list", "--porcelain"], cwd=root
    ).stdout
    assert porcelain_after_reuse.count(f"worktree {work_dir}") == 1
    assert porcelain_after_creation.count("worktree ") == porcelain_after_reuse.count(
        "worktree "
    )

    sha_after_reuse = run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()
    assert sha_after_reuse == sha_after_creation

    # Every role wrote into the worktree, not the main checkout.
    assert (run_dir / "artifacts" / "BA").is_dir()
    assert (run_dir / "artifacts" / "ARCHITECTURE").is_dir()
    assert not (root / ".dark-factory" / "runs" / str(run_id)).exists()


def test_ensure_worktree_invalid_base_branch_raises_git_command_error(
    git_repo_root: Path,
) -> None:
    """An invalid ``base_branch`` fails loudly and leaves no directory
    behind."""
    run_id = uuid.uuid4()
    branch = working_branch_name(run_id)

    with pytest.raises(GitCommandError) as excinfo:
        ensure_worktree(
            git_repo_root,
            run_id,
            base_branch="no-such-branch",
            working_branch=branch,
        )
    assert "no-such-branch" in str(excinfo.value)
    assert not worktree_path(git_repo_root, run_id).exists()


def test_ensure_worktree_none_working_branch_raises_worktree_path_error(
    git_repo_root: Path,
) -> None:
    """A ``None`` ``working_branch`` -- a legacy run row -- raises naming the
    run id, rather than re-deriving a branch name."""
    run_id = uuid.uuid4()

    with pytest.raises(WorktreePathError) as excinfo:
        ensure_worktree(
            git_repo_root,
            run_id,
            base_branch="main",
            working_branch=None,
        )
    assert str(run_id) in str(excinfo.value)
