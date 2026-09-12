"""The run-status vocabulary (STATE-07) and the drive loop's stop-condition sets.

`RunStatus` is the single closed set of lifecycle states. All ten values are
defined here from Phase 1 even though only ``CREATED``, ``BA``, ``COMPLETED`` and
``FAILED`` are reachable while the pipeline is ``["BA"]`` (D-08). Defining the
whole set once avoids an ``ALTER TYPE``/``CHECK``-constraint migration hazard in
every later phase (RESEARCH Pitfall 6).

``VerdictStatus`` and ``IssueSeverity`` (Phase 4, D-04) live here rather than in
``domain/artifacts.py`` because they are small closed vocabularies in the same
"value equals name" ``StrEnum`` register as ``RunStatus`` -- not because they
describe run lifecycle. ``VerdictStatus`` is QA's declared-and-computed PASS/FAIL
outcome for ``verdict.json`` and doubles as the per-case result in
``test_report.json``; ``IssueSeverity`` is the severity of one ``verdict.json``
issue entry.
"""

from enum import StrEnum

__all__ = [
    "STOP_STATUSES",
    "TERMINAL_STATUSES",
    "IssueSeverity",
    "RunStatus",
    "VerdictStatus",
]


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


class VerdictStatus(StrEnum):
    """QA's overall PASS/FAIL outcome (D-04). Each member's value equals its name.

    Doubles as the per-case ``result`` in ``test_report.json``
    (:class:`~dark_factory.domain.artifacts.TestCaseResult`) and the per-criterion
    ``result`` in ``verdict.json``
    (:class:`~dark_factory.domain.artifacts.VerdictCriterionResult`) -- one closed
    vocabulary for "did this pass or fail", never a second parallel enum.
    """

    PASS = "PASS"
    FAIL = "FAIL"


class IssueSeverity(StrEnum):
    """The severity of one ``verdict.json`` issue entry (D-04). Value equals name.

    ``blocking`` makes the overall verdict FAIL regardless of criteria outcomes;
    ``minor`` does not. Deliberately lowercase, matching D-04's two severities
    verbatim rather than the uppercase convention :class:`RunStatus` /
    :class:`VerdictStatus` use -- this is QA-authored free-form severity, not a
    ``RunStatus``-adjacent lifecycle value.
    """

    blocking = "blocking"
    minor = "minor"
