"""The role pipeline: an ordered list of :class:`RoleNode`, length never assumed.

The orchestrator iterates this ordered list. It must never encode a role
*count* -- no "call these N roles", no index arithmetic that assumes exactly one
entry. :func:`pipeline_from_snapshot` builds the pipeline from the persisted
effective-config snapshot (Phase 3, ORCH-02); :data:`DEFAULT_PIPELINE` is
retained only as a fixture for the Phase 1 / Phase 2 test suites -- plan 03-03
removes the last orchestrator parameter-default reference to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dark_factory.roles.registry import ba_role

__all__ = [
    "DEFAULT_PIPELINE",
    "Pipeline",
    "RoleNode",
    "current_node",
    "next_node",
    "pipeline_from_snapshot",
]


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
"""Retained as a test fixture only.

The single-BA pipeline the Phase 1 / Phase 2 suites import directly. Production
code builds its pipeline with :func:`pipeline_from_snapshot` from the persisted
run snapshot; the orchestrator's remaining parameter-default reference is removed
in plan 03-03. No new code should reference this object.
"""


def pipeline_from_snapshot(snapshot: Mapping[str, Any]) -> Pipeline:
    """Build the :class:`Pipeline` from the persisted effective-config snapshot.

    ``snapshot["roles"]`` is the ordered role list. Two shapes are accepted:

    * the legacy Phase 1 / Phase 2 shape -- a list of bare role-name strings,
      each mapped to ``worker="fake"``;
    * the Phase 3 shape -- a list of ``{"name": ..., "worker": ...}`` mappings.

    Raises ``KeyError`` when ``"roles"`` is absent: a run with no persisted
    snapshot is a bug, not a case to paper over with a hardcoded default.
    """
    return Pipeline(
        nodes=tuple(
            RoleNode(name=entry, worker="fake")
            if isinstance(entry, str)
            else RoleNode(name=entry["name"], worker=entry["worker"])
            for entry in snapshot["roles"]
        )
    )


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
