"""The five MVP built-in actions referenced by the example role YAML.

Each is a callable no-op in Phase 3. The runner must be able to actually invoke a
hook a role's YAML names, so a raising stub would break every run that configures
one; each becomes real in the phase named in its docstring.

An action must never open a database session, construct a ``RunEvent`` /
``RoleExecution`` / ``HumanInteraction``, or assign a lifecycle ``.status`` --
``tests/unit/test_single_mutation_path.py`` rglobs ``src/`` and covers this
package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dark_factory.actions.context import ActionContext

__all__ = [
    "collect_diff",
    "collect_test_results",
    "ensure_clean_worktree",
    "prepare_role_context",
    "store_role_artifacts",
]


def prepare_role_context(ctx: ActionContext) -> None:
    """No-op until Phase 4 (CTX-01): builds the role-specific RoleContext."""
    return None


def ensure_clean_worktree(ctx: ActionContext) -> None:
    """No-op until Phase 5 (GIT-01): asserts the run worktree is clean."""
    return None


def collect_diff(ctx: ActionContext) -> None:
    """No-op until Phase 5 / Phase 9: collects the role's working-tree diff."""
    return None


def store_role_artifacts(ctx: ActionContext) -> None:
    """No-op until Phase 4 (ART-01/03): persists the role's output artifacts."""
    return None


def collect_test_results(ctx: ActionContext) -> None:
    """No-op until Phase 9 (GATE-04): captures the quality-gate test results."""
    return None
