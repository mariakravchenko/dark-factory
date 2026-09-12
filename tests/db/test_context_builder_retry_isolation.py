"""Phase 4 Success Criterion 4 (`.planning/ROADMAP.md`, Phase 4):

    "A retried attempt's rebuilt context contains no artifact from the
    superseded attempt."

**No Phase 4 code path produces a second attempt of one role.** The QA-FAIL to
Developer bounce that would naturally create a retry is Phase 9's bounded
feedback loop (D-06, deferred in `04-CONTEXT.md`). This module therefore
constructs the two-attempt state directly through the one mutation path --
`create_run`, then `apply_transition` with a `RoleExecutionWrite` in insert
mode to open each attempt (the attempt number is computed in SQL inside the
transaction, so the second insert for the same run and role naturally becomes
attempt 2) and in update mode to close it -- exactly the sequence Phase 9's
real retry will eventually produce. This is a deliberate, recorded
substitution: the query under test (`context/builder.py`'s D-03 selection --
`_latest_completed_execution`, filtering on `status == "COMPLETED"` and
ordering by `attempt DESC LIMIT 1`) is the real production query; only the
state that reaches it is arranged by the test rather than by a feedback loop.

Follows the in-process db-test idiom `tests/db/test_apply_transition.py` and
`tests/db/test_load_run_state.py` established: drive `create_run` /
`apply_transition` directly against `db_session`, then read state back with
`load_run_state`. Artifact files are written with
`tests/support/fake_artifacts.py::write_role_artifacts`.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from dark_factory.artifacts import MissingArtifactContentError
from dark_factory.artifacts.paths import ensure_run_tree, run_root
from dark_factory.context.builder import build_role_context
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.persistence.mutations import (
    ArtifactReferenceWrite,
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)
from dark_factory.persistence.repositories import load_run_state
from tests.support.fake_artifacts import write_role_artifacts

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

_FILENAME = "acceptance_criteria.json"

# One producing role ("BA") declaring `_FILENAME` as an output, and one
# downstream role ("ARCHITECTURE") declaring it as an input -- the minimal
# two-role snapshot shape `_producing_role` scans.
_WORKFLOW: dict[str, object] = {
    "roles": [
        {"name": "BA", "outputs": [_FILENAME], "before": [], "after": []},
        {
            "name": "ARCHITECTURE",
            "inputs": [_FILENAME],
            "outputs": [],
            "before": [],
            "after": [],
        },
    ]
}

_ROLE_DEF = {
    "name": "ARCHITECTURE",
    "worker": "fake",
    "inputs": [_FILENAME],
    "outputs": [],
    "examples": [],
    "before": [],
    "after": [],
}


def _task() -> NormalizedTask:
    return NormalizedTask(
        source_kind="text", source_ref=None, title="t", body="b", metadata={}
    )


def _created_run(session: Session) -> UUID:
    return create_run(session, task=_task(), workflow=_WORKFLOW)


def _insert_attempt(session: Session, run_id: UUID) -> None:
    """Insert a fresh ``RUNNING`` ``role_executions`` row for ``BA``. The
    transaction stays at ``BA`` -> ``BA`` (no status change), mirroring
    `test_apply_transition.py::test_second_insert_for_same_run_and_role_gets_attempt_two`.
    """
    apply_transition(
        session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="insert", role="BA", worker="fake", status="RUNNING"
        ),
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={"role": "BA"})],
    )


def _enter_ba(session: Session, run_id: UUID) -> None:
    """``CREATED -> BA``, inserting attempt 1's ``RUNNING`` row."""
    apply_transition(
        session,
        run_id=run_id,
        expected_status=RunStatus.CREATED,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="insert", role="BA", worker="fake", status="RUNNING"
        ),
        events=[EventWrite(type=EventType.ROLE_STARTED, payload={"role": "BA"})],
    )


def _latest_ba_execution_id(session: Session, run_id: UUID) -> UUID:
    """A bare read. Per `test_apply_transition.py`'s own module docstring, a
    bare read autobegins a transaction that must be released with
    `session.rollback()` before the next mutation opens its own
    `session.begin()` -- done here, internally, so every call site is free to
    chain straight into the next `apply_transition` call."""
    from dark_factory.persistence.models import RoleExecution

    result = session.scalars(
        sa.select(RoleExecution.id)
        .where(RoleExecution.run_id == run_id, RoleExecution.role == "BA")
        .order_by(RoleExecution.attempt.desc())
        .limit(1)
    ).one()
    session.rollback()
    return result


