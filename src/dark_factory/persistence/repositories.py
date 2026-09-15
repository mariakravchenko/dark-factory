"""`load_run_state` + `RunState` — the reconstruct half of resume-first advance
(Plan 01-05, Task 2 — STATE-06, STATE-08).

``advance()`` is always resume-first: every call rebuilds the whole run from Neon
into a plain value object with **no ``Session``, no ORM instance and no
lazy-loading proxy**, so the happy path and the resume path are literally the
same code (RESEARCH Pattern 1). This module is the one read path that does it.

**The Phase-1 column-not-variable list.** Every value ``advance()`` needs is a
persisted column and appears as a ``RunState`` field:

* ``run_id`` — ``runs.id``
* ``status`` — ``runs.status`` (as :class:`RunStatus`)
* ``current_role`` — ``runs.current_role`` (the authoritative pointer, A5)
* ``current_step`` — ``runs.current_step``
* ``normalized_task`` — ``runs.normalized_task`` (as :class:`NormalizedTask`)
* ``workflow`` — ``runs.workflow`` snapshot dict
* ``qa_developer_iterations`` — ``runs.qa_developer_iterations``
* ``quality_gate_iterations`` — ``runs.quality_gate_iterations``
* ``latest_execution`` — the single latest ``role_executions`` row (id, role,
  worker, status, attempt, worker_session_id, **result**), or ``None``. The
  ``result`` is the persisted worker outcome — for a paused role it is the
  ``NEEDS_INPUT`` dict a resume validates back into ``previous``.
* ``pending_answer`` — the ``answer`` of the ``ANSWERED`` ``human_interactions``
  row bound to ``latest_execution``, or ``None``. This is what a resume feeds to
  ``worker.resume(context, previous, answer)``.

If ``advance()`` needs a value it is added here; if it is not here, ``advance()``
may not need it.

**STATE-06 is architectural, not just behavioural.** This module imports nothing
from ``dark_factory``'s event package and issues no query touching the audit
log — control state comes from state columns, never from folding events. A read
path that *can* fold the log will eventually be made to. ``human_interactions``
is a **state table**, not the audit log: reading ``answer`` / ``question`` here
does not weaken that rule, because it is not reconstructing position by folding
an append-only stream — it is reading one current-state column, exactly like
``runs.status``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.persistence.models import HumanInteraction, RoleExecution, Run

__all__ = ["LatestExecution", "RunState", "load_run_state", "pending_question"]


class LatestExecution(BaseModel):
    """The single most-recent ``role_executions`` row, flattened to scalars."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    role: str
    worker: str
    status: str
    attempt: int
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    # wip_commit_sha (Phase 5, GIT-01/GIT-02): the recovery commit SHA this
    # attempt wrote via a ``patch``-mode write, or ``None`` -- lets the
    # runner see whether the current attempt already recorded a recovery.
    wip_commit_sha: str | None = None


class RunState(BaseModel):
    """Everything a Phase-1 step needs to resume, reconstructed from columns.

    Frozen and fully detached: built from scalar column values, never by stashing
    ORM instances, so closing the session that produced it cannot turn a later
    attribute read into a lazy-load against a dead connection.

    ``workflow`` is the ``runs.workflow`` JSONB column verbatim. Since Phase 3
    (03-03) it has a dual role: it is both the pipeline shape *and* the full
    effective-config snapshot resolved at run creation. The resume path builds
    the pipeline from this dict (``pipeline_from_snapshot(state.workflow)``) and
    never re-reads ``.dark-factory.yaml`` -- editing that file cannot change an
    in-flight run.

    ``base_branch`` / ``working_branch`` (Phase 5, GIT-01) are the persisted
    git identifiers ``create_run`` wrote before any git command ran; the
    orchestrator reads them back from these columns and never re-derives them
    at use time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    status: RunStatus
    current_role: str | None
    current_step: int | None
    normalized_task: NormalizedTask
    workflow: dict[str, Any]
    qa_developer_iterations: int
    quality_gate_iterations: int
    latest_execution: LatestExecution | None
    pending_answer: str | None
    base_branch: str | None
    working_branch: str | None


def load_run_state(session: Session, run_id: UUID) -> RunState | None:
    """Reconstruct the full run state from ``runs`` + the latest ``role_executions``
    row. Returns ``None`` for an unknown run id and never fabricates a state.

    Two selects, both bound-parameterised: the ``runs`` row, then the single
    most-recent ``role_executions`` row for this run. ``run_events`` is never
    queried (STATE-06). ``.dark-factory.yaml`` / ``.dark-factory/`` files are
    never read here: the returned ``RunState.workflow`` is the persisted
    effective-config snapshot and is the only configuration input on resume.

    "Most recent" is ``ORDER BY created_at DESC, attempt DESC, id DESC``, not
    ``attempt DESC`` alone: ``attempt`` restarts at 1 for every role, so once a
    pipeline has more than one role, BA/Architect/Developer all tie at
    ``attempt = 1`` and ``LIMIT 1`` would return an arbitrary row. ``created_at``
    is the database clock at insert time (each role starts in its own
    transaction, so values do not tie in practice); ``attempt`` then ``id`` are
    deterministic tiebreakers so the result is stable even if two rows ever
    share a timestamp.
    """
    run = session.get(Run, run_id)
    if run is None:
        return None

    latest_row = session.scalar(
        select(RoleExecution)
        .where(RoleExecution.run_id == run_id)
        .order_by(
            RoleExecution.created_at.desc(),
            RoleExecution.attempt.desc(),
            RoleExecution.id.desc(),
        )
        .limit(1)
    )
    latest = (
        LatestExecution(
            id=latest_row.id,
            role=latest_row.role,
            worker=latest_row.worker,
            status=latest_row.status,
            attempt=latest_row.attempt,
            worker_session_id=latest_row.worker_session_id,
            result=latest_row.result,
            wip_commit_sha=latest_row.wip_commit_sha,
        )
        if latest_row is not None
        else None
    )

    pending_answer: str | None = None
    if latest_row is not None:
        pending_answer = session.scalar(
            select(HumanInteraction.answer)
            .where(
                HumanInteraction.run_id == run_id,
                HumanInteraction.role_execution_id == latest_row.id,
                HumanInteraction.status == InteractionStatus.ANSWERED,
            )
            .order_by(HumanInteraction.answered_at.desc())
            .limit(1)
        )

    return RunState(
        run_id=run.id,
        status=run.status,
        current_role=run.current_role,
        current_step=run.current_step,
        normalized_task=NormalizedTask.model_validate(run.normalized_task),
        workflow=dict(run.workflow),
        qa_developer_iterations=run.qa_developer_iterations,
        quality_gate_iterations=run.quality_gate_iterations,
        latest_execution=latest,
        pending_answer=pending_answer,
        base_branch=run.base_branch,
        working_branch=run.working_branch,
    )


def pending_question(session: Session, run_id: UUID) -> str | None:
    """The question text of this run's single ``WAITING`` interaction, or ``None``.

    Used by ``orchestrator/answers.submit_answer`` as a precondition check. The
    partial unique index ``uq_one_waiting_interaction_per_run`` guarantees at
    most one candidate row.
    """
    return session.scalar(
        select(HumanInteraction.question).where(
            HumanInteraction.run_id == run_id,
            HumanInteraction.status == InteractionStatus.WAITING,
        )
    )
