"""The resume-first orchestrator entry points: ``start_run``, ``advance``, ``drive``.

``advance(run_id)`` is the single orchestrator entry point and it is *always*
resume-first (D-02). Every call, without exception:

* opens a fresh session and calls ``load_run_state`` -- the whole run is
  reconstructed from Neon columns, never from a value held between calls;
* returns immediately, writing nothing, when the run is already terminal;
* determines the current node from the pipeline plus ``current_role``;
* executes exactly **one** committed step through ``apply_transition``;
* returns the new status.

Nothing is carried between ``advance`` calls -- no run object, no task, no
worker instance, no attempt counter. If a step needs a value it is a column read
fresh by ``load_run_state``. That is what makes the happy path and the resume
path the same code: the drive loop below exercises resume on every iteration.

The one-role happy path is therefore **two** committed ``advance`` calls --
``CREATED -> BA`` commits the role start, ``BA -> COMPLETED`` commits the worker
result -- so there is a real committed intermediate state at ``BA`` for a later
plan to kill at.

``DARK_FACTORY_CRASH_AFTER`` is a **test-only** environment variable, honoured by
:func:`_maybe_crash_after` in exactly one place, that abruptly ends the process
immediately after a named transition commits. It is inert on every ordinary run
and has no production role -- it exists so the SC2 fresh-process resume proof can
kill a process at a precisely chosen, already-committed point.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from structlog.contextvars import bind_contextvars, unbind_contextvars

from dark_factory.domain.signal import Signal, signal_from_result
from dark_factory.domain.status import STOP_STATUSES, TERMINAL_STATUSES, RunStatus
from dark_factory.events.catalog import EventType
from dark_factory.input.loaders import load
from dark_factory.input.resolver import classify
from dark_factory.orchestrator.lifecycle import IllegalTransitionError, transition
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.mutations import (
    EventWrite,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)
from dark_factory.persistence.repositories import RunState, load_run_state
from dark_factory.workers.registry import WorkerRegistry, default_registry
from dark_factory.workflows.pipeline import (
    DEFAULT_PIPELINE,
    Pipeline,
    RoleNode,
    current_node,
)

__all__ = [
    "DriveLoopExhausted",
    "RunNotFoundError",
    "advance",
    "drive",
    "run_state",
    "start_run",
]

# A generous bound so a transition-graph bug becomes a loud error rather than a
# process that spins forever writing events.
_MAX_DRIVE_ITERATIONS = 1000

# ``role_executions.status`` values. "RUNNING" is the in-flight marker written
# when a role starts; the worker outcome overwrites it in the same attempt row.
_ROLE_RUNNING = "RUNNING"
_ROLE_COMPLETED = "COMPLETED"
_ROLE_FAILED = "FAILED"

# Test seam only -- consumed by ``_maybe_crash_after`` and nowhere else. Never set
# on an ordinary run; see that function's docstring.
_CRASH_AFTER_ENV = "DARK_FACTORY_CRASH_AFTER"
_CRASH_EXIT_STATUS = 137

SessionFactory = Callable[[], Session]
TransitionCallback = Callable[[RunStatus, RunStatus], None]


class RunNotFoundError(LookupError):
    """Raised when ``advance`` / ``drive`` is given a run id with no ``runs`` row."""


class DriveLoopExhausted(RuntimeError):
    """Raised when the drive loop exceeds :data:`_MAX_DRIVE_ITERATIONS` -- a
    transition-graph bug, surfaced loudly instead of spinning."""


def _workflow_snapshot(pipeline: Pipeline) -> dict[str, Any]:
    """The pipeline shape persisted to ``runs.workflow`` at creation time."""
    return {"roles": [node.name for node in pipeline.nodes]}


def _build_context(run_id: UUID, state: RunState, node: RoleNode) -> dict[str, Any]:
    """The role context handed to ``worker.execute``.

    Built fresh from ``RunState`` on every call -- never carried between
    ``advance`` invocations. Phase 1's ``FakeWorker`` does not read it; the shape
    is here so a real adapter has something to consume.
    """
    attempt = state.latest_execution.attempt if state.latest_execution else 1
    return {
        "run_id": str(run_id),
        "role": node.name,
        "worker": node.worker,
        "attempt": attempt,
        "task": state.normalized_task.model_dump(mode="json"),
    }


def _maybe_crash_after(previous: RunStatus, new: RunStatus) -> None:
    """Abruptly terminate the process after a just-committed transition -- a test
    seam with **no production role**.

    When ``DARK_FACTORY_CRASH_AFTER`` is set to the name of the transition that
    just committed -- ``"<PREVIOUS>_<NEXT>"`` in status values, e.g.
    ``"CREATED_BA"``, ``"BA_COMPLETED"`` or ``"BA_FAILED"`` -- this calls
    :func:`os._exit`, which ends the interpreter immediately: no exception is
    raised, so no ``finally`` block, context manager or handler runs, and no
    rollback or further write can happen. That is what makes it a faithful
    stand-in for a power loss the instant after the commit returned.

    The variable is read from the environment on every call, never cached at
    import, so the hook is inert on every ordinary run -- the function returns at
    once when the variable is unset or names a different transition -- and a test
    can arm it for a single subprocess.
    """
    target = os.environ.get(_CRASH_AFTER_ENV)
    if target and target == f"{previous.value}_{new.value}":
        os._exit(_CRASH_EXIT_STATUS)


def start_run(
    source: str,
    *,
    session_factory: SessionFactory = new_session,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> UUID:
    """Classify, load and create -- return the new run id.

    Raises ``UnresolvableSourceError`` / ``SourceNotSupportedError`` *before*
    anything is persisted; the CLI turns either into exit 2. Once this returns,
    a ``runs`` row exists and the outcome is 0 or 1.
    """
    kind, locator = classify(source)
    task = load(kind, locator)
    session = session_factory()
    try:
        return create_run(session, task=task, workflow=_workflow_snapshot(pipeline))
    finally:
        session.close()


def run_state(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> RunState | None:
    """Reconstruct a run's state, or ``None`` if the id is unknown.

    Used by the CLI to check a ``resume`` target exists and to render the final
    summary block. It is a read, not lifecycle logic.
    """
    session = session_factory()
    try:
        return load_run_state(session, run_id)
    finally:
        session.close()


def advance(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> RunStatus:
    """Reconstruct from Neon, execute exactly one committed step, return the new status."""
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
    finally:
        read_session.close()

    if state is None:
        raise RunNotFoundError(run_id)
    if state.status in TERMINAL_STATUSES:
        return state.status

    attempt = state.latest_execution.attempt if state.latest_execution else None
    bind_contextvars(run_id=str(run_id), role=state.current_role, attempt=attempt)
    try:
        if state.status is RunStatus.CREATED:
            return _enter_first_role(run_id, state, pipeline, session_factory)
        return _run_current_role(run_id, state, pipeline, registry, session_factory)
    finally:
        unbind_contextvars("run_id", "role", "attempt")


def _enter_first_role(
    run_id: UUID,
    state: RunState,
    pipeline: Pipeline,
    session_factory: SessionFactory,
) -> RunStatus:
    """Commit ``CREATED -> <first role>``: insert the attempt row, emit ROLE_STARTED."""
    next_status, next_role, next_step = transition(state, Signal.ENTER, pipeline)
    assert next_role is not None
    node = current_node(pipeline, next_role)
    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=RunStatus.CREATED,
            next_status=next_status,
            next_current_role=next_role,
            next_current_step=next_step,
            role_execution=RoleExecutionWrite(
                mode="insert",
                role=node.name,
                worker=node.worker,
                status=_ROLE_RUNNING,
            ),
            events=[
                EventWrite(
                    type=EventType.ROLE_STARTED,
                    payload={"role": node.name, "worker": node.worker},
                )
            ],
        )
        _maybe_crash_after(RunStatus.CREATED, new_status)
        return new_status
    finally:
        session.close()


def _run_current_role(
    run_id: UUID,
    state: RunState,
    pipeline: Pipeline,
    registry: WorkerRegistry,
    session_factory: SessionFactory,
) -> RunStatus:
    """Run the current role's worker outside any transaction, then commit the outcome."""
    node = current_node(pipeline, state.current_role)
    latest = state.latest_execution
    if latest is None:
        raise RuntimeError(
            f"run {run_id} is in {state.status.value} with no role_executions row"
        )

    worker = registry.get(node.worker)
    result = worker.execute(_build_context(run_id, state, node))
    signal = signal_from_result(result)
    next_status, next_role, next_step = transition(state, signal, pipeline)

    outcome = result.model_dump(mode="json")
    if signal is Signal.ROLE_COMPLETED:
        re_status = _ROLE_COMPLETED
        re_result: dict[str, Any] | None = outcome
        re_error: dict[str, Any] | None = None
        events = [
            EventWrite(
                type=EventType.ROLE_COMPLETED,
                payload={"role": node.name, "summary": result.summary},
            ),
        ]
        # RUN_COMPLETED belongs only to the transition that actually reaches the
        # terminal COMPLETED state -- i.e. the last node in the pipeline. For any
        # earlier role, transition() returns the next role status and the run
        # continues, so emitting RUN_COMPLETED here would write a false terminal
        # audit row (the "never assume one role" hazard in workflows/pipeline.py).
        if next_status is RunStatus.COMPLETED:
            events.append(
                EventWrite(type=EventType.RUN_COMPLETED, payload={"role": node.name})
            )
    elif signal is Signal.ROLE_FAILED:
        re_status = _ROLE_FAILED
        re_result = None
        re_error = outcome
        events = [
            EventWrite(
                type=EventType.ROLE_FAILED,
                payload={"role": node.name, "error": result.error or result.summary},
            ),
            EventWrite(type=EventType.RUN_FAILED, payload={"role": node.name}),
        ]
    else:  # pragma: no cover - transition() already rejects any other signal
        raise IllegalTransitionError(f"runner cannot act on {signal.value} in Phase 1")

    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=state.status,
            next_status=next_status,
            next_current_role=next_role,
            next_current_step=next_step,
            role_execution=RoleExecutionWrite(
                mode="update",
                id=latest.id,
                role=latest.role,
                worker=latest.worker,
                status=re_status,
                worker_session_id=result.worker_session_id,
                result=re_result,
                error=re_error,
            ),
            events=events,
        )
        _maybe_crash_after(state.status, new_status)
        return new_status
    finally:
        session.close()


def drive(
    run_id: UUID,
    on_transition: TransitionCallback | None = None,
    *,
    session_factory: SessionFactory = new_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline = DEFAULT_PIPELINE,
) -> RunStatus:
    """Loop ``advance`` until the run reaches a stop status; return that status.

    ``on_transition(previous, new)`` is invoked once per status change. The stop
    condition is the named constant :data:`STOP_STATUSES` -- Phase 2 adds
    ``WAITING_HUMAN`` to that set and nothing else (D-06).
    """
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
    finally:
        read_session.close()
    if state is None:
        raise RunNotFoundError(run_id)

    status = state.status
    for _ in range(_MAX_DRIVE_ITERATIONS):
        if status in STOP_STATUSES:
            return status
        new_status = advance(
            run_id,
            session_factory=session_factory,
            registry=registry,
            pipeline=pipeline,
        )
        if new_status != status and on_transition is not None:
            on_transition(status, new_status)
        status = new_status

    raise DriveLoopExhausted(
        f"drive loop for {run_id} exceeded {_MAX_DRIVE_ITERATIONS} iterations"
    )
