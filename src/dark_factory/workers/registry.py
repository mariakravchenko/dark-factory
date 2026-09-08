"""``WorkerRegistry`` -- a name-to-factory map (WORK-03).

The orchestrator calls ``registry.get(role.worker)`` and then reads only
:class:`WorkerResult` / :class:`WorkerCapabilities` fields. A worker's name never
appears in a conditional outside this package.

``get()`` returns whatever the registered factory returns: a factory bound to a
class hands back a fresh instance every call, a factory bound to a single object
hands back that same object every call. The choice is the registrant's, not the
registry's -- the registry stays a plain name-to-callable map.

**``default_registry``'s ``"fake"`` factory returns one long-lived
:class:`FakeWorker`.** ``_run_current_role`` calls ``registry.get(node.worker)``
inside every ``advance()``; a fresh ``FakeWorker`` per call would reset the
script cursor to 0 every step, so a multi-entry ``DARK_FACTORY_FAKE_SCRIPT``
would replay element 0 forever and never raise ``ScriptExhaustedError``. The
worker instance is not run state -- it is a registry-scoped singleton, and
``advance()``'s "reconstruct everything from columns" invariant is unaffected
(the cursor is test-scaffolding position, never lifecycle state). Tests that
need isolated cursors build their own :class:`WorkerRegistry` with a
per-instance factory (see ``tests/conftest.py::fake_worker_registry``).
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

# One process-lifetime FakeWorker so its script cursor advances across the
# repeated registry.get() calls a drive loop makes (see module docstring). Built
# lazily on first lookup so DARK_FACTORY_FAKE_SCRIPT is read at use time, not at
# import time.
_fake_worker: FakeWorker | None = None


def _shared_fake_worker() -> CodingWorker:
    global _fake_worker
    if _fake_worker is None:
        _fake_worker = FakeWorker()
    return _fake_worker


default_registry.register("fake", _shared_fake_worker)
