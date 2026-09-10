"""The actions package: an :class:`ActionRegistry`, the frozen :class:`ActionContext`,
and the five MVP built-ins registered into :data:`default_registry` at import
(mirrors ``workers/registry.py``'s lazy ``default_registry.register("fake", ...)``).
"""

from dark_factory.actions import builtins
from dark_factory.actions.context import ActionContext
from dark_factory.actions.registry import (
    ActionRegistry,
    UnknownActionError,
    default_registry,
)

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "UnknownActionError",
    "default_registry",
]

default_registry.register("prepare_role_context", builtins.prepare_role_context)
default_registry.register("ensure_clean_worktree", builtins.ensure_clean_worktree)
default_registry.register("collect_diff", builtins.collect_diff)
default_registry.register("store_role_artifacts", builtins.store_role_artifacts)
default_registry.register("collect_test_results", builtins.collect_test_results)
