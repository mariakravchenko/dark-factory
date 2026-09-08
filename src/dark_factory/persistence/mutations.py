"""The one lifecycle mutation path (Plan 01-05 — ORCH-06, STATE-03, SEC-02).

This module is the *entire* write surface for ``runs.status`` / ``runs.current_role``
/ ``runs.current_step`` / the two iteration counters, for every ``role_executions``
row, and for every ``run_events`` row. Nothing else in ``dark_factory`` may write
those — ``tests/unit/test_single_mutation_path.py`` walks the source tree and fails
on any violation.

Two sibling functions, one discipline (RESEARCH Open Question 3): "one mutation
path" means **one module, one transaction discipline, one redaction call** — not
literally one function. ``create_run`` cannot use the ``expected_status`` guard
because there is no row yet, so it is a sibling rather than a call into
``apply_transition``.

* ``create_run`` — inserts the ``CREATED`` row and the ``RUN_CREATED`` event.
* ``apply_transition`` — the guarded, single-transaction lifecycle mutation:
  role-execution row + ``runs`` state columns + counters + audit events, all
  inside one ``with session.begin():`` block that commits exactly once.

Redaction (``dark_factory.events.redaction.redact``) is applied *inside* this
module immediately before each ``session.add`` / attribute assignment, at the
single call site, so no caller can persist an unredacted JSONB payload. The
call-shape models ``RoleExecutionWrite`` and ``EventWrite`` deliberately carry
**raw** payloads — scrubbing is this module's responsibility, never the caller's.

No explicit commit call is ever made anywhere here: the
``with session.begin():`` context manager *is* the atomicity guarantee — one
BEGIN, one COMMIT, full ROLLBACK on any exception.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dark_factory.config.settings import get_settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.events.redaction import redact, scrub_known_values
from dark_factory.persistence.models import RoleExecution, Run, RunEvent

__all__ = [
    "ConcurrentTransition",
    "EventWrite",
    "RoleExecutionWrite",
    "apply_transition",
    "create_run",
]

# The only ``runs`` columns ``apply_transition`` will increment via
# ``counter_increments`` (D-19). Anything else is a caller error.
_INCREMENTABLE_COUNTERS = frozenset(
    {"qa_developer_iterations", "quality_gate_iterations"}
)


class ConcurrentTransition(RuntimeError):
    """Raised when ``apply_transition``'s ``expected_status`` guard fails: the row's
    current status is not what the caller expected, so another process advanced
    the run first. Nothing is written."""


class RoleExecutionWrite(BaseModel):
    """Insert-or-update spec for a ``role_executions`` row. ``result`` / ``error``
    are **raw** — redaction happens inside ``apply_transition``. ``attempt`` is
    never supplied by the caller; it is computed in SQL inside the transaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["insert", "update"]
    role: str
    worker: str
    status: str
    id: UUID | None = None  # required for mode="update"
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class EventWrite(BaseModel):
    """One ``run_events`` row to append in the same transaction as the state change
    it describes. ``payload`` is **raw** — redacted inside ``apply_transition``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: EventType
    role_execution_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _known_secrets() -> Mapping[str, str]:
    """The live ``{secret value: label}`` map from the single settings choke point."""
    return get_settings().known_secret_values()


def create_run(
    session: Session,
    *,
    task: NormalizedTask,
    workflow: dict[str, Any],
) -> UUID:
    """Insert the ``CREATED`` run row and its ``RUN_CREATED`` event; return the id.

    One ``with session.begin():`` block, one commit. ``normalized_task`` is scrubbed
    for **exact known secret values only** (D-18 — a task legitimately discussing
    connection-string syntax persists as written); the ``workflow`` snapshot and
    the ``RUN_CREATED`` payload get full pattern redaction like every other JSONB
    write in this module — no JSONB value reaches Neon without passing ``redact()``.
    """
    known = _known_secrets()
    run_id = uuid4()

    with session.begin():
        session.add(
            Run(
                id=run_id,
                source_kind=task.source_kind,
                source_ref=scrub_known_values(task.source_ref, known_secrets=known),
                normalized_task=scrub_known_values(
                    task.model_dump(mode="json"), known_secrets=known
                ),
                workflow=redact(workflow, known_secrets=known),
                status=RunStatus.CREATED,
                current_role=None,
                current_step=None,
            )
        )
        session.add(
            RunEvent(
                run_id=run_id,
                role_execution_id=None,
                type=EventType.RUN_CREATED.value,
                payload=redact(
                    {
                        "source_kind": task.source_kind,
                        "source_ref": task.source_ref,
                        "title": task.title,
                    },
                    known_secrets=known,
                ),
            )
        )

    return run_id


def apply_transition(
    session: Session,
    *,
    run_id: UUID,
    expected_status: RunStatus,
    next_status: RunStatus,
    next_current_role: str | None,
    next_current_step: int | None,
    role_execution: RoleExecutionWrite | None = None,
    events: Sequence[EventWrite] = (),
    counter_increments: Mapping[str, int] | None = None,
) -> RunStatus:
    """Apply one lifecycle transition atomically and return the new status.

    Order inside the single ``with session.begin():`` block:

    1. lock the ``runs`` row (``with_for_update``); ``LookupError`` if absent
    2. ``ConcurrentTransition`` if its status is not ``expected_status`` — no writes
    3. insert or update the ``role_executions`` row; for an insert, ``attempt`` is
       ``MAX(attempt) + 1`` for this run + role computed **in SQL, in this
       transaction** (D-19, RESEARCH Pitfall 2), never from an in-memory counter
    4. assign ``status`` / ``current_role`` / ``current_step`` / ``updated_at``
    5. apply each ``counter_increments`` entry to its column
    6. append one ``RunEvent`` per ``EventWrite``

    ``result`` / ``error`` / every event ``payload`` pass through ``redact()``
    immediately before assignment — the single scrubbing call site.

    A status change (``next_status != expected_status``) with an empty ``events``
    sequence is rejected outright (``ValueError``) before the transaction opens: a
    state change with no audit row is exactly the corruption ORCH-06 prevents.
    """
    events = tuple(events)
    increments = dict(counter_increments or {})

    if next_status != expected_status and not events:
        raise ValueError(
            "apply_transition refuses a status change with no audit event: "
            f"{expected_status.value} -> {next_status.value} with events=[]"
        )
    for name in increments:
        if name not in _INCREMENTABLE_COUNTERS:
            raise ValueError(f"unknown counter column: {name!r}")

    known = _known_secrets()

    with session.begin():
        run = session.get(Run, run_id, with_for_update=True)
        if run is None:
            raise LookupError(run_id)
        if run.status != expected_status:
            raise ConcurrentTransition(
                f"expected {expected_status.value}, found {run.status.value}"
            )

        if role_execution is not None:
            _write_role_execution(session, run_id, role_execution, known)

        run.status = next_status
        run.current_role = next_current_role
        run.current_step = next_current_step
        run.updated_at = func.now()

        for name, delta in increments.items():
            setattr(run, name, getattr(run, name) + delta)

        for event in events:
            session.add(
                RunEvent(
                    run_id=run_id,
                    role_execution_id=event.role_execution_id,
                    type=event.type.value,
                    payload=redact(event.payload, known_secrets=known),
                )
            )

    return next_status


def _write_role_execution(
    session: Session,
    run_id: UUID,
    spec: RoleExecutionWrite,
    known: Mapping[str, str],
) -> None:
    """Insert or update the ``role_executions`` row for this transition. Redaction
    of ``result`` / ``error`` happens here, at the single call site."""
    result = (
        redact(spec.result, known_secrets=known) if spec.result is not None else None
    )
    error = redact(spec.error, known_secrets=known) if spec.error is not None else None

    if spec.mode == "insert":
        next_attempt = session.scalar(
            select(func.coalesce(func.max(RoleExecution.attempt), 0) + 1).where(
                RoleExecution.run_id == run_id,
                RoleExecution.role == spec.role,
            )
        )
        assert next_attempt is not None  # coalesce(..., 0) + 1 always returns a row
        session.add(
            RoleExecution(
                run_id=run_id,
                role=spec.role,
                worker=spec.worker,
                status=spec.status,
                attempt=next_attempt,
                worker_session_id=spec.worker_session_id,
                result=result,
                error=error,
            )
        )
        return

    if spec.id is None:
        raise ValueError("RoleExecutionWrite(mode='update') requires id")
    row = session.get(RoleExecution, spec.id, with_for_update=True)
    if row is None:
        raise LookupError(spec.id)
    row.status = spec.status
    row.worker_session_id = spec.worker_session_id
    row.result = result
    row.error = error
    row.updated_at = func.now()
