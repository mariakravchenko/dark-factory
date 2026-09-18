"""The single place a role's capability grant is checked (TOOL-01, TOOL-03, D-01).

Nothing in this package opens a ``Session`` or constructs a lifecycle ORM row
(WR-01) -- ``tests/unit/test_single_mutation_path.py`` rglobs ``src/`` and
covers this package. ``ToolRegistry.invoke()`` (in :mod:`dark_factory.tools.registry`)
is the **one** enforcement point every caller funnels through (D-01, D-12):
orchestrator-owned call sites this phase, and an optional additional
transport a later plan adds as a sibling module that nothing on the core
import closure reaches. This package must never import that transport, nor
any third-party tool-transport package, under any circumstance -- doing so
would put a third-party dependency on the orchestrator's import graph.

Error hierarchy, in the ``ConfigError`` / ``UnknownWorkerError`` register:

* :class:`ToolError` -- the base class for every failure this package raises.
* :class:`CapabilityDeniedError` -- raised by
  :meth:`~dark_factory.tools.registry.ToolRegistry.invoke` when a role
  invokes a capability its grant list does not contain. Carries ``role``,
  ``capability`` and ``granted`` as instance attributes so a caller like
  ``orchestrator/runner.py`` reads the denied capability name directly
  rather than parsing the message (threat T-06-04).
* :class:`UnknownCapabilityError` -- raised by
  :meth:`~dark_factory.tools.registry.ToolRegistry.invoke` when a *granted*
  capability name has no registered implementation. A configuration bug,
  never an authorization decision -- matching the
  :class:`~dark_factory.workers.registry.UnknownWorkerError` /
  :class:`~dark_factory.actions.registry.UnknownActionError` precedent for a
  lookup miss.

Declaring the whole hierarchy in one place, before importing the submodule
that raises it, keeps this package's error surface legible from the start
and avoids a circular-import ordering problem: :mod:`dark_factory.tools.registry`
itself does ``from dark_factory.tools import CapabilityDeniedError,
UnknownCapabilityError``, which only works because those names already
exist in this module's namespace by the time that submodule import runs.
"""

from __future__ import annotations

__all__ = [
    "CapabilityDeniedError",
    "ToolError",
    "ToolRegistry",
    "UnknownCapabilityError",
    "default_registry",
]


class ToolError(RuntimeError):
    """Base class for every ``dark_factory.tools`` failure."""


class CapabilityDeniedError(ToolError):
    """Raised by :meth:`~dark_factory.tools.registry.ToolRegistry.invoke` when
    a role invokes a capability its grant list does not contain.

    Carries ``role``, ``capability`` and ``granted`` as instance attributes
    -- the runner reads ``capability`` directly rather than parsing this
    exception's message (threat T-06-04). The message never interpolates
    anything beyond the role name, the capability name and the sorted grant
    list -- never a capability call's keyword arguments, which may carry
    worker- or repo-supplied content and can reach an event payload.
    """

    def __init__(self, role: str, capability: str, granted: list[str]) -> None:
        self.role = role
        self.capability = capability
        self.granted = granted
        super().__init__(
            f"role {role!r} invoked {capability!r} without a grant "
            f"(granted: {sorted(granted)})"
        )


class UnknownCapabilityError(ToolError, KeyError):
    """Raised by :meth:`~dark_factory.tools.registry.ToolRegistry.invoke` for a
    *granted* capability name with no registered implementation -- a
    configuration bug, never an authorization decision, matching
    :class:`~dark_factory.workers.registry.UnknownWorkerError` /
    :class:`~dark_factory.actions.registry.UnknownActionError`."""


# Import the submodule after the error hierarchy is declared, so its own
# ``from dark_factory.tools import <ErrorClass>`` succeeds against this
# module's already-populated namespace (see the module docstring).
from dark_factory.tools.registry import ToolRegistry, default_registry
