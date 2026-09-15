"""Phase 4 Success Criterion 5 (`.planning/ROADMAP.md`, Phase 4):

    "A machine artifact that violates its JSON schema fails the role with a
    persisted error instead of advancing the run, and the transition after QA
    is decided by `verdict.json`, never by summary prose."

**D-06, recorded here verbatim** (`04-CONTEXT.md`): within Phase 4's scope the
run advances past QA regardless of verdict PASS or FAIL -- Phase 4 only needs
the transition to be *decided by* `verdict.json` rather than agent prose, not
to *act differently* on FAIL. The FAIL -> Developer bounce is Phase 9's
bounded feedback loop. This module therefore deliberately proves "prose
cannot change the outcome and an invalid contract can", never "PASS and FAIL
take different routes" -- asserting the latter would assert behaviour this
phase does not implement.

Follows the same real-run db-test idiom as `tests/db/test_four_role_pipeline.py`
/ `tests/db/test_run_failure_path.py`: a config tree, `start_run`, an injected
per-test `WorkerRegistry` wrapping one ordered `FakeWorker` script, `drive`
with the test's `repo_root`. Each scenario varies only the bytes
`write_role_artifacts` puts on disk (once the run id -- and therefore the run
tree -- exists) and the prose in the scripted `WorkerResult.summary`.

05-03 (D-04): unlike the artifact-reading tests migrated onto
`tests.support.git_repo.run_artifact_text` in this same plan, every scenario
here drives a run that ends `FAILED` (a schema violation), and `FAILED` runs
keep their worktree on disk (D-04's failure arm) -- so reading artifact
content directly off `run_dir` below is still correct, not a leftover.
"""

from __future__ import annotations

import json
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
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
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
from tests.support.fake_artifacts import write_role_artifacts

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

# Populated by every scenario below with the `run_events.type` values it
# actually wrote; asserted a subset of the shipped ten-member `EventType` enum
# by the module's final test (`test_run_events_never_leave_the_ten_member_event_type_enum`,
# which must stay the last test defined in the file: pytest's default
# collection order is file-definition order, and cleanup_runs deletes each
# scenario's run_events at that scenario's own teardown, so the aggregate
# check must read the module-level accumulator rather than re-querying rows
# that no longer exist by the time it runs).
_SEEN_EVENT_TYPES: set[str] = set()


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


def _single_role_tree(
    config_root_factory: Callable[..., Path], role: str, *, outputs: str
) -> Path:
    """A one-role `[role]` config tree with `role`'s `outputs` overwritten to
    `outputs` (a YAML flow-sequence literal, e.g. `"[verdict.json]"`) and
    `inputs: []` -- this module never needs cross-role context resolution,
    only the D-09 artifact-validation gate."""
    root = config_root_factory(roles=(role,))
    (root / f".dark-factory/roles/{role}.yaml").write_text(
        f"name: {role}\n"
        "worker: fake\n"
        f"instructions: ../instructions/{role.lower()}.md\n"
        "tools: []\n"
        "permissions:\n  write_scope: []\n"
        "before: [prepare_role_context]\n"
        "after: [store_role_artifacts]\n"
        "inputs: []\n"
        f"outputs: {outputs}\n"
        "examples: []\n",
        encoding="utf-8",
    )
    return root


def _start_run_and_get_run_dir(
    root: Path,
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> tuple[Any, Path]:
    """`start_run` alone -- no worker call yet -- returning `(run_id, run_dir)`
    so a scenario can write its artifact file(s) into the real run tree
    *before* scripting the `WorkerResult` that references them.

    GIT-01: pre-creates the run's worktree now (idempotent -- the runner's
    own `ensure_worktree` call inside `drive()` reuses it) so `run_dir`
    resolves under the worktree, exactly where the runner will look for
    scripted artifact content, mirroring what a real worker's own writes
    would already have produced.
    """
    snapshot = load_effective_config(root)
    run_id = start_run(
        "text:prove SC5",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch="main", working_branch=working_branch_name(run_id)
    )
    return run_id, run_root(work_dir, run_id)


def _drive(
    run_id: Any,
    root: Path,
    real_session_factory: SessionFactory,
    script: list[WorkerResult],
) -> RunStatus:
    worker = FakeWorker(script)
    return drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
    )


