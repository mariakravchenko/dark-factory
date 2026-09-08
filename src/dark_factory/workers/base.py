"""The ``CodingWorker`` port (WORK-01).

Every agent runtime -- and :class:`~dark_factory.workers.fake.FakeWorker` -- implements
exactly these three methods. ``resume`` ships now even though nothing calls it
until Phase 2: WORK-01 names all three methods, and adding one later would change
the contract every adapter implements.
"""

from abc import ABC, abstractmethod

from dark_factory.domain.worker import WorkerCapabilities, WorkerResult

__all__ = ["CodingWorker"]


class CodingWorker(ABC):
    """The one contract all agent runtimes implement."""

    @abstractmethod
    def execute(self, context: object) -> WorkerResult:
        """Perform the role's engineering work; return a normalized result."""

    @abstractmethod
    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Continue a paused role once a human answer is available (Phase 2)."""

    @abstractmethod
    def capabilities(self) -> WorkerCapabilities:
        """Declare what this worker can do, so the core never branches on its name."""
