"""The phase tracer: BA hands ``acceptance_criteria.json`` to ARCHITECTURE
through the artifacts table + the role ``inputs``/``outputs`` contract
(ORCH-04, ROLE-01, ROLE-02, CTX-01..CTX-04, ART-01..ART-03, STATE-05).

Follows the in-process db-test idiom of ``tests/db/test_role_hooks_invoked.py``:
``start_run`` + ``drive`` with an injected ``WorkerRegistry`` against the real
provisioned PostgreSQL, ``cleanup_runs`` deleting every fixture row (including
``artifacts``) at teardown.

A single :class:`~dark_factory.workers.fake.FakeWorker` script serves the whole
run (the registry-scoped-singleton note in ``workers/registry.py``'s
docstring), wrapped in a small capturing worker so the test can inspect the
``RoleContext`` object the runner actually built for ARCHITECTURE.
"""

from __future__ import annotations

import hashlib
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

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_BA_SUMMARY = "BA_ONLY_SUMMARY_MARKER_should_never_reach_ARCHITECTURE_context"

_VALID_ACCEPTANCE_CRITERIA = json.dumps(
    {"criteria": [{"id": "AC-1", "description": "the thing works"}]}
)
_INVALID_ACCEPTANCE_CRITERIA = json.dumps(
    {"criteria": [{"id": "AC-1"}]}  # missing required "description"
)


class _CapturingWorker(CodingWorker):
    """Delegates to a real :class:`FakeWorker` but records every ``context``
    object it is handed, so the test can inspect the ``RoleContext`` the
    runner built for each step."""

    def __init__(self, script: list[WorkerResult], captured: list[object]) -> None:
        self._inner = FakeWorker(script)
        self._captured = captured

    def execute(self, context: object) -> WorkerResult:
        self._captured.append(context)
        return self._inner.execute(context)

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        self._captured.append(context)
        return self._inner.resume(context, previous, answer)

    def capabilities(self) -> WorkerCapabilities:
        return self._inner.capabilities()


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


def _write_two_role_tree(
    config_root_factory: Callable[..., Path],
) -> Path:
    """A ``[BA, ARCHITECTURE]`` config tree with the real artifact contract:
    BA declares ``acceptance_criteria.json`` as an output, ARCHITECTURE
    declares it as an input. Overwrites the two role files
    ``config_root_factory`` wrote with generic empty ``inputs``/``outputs`` --
    the same build-then-overwrite idiom
    ``tests/integration/test_role_yaml_drives_behaviour.py`` uses."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE"))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: []\n"
        "outputs: [acceptance_criteria.json]\n"
        "examples: []\n",
        encoding="utf-8",
    )
    (root / ".dark-factory/roles/ARCHITECTURE.yaml").write_text(
        "name: ARCHITECTURE\n"
        "worker: fake\n"
        "instructions: ../instructions/architecture.md\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: [acceptance_criteria.json]\n"
        "outputs: []\n"
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


def test_ba_hands_acceptance_criteria_to_architecture(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _write_two_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:ba hands off acceptance criteria",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    # GIT-01: pre-create the run's worktree now (idempotent -- the runner's
    # own ensure_worktree call inside drive() reuses it) so scripted artifact
    # content can be written exactly where the runner will look, mirroring
    # what a real worker's own writes would already have produced.
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    ba_refs = write_role_artifacts(
        run_dir, "BA", {"acceptance_criteria.json": _VALID_ACCEPTANCE_CRITERIA}
    )

    captured: list[object] = []
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=_BA_SUMMARY,
            worker_session_id="fake-ba-001",
            artifacts=ba_refs,
        ),
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="architecture design complete",
            worker_session_id="fake-architecture-001",
        ),
    ]
    worker = _CapturingWorker(script, captured)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    # -- 05-03 (D-04): this run reaches COMPLETED, so its worktree is
    # -- removed by cleanup -- the content now lives only on the working
    # -- branch. read through the branch, never the (now-gone) disk path.
    with Session(engine) as session:
        completed_run = session.get(Run, run_id)
        assert completed_run is not None
        working_branch = completed_run.working_branch
    assert working_branch is not None
    file_text = run_artifact_text(
        root, run_id, working_branch, "artifacts/BA/acceptance_criteria.json"
    )
    assert file_text == _VALID_ACCEPTANCE_CRITERIA
    file_bytes = file_text.encode("utf-8")

    # -- exactly one artifacts row, metadata only ---------------------------
    with Session(engine) as session:
        rows = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.type == "acceptance_criteria.json"
    assert row.path == "artifacts/BA/acceptance_criteria.json"
    assert row.checksum == hashlib.sha256(file_bytes).hexdigest()
    assert row.artifact_metadata == {}

    # -- no column holds the file's body text --------------------------------
    for column_value in (
        row.type,
        row.path,
        row.checksum,
        json.dumps(row.artifact_metadata),
    ):
        assert _VALID_ACCEPTANCE_CRITERIA not in str(column_value)

    # -- ARCHITECTURE's RoleContext carries BA's content, never its prose ---
    assert len(captured) == 2
    architecture_context = captured[1]
    assert architecture_context is not None
    assert len(architecture_context.inputs) == 1  # type: ignore[union-attr]
    resolved_input = architecture_context.inputs[0]  # type: ignore[union-attr]
    assert resolved_input.filename == "acceptance_criteria.json"
    assert resolved_input.produced_by == "BA"
    assert resolved_input.content == _VALID_ACCEPTANCE_CRITERIA

    dumped = architecture_context.model_dump_json()  # type: ignore[union-attr]
    assert _BA_SUMMARY not in dumped
    assert not hasattr(architecture_context, "summary")


def test_malformed_acceptance_criteria_fails_the_role_with_zero_artifact_rows(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _write_two_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:ba writes a malformed acceptance criteria doc",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    # GIT-01: pre-create the run's worktree now (idempotent -- the runner's
    # own ensure_worktree call inside drive() reuses it) so scripted artifact
    # content can be written exactly where the runner will look, mirroring
    # what a real worker's own writes would already have produced.
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    ba_refs = write_role_artifacts(
        run_dir, "BA", {"acceptance_criteria.json": _INVALID_ACCEPTANCE_CRITERIA}
    )

    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="ba done (but the artifact is invalid)",
            worker_session_id="fake-ba-invalid",
            artifacts=ba_refs,
        ),
    ]
    worker = FakeWorker(script)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        latest_execution = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
        assert latest_execution is not None
        assert latest_execution.status == "FAILED"

        event_types = session.scalars(
            sa.select(RunEvent.type)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq)
        ).all()
        assert "ROLE_FAILED" in event_types
        assert "RUN_FAILED" in event_types

        artifact_rows = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).all()
    assert artifact_rows == []
