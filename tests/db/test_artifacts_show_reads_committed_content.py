"""Plan 12-05, OBS-01: ``--show`` reads a finished run's artifact content
through its working branch -- the window a filesystem read would have
missed, since ``_cleanup_run_worktree`` removes the worktree on every
``COMPLETED`` transition (D-04).

Drives one real four-role run to ``COMPLETED`` (the same
``LazyFourRoleWorker`` fixture composition ``tests/db/test_publish_step.py``
and ``tests/db/test_artifact_commit_per_role.py`` already use), then proves
that ``read_artifact_rows`` / ``read_artifact_target`` / ``run_artifact_text``
can still retell every artifact that run produced -- against real
PostgreSQL and real git -- after the worktree that once held them on disk is
gone.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import ArtifactRow
from dark_factory.git.committed import run_artifact_text
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.observability.run_detail import (
    UnknownArtifactError,
    read_artifact_rows,
    read_artifact_target,
)
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence import mutations
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import LazyFourRoleWorker

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# Greppably fake -- never a real credential (same literal shape as
# tests/conftest.py's own `_FAKE_DB_URL` family; duplicated here because this
# module's module-scoped fixture cannot depend on the function-scoped
# `use_fake_secrets` fixture it mirrors).
_FAKE_DB_URL = "postgresql+psycopg://df_fake_user:df_fake_pw_0123456789@fake.invalid:5432/df_fake_db"
_FAKE_DB_URL_DIRECT = "postgresql://df_fake_user:df_fake_pw_0123456789@fake-direct.invalid:5432/df_fake_db"
_FAKE_GITHUB_TOKEN = "ghp_FAKEfakeFAKEfake0000000000000000000000"

# The exact literal content `tests/support/fake_artifacts.py`'s
# `LazyFourRoleWorker` writes for QA's `verdict.json` -- sourced from that
# module's own `_FOUR_ROLE_FILES["QA"]["verdict.json"]` construction, not
# re-derived or read back from the git blob under test.
_EXPECTED_VERDICT_JSON = json.dumps(
    {
        "criteria": [{"criterion_id": "AC-1", "result": "PASS", "notes": ""}],
        "issues": [],
        "status": "PASS",
    }
)

_DEFINITIONS: dict[str, tuple[str, str]] = {
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
_TOOLS: dict[str, str] = {
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


def _write_four_role_tree(root: Path, *, roles: tuple[str, ...]) -> Path:
    """Write a complete ``.dark-factory/`` tree with real ``inputs:``/
    ``outputs:`` declarations for ``roles`` -- a self-contained, module-local
    duplicate of ``test_artifact_commit_per_role.py``'s own
    ``_write_four_role_tree`` (this repo's established convention: a sibling
    copy, never an import, per ``12-02-SUMMARY.md``'s identical decision)."""
    (root / ".dark-factory/roles").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory/instructions").mkdir(parents=True, exist_ok=True)
    (root / ".dark-factory.yaml").write_text(
        "version: 1\n"
        "repository:\n  base_branch: main\n"
        f"workflow:\n  roles: [{', '.join(roles)}]\n"
        "roles_dir: .dark-factory/roles\n"
        "quality_gate:\n  commands: []\n"
        "retry:\n"
        "  qa_developer_max_iterations: 3\n"
        "  quality_gate_max_iterations: 2\n"
        "publishing:\n  create_pr: false\n",
        encoding="utf-8",
    )
    for role in roles:
        inputs, outputs = _DEFINITIONS[role]
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {_TOOLS[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )
        (root / f".dark-factory/instructions/{role.lower()}.md").write_text(
            f"# {role}\n\nScripted {role} instruction text for tests.\n",
            encoding="utf-8",
        )
    from tests.support.git_repo import make_git_repo

    return make_git_repo(root)


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


@contextmanager
def _fake_secrets_patched() -> Iterator[None]:
    fake_settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
    )
    with patch.object(mutations, "get_settings", lambda: fake_settings):
        yield


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


@dataclass(frozen=True)
class _CompletedRun:
    run_id: UUID
    repo_root: Path
    work_dir: Path
    working_branch: str
    rows: list[ArtifactRow]


@pytest.fixture(scope="module")
def _module_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture(scope="module")
def completed_four_role_run(
    tmp_path_factory: pytest.TempPathFactory,
    engine: Engine,
    _module_session_factory: SessionFactory,
) -> Iterator[_CompletedRun]:
    """Drive one real four-role run to ``COMPLETED`` exactly once, shared by
    every test in this module that only needs to *read back* the result --
    the expensive part (a real ``drive()`` against real PostgreSQL and real
    git) happens a single time."""
    root = tmp_path_factory.mktemp("repo")
    root = _write_four_role_tree(
        root, roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA")
    )
    snapshot = load_effective_config(root)

    with _fake_secrets_patched():
        run_id = start_run(
            "text:prove --show reads committed content, not a live path",
            session_factory=_module_session_factory,
            snapshot=snapshot,
        )

        working_branch = working_branch_name(run_id)
        work_dir = ensure_worktree(
            root, run_id, base_branch="main", working_branch=working_branch
        )
        run_dir = run_root(work_dir, run_id)
        registry = _registry(LazyFourRoleWorker(run_dir))

        final = drive(
            run_id,
            session_factory=_module_session_factory,
            registry=registry,
            repo_root=root,
        )
        assert final is RunStatus.COMPLETED

    rows = read_artifact_rows(run_id, session_factory=_module_session_factory)

    yield _CompletedRun(
        run_id=run_id,
        repo_root=root,
        work_dir=work_dir,
        working_branch=working_branch,
        rows=rows,
    )

    with engine.begin() as conn:
        conn.execute(
            sa.delete(ArtifactReference).where(ArtifactReference.run_id == run_id)
        )
        conn.execute(sa.delete(RunEvent).where(RunEvent.run_id == run_id))
        conn.execute(
            sa.delete(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )
        conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id == run_id))
        conn.execute(sa.delete(Run).where(Run.id == run_id))


