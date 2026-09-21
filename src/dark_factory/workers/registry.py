"""``WorkerRegistry`` -- a name-to-factory map (WORK-03).

The orchestrator calls ``registry.get(role.worker)`` and then reads only
:class:`WorkerResult` / :class:`WorkerCapabilities` fields. A worker's name never
appears in a conditional outside this package.

``get()`` returns whatever the registered factory returns: a factory bound to a
class hands back a fresh instance every call, a factory bound to a single object
hands back that same object every call. The choice is the registrant's, not the
registry's -- the registry stays a plain name-to-callable map.

``default_registry`` maps four names: ``"fake"`` (the real, working test worker),
``"claude-code"`` (Plan 07-01: a real adapter that spawns the ``claude`` CLI),
``"copilot"`` (Plan 08-01: a real adapter that spawns the ``copilot`` CLI), and
``"hermes"``, which still resolves to a placeholder so config validation at run
creation can accept a role that names it -- every :class:`CodingWorker` entry
point on its placeholder raises ``NotImplementedError`` until its real adapter
lands later in Phase 8 (08-02). Config validation must therefore test
membership with ``name in registry`` (see :meth:`WorkerRegistry.__contains__`),
never ``registry.get(name)`` -- ``get`` invokes the factory.

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
from typing import NoReturn

from dark_factory.domain.worker import WorkerCapabilities, WorkerResult
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.claude_code import ClaudeCodeWorker
from dark_factory.workers.copilot import CopilotWorker
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

    def __contains__(self, name: object) -> bool:
        """Membership without construction. Config validation uses this and never
        :meth:`get`, because ``get`` invokes the factory -- a placeholder factory
        would raise ``NotImplementedError`` during validation."""
        return name in self._factories


class _NotYetImplementedWorker(CodingWorker):
    """A registered-but-inert worker: its name resolves so run-creation config
    validation passes, but every :class:`CodingWorker` entry point raises
    ``NotImplementedError`` naming the phase its real adapter lands in."""

    def __init__(self, name: str, phase: str) -> None:
        self._name = name
        self._phase = phase

    def _fail(self) -> NoReturn:
        raise NotImplementedError(
            f"{self._name} worker adapter lands in Phase {self._phase}"
        )

    def execute(self, context: object) -> WorkerResult:
        self._fail()

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        self._fail()

    def capabilities(self) -> WorkerCapabilities:
        self._fail()


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

# Plan 07-01: the real adapter, the class itself as the factory -- a fresh
# instance per get(), with no shared-singleton treatment because the adapter
# carries no cursor state (contrast the "fake" registration above).
default_registry.register("claude-code", ClaudeCodeWorker)

# Plan 08-01: the second real adapter, the class itself as the factory --
# mirrors the claude-code registration exactly.
default_registry.register("copilot", CopilotWorker)

# The one remaining real agent-runtime name. Registered so a role that names
# it passes run-creation config validation; the placeholder raises
# NotImplementedError on every entry point until its adapter lands (08-02).
default_registry.register("hermes", lambda: _NotYetImplementedWorker("hermes", "8"))
