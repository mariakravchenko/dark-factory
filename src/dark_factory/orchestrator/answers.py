"""``submit_answer`` — the one guarded transition out of ``WAITING_HUMAN`` (HITL-03).

A *second caller* of the one mutation path, never a second mutation path: it
performs exactly one ``apply_transition`` and constructs no ORM row itself. The
whole decision is driven by persisted columns, so a process that crashes between
storing the answer and dispatching the role still resumes correctly on the next
attempt.

**Why the lease is taken and released around just this transition** rather than
held into the following drive: both the answer transition and the following step
are independently guarded by their expected status, so a process that claims in
between simply advances the run — correct behaviour, not duplicated work. A
second process racing an answer loses at the lease and gets the same clean
``LeaseNotAcquired``.

The run status / pending-question preconditions are checked *before* the lease
is claimed. A terminal or otherwise non-waiting run has no pause to answer, and
claiming a lease on a terminal run would raise ``LeaseNotAcquired`` where the
caller expects ``NotWaitingForHuman``.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.events.catalog import EventType
from dark_factory.orchestrator.lease import run_lease
from dark_factory.orchestrator.runner import RunNotFoundError
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.mutations import (
    EventWrite,
    HumanInteractionWrite,
    RoleExecutionWrite,
    apply_transition,
)
from dark_factory.persistence.repositories import load_run_state, pending_question

__all__ = ["NoPendingInteraction", "NotWaitingForHuman", "submit_answer"]

# ``role_executions.status`` marker written to the paused attempt row once an
# answer is submitted; ``_run_current_role`` branches on it to call
# ``worker.resume`` instead of ``worker.execute``. Kept in sync with
# ``orchestrator.runner._ROLE_RESUMING`` by value, not by import (the runner
# imports this module's siblings, not the reverse would-be cycle).
_ROLE_RESUMING = "RESUMING"

_log = structlog.get_logger(__name__)

SessionFactory = Callable[[], Session]


class NotWaitingForHuman(RuntimeError):
    """The run is not in ``WAITING_HUMAN``, so there is no pause to answer. The
    answer is accept-once: after the first answer the run has left
    ``WAITING_HUMAN`` and a second ``submit_answer`` raises this."""


class NoPendingInteraction(RuntimeError):
    """The run is in ``WAITING_HUMAN`` but has no ``WAITING`` interaction row."""


def submit_answer(
    run_id: UUID,
    answer: str,
    *,
    session_factory: SessionFactory = new_session,
    github_comment_id: int | None = None,
) -> RunStatus:
    """Record ``answer`` against the run's open question and move it from
    ``WAITING_HUMAN`` back to its retained current role, all in one
    ``apply_transition``. Returns the new status (the role status).

    ``github_comment_id`` (Phase 10, plan 10-04, D-05) is the id of the
    GitHub comment that answered the question, threaded straight into the
    ``HumanInteractionWrite`` this function already builds -- a durable,
    business-level dedup key (Phase 10, D-05). Today's only caller (the
    CLI's ``resume --answer``) omits it, leaving it ``None`` and changing
    nothing about the existing precondition checks, lease, re-read or
    ``expected_status`` guard.

    Raises :class:`RunNotFoundError` for an unknown id,
    :class:`NotWaitingForHuman` when the run is not paused,
    :class:`NoPendingInteraction` when there is no waiting question, and
    :class:`~dark_factory.orchestrator.lease.LeaseNotAcquired` when another
    process owns the run. Writes nothing in any of those cases.
    """
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
        question = pending_question(read_session, run_id) if state is not None else None
    finally:
        read_session.close()

    if state is None:
        raise RunNotFoundError(run_id)
    if state.status is not RunStatus.WAITING_HUMAN:
        raise NotWaitingForHuman(
            f"run {run_id} is not waiting for a human (status {state.status.value})"
        )
    if question is None:
        raise NoPendingInteraction(f"run {run_id} has no pending question")

    with run_lease(run_id, session_factory=session_factory) as lease:
        # Re-read inside the lease: a racing process could have answered between
        # the pre-check and the claim. ``apply_transition``'s expected_status
        # guard is the ultimate authority; this just yields a clean error.
        reread_session = session_factory()
        try:
            state = load_run_state(reread_session, run_id)
        finally:
            reread_session.close()
        if state is None or state.status is not RunStatus.WAITING_HUMAN:
            raise NotWaitingForHuman(f"run {run_id} is no longer waiting for a human")

        latest = state.latest_execution
        assert latest is not None  # a WAITING_HUMAN run always has a role attempt
        assert state.current_role is not None

        write_session = session_factory()
        try:
            new_status = apply_transition(
                write_session,
                run_id=run_id,
                expected_status=RunStatus.WAITING_HUMAN,
                next_status=RunStatus(state.current_role),
                next_current_role=state.current_role,
                next_current_step=state.current_step,
                role_execution=RoleExecutionWrite(
                    mode="update",
                    id=latest.id,
                    role=latest.role,
                    worker=latest.worker,
                    status=_ROLE_RESUMING,
                    worker_session_id=latest.worker_session_id,
                    result=latest.result,
                ),
                events=[
                    EventWrite(
                        type=EventType.HUMAN_ANSWER_RECEIVED,
                        payload={"role": state.current_role},
                    ),
                    EventWrite(
                        type=EventType.RUN_RESUMED,
                        payload={"role": state.current_role},
                    ),
                ],
                expected_owner_token=lease.token,
                human_interaction=HumanInteractionWrite(
                    mode="answer",
                    answer=answer,
                    github_comment_id=github_comment_id,
                ),
            )
        finally:
            write_session.close()

    _log.info("run.resumed", run_id=str(run_id), role=state.current_role)
    return new_status
