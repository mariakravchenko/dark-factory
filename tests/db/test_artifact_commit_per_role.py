"""The D-09 proof: one artifact commit per completed role, in pipeline
order, force-added past the repository's own ``.gitignore`` -- and a
source-code change a worker left staged in the index survives an artifact
commit untouched (T-05-17) (05-03 Task 2).

Drives a real four-role run step by step (not via ``drive()``'s single-call
loop) so a source-file edit can be staged in the worktree's index at a
precise point between roles -- the same in-process db-test idiom as
``tests/db/test_four_role_pipeline.py``, but calling ``advance()`` directly
to control timing.

Also carries the Task 3 cleanup-arm coverage (D-04): a ``COMPLETED`` run
whose terminal role left a trailing uncommitted edit gets a final recovery
commit and then loses its worktree; a ``FAILED`` run and a ``WAITING_HUMAN``
run both keep theirs. Each asserts through ``git worktree list
--porcelain`` in the main repository, not merely directory existence, so a
half-removed worktree with stale ``.git/worktrees/`` bookkeeping cannot
pass.
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
from dark_factory.git.diff import ARTIFACT_COMMIT_SUBJECT_PREFIX
from dark_factory.git.lifecycle import WIP_COMMIT_SUBJECT_PREFIX
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
from tests.support.fake_artifacts import write_role_artifacts

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# The same minimal, schema-valid-per-D-07 content
# ``tests.support.fake_artifacts.four_role_script`` writes -- but keyed by
# role so :class:`_LazyFourRoleWorker` below can write only one role's files
# at a time, from *inside* that role's own ``execute()`` call.
_ROLE_ARTIFACT_FILES: dict[str, dict[str, str]] = {
    "BA": {
        "requirements.md": (
            "# Requirements\n\n1. The system does the thing correctly.\n"
        ),
        "acceptance_criteria.json": json.dumps(
            {"criteria": [{"id": "AC-1", "description": "the thing works"}]}
        ),
    },
    "ARCHITECTURE": {
        "design.md": (
            "# Design\n\nImplement the thing in the existing service layer; "
            "no new component is needed.\n"
        ),
        "constraints.json": json.dumps(
            {"constraints": [{"id": "C-1", "description": "no new database migration"}]}
        ),
    },
    "DEVELOPMENT": {
        "implementation_summary.json": json.dumps(
            {
                "summary": "implemented the thing",
                "changed_files": [],
                "tests_added": [],
            }
        ),
    },
    "QA": {
        "test_report.json": json.dumps(
            {
                "cases": [
                    {
                        "name": "AC-1: the thing works",
                        "result": "PASS",
                        "detail": "reproduced manually",
                    }
                ]
            }
        ),
        "verdict.json": json.dumps(
            {
                "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
                "issues": [],
                "status": "PASS",
            }
        ),
    },
}


class _LazyFourRoleWorker(CodingWorker):
    """Writes each role's artifact files at ``execute()`` time -- not
    upfront the way ``tests.support.fake_artifacts.four_role_script`` does.

    ``commit_run_artifacts``'s force-add pathspec covers the *whole* run
    tree (``.dark-factory/runs/<run_id>``, not a per-role subdirectory --
    it must also carry ``verification/diff.patch`` when a role's ``after:``
    list configures ``collect_diff``), relying on nothing appearing under
    that tree until the role that produces it actually runs. A
    front-loaded write (``four_role_script``'s shape) defeats that: every
    later role's not-yet-run files would already be sitting on disk when
    the *first* completed role's own artifact commit force-adds the whole
    tree, so that first commit sweeps them all up and leaves nothing new
    for the later roles' own commits to stage -- exactly the bug this test
    exists to prove does NOT happen. A real worker call only ever writes
    its own role's files exactly when it runs; this fixture matches that
    timing.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role in _ROLE_ARTIFACT_FILES, role
        refs = write_role_artifacts(self._run_dir, role, _ROLE_ARTIFACT_FILES[role])
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=f"{role} completed",
            worker_session_id=f"fake-{role.lower()}",
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
    # Phase 6 (plan 06-01, TOOL-03, A-06-02): mirrors the shipped
    # .dark-factory/roles/*.yaml `tools:` grants exactly -- artifact reads
    # are now capability-gated (D-03), so every role above (all four
    # declare non-empty `outputs:`) needs `artifacts.read`.
    tools = {
        "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "DEVELOPMENT": (
            "[repo.read, repo.search, repo.write, repo.write_tests, "
            "shell.execute, artifacts.read, artifacts.write]"
        ),
        "QA": (
            "[repo.read, repo.search, repo.write_tests, shell.execute, "
            "artifacts.read, artifacts.write]"
        ),
    }
    for role, (inputs, outputs) in definitions.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {tools[role]}\n"
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
    registry = _registry(_LazyFourRoleWorker(run_dir))

    # CREATED -> BA (enter: insert the row, no worker call yet)
    advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    # BA runs -> ARCHITECTURE (BA's artifact commit happens here)
    advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    # ARCHITECTURE (enter)
    advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )

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
    advance(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )

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


