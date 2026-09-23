"""LOOP-03, LOOP-04 (Phase 9, plan 09-02): exhausting either iteration cap
proved against a real `drive()` run.

    The iteration counter is checked against its configured cap before the
    signal is chosen (LOOP-03); exhausting either cap ends the run in
    `FAILED` with the reason, the counter's value and its cap persisted,
    and every prior attempt still present as its own `role_executions` row
    (LOOP-04); re-driving an already-exhausted run is a no-op.

Follows `tests/db/test_qa_bounce.py`'s idiom and config-tree helper exactly:
`start_run` + `drive` against real PostgreSQL, `AttemptAwareFourRoleWorker`,
`cleanup_runs` deleting every fixture row at teardown.
"""

from __future__ import annotations

import json
import shlex
import sys
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
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import (
    QA_VERDICT_FAIL_FILES,
    AttemptAwareFourRoleWorker,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_QUALITY_GATE_BLOCK = "quality_gate:\n  commands: []\n"
_RETRY_BLOCK = (
    "retry:\n"
    "  qa_developer_max_iterations: 3\n"
    "  quality_gate_max_iterations: 2\n"
)


def _write_four_role_tree(
    config_root_factory: Callable[..., Path],
    *,
    quality_gate_commands: list[str] | None = None,
    qa_developer_max_iterations: int = 3,
    quality_gate_max_iterations: int = 2,
) -> Path:
    """The same `[BA, ARCHITECTURE, DEVELOPMENT, QA]` config tree
    `tests/db/test_qa_bounce.py` writes -- duplicated rather than imported,
    matching every other db-tier module's own self-contained config-tree
    helper in this project (see e.g. `test_quality_gate_gates_the_run.py`
    vs. `test_four_role_pipeline.py`)."""
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

    config_path = root / ".dark-factory.yaml"
    original = config_path.read_text(encoding="utf-8")
    assert _QUALITY_GATE_BLOCK in original, (
        "config_root_factory no longer writes 'quality_gate:\\n  commands: []\\n'"
        " verbatim -- update this test's overwrite string to match"
    )
    commands = quality_gate_commands or []
    commands_yaml = "[" + ", ".join(json.dumps(c) for c in commands) + "]"
    patched = original.replace(
        _QUALITY_GATE_BLOCK, f"quality_gate:\n  commands: {commands_yaml}\n"
    )
    assert _RETRY_BLOCK in patched, (
        "config_root_factory no longer writes the retry: block verbatim -- "
        "update this test's overwrite string to match"
    )
    patched = patched.replace(
        _RETRY_BLOCK,
        "retry:\n"
        f"  qa_developer_max_iterations: {qa_developer_max_iterations}\n"
        f"  quality_gate_max_iterations: {quality_gate_max_iterations}\n",
    )
    config_path.write_text(patched, encoding="utf-8")
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


def _events(engine: Engine, run_id: Any) -> list[RunEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def _role_executions(engine: Engine, run_id: Any, role: str) -> list[RoleExecution]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RoleExecution)
                .where(RoleExecution.run_id == run_id, RoleExecution.role == role)
                .order_by(RoleExecution.attempt)
            ).all()
        )


