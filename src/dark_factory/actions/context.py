"""``ActionContext`` -- the frozen value handed to every before/after hook.

Built fresh per role step from ``RunState``, never carried across steps -- the
same discipline as ``orchestrator/runner._build_context``. ``extra="forbid"`` so a
hook author cannot smuggle an unmodelled field through the boundary; ``frozen`` so
a hook cannot use the context as a back-channel to mutate run state.
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