# --------------------------------------------------------------------------- #
# Task 3 cleanup-arm coverage (D-04): COMPLETED recovers-then-removes,
# FAILED and WAITING_HUMAN both keep their worktree.
# --------------------------------------------------------------------------- #


def test_completed_run_with_a_trailing_edit_gets_a_recovery_commit_then_loses_its_worktree(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:terminal role leaves a trailing uncommitted edit",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )

    class _TrailingEditWorker(CodingWorker):
        """Leaves an uncommitted trailing edit *inside* its own ``execute``
        call -- after the before-hook's own ``ensure_clean_worktree`` pass
        has already run and found the tree clean, so only the ``COMPLETED``
        cleanup's own recovery pass (not the before-hook) can catch it."""

        def __init__(self, inner: FakeWorker) -> None:
            self._inner = inner

        def execute(self, context: Any) -> WorkerResult:
            (work_dir / "trailing_edit.txt").write_text(
                "left behind by the terminal role\n", encoding="utf-8"
            )
            return self._inner.execute(context)

        def resume(
            self, context: Any, previous: WorkerResult, answer: str | None
        ) -> WorkerResult:
            return self._inner.resume(context, previous, answer)

        def capabilities(self) -> WorkerCapabilities:
            return self._inner.capabilities()

    inner = FakeWorker(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="BA done, but left a trailing edit",
                worker_session_id="fake-ba-trailing",
            )
        ]
    )
    registry = _registry(_TrailingEditWorker(inner))

    final = drive(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert final is RunStatus.COMPLETED

    # -- the worktree is gone, proven through git's own bookkeeping, not
    # -- merely directory existence -----------------------------------------
    assert not work_dir.exists()
    porcelain = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert str(work_dir) not in porcelain

    # -- the trailing edit was recovered onto the working branch via a WIP
    # -- commit before removal (A-05-07, RESEARCH Pitfall 5) ----------------
    log_output = run_git(
        ["log", working_branch, "--format=%s"], cwd=root
    ).stdout.splitlines()
    assert any(subject.startswith(WIP_COMMIT_SUBJECT_PREFIX) for subject in log_output)


def test_failed_run_keeps_its_worktree(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:BA fails outright",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )

    script = [
        WorkerResult(
            status=WorkerResultStatus.FAILED,
            summary="BA failed",
            worker_session_id="fake-ba-failed",
            error="synthetic failure",
        )
    ]
    registry = _registry(FakeWorker(script))

    final = drive(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert final is RunStatus.FAILED

    assert work_dir.exists()
    porcelain = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert str(work_dir) in porcelain


def test_waiting_human_run_keeps_its_worktree(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:BA needs a human answer",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )

    script = [
        WorkerResult(
            status=WorkerResultStatus.NEEDS_INPUT,
            summary="BA needs clarification",
            worker_session_id="fake-ba-needs-input",
            questions=["What should the endpoint be named?"],
        )
    ]
    registry = _registry(FakeWorker(script))

    final = drive(
        run_id, session_factory=real_session_factory, registry=registry, repo_root=root
    )
    assert final is RunStatus.WAITING_HUMAN

    assert work_dir.exists()
    porcelain = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    assert str(work_dir) in porcelain
