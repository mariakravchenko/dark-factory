"""Gap CR-01 (09-VERIFICATION.md, failed truth #22, Phase 9 plan 09-04):
``enforce_write_scope`` is a ROLE-05 authorization control, and a bounce is
write-scope-enforced exactly like a completion -- the guard was widened in
this plan's Task 1 to cover ``Signal.ROLE_BOUNCED`` alongside
``Signal.ROLE_COMPLETED``, the two signals under which an attempt's worktree
changes are retained rather than the run ending outright.

This module proves it against a real ``drive()`` run: QA writes outside its
declared ``write_scope`` on an attempt whose verdict also FAILs under an
unexhausted cap -- the exact shape that, pre-fix, would have chosen
``Signal.ROLE_BOUNCED`` and skipped ``enforce_write_scope`` entirely.

Like every other ``db``-marked test in this repository, this module requires
a reachable PostgreSQL 17 (``tests/conftest.py`` raises a loud
``pytest.UsageError`` naming the missing database rather than skipping).

Follows ``tests/db/test_qa_bounce.py``'s idiom exactly, with local copies of
its helpers -- the same per-module-copy convention plan 09-02's two db
modules already use, rather than extracting a shared helper module in a
gap-closure pass.
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


def _write_four_role_tree(config_root_factory: Callable[..., Path]) -> Path:
    """The same `[BA, ARCHITECTURE, DEVELOPMENT, QA]` config tree
    `tests/db/test_qa_bounce.py::_write_four_role_tree` writes, left at its
    default caps -- `qa_developer_max_iterations` stays 3, so this scenario's
    attempt is genuinely *under* cap and the pre-fix code path would have
    chosen `ROLE_BOUNCED`. Every role in this tree already carries
    `permissions: write_scope: []` (D-14 zero tolerance), so any
    tracked-visible worktree write is a violation with no further config
    change needed."""
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
    assert _RETRY_BLOCK in original, (
        "config_root_factory no longer writes the retry: block verbatim -- "
        "update this test's overwrite string to match"
    )
    config_path.write_text(original, encoding="utf-8")
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


def test_a_bounce_is_write_scope_enforced_exactly_like_a_completion(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """QA writes outside its declared write_scope on attempt 1, whose
    verdict also FAILs under an unexhausted cap (qa_developer_max_iterations
    stays at its default of 3) -- the pre-fix code path would have chosen
    ``ROLE_BOUNCED`` and skipped ``enforce_write_scope`` entirely, letting
    the out-of-scope write survive into the Developer's next WIP-recovery
    commit. Post-fix, the write-scope violation downgrades the would-be
    bounce to a genuine ``ROLE_FAILED``/``RUN_FAILED``, and the run ends
    FAILED with the planted file reverted."""
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa writes outside its write_scope on a would-be-bounced attempt",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    # Placed on QA's attempt 1 specifically -- QA is the terminal role, and
    # the Developer's own earlier attempt stays clean so the violation is
    # unambiguously QA's.
    worker = AttemptAwareFourRoleWorker(
        run_dir,
        attempt_files={("QA", 1): QA_VERDICT_FAIL_FILES},
        out_of_scope_writes={("QA", 1): "src/leaked_by_qa.py"},
        worktree_root=work_dir,
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )

    # 6. Corroborating, not discriminating: the run ends FAILED. This alone
    # does not prove the fix -- pre-fix the run also eventually fails, but
    # for the wrong reason and only after the leftover file trips a *later*
    # role's own check, which is precisely the misattribution this test
    # exists to forbid.
    assert final is RunStatus.FAILED

    events = _events(engine, run_id)

    # 1. Discriminating: zero ROLE_BOUNCED events -- pre-fix there is
    # exactly one.
    bounced = [e for e in events if e.type == "ROLE_BOUNCED"]
    assert bounced == []

    # 2. Discriminating: the stale increment CR-01's fix clears.
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.qa_developer_iterations == 0

    # 3. Discriminating: exactly one role_executions row for DEVELOPMENT and
    # exactly one for QA, both at attempt 1 -- pre-fix the bounce creates a
    # DEVELOPMENT attempt-2 row.
    dev_executions = _role_executions(engine, run_id, "DEVELOPMENT")
    qa_executions = _role_executions(engine, run_id, "QA")
    assert [e.attempt for e in dev_executions] == [1]
    assert [e.attempt for e in qa_executions] == [1]

    # 4. Discriminating: QA's single row is FAILED with an error naming
    # write_scope and the offending path.
    qa_attempt_1 = qa_executions[0]
    assert qa_attempt_1.status == "FAILED"
    assert qa_attempt_1.error is not None
    error_text = str(qa_attempt_1.error.get("error", ""))
    assert "write_scope" in error_text
    assert "src/leaked_by_qa.py" in error_text

    # 5. Discriminating: the revert happened -- pre-fix the file is still on
    # disk.
    assert not (work_dir / "src" / "leaked_by_qa.py").exists()

    # 7. Corroborating: exactly one RUN_FAILED event, whose payload carries
    # no "counter" key -- this is a violation failure, not a cap-exhaustion
    # failure, so _EXHAUSTION_REASON_TO_COUNTER must miss.
    run_failed = [e for e in events if e.type == "RUN_FAILED"]
    assert len(run_failed) == 1
    assert "counter" not in run_failed[0].payload
