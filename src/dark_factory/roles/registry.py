"""The role catalog. Phase 1 defined one real role: Business Analyst (D-07).
Phase 4 has now added Architect, Developer and QA beside it (ROLE-01..ROLE-04) --
this module names all four; ``.dark-factory/roles/*.yaml`` is what actually
resolves their instructions, tools and artifact contracts.

``BA`` is not a placeholder. It is genuinely first in the delivery pipeline and
it is read-only with respect to repository source, so it needs no git worktree --
which is exactly what makes it the honest choice for a phase with no git.
``ARCHITECTURE`` is also read-only on repository source. ``DEVELOPMENT`` and
``QA`` may write -- production code / tests respectively -- but that write
scope is stored, not enforced, until Phase 5 (ROLE-05) / Phase 6 (TOOL-03).

A role names the worker that performs it. The orchestrator resolves that name
through :class:`~dark_factory.workers.registry.WorkerRegistry`; it never branches
on the value.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Role", "architect_role", "ba_role", "developer_role", "qa_role"]


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

architect_role = Role(
    name="ARCHITECTURE",
    worker="fake",
    description=(
        "Architect -- turns BA's requirements and acceptance criteria into a "
        "concrete design; read-only on repository source, so it needs no "
        "worktree."
    ),
)

developer_role = Role(
    name="DEVELOPMENT",
    worker="fake",
    description=(
        "Developer -- implements the Architect's design, adds/updates tests, "
        "and runs tests/lint/build; may modify production code and tests."
    ),
)

qa_role = Role(
    name="QA",
    worker="fake",
    description=(
        "QA -- independently verifies each acceptance criterion; may modify "
        "tests/fixtures/test utilities only."
    ),
)