def _close_attempt(
    session: Session,
    run_id: UUID,
    execution_id: UUID,
    *,
    status: str,
    artifact_ref: ArtifactReferenceWrite | None = None,
) -> None:
    """Update the named attempt row to ``status`` (``COMPLETED`` or
    ``FAILED``), optionally supplying its ``artifact_references``. The
    transaction stays at ``BA`` -> ``BA`` (no status change)."""
    refs: list[ArtifactReferenceWrite] = []
    if artifact_ref is not None:
        refs = [artifact_ref]
    apply_transition(
        session,
        run_id=run_id,
        expected_status=RunStatus.BA,
        next_status=RunStatus.BA,
        next_current_role="BA",
        next_current_step=0,
        role_execution=RoleExecutionWrite(
            mode="update",
            id=execution_id,
            role="BA",
            worker="fake",
            status=status,
            result={"summary": "done"} if status == "COMPLETED" else None,
            error={"detail": "boom"} if status == "FAILED" else None,
        ),
        events=[
            EventWrite(
                type=EventType.ROLE_COMPLETED
                if status == "COMPLETED"
                else EventType.ROLE_FAILED,
                payload={"role": "BA"},
            )
        ],
        artifact_references=refs,
    )


def _write_and_ref(
    run_dir: Path, execution_id: UUID, content: str
) -> ArtifactReferenceWrite:
    (artifact_ref,) = write_role_artifacts(run_dir, "BA", {_FILENAME: content})
    return ArtifactReferenceWrite(
        role_execution_id=execution_id,
        type=_FILENAME,
        path=artifact_ref.path,
        checksum=artifact_ref.checksum,
        metadata={},
    )


def _artifacts_row_count(session: Session, run_id: UUID) -> int:
    """A bare read; see `_latest_ba_execution_id`'s docstring."""
    from dark_factory.persistence.models import ArtifactReference

    result = session.scalar(
        sa.select(sa.func.count())
        .select_from(ArtifactReference)
        .where(ArtifactReference.run_id == run_id)
    )
    session.rollback()
    assert result is not None
    return result


def test_two_completed_attempts_resolve_to_the_higher_numbered_attempts_content(
    db_session: Session, tmp_path: Path
) -> None:
    """SC4, first bullet: a downstream role's context receives the
    higher-numbered COMPLETED attempt's artifact content, and both attempts'
    reported content differ so a query that happened to pick the right row
    for the wrong reason still fails."""
    run_id = _created_run(db_session)
    run_dir = run_root(tmp_path, run_id)
    ensure_run_tree(run_dir)

    _enter_ba(db_session, run_id)
    attempt1_id = _latest_ba_execution_id(db_session, run_id)
    ref1 = _write_and_ref(run_dir, attempt1_id, "attempt-1-content")
    _close_attempt(
        db_session, run_id, attempt1_id, status="COMPLETED", artifact_ref=ref1
    )

    _insert_attempt(db_session, run_id)
    attempt2_id = _latest_ba_execution_id(db_session, run_id)
    assert attempt2_id != attempt1_id
    ref2 = _write_and_ref(run_dir, attempt2_id, "attempt-2-content")
    _close_attempt(
        db_session, run_id, attempt2_id, status="COMPLETED", artifact_ref=ref2
    )

    state = load_run_state(db_session, run_id)
    assert state is not None

    context = build_role_context(db_session, tmp_path, run_id, state, _ROLE_DEF)

    assert len(context.inputs) == 1
    resolved = context.inputs[0]
    assert resolved.content == "attempt-2-content"
    assert resolved.content != "attempt-1-content"


def test_superseded_attempts_artifact_row_survives_for_audit(
    db_session: Session, tmp_path: Path
) -> None:
    """SC4, second bullet: the superseded attempt's `ArtifactReference` row is
    still present -- and independently selectable by its own id -- after the
    context is built. Isolation is achieved by never selecting it, not by
    deleting it."""
    from dark_factory.persistence.models import ArtifactReference

    run_id = _created_run(db_session)
    run_dir = run_root(tmp_path, run_id)
    ensure_run_tree(run_dir)

    _enter_ba(db_session, run_id)
    attempt1_id = _latest_ba_execution_id(db_session, run_id)
    ref1 = _write_and_ref(run_dir, attempt1_id, "attempt-1-content")
    _close_attempt(
        db_session, run_id, attempt1_id, status="COMPLETED", artifact_ref=ref1
    )

    superseded_row_id = db_session.scalars(
        sa.select(ArtifactReference.id).where(
            ArtifactReference.role_execution_id == attempt1_id
        )
    ).one()
    db_session.rollback()

    _insert_attempt(db_session, run_id)
    attempt2_id = _latest_ba_execution_id(db_session, run_id)
    ref2 = _write_and_ref(run_dir, attempt2_id, "attempt-2-content")
    _close_attempt(
        db_session, run_id, attempt2_id, status="COMPLETED", artifact_ref=ref2
    )

    state = load_run_state(db_session, run_id)
    assert state is not None
    build_role_context(db_session, tmp_path, run_id, state, _ROLE_DEF)

    superseded_row = db_session.get(ArtifactReference, superseded_row_id)
    assert superseded_row is not None
    assert superseded_row.role_execution_id == attempt1_id


