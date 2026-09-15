"""The SC4 proof: a role whose diff touches a path outside its configured
``write_scope`` fails the role, the violating path is reverted, and a role
working inside its scope -- or a role that changed nothing -- is untouched
(ROLE-05, D-12, D-13, D-14, 05-04 Task 2).

Drives real runs in-process (``start_run`` + ``drive``/``advance`` against a
real Postgres engine), the same idiom
``tests/db/test_artifact_schema_violation_fails_role.py`` and
``tests/db/test_artifact_commit_per_role.py`` already use. Because
``FakeWorker`` never edits the repository itself, each scenario below wraps
it (or replaces it entirely) with a small :class:`CodingWorker` that performs
the file change *inside* its own ``execute()`` call, locating the run's
worktree through :func:`~dark_factory.git.worktree.worktree_path` -- never by
rebuilding the path -- exactly matching the timing a real worker's own writes
would have.
"""

from __future__ import annotations

import json
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
from dark_factory.git.client import run_git
from dark_factory.git.worktree import (
    ensure_worktree,
    working_branch_name,
    worktree_path,
)
from dark_factory.orchestrator.runner import drive, start_run
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
from tests.support.fake_artifacts import write_role_artifacts
from tests.support.git_repo import git_commit_all, read_committed, run_artifact_text

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]


def _capabilities() -> WorkerCapabilities:
    return WorkerCapabilities(
        native_resume=False,
        session_id=True,
        structured_output=True,
        non_interactive=True,
    )


