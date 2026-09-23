"""GATE-01 through GATE-04, proved against a real `drive()` run (Phase 9,
plan 09-01, Task 2):

    Once QA's own attempt transitions with a PASS `verdict.json`, Dark
    Factory independently re-runs the repository's own `quality_gate.commands`
    in the run's worktree; every command runs even after an earlier one
    fails (D-09); the persisted `verification/quality_gate.json` matches
    D-11's exact shape; a non-zero exit keeps the run out of `COMPLETED`
    regardless of a success-claiming worker summary; and a FAIL verdict
    short-circuits the gate entirely -- closing 09-RESEARCH.md's Critical
    Mechanics Gap 1 (`tests/db/test_artifact_schema_violation_fails_role.py`'s
    own docstring records the Phase 4 deferral this module closes).

Follows `tests/db/test_four_role_pipeline.py`'s idiom exactly: `start_run` +
`drive` against real PostgreSQL, an injected `WorkerRegistry` wrapping
`tests.support.fake_artifacts.LazyFourRoleWorker`, `cleanup_runs` deleting
every fixture row at teardown. Each scenario builds its config tree with
`config_root_factory` and then overwrites the generated `.dark-factory.yaml`'s
`quality_gate.commands` list before calling `load_effective_config` -- the
build-then-overwrite idiom `tests/conftest.py` documents. Commands are
`sys.executable -c ...` invocations so they are hermetic and sub-second.
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
from tests.support.fake_artifacts import QA_VERDICT_FAIL_FILES, LazyFourRoleWorker
from tests.support.git_repo import run_artifact_text

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_QUALITY_GATE_BLOCK = "quality_gate:\n  commands: []\n"


def _py(*args: str) -> str:
    """A `quality_gate.commands` entry invoking the current interpreter,
    built with `shlex.join` so it round-trips exactly through the
    production `shlex.split` call inside `run_quality_gate`."""
    return shlex.join([sys.executable, *args])


def _write_four_role_tree(
    config_root_factory: Callable[..., Path], *, quality_gate_commands: list[str]
) -> Path:
    """The same `[BA, ARCHITECTURE, DEVELOPMENT, QA]` config tree
    `tests/db/test_four_role_pipeline.py` writes, with `quality_gate.commands`
    overwritten to `quality_gate_commands` -- the build-then-overwrite idiom
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
    commands_yaml = "[" + ", ".join(json.dumps(c) for c in quality_gate_commands) + "]"
    patched = original.replace(
        _QUALITY_GATE_BLOCK, f"quality_gate:\n  commands: {commands_yaml}\n"
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


def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def test_gate_pass_completes_the_run_and_persists_both_command_results(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    first = _py("-c", "print('one')")
    second = _py("-c", "print('two')")
    root = _write_four_role_tree(
        config_root_factory, quality_gate_commands=[first, second]
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:the gate passes on two green commands",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
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

    # GATE-04: the persisted result is readable from the run's committed
    # working branch (the terminal role's worktree is removed on COMPLETED,
    # D-04) and matches D-11's exact shape.
    content = run_artifact_text(
        root, run_id, working_branch, "verification/quality_gate.json"
    )
    parsed = json.loads(content)
    assert parsed["status"] == "PASS"
    assert [c["command"] for c in parsed["commands"]] == [first, second]
    assert all(c["exit_code"] == 0 for c in parsed["commands"])

    event_types = _event_types(engine, run_id)
    assert event_types.count("QUALITY_GATE_STARTED") == 1
    assert event_types.count("QUALITY_GATE_PASSED") == 1
    assert event_types.count("QUALITY_GATE_FAILED") == 0


def test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    failing = _py("-c", "import sys; sys.exit(1)")
    passing = _py("-c", "pass")
    root = _write_four_role_tree(
        config_root_factory, quality_gate_commands=[failing, passing]
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:the gate fails on the first of two commands",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    # LazyFourRoleWorker's own scripted summary text ("QA completed") is the
    # success-claiming prose GATE-03 requires be overridden by exit codes,
    # not by any special-cased "failure" wording -- the default is enough.
    worker = LazyFourRoleWorker(run_dir)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    # D-04: a FAILED run keeps its worktree, so the file is still readable
    # directly off disk.
    content = (run_dir / "verification" / "quality_gate.json").read_text(
        encoding="utf-8"
    )
    parsed = json.loads(content)
    assert parsed["status"] == "FAIL"
    assert len(parsed["commands"]) == 2  # D-09: the second command still ran
    assert parsed["commands"][0]["exit_code"] != 0
    assert parsed["commands"][1]["exit_code"] == 0

    event_types = _event_types(engine, run_id)
    assert "QUALITY_GATE_FAILED" in event_types
    assert "RUN_COMPLETED" not in event_types

    with Session(engine) as session:
        qa_execution = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "QA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
    assert qa_execution is not None
    assert qa_execution.error is not None
    assert qa_execution.error.get("error") == "quality_gate_fail"


def test_a_failing_verdict_short_circuits_the_gate_entirely(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    sentinel_name = "gate_ran_sentinel.txt"
    gate_command = _py("-c", f"open({sentinel_name!r}, 'w').close()")
    root = _write_four_role_tree(
        config_root_factory, quality_gate_commands=[gate_command]
    )
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa's own verdict fails before the gate ever runs",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir, qa_files=QA_VERDICT_FAIL_FILES)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    # The gate command would have written this file into the worktree root
    # had it ever run -- it must not exist (D-04 keeps the worktree on a
    # FAILED run, so this is a genuine absence check, not a window that has
    # already closed).
    assert not (work_dir / sentinel_name).exists()
    assert not (run_dir / "verification" / "quality_gate.json").exists()

    event_types = _event_types(engine, run_id)
    assert "QUALITY_GATE_STARTED" not in event_types
    assert "QUALITY_GATE_PASSED" not in event_types
    assert "QUALITY_GATE_FAILED" not in event_types

    with Session(engine) as session:
        qa_execution = session.scalars(
            sa.select(RoleExecution)
            .where(RoleExecution.run_id == run_id, RoleExecution.role == "QA")
            .order_by(RoleExecution.attempt.desc())
        ).first()
    assert qa_execution is not None
    assert qa_execution.error is not None
    assert qa_execution.error.get("error") == "qa_verdict_fail"
