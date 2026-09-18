"""``ToolRegistry`` -- the one enforcement point every capability invocation
funnels through (D-01, TOOL-01, TOOL-03).

Mirrors :class:`~dark_factory.workers.registry.WorkerRegistry` /
:class:`~dark_factory.actions.registry.ActionRegistry` for the base map: a
plain ``dict`` from a capability name to its implementation callable.
:meth:`ToolRegistry.invoke` is the only way to reach an implementation --
this class deliberately exposes no accessor that returns a raw callable, so
"one enforcement point" is a structural property, not a convention a caller
could route around.

``invoke``'s order is load-bearing: the deny check runs *before* the
implementation lookup, so a denied invocation has zero side effects
regardless of what is registered or in what order (TOOL-03, edge:
ordering). Membership is exact-name set containment -- no prefix match, no
wildcard, no hierarchy, no default (TOOL-03, edge: adjacency).

``invoke`` opens no ``Session`` and constructs no lifecycle ORM row (WR-01,
D-06) -- ``tests/unit/test_single_mutation_path.py`` covers this module.

TOOL-02 extension seam: a new capability is added with one
``default_registry.register(name, fn)`` call at module bottom, mirroring
``workers/registry.py`` / ``actions/registry.py`` exactly -- zero change to
the orchestrator, the pipeline, or any role executor. Re-registering an
already-registered name replaces the earlier implementation rather than
keeping both (TOOL-02, edge: adjacency) -- this is a plain dict assignment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from dark_factory.artifacts.store import read_artifact_text, write_artifact_text
from dark_factory.tools import CapabilityDeniedError, UnknownCapabilityError

__all__ = ["ToolRegistry", "default_registry"]


class ToolRegistry:
    """A plain ``dict`` lookup from a capability name to its implementation
    callable, gated by :meth:`invoke`'s per-call grant check."""

    def __init__(self) -> None:
        self._impls: dict[str, Callable[..., object]] = {}

    def register(self, name: str, fn: Callable[..., object]) -> None:
        """Bind ``name`` to ``fn``. Replaces any earlier implementation
        registered under the same name (TOOL-02, edge: adjacency)."""
        self._impls[name] = fn

    def __contains__(self, name: object) -> bool:
        """Membership without invocation -- ``config/loader.py`` validates a
        role's ``tools:`` entries against this, never :meth:`invoke`."""
        return name in self._impls

    def names(self) -> frozenset[str]:
        """Every registered capability name. Used by config-load validation
        and by the guard tests -- never returns a raw implementation."""
        return frozenset(self._impls)

    def invoke(
        self, role: str, capability: str, granted: Sequence[str], /, **kwargs: object
    ) -> object:
        """The deny-by-default gate (TOOL-01, TOOL-03, D-01).

        Order is load-bearing: the grant check runs first -- exact-name set
        membership against ``granted``, never a prefix or wildcard match --
        and only once a role is proven to hold the grant is the
        implementation looked up. A denied invocation therefore never
        reaches an implementation, registered or not.

        Raises :class:`~dark_factory.tools.CapabilityDeniedError` when
        ``capability`` is not in ``granted``, and
        :class:`~dark_factory.tools.UnknownCapabilityError` when it is
        granted but nothing is registered under that name -- a
        configuration bug, never an authorization decision, so it is never
        confused with a denial and never surfaces as a bare ``KeyError``.

        ``**kwargs`` is never interpolated into
        :class:`~dark_factory.tools.CapabilityDeniedError`'s message -- a
        capability argument can carry worker- or repo-supplied content, and
        this string reaches an event payload (threat T-06-04).
        """
        if capability not in set(granted):
            raise CapabilityDeniedError(role, capability, list(granted))
        try:
            impl = self._impls[capability]
        except KeyError:
            raise UnknownCapabilityError(capability) from None
        return impl(**kwargs)


def _artifacts_read(*, root: Path, relative_path: str) -> str:
    """Thin wrapper over
    :func:`~dark_factory.artifacts.store.read_artifact_text` -- the
    capability layer adds the permission check here in :meth:`ToolRegistry.invoke`;
    it does not reimplement the I/O, and this implementation must never
    re-check or second-guess the grant that already ran."""
    return read_artifact_text(root, relative_path)


def _artifacts_write(
    *, root: Path, role: str, filename: str, text: str
) -> tuple[str, str]:
    """Thin wrapper over
    :func:`~dark_factory.artifacts.store.write_artifact_text` -- same
    discipline as :func:`_artifacts_read`: the grant check already ran in
    :meth:`ToolRegistry.invoke`."""
    return write_artifact_text(root, role, filename, text)


default_registry = ToolRegistry()
# TOOL-02 extension seam: a new capability is added with one
# ``default_registry.register(name, fn)`` call here -- zero change to the
# orchestrator, the pipeline, or any role executor.
#
# ``repo.read`` / ``repo.search`` / ``repo.write`` / ``repo.write_tests`` and
# ``shell.execute`` are deliberately NOT registered by this task (plan
# 06-01, Task 1): ``shell.execute``'s body cannot exist without the
# credential-boundary builder (D-11), and the ``repo.*`` implementations are
# kept out so this tracer plan stays thin. Plan 06-01 Task 2 registers all
# five.
default_registry.register("artifacts.read", _artifacts_read)
default_registry.register("artifacts.write", _artifacts_write)