def _record_event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        types = list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    _SEEN_EVENT_TYPES.update(types)
    return types


def test_ba_invalid_json_acceptance_criteria_fails_the_role_with_zero_artifact_rows(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 1: unparseable JSON fails the role with a complete
    persisted error trail and zero `artifacts` rows for that attempt; the
    file itself is untouched on disk -- the failure is a refusal to record,
    not a cleanup."""
    root = _single_role_tree(
        config_root_factory, "BA", outputs="[acceptance_criteria.json]"
    )
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir, "BA", {"acceptance_criteria.json": "{not valid json at all"}
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.result is None
        assert execution.error is not None
        assert "acceptance_criteria.json" in json.dumps(execution.error)

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.role_execution_id == execution.id)
        )
        assert artifact_count == 0

    types = _record_event_types(engine, run_id)
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types

    path = run_dir / "artifacts" / "BA" / "acceptance_criteria.json"
    assert path.is_file()
    assert path.read_text("utf-8") == "{not valid json at all"


def test_ba_schema_violating_acceptance_criteria_fails_the_role_naming_the_filename(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 2: JSON that parses but violates the model (here, an
    empty `criteria` list -- `AcceptanceCriteriaDocument` requires at least
    one) fails the role the same way, and the persisted error names the
    filename."""
    root = _single_role_tree(
        config_root_factory, "BA", outputs="[acceptance_criteria.json]"
    )
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir,
        "BA",
        {"acceptance_criteria.json": json.dumps({"criteria": []})},
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.error is not None
        assert "acceptance_criteria.json" in json.dumps(execution.error)

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.role_execution_id == execution.id)
        )
        assert artifact_count == 0

    types = _record_event_types(engine, run_id)
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types

    path = run_dir / "artifacts" / "BA" / "acceptance_criteria.json"
    assert path.is_file()


def test_ba_declared_output_not_reported_fails_the_role(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 3: a role that declares `acceptance_criteria.json` in
    `outputs` but reports no matching artifact fails the same way -- a
    declared machine output that never arrived is a contract violation, not a
    silent success. No file is ever written for this scenario (the worker
    genuinely produced nothing), so there is no "still on disk" claim to
    make -- unlike the schema-violation scenarios, there is nothing to leave
    behind."""
    root = _single_role_tree(
        config_root_factory, "BA", outputs="[acceptance_criteria.json]"
    )
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            artifacts=[],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.error is not None
        assert "acceptance_criteria.json" in json.dumps(execution.error)

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.role_execution_id == execution.id)
        )
        assert artifact_count == 0

    types = _record_event_types(engine, run_id)
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types

    assert not (run_dir / "artifacts" / "BA" / "acceptance_criteria.json").exists()


def test_role_emitting_markdown_prose_still_completes_unvalidated(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 4: a role that emits `requirements.md` containing
    arbitrary prose still completes -- Markdown is human documentation and is
    never schema-validated."""
    root = _single_role_tree(config_root_factory, "BA", outputs="[requirements.md]")
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir,
        "BA",
        {
            "requirements.md": "# Requirements\n\nThis is not JSON at all, and never needs to be.\n"
        },
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="BA analysis complete",
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "COMPLETED"

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.role_execution_id == execution.id)
        )
        assert artifact_count == 1

    types = _record_event_types(engine, run_id)
    assert "ROLE_COMPLETED" in types
    assert "RUN_COMPLETED" in types
    assert "ROLE_FAILED" not in types


def _verdict_json(*, declared_status: str, criterion_result: str) -> str:
    return json.dumps(
        {
            "criteria": [
                {"criterion_id": "AC-1", "result": criterion_result, "notes": ""}
            ],
            "issues": [],
            "status": declared_status,
        }
    )


