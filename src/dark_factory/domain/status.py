"""The run-status vocabulary (STATE-07) and the drive loop's stop-condition sets.

`RunStatus` is the single closed set of lifecycle states. All ten values are
defined here from Phase 1 even though only ``CREATED``, ``BA``, ``COMPLETED`` and
``FAILED`` are reachable while the pipeline is ``["BA"]`` (D-08). Defining the
whole set once avoids an ``ALTER TYPE``/``CHECK``-constraint migration hazard in
every later phase (RESEARCH Pitfall 6).
"""

from enum import StrEnum

__all__ = ["STOP_STATUSES", "TERMINAL_STATUSES", "RunStatus"]


class RunStatus(StrEnum):
    """Every lifecycle state a run can occupy. Each member's value equals its name."""

    CREATED = "CREATED"
    BA = "BA"
    ARCHITECTURE = "ARCHITECTURE"
    DEVELOPMENT = "DEVELOPMENT"
    QA = "QA"
    VERIFYING = "VERIFYING"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    WAITING_HUMAN = "WAITING_HUMAN"
    FAILED = "FAILED"


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED}
)
"""The states from which a run never advances again: delivery succeeded or failed."""

STOP_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})
"""States at which the drive loop stops calling ``advance(run_id)``.

Equal to :data:`TERMINAL_STATUSES` in Phase 1, but kept as a separate name on
purpose: Phase 2 adds ``WAITING_HUMAN`` to *this* set (and only this set) so the
loop halts for a human answer without ``WAITING_HUMAN`` ever counting as terminal
(D-06).
"""
