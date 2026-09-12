"""Unit contract for ``build_role_context`` (CTX-01, CTX-02, CTX-03, CTX-04).

Drives ``build_role_context`` directly against a ``tmp_path`` repo root and a
real (but hand-built) :class:`RunState`, with a stub session standing in for
the builder's one database dependency -- the ``select`` inside
``_latest_completed_execution`` and the follow-up ``artifacts`` row lookup in
``_resolve_input``. No PostgreSQL is needed for any assertion here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from dark_factory.artifacts import ArtifactContractError, ArtifactTooLargeError
from dark_factory.artifacts import MissingArtifactContentError as ArtifactMissing
from dark_factory.context.builder import build_role_context
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.persistence.models import ArtifactReference, RoleExecution
from dark_factory.persistence.repositories import LatestExecution, RunState

pytestmark = pytest.mark.unit


class _FakeSession:
    """A minimal stand-in for the one database dependency: ``session.scalar``.

    Cycles through ``responses`` (never raises ``StopIteration``/``IndexError``)
    so the *same* stub can serve two consecutive ``build_role_context`` calls
    with identical results -- what the idempotency test needs.
    """

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self._calls = 0

    def scalar(self, _stmt: object) -> object:
        if not self._responses:
            raise AssertionError("session.scalar() called with no responses queued")
        value = self._responses[self._calls % len(self._responses)]
        self._calls += 1
        return value


def _task() -> NormalizedTask:
    return NormalizedTask(
        source_kind="text", source_ref=None, title="t", body="do it", metadata={}
    )


def _state(*, workflow: dict[str, Any], latest_role: str | None = None) -> RunState:
    latest = (
        LatestExecution(
            id=uuid4(), role=latest_role, worker="fake", status="RUNNING", attempt=3
        )
        if latest_role is not None
        else None
    )
    return RunState(
        run_id=uuid4(),
        status=RunStatus.ARCHITECTURE,
        current_role=latest_role,
        current_step=0,
        normalized_task=_task(),
        workflow=workflow,
        qa_developer_iterations=0,
        quality_gate_iterations=0,
        latest_execution=latest,
        pending_answer=None,
    )


def _role_def(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "TARGET",
        "worker": "fake",
        "instruction_text": "do the target role's job",
        "tools": [],
        "permissions": {},
        "before": [],
        "after": [],
        "inputs": [],
        "outputs": [],
        "examples": [],
    }
    base.update(overrides)
    return base


def _role_execution(role: str, run_id: UUID, *, attempt: int = 1) -> RoleExecution:
    return RoleExecution(
        id=uuid4(),
        run_id=run_id,
        role=role,
        worker="fake",
        status="COMPLETED",
        attempt=attempt,
        worker_session_id=None,
        result=None,
        error=None,
    )


def _artifact_row(
    role_execution_id: UUID, run_id: UUID, filename: str, path: str
) -> ArtifactReference:
    return ArtifactReference(
        id=uuid4(),
        run_id=run_id,
        role_execution_id=role_execution_id,
        type=filename,
        path=path,
        checksum="deadbeef",
        artifact_metadata={},
    )


# --------------------------------------------------------------------------- #
# 1. filename resolution goes through outputs lists, not pipeline adjacency
# --------------------------------------------------------------------------- #


def test_input_resolves_through_outputs_not_pipeline_adjacency(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    run_dir = tmp_path / ".dark-factory" / "runs" / str(run_id)
    artifact_path = run_dir / "artifacts" / "BA" / "x.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"ok": true}', encoding="utf-8")

    ba_execution = _role_execution("BA", run_id)
    ba_artifact = _artifact_row(
        ba_execution.id, run_id, "x.json", "artifacts/BA/x.json"
    )

    state = _state(
        workflow={
            "roles": [
                {"name": "BA", "outputs": ["x.json"]},
                {"name": "MIDDLE", "outputs": []},  # sits directly before TARGET
                {"name": "TARGET", "outputs": []},
            ]
        },
    )
    role_def = _role_def(inputs=["x.json"])
    session = _FakeSession([ba_execution, ba_artifact])

    context = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]

    assert len(context.inputs) == 1
    assert context.inputs[0].filename == "x.json"
    assert context.inputs[0].produced_by == "BA"
    assert context.inputs[0].content == '{"ok": true}'


# --------------------------------------------------------------------------- #
# 2. empty inputs -> RoleContext.inputs == [], baseline + instructions present
# --------------------------------------------------------------------------- #


def test_empty_inputs_still_gets_baseline_and_instructions(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
    run_id = uuid4()
    state = _state(workflow={"roles": [{"name": "TARGET", "outputs": []}]})
    role_def = _role_def(inputs=[], instruction_text="follow these instructions")
    session = _FakeSession([])

    context = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]

    assert context.inputs == []
    assert context.instructions == "follow these instructions"
    assert context.baseline_docs["README.md"] == "# hello\n"


# --------------------------------------------------------------------------- #
# 3. a repo missing AGENTS.md still builds a context; only present files load
# --------------------------------------------------------------------------- #


def test_missing_baseline_file_is_skipped_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("readme text", encoding="utf-8")
    # AGENTS.md and CLAUDE.md deliberately absent.
    run_id = uuid4()
    state = _state(workflow={"roles": [{"name": "TARGET", "outputs": []}]})
    role_def = _role_def()
    session = _FakeSession([])

    context = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]

    assert context.baseline_docs == {"README.md": "readme text"}


# --------------------------------------------------------------------------- #
# 4. an oversized baseline file raises rather than silently truncating
# --------------------------------------------------------------------------- #


def test_oversized_baseline_file_raises(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x" * (64 * 1024 + 1), encoding="utf-8")
    run_id = uuid4()
    state = _state(workflow={"roles": [{"name": "TARGET", "outputs": []}]})
    role_def = _role_def()
    session = _FakeSession([])

    with pytest.raises(ArtifactTooLargeError):
        build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 5. examples load as inert text
# --------------------------------------------------------------------------- #


def test_examples_load_as_inert_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    example_dir = tmp_path / "examples"
    example_dir.mkdir()
    (example_dir / "sample.py").write_text(
        "print('should never execute')\n", encoding="utf-8"
    )
    run_id = uuid4()
    state = _state(workflow={"roles": [{"name": "TARGET", "outputs": []}]})
    role_def = _role_def(examples=["examples/sample.py"])
    session = _FakeSession([])

    context = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]

    assert len(context.examples) == 1
    assert context.examples[0].path == "examples/sample.py"
    assert context.examples[0].content == "print('should never execute')\n"
    captured = capsys.readouterr()
    assert "should never execute" not in captured.out


# --------------------------------------------------------------------------- #
# 6. two consecutive calls, same arguments, return equal RoleContext values
# --------------------------------------------------------------------------- #


def test_two_consecutive_calls_are_equal(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("baseline", encoding="utf-8")
    run_id = uuid4()
    run_dir = tmp_path / ".dark-factory" / "runs" / str(run_id)
    artifact_path = run_dir / "artifacts" / "BA" / "x.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("content", encoding="utf-8")

    ba_execution = _role_execution("BA", run_id)
    ba_artifact = _artifact_row(
        ba_execution.id, run_id, "x.json", "artifacts/BA/x.json"
    )

    state = _state(
        workflow={
            "roles": [
                {"name": "BA", "outputs": ["x.json"]},
                {"name": "TARGET", "outputs": []},
            ]
        }
    )
    role_def = _role_def(inputs=["x.json"])
    # Cycles: call 1 consumes [0]=execution, [1]=artifact; call 2 wraps back to
    # the same two responses -- a real select would likewise return the same
    # committed rows for the same (run_id, role, attempt) with no intervening
    # commit.
    session = _FakeSession([ba_execution, ba_artifact])

    first = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]
    second = build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]

    assert first == second


# --------------------------------------------------------------------------- #
# 7. a declared input no role in the snapshot outputs raises ArtifactContractError
# --------------------------------------------------------------------------- #


def test_undeclared_producing_role_raises_artifact_contract_error(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    state = _state(
        workflow={
            "roles": [
                {"name": "BA", "outputs": []},
                {"name": "TARGET", "outputs": []},
            ]
        }
    )
    role_def = _role_def(inputs=["never_produced.json"])
    session = _FakeSession([])

    with pytest.raises(ArtifactContractError) as excinfo:
        build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]
    assert "never_produced.json" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# 8. a producing role with no COMPLETED attempt raises MissingArtifactContentError
# --------------------------------------------------------------------------- #


def test_producing_role_with_no_completed_attempt_raises_missing_content(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    state = _state(
        workflow={
            "roles": [
                {"name": "BA", "outputs": ["x.json"]},
                {"name": "TARGET", "outputs": []},
            ]
        }
    )
    role_def = _role_def(inputs=["x.json"])
    session = _FakeSession([None])  # no COMPLETED role_executions row for BA

    with pytest.raises(ArtifactMissing) as excinfo:
        build_role_context(session, tmp_path, run_id, state, role_def)  # type: ignore[arg-type]
    assert "BA" in str(excinfo.value)
    assert "x.json" in str(excinfo.value)