def test_qa_cap_exhausted_ends_the_run_failed_with_every_attempt_persisted(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Scenario 1: `qa_developer_max_iterations: 1`, QA FAILs on every
    attempt. Attempt 1 bounces (0 < 1); attempt 2 exhausts (1 is not < 1)."""
    root = _write_four_role_tree(config_root_factory, qa_developer_max_iterations=1)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails on every attempt until the cap is exhausted",
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
        attempt_files={
            ("QA", 1): QA_VERDICT_FAIL_FILES,
            ("QA", 2): QA_VERDICT_FAIL_FILES,
        },
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    event_types = [e.type for e in _events(engine, run_id)]
    assert event_types.count("ROLE_BOUNCED") == 1
    assert event_types.count("ROLE_FAILED") == 1
    assert event_types.count("RUN_FAILED") == 1
    # LOOP-04 literal ordering: the bounce happens, then the run fails.
    assert event_types.index("ROLE_BOUNCED") < event_types.index("ROLE_FAILED")
    assert event_types.index("ROLE_FAILED") < event_types.index("RUN_FAILED")

    run_failed = next(e for e in _events(engine, run_id) if e.type == "RUN_FAILED")
    assert run_failed.payload["reason"] == "qa_developer_max_iterations_exhausted"
    assert run_failed.payload["counter"] == "qa_developer_iterations"
    assert run_failed.payload["value"] == 1
    assert run_failed.payload["cap"] == 1

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.qa_developer_iterations == 1

    # LOOP-04: every attempt is still its own persisted role_executions row.
    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in dev_executions] == [1, 2]
    assert [e.attempt for e in qa_executions] == [1, 2]


def test_gate_cap_exhausted_ends_the_run_failed_with_every_attempt_persisted(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Scenario 2: `quality_gate_max_iterations: 1`, the one configured gate
    command always exits non-zero. Attempt 1 bounces (0 < 1); attempt 2
    exhausts (1 is not < 1). `qa_developer_iterations` stays 0 throughout --
    the two counters never fold into each other (D-06)."""
    always_fails = shlex.join([sys.executable, "-c", "import sys; sys.exit(1)"])
    root = _write_four_role_tree(
        config_root_factory,
        quality_gate_commands=[always_fails],
        quality_gate_max_iterations=1,
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:the gate fails on every attempt until the cap is exhausted",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = AttemptAwareFourRoleWorker(run_dir, attempt_files={})

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    event_types = [e.type for e in _events(engine, run_id)]
    assert event_types.count("ROLE_BOUNCED") == 1
    assert event_types.count("ROLE_FAILED") == 1
    assert event_types.count("RUN_FAILED") == 1

    run_failed = next(e for e in _events(engine, run_id) if e.type == "RUN_FAILED")
    assert run_failed.payload["reason"] == "quality_gate_max_iterations_exhausted"
    assert run_failed.payload["counter"] == "quality_gate_iterations"
    assert run_failed.payload["value"] == 1
    assert run_failed.payload["cap"] == 1

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.quality_gate_iterations == 1
        assert run.qa_developer_iterations == 0

    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in dev_executions] == [1, 2]
    assert [e.attempt for e in qa_executions] == [1, 2]


def test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Scenario 3, the LOOP-04 empty edge: `qa_developer_max_iterations: 0`
    with a FAIL verdict on QA's first attempt. The very first rejection is
    terminal -- zero ROLE_BOUNCED events, no zero-value special case
    anywhere in the code path (``0 < 0`` is already false)."""
    root = _write_four_role_tree(config_root_factory, qa_developer_max_iterations=0)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails once under a zero iteration cap",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = AttemptAwareFourRoleWorker(
        run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    event_types = [e.type for e in _events(engine, run_id)]
    assert event_types.count("ROLE_BOUNCED") == 0
    assert event_types.count("ROLE_FAILED") == 1
    assert event_types.count("RUN_FAILED") == 1

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.qa_developer_iterations == 0

    # A single QA attempt -- no bounce, no second Developer/QA cycle.
    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in dev_executions] == [1]
    assert [e.attempt for e in qa_executions] == [1]


def test_redriving_an_exhausted_run_is_a_no_op(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """LOOP-04 idempotency: once a run has reached `FAILED` via cap
    exhaustion, calling `advance()` again writes no further `run_events`
    rows and changes neither counter column -- the existing `STOP_STATUSES`
    early return in `_advance_once` makes re-driving a terminal run a
    no-op."""
    root = _write_four_role_tree(config_root_factory, qa_developer_max_iterations=0)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:re-driving an exhausted run must be a no-op",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = AttemptAwareFourRoleWorker(
        run_dir, attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES}
    )
    registry = _registry(worker)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=registry,
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    events_before = _events(engine, run_id)
    with Session(engine) as session:
        run_before = session.get(Run, run_id)
        assert run_before is not None
        qa_iterations_before = run_before.qa_developer_iterations
        gate_iterations_before = run_before.quality_gate_iterations

    replayed = advance(
        run_id,
        session_factory=real_session_factory,
        registry=registry,
        repo_root=root,
    )
    assert replayed is RunStatus.FAILED

    events_after = _events(engine, run_id)
    assert len(events_after) == len(events_before)
    assert [e.id for e in events_after] == [e.id for e in events_before]
    with Session(engine) as session:
        run_after = session.get(Run, run_id)
        assert run_after is not None
        assert run_after.qa_developer_iterations == qa_iterations_before
        assert run_after.quality_gate_iterations == gate_iterations_before
