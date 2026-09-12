"""The role catalog. Phase 1 defined one real role: Business Analyst (D-07),
the only one with a consumer -- :data:`~dark_factory.workflows.pipeline.DEFAULT_PIPELINE`.

Phase 4 added the full four-role pipeline (Architect, Developer, QA beside
BA, ROLE-01..ROLE-04), but ``.dark-factory/roles/*.yaml`` -- not this module
-- is what actually resolves their instructions, tools and artifact
contracts, and nothing in ``src/`` or ``tests/`` ever imported an
``architect_role`` / ``developer_role`` / ``qa_role`` catalog entry here
(WR-02, 04-REVIEW): a second, un-consumed ``Role`` catalog duplicating what
the YAML files already own is a drift risk with no offsetting benefit, so
this module goes back to naming only the one role that has a real consumer.
A future ``dark-factory roles`` listing command (or similar) is the natural
place to reintroduce a role catalog, reading `.dark-factory/roles/*.yaml`
directly rather than a hand-maintained duplicate.

``BA`` is not a placeholder. It is genuinely first in the delivery pipeline and
it is read-only with respect to repository source, so it needs no git worktree --
which is exactly what makes it the honest choice for a phase with no git.

A role names the worker that performs it. The orchestrator resolves that name
through :class:`~dark_factory.workers.registry.WorkerRegistry`; it never branches
on the value.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Role", "ba_role"]


@dataclass(frozen=True, slots=True)
class Role:
    """One delivery-pipeline role: its name, the worker that performs it, and a
    one-line human description."""

    name: str
    worker: str
    description: str


ba_role = Role(
    name="BA",
    worker="fake",
    description=(
        "Business Analyst -- clarifies and analyses the task; read-only on "
        "repository source, so it needs no worktree."
    ),
)
