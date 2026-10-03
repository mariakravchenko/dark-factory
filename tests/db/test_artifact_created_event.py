"""The ``ARTIFACT_CREATED`` audit tie, end to end (Plan 12-01, Task 1, D-06,
OBS-02 / OBS-03).

Proves the whole vertical this phase's tracer task exists to establish: a
role attempt that wrote declared machine artifacts leaves exactly one
``ARTIFACT_CREATED`` event per ``artifacts`` row, in the same
``apply_transition`` call, and ``read_events`` / ``render_events_text``
retell that fact in ``seq`` order with every payload redacted.

Follows ``tests/db/test_four_role_pipeline.py``'s real ``drive()`` idiom
(``start_run`` + an injected ``WorkerRegistry`` wrapping
``tests.support.fake_artifacts.LazyFourRoleWorker`` against real
PostgreSQL) for the happy-path and adjacency proofs, and
``tests/db/test_artifact_schema_violation_fails_role.py``'s single-role
config-tree idiom (plus ``AttemptAwareFourRoleWorker``'s
``out_of_scope_writes`` seam) for the ART-04 transparency proof.
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
from dark_factory.events.catalog import EventType
from dark_factory.events.reader import read_events
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.observability.render import render_events_text
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
from tests.support.fake_artifacts import AttemptAwareFourRoleWorker, LazyFourRoleWorker

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """The same ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` config tree
    ``tests/db/test_four_role_pipeline.py`` writes -- a real inputs/outputs
    contract per role, so every role's artifact writes are genuinely
    declared and collected."""
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


def _single_role_ba_tree(config_root_factory: Callable[..., Path]) -> Path:
    """A one-role ``[BA]`` config tree with ``write_scope: []`` (D-14's zero
    tolerance) and both of BA's real declared outputs -- the tree the ART-04
    honesty scenario needs so ``collect_role_artifacts`` genuinely succeeds
    before the later write-scope check fails the role."""
    root = config_root_factory(roles=("BA",))
    (root / ".dark-factory/roles/BA.yaml").write_text(
        "name: BA\n"
        "worker: fake\n"
        "instructions: ../instructions/ba.md\n"
        "tools: [repo.read, repo.search, artifacts.read, artifacts.write]\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: []\n"
        "outputs: [requirements.md, acceptance_criteria.json]\n"
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


def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def test_artifact_created_events_exactly_match_artifact_rows_and_render(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:drive the four-role pipeline and tie artifacts to events",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

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
        artifact_rows = session.scalars(
            sa.select(ArtifactReference).where(ArtifactReference.run_id == run_id)
        ).all()
    assert len(artifact_rows) == 7  # the SC1 seven-filename set, across 4 roles

    rows = read_events(run_id, session_factory=real_session_factory)
    artifact_events = [r for r in rows if r.type == EventType.ARTIFACT_CREATED.value]

    # Exact equality, never >= or a membership check (acceptance criterion).
    assert len(artifact_events) == len(artifact_rows)

    artifacts_by_role_execution: dict[Any, list[ArtifactReference]] = {}
    for artifact in artifact_rows:
        artifacts_by_role_execution.setdefault(artifact.role_execution_id, []).append(
            artifact
        )

    for event in artifact_events:
        assert event.role_execution_id is not None
        candidates = artifacts_by_role_execution.get(event.role_execution_id, [])
        match = next(
            (
                a
                for a in candidates
                if a.type == event.payload.get("type")
                and a.path == event.payload.get("path")
            ),
            None,
        )
        assert match is not None, (
            f"no artifacts row matches event payload {event.payload!r} for "
            f"role_execution_id={event.role_execution_id}"
        )
        assert "role" in event.payload

    rendered = render_events_text(rows)
    for artifact in artifact_rows:
        assert artifact.path in rendered, f"expected {artifact.path} in rendered output"


def test_two_events_from_one_apply_transition_share_created_at_distinct_seq(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove the same-transaction adjacency edge",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

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

    rows = read_events(run_id, session_factory=real_session_factory)
    # BA's own apply_transition call writes ROLE_COMPLETED plus two
    # ARTIFACT_CREATED events (requirements.md, acceptance_criteria.json),
    # all three in one transaction. ROLE_COMPLETED carries no
    # role_execution_id (a pre-existing project behaviour), so the three are
    # grouped by their shared ``payload["role"]`` instead -- narrowed to the
    # two event types BA's own transition writes, excluding the earlier,
    # separately-transacted ROLE_STARTED event that also names BA.
    ba_events = [
        r
        for r in rows
        if r.payload.get("role") == "BA"
        and r.type in {EventType.ROLE_COMPLETED.value, EventType.ARTIFACT_CREATED.value}
    ]
    assert len(ba_events) == 3
    assert {r.type for r in ba_events} == {
        EventType.ROLE_COMPLETED.value,
        EventType.ARTIFACT_CREATED.value,
    }

    created_ats = {r.created_at for r in ba_events}
    assert len(created_ats) == 1, (
        "events from one apply_transition must share created_at"
    )

    seqs = [r.seq for r in ba_events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs), "seq values must be distinct, never merged"

    # read_events returns them in seq order, never created_at order.
    assert [r.seq for r in rows] == sorted(r.seq for r in rows)


def test_role_failing_after_collect_role_artifacts_succeeded_leaves_zero_artifacts_and_events(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """ART-04 transparency (OBS-02): a role whose ``collect_role_artifacts``
    call succeeded, but whose attempt is later discovered to carry an
    out-of-scope write (``enforce_write_scope`` raises after the artifact
    commit already landed), fails the role -- and its artifact content must
    never be reported as durable: zero ``artifacts`` rows, zero
    ``ARTIFACT_CREATED`` events."""
    root = _single_role_ba_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove ART-04 honesty on a late write-scope failure",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = AttemptAwareFourRoleWorker(
        run_dir,
        attempt_files={},
        out_of_scope_writes={("BA", 1): "escaped-out-of-scope.txt"},
        worktree_root=work_dir,
    )

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

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.run_id == run_id)
        )
        assert artifact_count == 0

    types = _event_types(engine, run_id)
    assert "ARTIFACT_CREATED" not in types
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types
