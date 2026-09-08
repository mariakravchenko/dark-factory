"""The pure transition function -- the only code that computes a next status.

``transition`` takes no ``Session``, performs no I/O, and reads nothing from a
worker result beyond the already-mapped :class:`~dark_factory.domain.signal.Signal`
(ORCH-01, ORCH-05). It reads three fields off the run state -- ``status``,
``current_role``, ``current_step`` -- which is why it is typed against a small
structural :class:`_RunStateView` rather than importing the persistence layer:
a pure function must not be able to reach the database even by accident.

The legal graph is tiny and enumerated on purpose -- it is reviewable and
unit-testable with no database and no mocks::

    CREATED --ENTER-------------> <first role>         (current_role = that role)
    <role>  --ROLE_COMPLETED----> <next role>          (or COMPLETED when last)
    <role>  --ROLE_FAILED-------> FAILED               (current_role retained)

Any (status, signal) pair not in the graph raises :class:`IllegalTransitionError`
rather than defaulting to some status.
"""

from __future__ import annotations

from typing import Protocol

from dark_factory.domain.signal import Signal
from dark_factory.domain.status import TERMINAL_STATUSES, RunStatus
from dark_factory.workflows.pipeline import Pipeline, current_node, next_node

__all__ = ["IllegalTransitionError", "transition"]


class IllegalTransitionError(RuntimeError):
    """Raised for a (status, signal) pair that is not in the legal graph."""


class _RunStateView(Protocol):
    """The read-only slice of run state the transition function needs.

    :class:`~dark_factory.persistence.repositories.RunState` satisfies this
    structurally; the Protocol keeps ``lifecycle`` free of any persistence
    import.
    """

    @property
    def status(self) -> RunStatus: ...

    @property
    def current_role(self) -> str | None: ...

    @property
    def current_step(self) -> int | None: ...


def transition(
    state: _RunStateView,
    signal: Signal,
    pipeline: Pipeline,
) -> tuple[RunStatus, str | None, int | None]:
    """Return ``(next_status, next_current_role, next_current_step)``.

    Pure: depends only on its three arguments. ``next_current_step`` is the
    ordinal of ``next_current_role`` in ``pipeline`` (unchanged on failure and
    when a run reaches ``COMPLETED`` on the last role).
    """
    status = state.status

    if status in TERMINAL_STATUSES:
        raise IllegalTransitionError(
            f"{status.value} is terminal; no transition for {signal.value}"
        )

    if status is RunStatus.CREATED:
        if signal is Signal.ENTER:
            first = pipeline.nodes[0]
            return RunStatus(first.name), first.name, 0
        raise IllegalTransitionError(f"no transition from CREATED on {signal.value}")

    # ``status`` is a role status: it must name a node in the pipeline.
    role = state.current_role
    try:
        current_node(pipeline, role)
    except LookupError as exc:
        raise IllegalTransitionError(
            f"{status.value} is not a role in the current pipeline"
        ) from exc
    assert role is not None  # current_node would have raised otherwise

    if signal is Signal.ROLE_COMPLETED:
        following = next_node(pipeline, role)
        if following is None:
            return RunStatus.COMPLETED, role, state.current_step
        return (
            RunStatus(following.name),
            following.name,
            pipeline.index_of(following.name),
        )

    if signal is Signal.ROLE_FAILED:
        return RunStatus.FAILED, role, state.current_step

    raise IllegalTransitionError(f"no transition from {status.value} on {signal.value}")
