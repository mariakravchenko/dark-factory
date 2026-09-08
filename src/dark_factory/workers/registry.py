"""``WorkerRegistry`` -- a name-to-factory map (WORK-03).

The orchestrator calls ``registry.get(role.worker)`` and then reads only
:class:`WorkerResult` / :class:`WorkerCapabilities` fields. A worker's name never
appears in a conditional outside this package.
"""

from collections.abc import Callable

from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker

__all__ = ["UnknownWorkerError", "WorkerRegistry", "default_registry"]


class UnknownWorkerError(KeyError):
    """Raised by :meth:`WorkerRegistry.get` for a name with no registered factory."""


class WorkerRegistry:
    """A plain ``dict`` lookup from a worker name to a zero-arg factory."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], CodingWorker]] = {}

    def register(self, name: str, factory: Callable[[], CodingWorker]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> CodingWorker:
        try:
            factory = self._factories[name]
        except KeyError:
            raise UnknownWorkerError(name) from None
        return factory()


default_registry = WorkerRegistry()
default_registry.register("fake", FakeWorker)
