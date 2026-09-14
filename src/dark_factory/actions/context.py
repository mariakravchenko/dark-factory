"""``ActionContext`` -- the frozen value handed to every before/after hook.

Built fresh per role step from ``RunState``, never carried across steps -- the
same discipline as ``orchestrator/runner._build_context``. ``extra="forbid"`` so a
hook author cannot smuggle an unmodelled field through the boundary; ``frozen`` so
a hook cannot use the context as a back-channel to mutate run state.

``worktree`` / ``run_root`` (Phase 5, GIT-01) are the resolved worktree and
run-tree paths as strings, so an action can perform git and filesystem work
without recomputing them and without importing the orchestrator.
``base_branch`` / ``working_branch`` are the same persisted git identifiers
carried on ``RunState``, handed through unchanged.
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = ["ActionContext"]


class ActionContext(BaseModel):
    """The immutable per-step context a before/after action receives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    role: str
    worker: str
    attempt: int
    phase: Literal["before", "after"]
    task: dict[str, Any]
    answer: str | None
    role_definition: dict[str, Any]
    worktree: str
    run_root: str
    base_branch: str | None
    working_branch: str | None
