"""The normalized worker-output contract (WORK-08).

A :class:`WorkerResult` is the only value that crosses back from a runtime the
orchestrator does not control. In Phase 1 the runtime is in-process, but the
boundary is validated as if it were not: the model is ``frozen`` (a result the
orchestrator cannot mutate cannot become a back-channel for state changes --
ORCH-05) and ``extra="forbid"`` (an adapter that invents a field is caught here
rather than silently dropping data into a JSONB column).
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ArtifactRef",
    "WorkerCapabilities",
    "WorkerResult",
    "WorkerResultStatus",
]


class WorkerResultStatus(StrEnum):
    """The three outcomes any coding worker can report. Value equals name."""

    COMPLETED = "COMPLETED"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


class ArtifactRef(BaseModel):
    """A reference to an artifact file -- shape only; Phase 1 persists no rows."""

    model_config = ConfigDict(extra="forbid")

    type: str
    path: str
    checksum: str | None = None


class WorkerCapabilities(BaseModel):
    """What a worker adapter can do, so the orchestrator never branches on its name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    native_resume: bool = False
    session_id: bool = False
    structured_output: bool = True
    non_interactive: bool = True
    emits_changed_files: bool = False
    max_prompt_bytes: int | None = None


class WorkerResult(BaseModel):
    """The one shape every adapter normalizes its output to (WORK-08)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkerResultStatus
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    worker_session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @model_validator(mode="after")
    def _require_question_for_needs_input(self) -> Self:
        """A pause with no question is a state the orchestrator cannot act on."""

        if self.status is WorkerResultStatus.NEEDS_INPUT and not self.questions:
            raise ValueError("questions must be non-empty when status is NEEDS_INPUT")
        return self
