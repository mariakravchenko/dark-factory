"""HITL-01: every node of an arbitrary pipeline pauses through the same code.

The pause path in ``orchestrator/runner._run_current_role`` branches on the
control *signal* (``Signal.ROLE_NEEDS_INPUT``), never on a role name. This module
proves that empirically: it builds a two-node pipeline -- the real ``BA`` role
plus a second node named ``ARCHITECTURE`` (a value already present in the
run-status vocabulary, so the pure transition function can convert it) -- injects
it through the ``pipeline`` keyword parameter that ``advance`` / ``drive``
already accept, and shows that a ``NEEDS_INPUT`` result returned by *either* node
produces a structurally identical pause.

``ARCHITECTURE`` is in no production pipeline configuration -- ``DEFAULT_PIPELINE``
is ``["BA"]`` -- so a node the test invents still pauses. That is what "generic"
means here: when a later phase adds the Architect, Developer and QA roles beside
BA, this pause path needs no change and this test keeps passing unchanged. The
thing really under test is the *absence of a per-role branch*.

Real commits against real PostgreSQL; ``cleanup_runs`` deletes every fixture row
(run_events, human_interactions, role_executions, runs) at teardown -- the idiom
from ``tests/db/test_transition_atomic.py`` extended to the interaction table.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import advance, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workflows.pipeline import DEFAULT_PIPELINE, Pipeline, RoleNode

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_SECOND_NODE = "ARCHITECTURE"
_TWO_NODE_PIPELINE = Pipeline(
    nodes=(
        RoleNode(name="BA", worker="fake"),
        RoleNode(name=_SECOND_NODE, worker="fake"),
    )
)
# The snapshot equivalent persisted at run creation; the drive here still injects
# ``_TWO_NODE_PIPELINE`` explicitly into ``advance``, so this only shapes
# ``runs.workflow``.
_TWO_NODE_SNAPSHOT: dict[str, object] = {
    "roles": [
        {"name": "BA", "worker": "fake"},
        {"name": _SECOND_NODE, "worker": "fake"},
    ],
    # GIT-01: create_run persists this into runs.base_branch, which
    # ensure_worktree requires non-null the first time a run's worktree is
    # created.
    "repository": {"base_branch": "main"},
}

_QUESTION = "Which cluster should the health endpoint report on?"
_SESSION_ID = "fake-generic-pause-001"


def _needs_input() -> WorkerResult:
    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a human decision",
        questions=[_QUESTION],
        worker_session_id=_SESSION_ID,
    )


def _completed(summary: str = "done") -> WorkerResult:
    return WorkerResult(
        status=WorkerResultStatus.COMPLETED,
        summary=summary,
        worker_session_id=_SESSION_ID,
    )


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    """A fresh ``Session`` on the real engine per call, committing for real
    (``NullPool`` discards the connection on close). Never shared across
    threads."""

    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _advance(
    run_id: UUID,
    factory: SessionFactory,
    registry_builder: Callable[..., Any],
    result: WorkerResult,
    repo_root: Path,
) -> RunStatus:
    """One committed step with a single-result fake.

    ``conftest.fake_worker_registry`` hands back a fresh ``FakeWorker`` on every
    ``registry.get`` call, so a multi-step ``drive`` would replay element 0 of
    the script forever. Stepping with one ``advance`` call per scripted result --
    the ``tests/db/test_lease_lost_aborts_step.py`` idiom -- keeps each node's
    result distinct while still exercising the one signal-dispatch branch.
    """
    return advance(
        run_id,
        session_factory=factory,
        registry=registry_builder([result]),
        pipeline=_TWO_NODE_PIPELINE,
        repo_root=repo_root,
    )


def _pause_at_node(
    node_name: str,
    factory: SessionFactory,
    registry_builder: Callable[..., Any],
    cleanup: list[Any],
    repo_root: Path,
) -> UUID:
    """Drive a fresh two-node run until ``node_name`` returns ``NEEDS_INPUT``.

    For the first node the fake returns ``NEEDS_INPUT`` on the role's first step;
    for the second the fake completes the first node, *enters* the second node
    (its own committed step -- see ``orchestrator/runner._enter_role``, which
    inserts the second node's own ``role_executions`` row before any worker is
    called), and only then returns ``NEEDS_INPUT``. Both reach the pause through
    the identical signal-dispatch branch -- no per-role code decides which one
    pauses.
    """
    run_id = start_run(
        "text:prove the pause mechanism is generic",
        session_factory=factory,
        snapshot=_TWO_NODE_SNAPSHOT,
    )
    cleanup.append(run_id)

    assert (
        _advance(run_id, factory, registry_builder, _completed(), repo_root)
        is RunStatus.BA
    )
    if node_name == _SECOND_NODE:
        assert (
            _advance(
                run_id, factory, registry_builder, _completed("BA done"), repo_root
            )
            is RunStatus.ARCHITECTURE
        )
        # Entering ARCHITECTURE is its own committed step: it inserts the row
        # but calls no worker, so the status is unchanged and this scripted
        # result is never consumed.
        assert (
            _advance(run_id, factory, registry_builder, _completed("unused"), repo_root)
            is RunStatus.ARCHITECTURE
        )
    status = _advance(run_id, factory, registry_builder, _needs_input(), repo_root)
    assert status is RunStatus.WAITING_HUMAN
    return run_id


def _pause_outcome(factory: SessionFactory, run_id: UUID) -> dict[str, Any]:
    """Collect the pause as a comparable dictionary. Keys prefixed ``_`` are the
    values allowed to differ between nodes (the recorded role name and the
    role-execution row identity); every other key is the structural remainder
    that must be identical."""
    session = factory()
    try:
        run = session.get(Run, run_id)
        assert run is not None
        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(
                RoleExecution.created_at.desc(),
                RoleExecution.attempt.desc(),
                RoleExecution.id.desc(),
            )
            .limit(1)
        )
        assert latest is not None
        interactions = list(
            session.scalars(
                select(HumanInteraction).where(HumanInteraction.run_id == run_id)
            )
        )
        events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        stored = WorkerResult.model_validate(latest.result)
        return {
            # -- projected out: the two things allowed to differ --
            "_current_role": run.current_role,
            "_role_execution_id": str(latest.id),
            "_role_execution_role": latest.role,
            # -- the structural remainder: identical for every node --
            "run_status": run.status,
            "lease_owner_token_null": run.owner_token is None,
            "lease_expiry_null": run.lock_expires_at is None,
            "role_execution_status_marker": latest.status,
            "role_execution_attempt": latest.attempt,
            "stored_result_status": stored.status,
            "stored_result_questions": list(stored.questions),
            "interaction_count": len(interactions),
            "interaction_status": (
                interactions[0].status.value if interactions else None
            ),
            "last_two_events": events[-2:],
        }
    finally:
        session.close()


@pytest.mark.parametrize("node_name", ["BA", _SECOND_NODE])
def test_either_node_pauses_with_the_same_properties(
    node_name: str,
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[..., Any],
    cleanup_runs: list[Any],
    git_repo_root: Path,
) -> None:
    run_id = _pause_at_node(
        node_name,
        real_session_factory,
        fake_worker_registry,
        cleanup_runs,
        git_repo_root,
    )
    outcome = _pause_outcome(real_session_factory, run_id)

    assert outcome["run_status"] is RunStatus.WAITING_HUMAN
    assert outcome["_current_role"] == node_name  # the node that asked is retained
    assert outcome["lease_owner_token_null"] is True
    assert outcome["lease_expiry_null"] is True
    assert outcome["role_execution_status_marker"] == "WAITING_HUMAN"
    assert outcome["stored_result_status"] is WorkerResultStatus.NEEDS_INPUT
    assert outcome["stored_result_questions"] == [_QUESTION]
    assert outcome["interaction_count"] == 1
    assert outcome["interaction_status"] == "WAITING"
    assert outcome["last_two_events"] == ["QUESTION_CREATED", "RUN_PAUSED"]


def test_the_two_nodes_pause_through_structurally_identical_code(
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[..., Any],
    cleanup_runs: list[Any],
    git_repo_root: Path,
) -> None:
    """The honest form of "the same code ran": collect both outcomes, project out
    the role name and the row identifiers, and assert the remainders are equal.
    A per-role branch on the pause path would make one of these remainders
    diverge."""
    # the second node names a status that never appears in a production pipeline
    assert _SECOND_NODE not in [node.name for node in DEFAULT_PIPELINE.nodes]

    first_id = _pause_at_node(
        "BA", real_session_factory, fake_worker_registry, cleanup_runs, git_repo_root
    )
    first = _pause_outcome(real_session_factory, first_id)
    second_id = _pause_at_node(
        _SECOND_NODE,
        real_session_factory,
        fake_worker_registry,
        cleanup_runs,
        git_repo_root,
    )
    second = _pause_outcome(real_session_factory, second_id)

    projected = {"_current_role", "_role_execution_id", "_role_execution_role"}
    first_remainder = {k: v for k, v in first.items() if k not in projected}
    second_remainder = {k: v for k, v in second.items() if k not in projected}
    assert first_remainder == second_remainder

    # the only value that legitimately differs is the recorded role name
    assert first["_current_role"] == "BA"
    assert second["_current_role"] == _SECOND_NODE


@pytest.mark.parametrize("node_name", ["BA", _SECOND_NODE])
def test_answering_either_pause_returns_to_that_node_and_the_run_completes(
    node_name: str,
    real_session_factory: SessionFactory,
    fake_worker_registry: Callable[..., Any],
    cleanup_runs: list[Any],
    git_repo_root: Path,
) -> None:
    run_id = _pause_at_node(
        node_name,
        real_session_factory,
        fake_worker_registry,
        cleanup_runs,
        git_repo_root,
    )
    attempt_before = _pause_outcome(real_session_factory, run_id)[
        "role_execution_attempt"
    ]

    resumed = submit_answer(
        run_id, "use the primary cluster", session_factory=real_session_factory
    )
    assert resumed.value == node_name  # returned to the node that asked

    # finish the pipeline one committed step at a time. When BA paused, the
    # answer returns the run to BA and the second node still has to run --
    # which is now two more committed steps of its own: entering ARCHITECTURE
    # (its own role_executions row, no worker call) and then actually running
    # it (see ``orchestrator/runner._enter_role``).
    final = _advance(
        run_id,
        real_session_factory,
        fake_worker_registry,
        _completed("resumed"),
        git_repo_root,
    )
    if node_name != _SECOND_NODE:
        assert final is RunStatus.ARCHITECTURE
        final = _advance(
            run_id,
            real_session_factory,
            fake_worker_registry,
            _completed("unused"),
            git_repo_root,
        )
        assert final is RunStatus.ARCHITECTURE  # entered, not yet run
        final = _advance(
            run_id,
            real_session_factory,
            fake_worker_registry,
            _completed("architecture"),
            git_repo_root,
        )
    assert final is RunStatus.COMPLETED

    session = real_session_factory()
    try:
        rows_by_role = {
            r.role: r
            for r in session.scalars(
                select(RoleExecution).where(RoleExecution.run_id == run_id)
            )
        }
        # Each node now owns its own row (STATE-03, WINDOWS.md #6) -- the
        # paused node's own attempt is never bumped by the resume, and BA's
        # completion doesn't recycle its row into ARCHITECTURE's.
        assert set(rows_by_role) == {"BA", _SECOND_NODE}
        assert rows_by_role[node_name].attempt == attempt_before
        assert all(row.attempt == 1 for row in rows_by_role.values())

        final_events = list(
            session.scalars(
                select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
        assert "RUN_RESUMED" in final_events
        assert final_events.count("ROLE_STARTED") == 2  # one per node
        assert final_events.count("ROLE_COMPLETED") == 2  # passed through both nodes
        assert final_events[-1] == "RUN_COMPLETED"
    finally:
        session.close()
