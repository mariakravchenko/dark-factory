"""The typed control signal and the pure mapping from a worker result to it.

``signal_from_result`` inspects *only* ``result.status``. A worker's prose,
questions or metadata can never influence a lifecycle transition (ORCH-05):
the orchestrator maps the result to a :class:`Signal` and the pure
``lifecycle.transition()`` takes it from there.

``Signal.ROLE_BOUNCED`` is the one exception to "every signal comes from
``signal_from_result``": it is computed by the orchestrator in
``runner.py`` by overriding an already-computed ``ROLE_COMPLETED`` signal
once a FAIL verdict or a FAIL quality gate is read back, under its own
configured iteration cap -- the same way a write-scope or artifact-scope
violation already overrides a signal post hoc. It is deliberately absent
from ``_RESULT_STATUS_TO_SIGNAL``: a worker's own ``WorkerResultStatus``
never means "bounced", so ``signal_from_result`` never returns it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from dark_factory.domain.worker import WorkerResultStatus

if TYPE_CHECKING:
    from dark_factory.domain.worker import WorkerResult

__all__ = ["Signal", "signal_from_result"]


class Signal(StrEnum):
    """What just happened, as the orchestrator sees it. Value equals name."""

    ENTER = "ENTER"
    ROLE_COMPLETED = "ROLE_COMPLETED"
    ROLE_FAILED = "ROLE_FAILED"
    ROLE_NEEDS_INPUT = "ROLE_NEEDS_INPUT"
    ROLE_BOUNCED = "ROLE_BOUNCED"


_RESULT_STATUS_TO_SIGNAL: dict[WorkerResultStatus, Signal] = {
    WorkerResultStatus.COMPLETED: Signal.ROLE_COMPLETED,
    WorkerResultStatus.FAILED: Signal.ROLE_FAILED,
    WorkerResultStatus.NEEDS_INPUT: Signal.ROLE_NEEDS_INPUT,
}


def signal_from_result(result: WorkerResult) -> Signal:
    """Map a worker result to its control signal, reading only ``result.status``."""

    return _RESULT_STATUS_TO_SIGNAL[result.status]
