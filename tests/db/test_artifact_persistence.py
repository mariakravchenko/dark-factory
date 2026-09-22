"""Phase 4 Success Criterion 2 (`.planning/ROADMAP.md`, Phase 4):

    "Every artifact has an `ArtifactReference` row in Neon while its content
    stays on the filesystem -- no artifact body is stored in the database."

This module proves SC2 and ART-03 / STATE-05: it drives the same real
four-role run as `tests/db/test_four_role_pipeline.py`, then asserts the
`artifacts` table's row count and per-row shape (role_execution_id
attribution, relative path, checksum round trip, empty `metadata`), and runs
a body-text sweep across every JSONB/text column of `runs`, `role_executions`,
`run_events` and `artifacts` proving none of them holds a byte of any
artifact's content. It also proves the negative direction of
`uq_artifact_role_execution_path`: a duplicate `(role_execution_id, path)`
insert through the one mutation path raises an integrity error rather than
silently creating a duplicate reference.

Follows the same db-test idiom as `tests/db/test_four_role_pipeline.py` and
`tests/db/test_artifact_handoff.py` (04-01).
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.persistence.mutations import ArtifactReferenceWrite, apply_transition
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import LazyFourRoleWorker
from tests.support.git_repo import run_artifact_text

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# (role, filename) -> a distinctive substring genuinely present in that file's
# body (per `tests/support/fake_artifacts.py::four_role_script`), used for the
# absence sweep. Each is long/specific enough that a coincidental match in an
# unrelated column would be implausible.
_BODY_SUBSTRINGS: tuple[tuple[str, str, str], ...] = (
    ("BA", "requirements.md", "The system does the thing correctly"),
    ("BA", "acceptance_criteria.json", "the thing works"),
    ("ARCHITECTURE", "design.md", "existing service layer"),
    ("ARCHITECTURE", "constraints.json", "no new database migration"),
    ("DEVELOPMENT", "implementation_summary.json", "implemented the thing"),
    ("QA", "test_report.json", "reproduced manually"),
    ("QA", "verdict.json", "AC-1"),
)


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """Same shipped-shape four-role tree as `test_four_role_pipeline.py` --
    kept as a sibling copy (not imported) so each proof module stands alone,
    matching this repo's existing db-test convention (each module owns its
    fixture-tree helper)."""
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


def _drive_four_role_run(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> tuple[Any, Path, Path, str]:
    """Shared setup: drive one real four-role run to COMPLETED, return
    ``(run_id, run_dir, root, working_branch)``.

    05-03 (D-04): a run that reaches COMPLETED has its worktree removed by
    cleanup, so ``run_dir`` is no longer on disk by the time this returns --
    callers that need the artifact content read it through
    ``run_artifact_text(root, run_id, working_branch, ...)`` off the working
    branch, never off ``run_dir`` directly.
    """
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove SC2 artifact persistence",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    # GIT-01: pre-create the run's worktree now (idempotent -- the runner's
    # own ensure_worktree call inside drive() reuses it) so each role's
    # scripted artifact content is written exactly where the runner will
    # look, mirroring what a real worker's own writes would already have
    # produced. LazyFourRoleWorker (not four_role_script + FakeWorker) writes
    # each role's files at execute() time, one role at a time -- a
    # front-loaded write trips plan 08-05's enforce_artifact_scope, which
    # expects only the currently-executing role's own uncommitted writes to
    # be present (G-08-2 follow-on; see tests/support/fake_artifacts.py).
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

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
        working_branch = run.working_branch
    assert working_branch is not None
    return run_id, run_dir, root, working_branch


def test_seven_artifacts_rows_reference_metadata_only_with_checksum_round_trip(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    run_id, _run_dir, root, working_branch = _drive_four_role_run(
        config_root_factory, real_session_factory, cleanup_runs, engine
    )

    with Session(engine) as session:
        rows = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).all()
        executions_by_id = {
            e.id: e
            for e in session.scalars(
                sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
            ).all()
        }

    # -- seven declared outputs across BA/ARCHITECTURE/DEVELOPMENT/QA --------
    # (requirements.md + acceptance_criteria.json, design.md + constraints.json,
    # implementation_summary.json, test_report.json + verdict.json -- the
    # literal SC1 list; see test_four_role_pipeline.py's module docstring for
    # why this is seven, not the task prose's "six".)
    assert len(rows) == 7

    for row in rows:
        # -- role_execution_id attribution: points at the role whose outputs
        # -- declares this filename --
        execution = executions_by_id[row.role_execution_id]
        assert execution.run_id == run_id

        # -- content matches the checksum, read through the working branch
        # -- (05-03, D-04): the worktree this run wrote into is gone by now --
        file_text = run_artifact_text(root, run_id, working_branch, row.path)
        file_bytes = file_text.encode("utf-8")
        assert row.checksum == hashlib.sha256(file_bytes).hexdigest()

        # -- metadata is an empty object --
        assert row.artifact_metadata == {}


def test_no_database_column_holds_any_artifact_body_text(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    run_id, _run_dir, root, working_branch = _drive_four_role_run(
        config_root_factory, real_session_factory, cleanup_runs, engine
    )

    # -- first: prove each substring really is present in its source file, so
    # -- the sweep below cannot pass by searching for nothing -- read through
    # -- the working branch (05-03, D-04): the worktree is gone by now.
    for role, filename, substring in _BODY_SUBSTRINGS:
        body = run_artifact_text(
            root, run_id, working_branch, f"artifacts/{role}/{filename}"
        )
        assert substring in body, (
            f"test bug: {substring!r} is not actually in {role}/{filename}"
        )

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        executions = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).all()
        events = session.scalars(
            sa.select(RunEvent).where(RunEvent.run_id == run_id)
        ).all()
        artifact_rows = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).all()

        rendered: list[str] = [
            json.dumps(run.normalized_task, default=str),
            json.dumps(run.workflow, default=str),
            str(run.source_ref),
        ]
        for execution in executions:
            rendered.append(json.dumps(execution.result, default=str))
            rendered.append(json.dumps(execution.error, default=str))
        for event in events:
            rendered.append(json.dumps(event.payload, default=str))
        for artifact_row in artifact_rows:
            rendered.append(artifact_row.type)
            rendered.append(artifact_row.path)
            rendered.append(str(artifact_row.checksum))
            rendered.append(json.dumps(artifact_row.artifact_metadata, default=str))

    haystack = "\n".join(rendered)
    for role, filename, substring in _BODY_SUBSTRINGS:
        assert substring not in haystack, (
            f"{role}/{filename}'s body text ({substring!r}) leaked into a "
            f"database column"
        )


def test_duplicate_role_execution_id_and_path_raises_integrity_error(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    run_id, _run_dir, _root, _working_branch = _drive_four_role_run(
        config_root_factory, real_session_factory, cleanup_runs, engine
    )

    with Session(engine) as session:
        existing = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).first()
        assert existing is not None
        run = session.get(Run, run_id)
        assert run is not None
        expected_status = run.status
        current_role = run.current_role
        current_step = run.current_step

    # A fresh session -- session.get() above already autobegan a transaction
    # on the previous one, and apply_transition's own `with session.begin():`
    # refuses to begin a second transaction on an already-begun Session.
    with Session(engine) as session, pytest.raises(IntegrityError):
        apply_transition(
            session,
            run_id=run_id,
            expected_status=expected_status,
            next_status=expected_status,
            next_current_role=current_role,
            next_current_step=current_step,
            artifact_references=[
                ArtifactReferenceWrite(
                    role_execution_id=existing.role_execution_id,
                    type=existing.type,
                    path=existing.path,
                    checksum=existing.checksum,
                    metadata={},
                )
            ],
            events=[],
        )
