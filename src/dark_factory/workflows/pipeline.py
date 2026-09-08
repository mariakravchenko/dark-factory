"""The Phase-1 pipeline: a hardcoded ordered list of one role (D-09).

The orchestrator iterates this ordered list. It must never encode a role
*count* -- no "call these N roles", no index arithmetic that assumes exactly one
entry. Phase 3 replaces :data:`DEFAULT_PIPELINE` with a snapshot loaded from
``.dark-factory.yaml`` and must not need to touch the orchestrator to do it.
"""

from __future__ import annotations

from dataclasses import dataclass

from dark_factory.roles.registry import ba_role

__all__ = ["DEFAULT_PIPELINE", "Pipeline", "RoleNode", "current_node", "next_node"]


@dataclass(frozen=True, slots=True)
class RoleNode:
    """One position in the pipeline: the role name and the worker that performs it."""

    name: str
    worker: str


@dataclass(frozen=True, slots=True)
class Pipeline:
    """An ordered sequence of :class:`RoleNode`. Length is never assumed."""

    nodes: tuple[RoleNode, ...]

    def index_of(self, role: str) -> int:
        """Return the ordinal of ``role`` in the pipeline, or raise ``LookupError``."""
        for i, node in enumerate(self.nodes):
            if node.name == role:
                return i
        raise LookupError(f"role {role!r} is not in this pipeline")


DEFAULT_PIPELINE = Pipeline(nodes=(RoleNode(name=ba_role.name, worker=ba_role.worker),))
"""Phase 1's hardcoded default: the single BA role, performed by the fake worker."""


def current_node(pipeline: Pipeline, current_role: str | None) -> RoleNode:
    """Return the node whose name is ``current_role``.

    Raises ``LookupError`` if ``current_role`` is ``None`` or names no node --
    the caller (the pure transition function) turns that into an
    ``IllegalTransitionError``.
    """
    if current_role is None:
        raise LookupError("no current role")
    return pipeline.nodes[pipeline.index_of(current_role)]


def next_node(pipeline: Pipeline, current_role: str) -> RoleNode | None:
    """Return the node after ``current_role``, or ``None`` when it is the last one."""
    idx = pipeline.index_of(current_role)
    following = idx + 1
    if following >= len(pipeline.nodes):
        return None
    return pipeline.nodes[following]
