"""The D-09 proof: one artifact commit per completed role, in pipeline
order, force-added past the repository's own ``.gitignore`` -- and a
source-code change a worker left staged in the index survives an artifact
commit untouched (T-05-17) (05-03 Task 2).

Drives a real four-role run step by step (not via ``drive()``'s single-call
loop) so a source-file edit can be staged in the worktree's index at a
precise point between roles -- the same in-process db-test idiom as
``tests/db/test_four_role_pipeline.py``, but calling ``advance()`` directly
to control timing.
"""

from __future__ import annotations

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
from dark_factory.git.client import run_git
from dark_factory.git.diff import ARTIFACT_COMMIT_SUBJECT_PREFIX
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.orchestrator.runner import advance, drive, start_run
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
from tests.support.fake_artifacts import four_role_script

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """The same shipped-shape four-role tree ``test_four_role_pipeline.py``
    uses -- kept as a sibling copy (not imported), matching this repo's
    existing db-test convention."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"))
    definitions = {
        "BA": ("[]", "[requirements.md, acceptance_criteria.json]"),
        "ARCHITECTURE": (
            "[acceptance_criteria.json]",
            "[design.md, constraints.json]",
        ),
        "DEVELOPMENT": (
            "[design.md, constraints.json]",
            "[implementation_summary.json]",
        ),
        "QA": (
            "[acceptance_criteria.json, implementation_summary.json]",
            "[test_report.json, verdict.json]",
        ),
    }
    for role, (inputs, outputs) in definitions.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            "tools: []\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
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


def test_one_artifact_commit_per_role_force_added_and_source_edits_survive(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove one artifact commit per role",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    script = four_role_script(run_dir)
    registry = _registry(FakeWorker(script))

    # CREATED -> BA (enter: insert the row, no worker call yet)
    advance(run_id, session_factory=real_session_factory, registry=registry, repo_root=root)
    # BA runs -> ARCHITECTURE (BA's artifact commit happens here)
    advance(run_id, session_factory=real_session_factory, registry=registry, repo_root=root)
    # ARCHITECTURE (enter)
    advance(run_id, session_factory=real_session_factory, registry=registry, repo_root=root)

    # Stage a source-code edit in the worktree's index BEFORE the second
    # role's (ARCHITECTURE's) own advance -- proving a pathspec-limited
    # artifact commit never sweeps up something else a worker left staged
    # (T-05-17).
    (work_dir / "source_edit.txt").write_text(
        "a worker's own source change, not a Dark Factory artifact\n",
        encoding="utf-8",
    )
    run_git(["add", "source_edit.txt"], cwd=work_dir)

    # ARCHITECTURE runs -> DEVELOPMENT (ARCHITECTURE's artifact commit)
    advance(run_id, session_factory=real_session_factory, registry=registry, repo_root=root)

    staged_after = run_git(
        ["diff", "--cached", "--name-only"], cwd=work_dir
    ).stdout.splitlines()
    assert "source_edit.txt" in staged_after

    # Drive the remaining two roles (DEVELOPMENT, QA) to COMPLETED.
    final = drive(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.working_branch == working_branch

    # -- one commit per role, in pipeline order, no duplicates --------------
    log_output = run_git(
        ["log", working_branch, "--format=%s"], cwd=root
    ).stdout.splitlines()
    subjects = [
        line for line in log_output if line.startswith(ARTIFACT_COMMIT_SUBJECT_PREFIX)
    ]
    subjects.reverse()  # git log is newest-first; role order is oldest-first
    role_order = [
        subject.removeprefix(f"{ARTIFACT_COMMIT_SUBJECT_PREFIX} ").split(" ", 1)[0]
        for subject in subjects
    ]
    assert role_order == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]
    assert len(role_order) == len(set(role_order))

    # -- force-add actually happened: tracked on the working branch despite
    # -- the repository's own ignore rule still matching the path ----------
    tracked = run_git(
        ["ls-tree", "-r", "--name-only", working_branch], cwd=root
    ).stdout.splitlines()
    for role in ("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"):
        prefix = f".dark-factory/runs/{run_id}/artifacts/{role}/"
        assert any(line.startswith(prefix) for line in tracked), (
            f"{role}'s artifacts are not tracked on {working_branch}"
        )
    ignored = run_git(
        ["check-ignore", "--no-index", f".dark-factory/runs/{run_id}/"],
        cwd=root,
        check=False,
    )
    assert ignored.returncode == 0
