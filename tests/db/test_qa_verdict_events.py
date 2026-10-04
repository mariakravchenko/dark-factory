"""D-07 (Plan 12-04): the acceptance-criteria verdict becomes a first-class,
queryable fact -- cardinality and distinctness, proven against real
PostgreSQL across PASS, FAIL-under-cap, FAIL-at-cap, a PASS-verdict-with-
gate-FAIL distinctness scenario, and a late commit/push failure.

Follows ``tests/db/test_qa_bounce.py`` / ``tests/db/test_iteration_cap_exhaustion.py``'s
real ``drive()`` idiom (``start_run`` + an injected ``WorkerRegistry``
wrapping ``tests.support.fake_artifacts`` fixtures against real PostgreSQL,
``cleanup_runs`` deleting every fixture row at teardown) and
``tests/db/test_publish_step.py``'s ``_event_types`` helper shape.

The FAIL-under-cap scenario deliberately steps with ``advance()``, never
``drive()``: ``LazyFourRoleWorker``'s ``qa_files`` override is
attempt-independent (every QA attempt fails identically), so ``drive()``
would keep bouncing until the configured cap is genuinely exhausted. Only
the *first* bounce's event shape is what this scenario needs, so stepping
stops the instant it lands.

The FAIL-at-the-cap scenario deliberately uses a zero iteration cap (the
``test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce``
shape from ``test_iteration_cap_exhaustion.py``), not the two-attempt
exhaustion shape from that module's own cap=1 scenario: a run with two
FAIL verdicts (bounce, then exhaust) would legitimately carry *two*
``QA_FAILED`` events, one per attempt -- the zero-cap shape is the one
configuration that makes "exactly one ``QA_FAILED``" true by construction,
since there is exactly one QA attempt.
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

import dark_factory.orchestrator.runner as runner_module
from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.events.catalog import EventType
from dark_factory.events.reader import read_events
from dark_factory.git import GitError
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
    LazyFourRoleWorker,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_QUALITY_GATE_BLOCK = "quality_gate:\n  commands: []\n"
_RETRY_BLOCK = (
    "retry:\n  qa_developer_max_iterations: 3\n  quality_gate_max_iterations: 2\n"
)


def _write_four_role_tree(
    config_root_factory: Callable[..., Path],
    *,
    quality_gate_commands: list[str] | None = None,
    qa_developer_max_iterations: int = 3,
    quality_gate_max_iterations: int = 2,
) -> Path:
    """The same ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` config tree
    ``tests/db/test_qa_bounce.py`` writes -- duplicated rather than
    imported, matching every other db-tier module's own self-contained
    config-tree helper in this project."""
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


def _single_role_qa_tree(config_root_factory: Callable[..., Path]) -> Path:
    """A one-role ``[QA]`` config tree -- QA is both the first and the
    terminal role, so its own verdict block runs with nowhere to bounce to
    and no earlier role's artifacts to depend on. Used only by the
    late-failure honesty scenario, which needs a verdict-bearing terminal
    role whose ``commit_run_artifacts`` call is made to fail."""
    root = config_root_factory(roles=("QA",))
    (root / ".dark-factory/roles/QA.yaml").write_text(
        "name: QA\n"
        "worker: fake\n"
        "instructions: ../instructions/qa.md\n"
        "tools: [repo.read, repo.search, repo.write_tests, shell.execute, "
        "artifacts.read, artifacts.write]\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: []\n"
        "outputs: [verdict.json]\n"
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


def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def _advance_until_role_bounced(
    run_id: Any,
    *,
    session_factory: SessionFactory,
    registry: WorkerRegistry,
    repo_root: Path,
    engine: Engine,
    max_steps: int = 20,
) -> RunStatus:
    """Step with ``advance()`` -- never ``drive()`` -- until exactly one
    ``ROLE_BOUNCED`` event has landed, then stop. See the module docstring
    for why ``drive()`` is the wrong tool for this scenario."""
    status: RunStatus | None = None
    for _ in range(max_steps):
        status = advance(
            run_id,
            session_factory=session_factory,
            registry=registry,
            repo_root=repo_root,
        )
        if "ROLE_BOUNCED" in _event_types(engine, run_id):
            return status
    raise AssertionError(f"no ROLE_BOUNCED event after {max_steps} advance() steps")


def test_pass_verdict_emits_exactly_one_qa_passed_and_zero_qa_failed_in_order(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    """PASS: exactly one ``QA_PASSED``, zero ``QA_FAILED``, the generic
    ``ROLE_COMPLETED`` count is unaffected (4, one per role), and
    ``QA_PASSED``'s ``seq`` sits between the terminal role's own
    ``ROLE_COMPLETED`` and ``RUN_COMPLETED`` -- "the role finished, then
    the verdict was recorded, then the gate ran, then the run completed"."""
    root = _write_four_role_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove a PASS verdict becomes QA_PASSED",
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
    event_types = [r.type for r in rows]

    assert event_types.count(EventType.QA_PASSED.value) == 1
    assert event_types.count(EventType.QA_FAILED.value) == 0
    # Alongside, never instead of: the generic ROLE_COMPLETED is untouched --
    # exact count, not a presence check -- one per role across this
    # four-role PASS run (BA, ARCHITECTURE, DEVELOPMENT, QA).
    assert event_types.count("ROLE_COMPLETED") == 4

    qa_passed_seq = next(r.seq for r in rows if r.type == EventType.QA_PASSED.value)
    role_completed_seqs = [r.seq for r in rows if r.type == "ROLE_COMPLETED"]
    run_completed_seq = next(r.seq for r in rows if r.type == "RUN_COMPLETED")
    assert qa_passed_seq > max(role_completed_seqs)
    assert qa_passed_seq < run_completed_seq


def test_fail_under_cap_bounces_with_one_qa_failed_and_no_quality_gate_events(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """FAIL under the cap: a FAIL verdict that bounces leaves exactly one
    ``QA_FAILED`` and zero ``QA_PASSED``, alongside the ``ROLE_BOUNCED``
    the bounce itself produces. ``criteria_failed`` is non-empty and names
    exactly the fixture's own failing criterion id. GATE-01's converse:
    zero ``QUALITY_GATE_*`` events of any kind -- a FAIL verdict
    short-circuits the gate before it ever runs, so neither signal can be
    inferred from the other."""
    root = _write_four_role_tree(config_root_factory, qa_developer_max_iterations=2)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:qa fails once under a cap that allows a bounce",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir, qa_files=QA_VERDICT_FAIL_FILES)
    registry = _registry(worker)

    final = _advance_until_role_bounced(
        run_id,
        session_factory=real_session_factory,
        registry=registry,
        repo_root=root,
        engine=engine,
    )
    assert final is RunStatus.DEVELOPMENT  # bounced back to the Developer

    event_types = _event_types(engine, run_id)
    assert event_types.count("ROLE_BOUNCED") == 1
    assert event_types.count(EventType.QA_FAILED.value) == 1
    assert event_types.count(EventType.QA_PASSED.value) == 0
    assert not any(t.startswith("QUALITY_GATE_") for t in event_types)

    # Production read path, not a hand-written query: read_events and the
    # emission path must agree on the same row.
    qa_failed_rows = read_events(
        run_id,
        event_types=[EventType.QA_FAILED],
        session_factory=real_session_factory,
    )
    assert len(qa_failed_rows) == 1
    criteria_failed = qa_failed_rows[0].payload["criteria_failed"]
    assert (
        criteria_failed
    )  # non-empty -- a silent-emptiness bug would pass without this
    assert set(criteria_failed) == {
        "AC-1"
    }  # QA_VERDICT_FAIL_FILES' own failing criterion


def test_fail_at_zero_cap_is_terminal_with_exactly_one_qa_failed(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """FAIL at the cap: a zero iteration cap makes the very first QA
    rejection terminal, with no bounce and exactly one QA attempt -- the
    one configuration under which "exactly one QA_FAILED" is true by
    construction (a bounce-then-exhaust run would carry two). QA_FAILED
    survives into the ROLE_FAILED/RUN_FAILED arm, the arm an operator
    reaching for events most needs it in."""
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
    worker = LazyFourRoleWorker(run_dir, qa_files=QA_VERDICT_FAIL_FILES)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    event_types = _event_types(engine, run_id)
    assert event_types.count(EventType.QA_FAILED.value) == 1
    assert event_types.count("ROLE_BOUNCED") == 0
    assert event_types.count("ROLE_FAILED") == 1
    assert event_types.count("RUN_FAILED") == 1


def test_pass_verdict_coexists_with_quality_gate_failed(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Distinctness: a run whose acceptance-criteria verdict passes but
    whose independent quality gate fails (then passes once the Developer's
    retry creates the checked-for sentinel) carries both ``QA_PASSED`` and
    ``QUALITY_GATE_FAILED`` together -- a legal, meaningful disagreement
    the stream must be able to express, since one signal is never
    inferable from the other."""
    sentinel_name = "gate_ran_after_bounce_qa_verdict.txt"
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
        "text:prove QA_PASSED coexists with QUALITY_GATE_FAILED",
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

    event_types = _event_types(engine, run_id)
    assert "QA_PASSED" in event_types
    assert "QUALITY_GATE_FAILED" in event_types


def test_commit_failure_after_verdict_leaves_zero_qa_verdict_events(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Late-failure honesty: a verdict-bearing terminal role (QA, here
    both first and terminal) whose ``commit_run_artifacts`` call
    subsequently fails leaves zero ``QA_PASSED`` and zero ``QA_FAILED``
    events, alongside the zero ``artifacts`` rows the existing GitError
    catch already guarantees -- a verdict the run never durably acted on
    must leave no event claiming it did."""
    root = _single_role_qa_tree(config_root_factory)
    snapshot = load_effective_config(root)

    run_id = start_run(
        "text:prove a commit failure voids the verdict event",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    def _raise_git_error(*args: Any, **kwargs: Any) -> str | None:
        raise GitError("simulated commit failure for the late-failure honesty test")

    monkeypatch.setattr(runner_module, "commit_run_artifacts", _raise_git_error)

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.run_id == run_id)
        )
        assert artifact_count == 0

    event_types = _event_types(engine, run_id)
    assert EventType.QA_PASSED.value not in event_types
    assert EventType.QA_FAILED.value not in event_types
    assert "ROLE_FAILED" in event_types
    assert "RUN_FAILED" in event_types
