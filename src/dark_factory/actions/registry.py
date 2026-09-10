"""``ActionRegistry`` -- a name-to-callable allowlist for before/after hooks (CFG-04).

A verbatim clone of :class:`~dark_factory.workers.registry.WorkerRegistry`: the
config loader resolves a hook name configured in ``.dark-factory/roles/*.yaml`` to
a Python callable through this map, and a name that is not registered is rejected
at run creation rather than becoming an arbitrary ``getattr`` / ``importlib``
import surface. ``__contains__`` is the membership check config validation uses --
it never goes through :meth:`get`.

A new action is added by calling ``default_registry.register("name", fn)`` at
import time -- zero change to the orchestrator, the pipeline, or the pure
lifecycle function (the Compatibility constraint).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dark_factory.actions.context import ActionContext

__all__ = ["ActionRegistry", "UnknownActionError", "default_registry"]


class UnknownActionError(KeyError):
    """Raised by :meth:`ActionRegistry.get` for a name with no registered callable."""


class ActionRegistry:
    """A plain ``dict`` lookup from an action name to its ``(ActionContext) -> None`` callable."""

    def __init__(self) -> None:
        self._actions: dict[str, Callable[[ActionContext], None]] = {}

    def register(self, name: str, fn: Callable[[ActionContext], None]) -> None:
        self._actions[name] = fn

    def get(self, name: str) -> Callable[[ActionContext], None]:
        try:
            return self._actions[name]
        except KeyError:
            raise UnknownActionError(name) from None

    def __contains__(self, name: object) -> bool:
        return name in self._actions


default_registry = ActionRegistry()
