"""The role catalog. Phase 1 defines one real role: Business Analyst (D-07).

``BA`` is not a placeholder. It is genuinely first in the delivery pipeline and
it is read-only with respect to repository source, so it needs no git worktree --
which is exactly what makes it the honest choice for a phase with no git. Phase 4
*adds* Architect, Developer and QA beside it rather than replacing a stub.

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