def test_the_worktree_directory_no_longer_exists_on_disk(
    completed_four_role_run: _CompletedRun,
) -> None:
    """The precondition the whole task exists for -- asserted first and on
    its own, so the read assertions that follow cannot accidentally pass
    against a surviving directory."""
    run = completed_four_role_run
    assert not run.work_dir.exists()


def test_read_artifact_rows_returns_one_row_per_artifacts_table_row(
    completed_four_role_run: _CompletedRun,
    engine: Engine,
) -> None:
    run = completed_four_role_run
    with Session(engine) as session:
        db_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.run_id == run.run_id)
        )
    assert db_count == len(run.rows)
    assert db_count == 7  # BA(2) + ARCHITECTURE(2) + DEVELOPMENT(1) + QA(2)

    role_set = {row.role for row in run.rows}
    assert role_set == {"BA", "ARCHITECTURE", "DEVELOPMENT", "QA"}

    with Session(engine) as session:
        db_paths = set(
            session.scalars(
                sa.select(ArtifactReference.path).where(
                    ArtifactReference.run_id == run.run_id
                )
            ).all()
        )
    assert {row.path for row in run.rows} == db_paths


def test_run_artifact_text_returns_the_exact_fixture_content_for_a_removed_worktree(
    completed_four_role_run: _CompletedRun,
    engine: Engine,
) -> None:
    """Item 3: for the artifact whose content the fixture pins most
    precisely (QA's ``verdict.json``), the git-read content is byte-for-byte
    the literal the fixture wrote -- read through
    :func:`read_artifact_target` + :func:`run_artifact_text`, never a second
    read of the same filesystem source (the worktree is already gone)."""
    run = completed_four_role_run

    def _session_factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    verdict_row = next(row for row in run.rows if row.path.endswith("verdict.json"))

    target = read_artifact_target(
        verdict_row.artifact_id, session_factory=_session_factory
    )
    assert target.run_id == run.run_id
    assert target.working_branch == run.working_branch
    assert target.path == verdict_row.path

    content = run_artifact_text(
        run.repo_root, target.run_id, target.working_branch, target.path
    )
    assert content == _EXPECTED_VERDICT_JSON


def test_the_same_artifact_is_absent_under_the_removed_worktree_filesystem_path(
    completed_four_role_run: _CompletedRun,
) -> None:
    """Item 4: the live-filesystem path a pre-12-05 implementation would
    have read from is provably gone -- records *why* the git read is
    mandatory, not merely that it works. A future reader who replaces the
    git read with a disk read must be able to see this assertion fail and
    understand why from the assertion alone."""
    run = completed_four_role_run
    verdict_row = next(row for row in run.rows if row.path.endswith("verdict.json"))

    live_path = run_root(run.work_dir, run.run_id) / verdict_row.path
    assert not live_path.exists(), (
        "the artifact is still readable from a live filesystem path -- the "
        "whole point of this plan is that after COMPLETED, it is not"
    )


def test_read_artifact_target_with_an_unused_uuid_raises_unknown_artifact_error(
    engine: Engine,
) -> None:
    def _session_factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    with pytest.raises(UnknownArtifactError):
        read_artifact_target(uuid4(), session_factory=_session_factory)


def test_an_artifact_whose_run_has_no_working_branch_yields_none_not_a_raise(
    tmp_path: Path,
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Item 6: constructed by driving a one-role run to completion and then
    reading back a run whose ``working_branch`` column is ``NULL`` -- the
    same state a Phase-1-era or text-sourced run predating a working-branch
    assignment would carry. ``ArtifactTarget.working_branch`` must be
    ``None``, not a raise."""
    root = _write_four_role_tree(tmp_path / "repo", roles=("BA",))
    snapshot = load_effective_config(root)

    with _fake_secrets_patched():
        run_id = start_run(
            "text:a run whose working_branch is later nulled",
            session_factory=real_session_factory,
            snapshot=snapshot,
        )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    registry = _registry(LazyFourRoleWorker(run_dir))

    with _fake_secrets_patched():
        final = drive(
            run_id,
            session_factory=real_session_factory,
            registry=registry,
            repo_root=root,
        )
    assert final is RunStatus.COMPLETED

    rows = read_artifact_rows(run_id, session_factory=real_session_factory)
    assert rows, "a one-role BA pipeline produced no artifacts to test against"

    # Simulate the "no working branch" state honestly: NULL the column this
    # run already has, rather than fabricate a row through a different path.
    with engine.begin() as conn:
        conn.execute(sa.update(Run).where(Run.id == run_id).values(working_branch=None))

    target = read_artifact_target(
        rows[0].artifact_id, session_factory=real_session_factory
    )
    assert target.working_branch is None
    assert target.run_id == run_id
    assert target.path == rows[0].path
