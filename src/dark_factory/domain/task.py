"""The origin-agnostic task model (INTAKE-05).

Every source -- ``text:``, ``spec:`` (Phase 4), ``github:`` (Phase 10) -- is
loaded through a source-specific loader and normalized to one
:class:`NormalizedTask`. After that object exists nothing downstream knows or
cares where the task came from.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["NormalizedTask"]


class NormalizedTask(BaseModel):
    """A delivery request, normalized away from its origin."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: str
    source_ref: str | None = None
    title: str = ""
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
