"""LOOP-02, LOOP-03, LOOP-04 (Phase 9, plan 09-02): the bounded feedback loop
proved against a real `drive()` run.

    A QA-verdict FAIL and a quality-gate FAIL each send the run back to the
    Developer with a fresh attempt row, under their own independent
    iteration cap, after which the Developer's next attempt is picked up by
    QA re-evaluating and, on a gate bounce, by the gate re-running.

Follows `tests/db/test_quality_gate_gates_the_run.py`'s idiom exactly:
`start_run` + `drive` against real PostgreSQL, an injected `WorkerRegistry`
wrapping `tests.support.fake_artifacts.AttemptAwareFourRoleWorker` (new in
this plan -- unlike `LazyFourRoleWorker`, its content varies by
`context.attempt`, which is what makes "QA fails on attempt 1 and passes on
attempt 2" expressible), `cleanup_runs` deleting every fixture row at
teardown. Each scenario builds its config tree with `config_root_factory`
and then overwrites the generated `.dark-factory.yaml`'s `quality_gate:` /
`retry:` blocks before calling `load_effective_config` -- the
build-then-overwrite idiom `tests/conftest.py` documents.
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
    `tests/db/test_four_role_pipeline.py` writes, with `quality_gate.commands`
    and the two retry caps overwritten -- the build-then-overwrite idiom
    `tests/conftest.py` documents."""
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


def test_qa_fail_then_pass_bounces_once_and_completes(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Scenario 1: QA FAILs on attempt 1, PASSes on attempt 2 -- the run
    ends COMPLETED, both counters stay independent (D-06), every attempt is
    its own persisted row (D-05, LOOP-04), and the audit trail carries
    exactly one ROLE_BOUNCED event and zero RUN_FAILED events."""
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails once then passes",
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
    assert final is RunStatus.COMPLETED

    # D-05/LOOP-04: four independently persisted attempt rows, none reused.
    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in dev_executions] == [1, 2]
    assert [e.attempt for e in qa_executions] == [1, 2]
    assert len({e.id for e in dev_executions + qa_executions}) == 4

    # D-06: the two counters are independent.
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.qa_developer_iterations == 1
        assert run.quality_gate_iterations == 0

    # T-09-09: exactly one ROLE_BOUNCED event, no RUN_FAILED at all.
    events = _events(engine, run_id)
    bounced = [e for e in events if e.type == "ROLE_BOUNCED"]
    assert len(bounced) == 1
    assert bounced[0].payload["reason"] == "qa_verdict_fail"
    assert bounced[0].payload["counter"] == "qa_developer_iterations"
    assert all(e.type != "RUN_FAILED" for e in events)

    # The bounced QA attempt-1 row stays "COMPLETED" with no error (A3): it
    # must remain visible to _latest_completed_execution for plan 09-03's
    # feedback delivery to resolve verdict.json at all.
    qa_attempt_1 = qa_executions[0]
    assert qa_attempt_1.status == "COMPLETED"
    assert qa_attempt_1.error is None


def test_gate_fail_then_pass_bounces_once_and_completes(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Scenario 2: the gate FAILs on the Developer's attempt 1 (the sentinel
    file it checks for is absent) and PASSes once the Developer's attempt 2
    creates it. LOOP-02's literal "QA re-evaluates and the gate re-runs":
    two QUALITY_GATE_STARTED events (one FAILED, one PASSED) and a second QA
    role_executions row."""
    sentinel_name = "gate_ran_after_bounce.txt"
    # Relative to cwd=work_dir (D-03): the sentinel lives under the
    # gitignored ``.dark-factory/runs/`` prefix -- see
    # AttemptAwareFourRoleWorker's docstring for why not the bare worktree
    # root -- at a run-id-independent path, since this command is fixed into
    # config before the run id exists.
    sentinel_rel_path = f".dark-factory/runs/{sentinel_name}"
    gate_command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import os, sys; "
                f"sys.exit(0 if os.path.exists({sentinel_rel_path!r}) else 1)"
            ),
        ]
    )
    root = _write_four_role_tree(
        config_root_factory, quality_gate_commands=[gate_command]
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:the gate fails once then passes",
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
        sentinel_writes={("DEVELOPMENT", 2): sentinel_name},
    )

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
        assert run.quality_gate_iterations == 1
        assert run.qa_developer_iterations == 0

    events = _events(engine, run_id)
    event_types = [e.type for e in events]
    assert event_types.count("QUALITY_GATE_STARTED") == 2
    assert event_types.count("QUALITY_GATE_FAILED") == 1
    assert event_types.count("QUALITY_GATE_PASSED") == 1
    assert event_types.count("RUN_FAILED") == 0
    bounced = [e for e in events if e.type == "ROLE_BOUNCED"]
    assert len(bounced) == 1
    assert bounced[0].payload["reason"] == "quality_gate_fail"
    assert bounced[0].payload["counter"] == "quality_gate_iterations"

    # QA re-evaluated between the two gate runs: a second QA role_executions row.
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in qa_executions] == [1, 2]
    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    assert [e.attempt for e in dev_executions] == [1, 2]
