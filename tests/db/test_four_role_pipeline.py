"""Phase 4 Success Criterion 1 (`.planning/ROADMAP.md`, Phase 4):

    "A run started from `spec:./task.md` executes all four roles in order on
    `FakeWorker` and produces `requirements.md` + `acceptance_criteria.json`,
    `design.md` + `constraints.json`, `implementation_summary.json`, and
    `test_report.json` + `verdict.json` under `.dark-factory/runs/<run-id>/`."

That is seven filenames across four roles -- BA's `requirements.md` and
ARCHITECTURE's `design.md` are declared, unvalidated Markdown outputs
alongside their JSON siblings, exactly as `.dark-factory/roles/BA.yaml` and
`.dark-factory/roles/ARCHITECTURE.yaml` have shipped since Phase 3 / 04-01.
This module drives one real four-role run (BA -> ARCHITECTURE -> DEVELOPMENT
-> QA) on the shared `fake` worker and proves the run reaches `COMPLETED`
with exactly one `COMPLETED` `role_executions` row per role, in pipeline
order, with all seven files present on disk, and that QA's `RoleContext`
carries exactly the two inputs its role config declares -- one of them
(`acceptance_criteria.json`) produced two roles earlier, proving selection is
by declared filename, never pipeline adjacency (ROLE-04, CTX-01).

Follows the in-process db-test idiom of `tests/db/test_role_hooks_invoked.py`
and `tests/db/test_artifact_handoff.py` (04-01): `start_run` + `drive` with an
injected `WorkerRegistry` against the real provisioned PostgreSQL,
`cleanup_runs` deleting every fixture row (including `artifacts`) at
teardown. The single four-element script comes from
`tests/support/fake_artifacts.py::four_role_script` (Task 2), wrapped in a
small capturing worker so the test can inspect the `RoleContext` object the
runner built for each of the four roles.
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
)
from dark_factory.events.catalog import EventType
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
from tests.support.fake_artifacts import four_role_script
from tests.support.git_repo import run_artifact_text

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# The seven filenames SC1 names, keyed by the role that produces them -- the
# exact "artifacts/<role>/<filename>" paths the test asserts on disk.
_EXPECTED_FILES: tuple[tuple[str, str], ...] = (
    ("BA", "requirements.md"),
    ("BA", "acceptance_criteria.json"),
    ("ARCHITECTURE", "design.md"),
    ("ARCHITECTURE", "constraints.json"),
    ("DEVELOPMENT", "implementation_summary.json"),
    ("QA", "test_report.json"),
    ("QA", "verdict.json"),
)


class _CapturingWorker(CodingWorker):
    """Delegates to a real :class:`FakeWorker` but records every ``context``
    object it is handed, so the test can inspect the ``RoleContext`` the
    runner built for each step, in call order."""

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


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """A ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` config tree carrying the same
    inputs/outputs contract as the shipped ``.dark-factory/roles/*.yaml`` set
    -- the build-then-overwrite idiom ``tests/db/test_artifact_handoff.py``
    (04-01) established for two roles, extended here to all four."""
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


def test_four_roles_run_in_order_and_produce_the_sc1_artifact_set(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:drive the full four-role pipeline",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    # GIT-01: pre-create the run's worktree now (idempotent -- the runner's
    # own ensure_worktree call inside drive() reuses it) so the scripted
    # four-role artifact content is written exactly where the runner will
    # look, mirroring what a real worker's own writes would already have
    # produced.
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    script = four_role_script(run_dir)

    captured: list[object] = []
    worker = _CapturingWorker(script, captured)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.COMPLETED

    # -- one COMPLETED role_executions row per role, in pipeline order -------
    with Session(engine) as session:
        executions = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(RoleExecution.created_at)
        ).all()
    assert [e.role for e in executions] == ["BA", "ARCHITECTURE", "DEVELOPMENT", "QA"]
    assert all(e.status == "COMPLETED" for e in executions)
    assert all(e.attempt == 1 for e in executions)

    # -- every SC1 file exists -- 05-03 (D-04): this run reaches COMPLETED,
    # -- so its worktree is removed by cleanup; read through the working
    # -- branch, the only place the content still exists.
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        working_branch = run.working_branch
    assert working_branch is not None
    for role, filename in _EXPECTED_FILES:
        content = run_artifact_text(
            root, run_id, working_branch, f"artifacts/{role}/{filename}"
        )
        assert content, f"expected artifacts/{role}/{filename} to have content"

    # -- exactly four worker calls, one per role -----------------------------
    assert len(captured) == 4

    # -- QA's RoleContext carries exactly its declared inputs, nothing more --
    qa_context = captured[3]
    assert qa_context is not None
    input_filenames = {i.filename for i in qa_context.inputs}  # type: ignore[union-attr]
    assert input_filenames == {
        "acceptance_criteria.json",
        "implementation_summary.json",
    }
    produced_by = {i.filename: i.produced_by for i in qa_context.inputs}  # type: ignore[union-attr]
    assert produced_by["acceptance_criteria.json"] == "BA"
    assert produced_by["implementation_summary.json"] == "DEVELOPMENT"
    assert "design.md" not in input_filenames
    assert "constraints.json" not in input_filenames

    # -- the run_events trail: four ROLE_STARTED, four ROLE_COMPLETED, one --
    # -- RUN_COMPLETED, and nothing outside the ten-member EventType enum ----
    with Session(engine) as session:
        event_types = session.scalars(
            sa.select(RunEvent.type)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq)
        ).all()
    assert event_types.count("ROLE_STARTED") == 4
    assert event_types.count("ROLE_COMPLETED") == 4
    assert event_types.count("RUN_COMPLETED") == 1
    legal_types = {member.value for member in EventType}
    assert all(t in legal_types for t in event_types)
