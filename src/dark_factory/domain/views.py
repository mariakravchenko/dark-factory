"""``RunView`` -- the read-model DTO for ``dark-factory status`` (Plan 01-08, D-12 / D-13).

``RunView`` carries **exactly** the D-12 field set and nothing else: no per-role
pipeline visualisation, no event list, no artifact list. Those belong to Phase
12's observability surface; D-12 is deliberately a flat ``key: value`` field list,
and shipping the smaller thing now is what makes success criterion SC3 cleanly
testable.

It is a frozen value object. It performs no I/O and imports nothing from
``dark_factory.persistence`` or ``dark_factory.events``, so the architectural
constraint on the status read path -- *no events import, even transitively* -- is
satisfied by construction for anything that merely returns one.

**Rendering owns the sink discipline.** ``as_text`` / ``as_json`` accept an
optional ``redactor`` callable so the *caller* (the CLI) chooses the scrubber
(``dark_factory.events.redaction.redact``) without this module -- or the read
path -- importing it. The source is passed through that redactor before it is
rendered in **both** output modes, so the terminal and a CI log are treated as
sinks on the same terms as Neon and the log file (T-01-01). ``base_branch`` and
``working_branch`` are always rendered, with an explicit null marker, even though
they stay null until Phase 5: a field absent from the output looks like a field
that does not exist.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from dark_factory.domain.status import RunStatus

__all__ = ["NULL_MARKER", "RunView"]

NULL_MARKER = "-"

Redactor = Callable[[Any], Any]


class RunView(BaseModel):
    """Where a run is, as read from state columns -- ``runs`` plus the latest
    ``role_executions`` row. Frozen, fully detached, no ORM instance inside."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Declaration order IS the rendered order (as_text / as_json both iterate
    # ``model_fields``). Phase 11's CI trigger and Phase 12's observability
    # surface extend this set; they do not reorder or drop from it.
    run_id: UUID
    source_kind: str
    source_ref: str | None
    status: RunStatus
    current_role: str | None
    current_step: int | None
    latest_attempt: int | None
    created_at: datetime
    updated_at: datetime
    base_branch: str | None
    working_branch: str | None

    def _rendered_fields(self, redactor: Redactor | None) -> dict[str, Any]:
        """The model in JSON-primitive form (UUID/enum/datetime as strings), with
        the source passed through ``redactor`` when one is supplied."""
        dumped: dict[str, Any] = self.model_dump(mode="json")
        if redactor is not None:
            dumped["source_kind"] = redactor(dumped["source_kind"])
            if dumped["source_ref"] is not None:
                dumped["source_ref"] = redactor(dumped["source_ref"])
        return dumped

    def as_text(self, *, redactor: Redactor | None = None) -> str:
        """One ``key: value`` line per field, in declaration order. Unset values
        render as :data:`NULL_MARKER`."""
        dumped = self._rendered_fields(redactor)
        return "\n".join(
            f"{name}: {NULL_MARKER if dumped[name] is None else dumped[name]}"
            for name in type(self).model_fields
        )

    def as_json(self, *, redactor: Redactor | None = None) -> str:
        """A single JSON object carrying the same field set as :meth:`as_text`,
        with no preamble and no trailing text. Datetimes and the status enum
        serialise as strings via the model's own JSON mode."""
        return json.dumps(self._rendered_fields(redactor))