def test_qa_misleading_failure_prose_with_valid_verdict_still_advances(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 5 (D-06): a QA attempt whose `WorkerResult.summary`
    prose asserts failure, while its `verdict.json` is valid and internally
    consistent (declared PASS, matching a PASS criterion), still advances the
    run -- the transition is computed from the JSON contract, never the
    prose."""
    root = _single_role_tree(config_root_factory, "QA", outputs="[verdict.json]")
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir,
        "QA",
        {
            "verdict.json": _verdict_json(
                declared_status="PASS", criterion_result="PASS"
            )
        },
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=(
                "QA REJECTS this implementation outright. Every criterion "
                "fails and the change must not proceed."
            ),
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "COMPLETED"

    types = _record_event_types(engine, run_id)
    assert "ROLE_COMPLETED" in types
    assert "RUN_COMPLETED" in types


def test_qa_misleading_success_prose_with_inconsistent_verdict_fails_the_role(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 6: a QA attempt whose `WorkerResult.summary` prose
    asserts success, while its `verdict.json` declares PASS with a FAIL
    criterion (internally inconsistent -- `Verdict`'s own after-validator
    rejects this), fails the role. The JSON contract, not the prose, is what
    the transition depends on."""
    root = _single_role_tree(config_root_factory, "QA", outputs="[verdict.json]")
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir,
        "QA",
        {
            "verdict.json": _verdict_json(
                declared_status="PASS", criterion_result="FAIL"
            )
        },
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=(
                "QA verified every acceptance criterion successfully. "
                "Everything passes cleanly."
            ),
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.FAILED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "FAILED"
        assert execution.error is not None
        assert "verdict.json" in json.dumps(execution.error)

        run = session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.FAILED

        artifact_count = session.scalar(
            sa.select(sa.func.count())
            .select_from(ArtifactReference)
            .where(ArtifactReference.role_execution_id == execution.id)
        )
        assert artifact_count == 0

    types = _record_event_types(engine, run_id)
    assert "ROLE_FAILED" in types
    assert "RUN_FAILED" in types

    path = run_dir / "artifacts" / "QA" / "verdict.json"
    assert path.is_file()


def test_qa_verdict_fail_advances_the_run_exactly_like_pass(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
) -> None:
    """Behavior bullet 7 (D-06): a QA attempt whose `verdict.json` declares
    FAIL consistently (one FAIL criterion, declared status FAIL -- internally
    consistent) advances the run exactly as a PASS verdict does. Phase 4 does
    not branch the transition on verdict content."""
    root = _single_role_tree(config_root_factory, "QA", outputs="[verdict.json]")
    run_id, run_dir = _start_run_and_get_run_dir(
        root, real_session_factory, cleanup_runs
    )
    (ref,) = write_role_artifacts(
        run_dir,
        "QA",
        {
            "verdict.json": _verdict_json(
                declared_status="FAIL", criterion_result="FAIL"
            )
        },
    )
    script = [
        WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary="QA found a genuine failure.",
            artifacts=[ref],
        )
    ]

    final = _drive(run_id, root, real_session_factory, script)
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        execution = session.scalars(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        ).one()
        assert execution.status == "COMPLETED"

    types = _record_event_types(engine, run_id)
    assert "ROLE_COMPLETED" in types
    assert "RUN_COMPLETED" in types


def test_run_events_never_leave_the_ten_member_event_type_enum() -> None:
    """Behavior bullet 8: across every scenario above, `run_events` gains no
    event type outside the ten-member `EventType` enum. Must stay the last
    test defined in this module -- see `_SEEN_EVENT_TYPES`'s module-level
    docstring for why."""
    assert _SEEN_EVENT_TYPES, "no scenario above recorded any event types"
    legal_types = {member.value for member in EventType}
    assert legal_types >= _SEEN_EVENT_TYPES
