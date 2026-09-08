"""The normalized worker-output contract (WORK-08).

Task 1 of Plan 01-02 needs :class:`WorkerResultStatus` for ``signal_from_result``;
:class:`ArtifactRef`, :class:`WorkerCapabilities` and :class:`WorkerResult` are
added in Task 2.
"""

from enum import StrEnum

__all__ = ["WorkerResultStatus"]


class WorkerResultStatus(StrEnum):
    """The three outcomes any coding worker can report. Value equals name."""

    COMPLETED = "COMPLETED"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"
