"""The phase tracer: a role invoking a capability its `tools:` list does not
grant is denied by `ToolRegistry.invoke()`, the attempt fails in the existing
Phase 4/5 failure shape, and Neon holds a `CAPABILITY_DENIED` row alongside
`ROLE_FAILED` / `RUN_FAILED` for it (TOOL-01, TOOL-03, D-01, D-05..D-08, SC1).

Follows the in-process db-test idiom of
`tests/db/test_run_owns_a_worktree.py`: a config tree built by
`config_root_factory` (git-initialised), `start_run` with the resolved
snapshot, a per-test `WorkerRegistry` injecting a worker that writes its own
artifact file (mimicking a real worker, which writes files before reporting
them), `drive` against the config tree's `repo_root`, and a teardown that
deletes every fixture row and force-removes any worktree left on disk.

The denial proof (a BA role whose `tools:` list omits `artifacts.read`) is
worthless without the grant proof beside it -- the identical tree with
`artifacts.read` granted reaches `COMPLETED` -- so both tests live here.
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
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.git.worktree import remove_worktree, worktree_path
from dark_factory.orchestrator.runner import drive, start_run
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

_ACCEPTANCE_CRITERIA = (
    '{"criteria": [{"id": "AC-1", "description": "the thing works"}]}'
)


class _ArtifactWritingWorker(CodingWorker):
    """A ``COMPLETED``-only worker that writes ``acceptance_criteria.json``
    into a precomputed run root, then returns a matching
    :class:`WorkerResult` -- mirrors
    ``tests/db/test_run_owns_a_worktree.py::_ArtifactWritingWorker``. Whether
    the write actually lands under ``artifacts.read``'s grant is irrelevant
    to this worker: it always writes the file and always reports it, exactly
    as a real worker would -- the grant is checked downstream, in
    ``collect_role_artifacts``, never here.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def _record(self, context: object) -> WorkerResult:
        role = getattr(context, "role", None)
        assert role is not None
        refs = write_role_artifacts(
            self._run_dir, role, {"acceptance_criteria.json": _ACCEPTANCE_CRITERIA}
        )
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


def _one_role_ba_tree(config_root_factory: Callable[..., Path], *, tools: str) -> Path:
    """A one-role ``[BA]`` config tree whose ``BA.yaml`` declares
    ``acceptance_criteria.json`` as its only output and carries ``tools``
    (a YAML flow-sequence literal, e.g. ``"[repo.read, repo.search]"``)."""
    root = config_root_factory(roles=("BA",))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        f"tools: {tools}\n"
        "permissions:\n  write_scope: []\n"
        "before: [ensure_clean_worktree]\n"
        "after: []\n"
        "inputs: []\n"
        "outputs: [acceptance_criteria.json]\n"
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


def test_a_role_invoking_an_ungranted_capability_is_denied_and_recorded(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
    engine: Engine,
) -> None:
    """SC1 tracer: BA declares ``acceptance_criteria.json`` as an output but
    its ``tools:`` list omits ``artifacts.read`` -- the read is denied by
    ``ToolRegistry.invoke()`` before the reported file is ever opened, the
    run fails in the existing Phase 4/5 shape, and ``run_events`` carries
    ``CAPABILITY_DENIED`` ahead of ``ROLE_FAILED`` and ``RUN_FAILED``, in
    that relative order, with zero ``artifacts`` rows for the attempt."""
    root = _one_role_ba_tree(config_root_factory, tools="[repo.read, repo.search]")
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:a role invokes a capability it was not granted",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    work_dir = worktree_path(root, run_id)
    run_dir = run_root(work_dir, run_id)
    worker = _ArtifactWritingWorker(run_dir)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        execution = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
        assert execution is not None
        assert execution.status == "FAILED"
        assert execution.error is not None

        event_rows = session.scalars(
            sa.select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        ).all()
        event_types = [row.type for row in event_rows]
        assert "CAPABILITY_DENIED" in event_types
        assert "ROLE_FAILED" in event_types
        assert "RUN_FAILED" in event_types
        assert event_types.index("CAPABILITY_DENIED") < event_types.index(
            "ROLE_FAILED"
        )
        assert event_types.index("ROLE_FAILED") < event_types.index("RUN_FAILED")

        (denial_row,) = [row for row in event_rows if row.type == "CAPABILITY_DENIED"]
        assert set(denial_row.payload) == {"role", "capability", "reason"}
        assert denial_row.payload["capability"] == "artifacts.read"
        assert denial_row.payload["role"] == "BA"

        artifact_rows = session.scalars(
            sa.select(ArtifactReference).where(
                ArtifactReference.role_execution_id == execution.id
            )
        ).all()
    assert artifact_rows == []


def test_the_same_tree_with_the_grant_present_reaches_completed(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[tuple[Any, Path]],
    engine: Engine,
) -> None:
    """The grant proof beside the denial proof: the identical one-role
    ``[BA]`` tree, differing only in that ``tools:`` grants
    ``artifacts.read`` (and ``artifacts.write``, matching the shipped BA
    grant set), reaches ``COMPLETED`` with its declared artifact row
    present -- proving the migration is behaviour-preserving when the grant
    is present."""
    root = _one_role_ba_tree(
        config_root_factory,
        tools="[repo.read, repo.search, artifacts.read, artifacts.write]",
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:a role invokes a capability it was granted",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append((run_id, root))

    work_dir = worktree_path(root, run_id)
    run_dir = run_root(work_dir, run_id)
    worker = _ArtifactWritingWorker(run_dir)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.COMPLETED

        execution = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
        assert execution is not None
        assert execution.status == "COMPLETED"

        event_types = session.scalars(
            sa.select(RunEvent.type)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq)
        ).all()
        assert "CAPABILITY_DENIED" not in event_types

        artifact_rows = session.scalars(
            sa.select(ArtifactReference).where(
                ArtifactReference.role_execution_id == execution.id
            )
        ).all()
    assert len(artifact_rows) == 1
    assert artifact_rows[0].type == "acceptance_criteria.json"
