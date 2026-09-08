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
  worker, status, attempt, worker_session_id), or ``None``

If ``advance()`` needs a value it is added here; if it is not here, ``advance()``
may not need it.

**STATE-06 is architectural, not just behavioural.** This module imports nothing
from ``dark_factory``'s event package and issues no query touching the audit
log — control state comes from state columns, never from folding events. A read
path that *can* fold the log will eventually be made to.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.persistence.models import RoleExecution, Run

__all__ = ["LatestExecution", "RunState", "load_run_state"]


class LatestExecution(BaseModel):
    """The single most-recent ``role_executions`` row, flattened to scalars."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    role: str
    worker: str
    status: str
    attempt: int
    worker_session_id: str | None = None


class RunState(BaseModel):
    """Everything a Phase-1 step needs to resume, reconstructed from columns.

    Frozen and fully detached: built from scalar column values, never by stashing
    ORM instances, so closing the session that produced it cannot turn a later
    attribute read into a lazy-load against a dead connection.
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


def load_run_state(session: Session, run_id: UUID) -> RunState | None:
    """Reconstruct the full run state from ``runs`` + the latest ``role_executions``
    row. Returns ``None`` for an unknown run id and never fabricates a state.

    Two selects, both bound-parameterised: the ``runs`` row, then the single
    highest-``attempt`` ``role_executions`` row for this run. ``run_events`` is
    never queried (STATE-06).
    """
    run = session.get(Run, run_id)
    if run is None:
        return None

    latest_row = session.scalar(
        select(RoleExecution)
        .where(RoleExecution.run_id == run_id)
        .order_by(RoleExecution.attempt.desc())
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
        )
        if latest_row is not None
        else None
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
    )
