"""The D-10 proof: the PR-bound diff excludes every ``.dark-factory`` path
even while artifact commits and work commits interleave on the working
branch, and the three-dot merge-base form (not the two-dot direct-tree
form) is what correctly ignores a base-branch commit made *after* the
working branch was cut (05-03 Task 4).

Drives a real two-role run (BA -> DEVELOPMENT) step by step so a source-code
change ("work") can be written from inside a role's own worker call --
never before driving starts, which would let an earlier before-hook's own
``ensure_clean_worktree`` recovery pass sweep it up prematurely and defeat
the interleaving this test needs to prove. An unrelated commit is added to
the base branch after the working branch has been cut, mirroring the exact
scenario RESEARCH verified empirically as the one that distinguishes a
correct three-dot diff from a plausible-looking two-dot one.
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
    ArtifactRef,
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.git.client import run_git
from dark_factory.git.diff import ARTIFACT_EXCLUDE_PATHSPEC, collect_pr_diff
from dark_factory.git.worktree import ensure_worktree, working_branch_name
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
from tests.support.git_repo import run_artifact_text

pytestmark = pytest.mark.integration

SessionFactory = Callable[[], Session]

_BA_REQUIREMENTS = "# Requirements\n\nAdd a new feature.\n"
_FEATURE_SOURCE = "def new_feature():\n    return True\n"
_DEVELOPMENT_SUMMARY = json.dumps(
    {
        "summary": "implemented the new feature",
        "changed_files": ["feature.py"],
        "tests_added": [],
    }
)
_POST_CUT_MARKER = "the base branch moved on after the working branch was cut\n"


def _write_two_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """A ``[BA, DEVELOPMENT]`` tree mirroring the shipped
    ``.dark-factory/roles/*.yaml`` set closely enough for this proof:
    DEVELOPMENT alone carries ``collect_diff`` in its ``after:`` list."""
    root = config_root_factory(roles=("BA", "DEVELOPMENT"))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        "before: [ensure_clean_worktree]\n"
        "after: []\n"
        "inputs: []\n"
        "outputs: [requirements.md]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    (root / ".dark-factory/roles/DEVELOPMENT.yaml").write_text(
        "name: DEVELOPMENT\n"
        "worker: fake\n"
        "instructions: ../instructions/development.md\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        "before: [ensure_clean_worktree]\n"
        "after: [collect_diff]\n"
        "inputs: []\n"
        "outputs: [implementation_summary.json]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    return root


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


class _FileWritingWorker(CodingWorker):
    """Writes real files into the worktree from *inside* ``execute()`` --
    exactly when the runner calls it, never before driving starts -- so no
    write is prematurely swept up by an earlier role's own before-hook
    recovery pass."""

    def __init__(self, inner: FakeWorker, writer: Callable[[], None]) -> None:
        self._inner = inner
        self._writer = writer

    def execute(self, context: Any) -> WorkerResult:
        self._writer()
        return self._inner.execute(context)

    def resume(
        self, context: Any, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        return self._inner.resume(context, previous, answer)

    def capabilities(self) -> WorkerCapabilities:
        return self._inner.capabilities()


def test_pr_diff_excludes_dark_factory_and_ignores_the_base_branchs_own_post_cut_commit(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = _write_two_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove the PR-bound diff excludes dark-factory paths",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)

    def _write_ba_files() -> None:
        write_role_artifacts(run_dir, "BA", {"requirements.md": _BA_REQUIREMENTS})
        (work_dir / "feature.py").write_text(_FEATURE_SOURCE, encoding="utf-8")

    def _write_development_files() -> None:
        write_role_artifacts(
            run_dir, "DEVELOPMENT", {"implementation_summary.json": _DEVELOPMENT_SUMMARY}
        )

    ba_worker = _FileWritingWorker(
        FakeWorker(
            [
                WorkerResult(
                    status=WorkerResultStatus.COMPLETED,
                    summary="BA analysis complete",
                    worker_session_id="fake-ba-diff-proof",
                    artifacts=[ArtifactRef(type="requirements.md", path="artifacts/BA/requirements.md")],
                )
            ]
        ),
        _write_ba_files,
    )

    # BA enters, then runs (writes requirements.md + the stray feature.py
    # source change, commits requirements.md as an artifact commit, leaves
    # feature.py dirty for DEVELOPMENT's before-hook to recover).
    registry_ba = _registry(ba_worker)
    drive(run_id, session_factory=real_session_factory, registry=registry_ba, repo_root=root)

    # The base branch moves on AFTER the working branch was cut -- the exact
    # scenario that distinguishes the three-dot form from the two-dot one.
    (root / "post_cut.txt").write_text(_POST_CUT_MARKER, encoding="utf-8")
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "-m", "base moved on after the branch was cut"], cwd=root)

    development_worker = _FileWritingWorker(
        FakeWorker(
            [
                WorkerResult(
                    status=WorkerResultStatus.COMPLETED,
                    summary="implementation complete",
                    worker_session_id="fake-development-diff-proof",
                    artifacts=[
                        ArtifactRef(
                            type="implementation_summary.json",
                            path="artifacts/DEVELOPMENT/implementation_summary.json",
                        )
                    ],
                )
            ]
        ),
        _write_development_files,
    )
    registry_development = _registry(development_worker)
    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=registry_development,
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    # -- the three-dot (merge-base) form: has the work commit, excludes
    # -- .dark-factory entirely, and does NOT mention the base's own
    # -- post-cut file (D-10) -----------------------------------------------
    three_dot = collect_pr_diff(root, base_branch="main", working_branch=working_branch)
    assert "feature.py" in three_dot
    assert ".dark-factory" not in three_dot
    assert "post_cut.txt" not in three_dot

    # -- the contrast case: the two-dot direct-tree form DOES mention the
    # -- base's own post-cut file -- this is why D-10 names the three-dot
    # -- form specifically, not merely a happy-path assertion -------------
    two_dot = run_git(
        ["diff", f"main..{working_branch}", "--", ".", ARTIFACT_EXCLUDE_PATHSPEC],
        cwd=root,
    ).stdout
    assert "post_cut.txt" in two_dot

    # -- verification/diff.patch exists in the run tree after DEVELOPMENT
    # -- completed, and its content matches collect_pr_diff's output -------
    patch_text = run_artifact_text(
        root, run_id, working_branch, "verification/diff.patch"
    )
    assert patch_text == three_dot