def test_a_failed_later_attempt_does_not_hide_an_earlier_completed_result(
    db_session: Session, tmp_path: Path
) -> None:
    """SC4, third bullet: when the only later attempt is FAILED, the context
    still receives the earlier COMPLETED attempt's artifact."""
    run_id = _created_run(db_session)
    run_dir = run_root(tmp_path, run_id)
    ensure_run_tree(run_dir)

    _enter_ba(db_session, run_id)
    attempt1_id = _latest_ba_execution_id(db_session, run_id)
    ref1 = _write_and_ref(run_dir, attempt1_id, "the-good-result")
    _close_attempt(
        db_session, run_id, attempt1_id, status="COMPLETED", artifact_ref=ref1
    )

    _insert_attempt(db_session, run_id)
    attempt2_id = _latest_ba_execution_id(db_session, run_id)
    assert attempt2_id != attempt1_id
    # The failed attempt reports no artifact at all -- it never got that far.
    _close_attempt(db_session, run_id, attempt2_id, status="FAILED", artifact_ref=None)

    state = load_run_state(db_session, run_id)
    assert state is not None

    context = build_role_context(db_session, tmp_path, run_id, state, _ROLE_DEF)

    assert len(context.inputs) == 1
    assert context.inputs[0].content == "the-good-result"


@pytest.mark.parametrize("in_flight_status", ["RUNNING", "WAITING_HUMAN"])
def test_an_in_flight_only_attempt_raises_rather_than_degrading_silently(
    db_session: Session, tmp_path: Path, in_flight_status: str
) -> None:
    """SC4, fourth bullet: a role whose only attempt is RUNNING or
    WAITING_HUMAN raises `MissingArtifactContentError` naming the role and
    the filename, rather than silently returning an empty context."""
    run_id = _created_run(db_session)
    run_dir = run_root(tmp_path, run_id)
    ensure_run_tree(run_dir)

    _enter_ba(db_session, run_id)
    if in_flight_status != "RUNNING":
        attempt1_id = _latest_ba_execution_id(db_session, run_id)
        apply_transition(
            db_session,
            run_id=run_id,
            expected_status=RunStatus.BA,
            next_status=RunStatus.BA,
            next_current_role="BA",
            next_current_step=0,
            role_execution=RoleExecutionWrite(
                mode="update",
                id=attempt1_id,
                role="BA",
                worker="fake",
                status=in_flight_status,
                result={"status": "NEEDS_INPUT", "questions": ["q"]},
            ),
            events=[
                EventWrite(type=EventType.QUESTION_CREATED, payload={"role": "BA"})
            ],
        )

    state = load_run_state(db_session, run_id)
    assert state is not None

    with pytest.raises(MissingArtifactContentError) as excinfo:
        build_role_context(db_session, tmp_path, run_id, state, _ROLE_DEF)

    message = str(excinfo.value)
    assert "BA" in message
    assert _FILENAME in message


def test_building_a_context_writes_no_artifacts_row(
    db_session: Session, tmp_path: Path
) -> None:
    """SC4's construction guarantee: `build_role_context` is a pure read --
    the `artifacts` row count for the run is unchanged by building a
    context."""
    run_id = _created_run(db_session)
    run_dir = run_root(tmp_path, run_id)
    ensure_run_tree(run_dir)

    _enter_ba(db_session, run_id)
    attempt1_id = _latest_ba_execution_id(db_session, run_id)
    ref1 = _write_and_ref(run_dir, attempt1_id, "attempt-1-content")
    _close_attempt(
        db_session, run_id, attempt1_id, status="COMPLETED", artifact_ref=ref1
    )

    _insert_attempt(db_session, run_id)
    attempt2_id = _latest_ba_execution_id(db_session, run_id)
    ref2 = _write_and_ref(run_dir, attempt2_id, "attempt-2-content")
    _close_attempt(
        db_session, run_id, attempt2_id, status="COMPLETED", artifact_ref=ref2
    )

    before = _artifacts_row_count(db_session, run_id)

    state = load_run_state(db_session, run_id)
    assert state is not None
    build_role_context(db_session, tmp_path, run_id, state, _ROLE_DEF)

    after = _artifacts_row_count(db_session, run_id)
    assert before == after == 2
