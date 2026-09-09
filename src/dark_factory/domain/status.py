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

STOP_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_HUMAN}
)
"""States at which the drive loop stops calling ``advance(run_id)``.

A superset of :data:`TERMINAL_STATUSES`: it also contains ``WAITING_HUMAN``. The
two sets are deliberately distinct and must stay that way. A run in
``WAITING_HUMAN`` still has work left -- it is waiting on an answer, not
finished -- so the drive loop must halt on it (stop) while ``advance`` must
remain willing to act on it once an answer exists. ``TERMINAL_STATUSES`` is the
narrower "never advances again" set (delivery succeeded or failed); nothing may
resume a run from there (D-06).
"""