class _WriteFileWorker(CodingWorker):
    """Writes ``relative_path`` under the run's worktree from inside
    ``execute()``, then completes -- the file change lands at exactly the
    moment a real worker's own write would, after the before-hook pass (and
    therefore after any WIP recovery) has already run for this attempt."""

    def __init__(self, work_dir: Path, relative_path: str, content: str) -> None:
        self._work_dir = work_dir
        self._relative_path = relative_path
        self._content = content

    def _write(self) -> None:
        target = self._work_dir / self._relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._content, encoding="utf-8")

    def execute(self, context: Any) -> WorkerResult:
        self._write()
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"wrote {self._relative_path}",
            worker_session_id="fake-write-file",
        )

    def resume(
        self, context: Any, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self.execute(context)

    def capabilities(self) -> WorkerCapabilities:
        return _capabilities()


class _RoleDispatchWorker(CodingWorker):
    """Dispatches ``execute()``/``resume()`` by ``context.role`` -- one
    real ``CodingWorker`` script per role name, so two roles in the same
    ``[worker: fake]`` pipeline can behave differently within a single
    ``drive()`` call (mirrors ``tests/db/test_artifact_commit_per_role.py``'s
    ``_LazyFourRoleWorker``)."""

    def __init__(self, per_role: dict[str, CodingWorker]) -> None:
        self._per_role = per_role

    def execute(self, context: Any) -> WorkerResult:
        role = context.role
        assert role in self._per_role, role
        return self._per_role[role].execute(context)

    def resume(
        self, context: Any, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        role = context.role
        return self._per_role[role].resume(context, previous, answer)

    def capabilities(self) -> WorkerCapabilities:
        return _capabilities()


class _ValidArtifactAndViolationWorker(CodingWorker):
    """Writes a schema-valid declared artifact AND an out-of-scope repository
    file in the same ``execute()`` call -- the "artifact commit happened
    first, the violation still fails the role" proof."""

    def __init__(self, run_dir: Path, work_dir: Path) -> None:
        self._run_dir = run_dir
        self._work_dir = work_dir

    def execute(self, context: Any) -> WorkerResult:
        refs = write_role_artifacts(
            self._run_dir,
            "DEVELOPMENT",
            {
                "implementation_summary.json": json.dumps(
                    {
                        "summary": "implemented the thing",
                        "changed_files": [],
                        "tests_added": [],
                    }
                )
            },
        )
        out_of_scope = self._work_dir / "tests" / "leftover.py"
        out_of_scope.parent.mkdir(parents=True, exist_ok=True)
        out_of_scope.write_text("# out of scope for DEVELOPMENT\n", encoding="utf-8")
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="implemented, but also touched tests/",
            worker_session_id="fake-development-with-violation",
            artifacts=refs,
        )

    def resume(
        self, context: Any, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self.execute(context)

    def capabilities(self) -> WorkerCapabilities:
        return _capabilities()


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


def _seed_tracked_file(root: Path, relative_path: str, content: str) -> None:
    """Write ``relative_path`` at ``root`` and commit it directly onto
    whatever branch is checked out (``main``, ``config_root_factory``'s base
    branch) -- so a run's working branch, cut from that tip, starts with the
    file already tracked in its own ``HEAD``."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git_commit_all(root, f"seed {relative_path}")


def _development_with_declared_output(config_root_factory: Callable[..., Path]) -> Path:
    root = config_root_factory(roles=("DEVELOPMENT",))
    (root / ".dark-factory/roles/DEVELOPMENT.yaml").write_text(
        "name: DEVELOPMENT\n"
        "worker: fake\n"
        "instructions: ../instructions/development.md\n"
        "tools: []\n"
        'permissions:\n  write_scope: ["src/**"]\n'
        "before: [ensure_clean_worktree]\n"
        "after: []\n"
        "inputs: []\n"
        "outputs: [implementation_summary.json]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
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


def _start(
    root: Path,
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    *,
    source: str,
) -> tuple[Any, Path]:
    """``start_run`` and return ``(run_id, work_dir)`` -- ``work_dir`` is a
    pure path computation (:func:`worktree_path`), safe to compute before the
    worktree physically exists."""
    snapshot = load_effective_config(root)
    run_id = start_run(source, session_factory=real_session_factory, snapshot=snapshot)
    cleanup_runs.append(run_id)
    return run_id, worktree_path(root, run_id)


def _assert_failure_shape(
    engine: Engine, run_id: Any, *, violating_path: str, patterns: list[str]
) -> None:
    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.result is None
        assert execution.error is not None
        error_blob = json.dumps(execution.error)
        assert violating_path in error_blob
        for pattern in patterns:
            assert pattern in error_blob

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        types = list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types


# --------------------------------------------------------------------------- #
# Behavior bullet 1: an in-scope edit completes normally.
# --------------------------------------------------------------------------- #


def test_an_in_scope_edit_completes_with_no_revert(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = config_root_factory(roles=("DEVELOPMENT",))
    run_id, work_dir = _start(
        root, real_session_factory, cleanup_runs, source="text:development in scope"
    )
    worker = _WriteFileWorker(work_dir, "src/app.py", "print('in scope')\n")

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    # -- the in-scope edit is durable on the working branch, not on the
    # worktree filesystem: on COMPLETED, `_cleanup_run_worktree` commits any
    # trailing worktree content onto the working branch via
    # `wip_commit_if_dirty` and then removes the entire worktree directory
    # (D-04). The working branch is therefore the only place this content
    # still exists after COMPLETED -- reading from `work_dir` here would be
    # asserting against a location the design guarantees is gone. Do not
    # "simplify" this back to a filesystem read. ---------------------------
    working_branch = working_branch_name(run_id)
    committed = read_committed(root, working_branch, "src/app.py")
    assert committed == "print('in scope')\n"

    # -- companion proof of the same D-04 contract: the worktree directory
    # itself no longer exists once the run reaches COMPLETED (the mirror
    # image of test 6's `assert work_dir.exists()` for a FAILED run). ------
    assert not work_dir.exists()


# --------------------------------------------------------------------------- #
# Behavior bullet 2: a tracked-edit violation is restored from HEAD.
# --------------------------------------------------------------------------- #


def test_a_tracked_edit_outside_scope_is_restored_from_head_and_fails_the_role(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("QA",))
    _seed_tracked_file(root, "src/app.py", "print('original')\n")

    run_id, work_dir = _start(
        root, real_session_factory, cleanup_runs, source="text:qa edits tracked src"
    )
    worker = _WriteFileWorker(
        work_dir, "src/app.py", "print('qa tampered with this')\n"
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    _assert_failure_shape(
        engine, run_id, violating_path="src/app.py", patterns=["tests/**"]
    )

    # -- the restore used HEAD as its source: read the committed blob
    # through git, not merely "the file changed back" --------------------
    head_content = run_git(["show", "HEAD:src/app.py"], cwd=work_dir).stdout
    assert head_content == "print('original')\n"
    assert (work_dir / "src" / "app.py").read_text("utf-8") == "print('original')\n"

    staged = run_git(["diff", "--cached", "--name-only"], cwd=work_dir).stdout
    assert "src/app.py" not in staged.splitlines()


# --------------------------------------------------------------------------- #
# Behavior bullet 3: a new-file violation is removed from disk AND the index.
# --------------------------------------------------------------------------- #


def test_a_new_file_outside_scope_is_removed_from_disk_and_the_index(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("QA",))

    run_id, work_dir = _start(
        root,
        real_session_factory,
        cleanup_runs,
        source="text:qa creates a new src file",
    )
    worker = _WriteFileWorker(
        work_dir, "src/new_file.py", "# QA should not have written this\n"
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    _assert_failure_shape(
        engine, run_id, violating_path="src/new_file.py", patterns=["tests/**"]
    )

    assert not (work_dir / "src" / "new_file.py").exists()
    cached = run_git(["ls-files", "--cached"], cwd=work_dir).stdout.splitlines()
    assert "src/new_file.py" not in cached


# --------------------------------------------------------------------------- #
# Behavior bullet 4: an empty write_scope is zero tolerance, never "unrestricted".
# --------------------------------------------------------------------------- #


def test_a_role_with_empty_write_scope_fails_on_any_change(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("BA",))

    run_id, work_dir = _start(
        root, real_session_factory, cleanup_runs, source="text:ba touches anything"
    )
    worker = _WriteFileWorker(work_dir, "notes.txt", "BA should never write this\n")

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.error is not None
        assert "notes.txt" in json.dumps(execution.error)

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

    assert not (work_dir / "notes.txt").exists()


# --------------------------------------------------------------------------- #
# Behavior bullet 8 (A-05-14): enforcement checks this attempt's own changes
# only -- an earlier role's legitimate in-scope work never fails a later
# role that touched nothing.
# --------------------------------------------------------------------------- #


def test_a_later_role_is_not_failed_for_an_earlier_roles_legitimate_edit(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = config_root_factory(roles=("DEVELOPMENT", "QA"))

    run_id, work_dir = _start(
        root,
        real_session_factory,
        cleanup_runs,
        source="text:development edits src, qa touches nothing",
    )
    development_worker = _WriteFileWorker(
        work_dir, "src/feature.py", "print('a legitimate development edit')\n"
    )
    qa_worker = FakeWorker(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="QA touched nothing",
                worker_session_id="fake-qa-no-op",
            )
        ]
    )
    worker = _RoleDispatchWorker({"DEVELOPMENT": development_worker, "QA": qa_worker})

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        executions = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(RoleExecution.attempt)
        ).all()
        statuses = {execution.role: execution.status for execution in executions}
    assert statuses["DEVELOPMENT"] == "COMPLETED"
    assert statuses["QA"] == "COMPLETED"


# --------------------------------------------------------------------------- #
# Behavior bullet 7: a role that writes both a valid artifact and a
# violation still fails -- the artifact commit and the failure are
# independent.
# --------------------------------------------------------------------------- #


def test_a_valid_artifact_commit_survives_even_though_the_role_still_fails(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _development_with_declared_output(config_root_factory)

    run_id, work_dir = _start(
        root,
        real_session_factory,
        cleanup_runs,
        source="text:development ships a valid artifact plus a violation",
    )
    working_branch = working_branch_name(run_id)
    # Pre-create the worktree so `run_dir` resolves before the worker call
    # (mirrors `tests/db/test_artifact_schema_violation_fails_role.py`'s
    # `_start_run_and_get_run_dir`); `ensure_worktree` is idempotent, so the
    # runner's own call inside `drive()` reuses this exact directory.
    ensure_worktree(root, run_id, base_branch="main", working_branch=working_branch)
    run_dir = run_root(work_dir, run_id)
    worker = _ValidArtifactAndViolationWorker(run_dir, work_dir)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    _assert_failure_shape(
        engine, run_id, violating_path="tests/leftover.py", patterns=["src/**"]
    )

    # -- the artifact content is durably on the working branch, independent
    # of the role having failed -------------------------------------------
    committed = run_artifact_text(
        root,
        run_id,
        working_branch,
        "artifacts/DEVELOPMENT/implementation_summary.json",
    )
    assert json.loads(committed) == {
        "summary": "implemented the thing",
        "changed_files": [],
        "tests_added": [],
    }

    # -- the violation was still reverted -----------------------------------
    assert not (work_dir / "tests" / "leftover.py").exists()

    # -- the failed run keeps its worktree on disk for inspection (D-04) ----
    assert work_dir.exists()
