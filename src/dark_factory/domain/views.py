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
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus

__all__ = [
    "NULL_MARKER",
    "ArtifactRow",
    "EventRow",
    "GateCommandRow",
    "InteractionRow",
    "QualityGateView",
    "RoleAttemptRow",
    "RunDetail",
    "RunListRow",
    "RunReport",
    "RunView",
]

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


class RunListRow(BaseModel):
    """One ``runs`` row, read back for ``dark-factory runs`` (Plan 12-02,
    OBS-03 / D-03) -- a frozen sibling of :class:`RunView` carrying only the
    triage-relevant columns. Deliberately carries no ``source_ref``: the
    table's job is "which of my runs needs attention", and a long free-text
    task reference is exactly what would force the ``id`` column to shrink
    below its 36-character minimum."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    status: RunStatus
    source_kind: str
    created_at: datetime
    updated_at: datetime


class EventRow(BaseModel):
    """One ``run_events`` row, read back for ``dark-factory events`` (Plan
    12-01, OBS-02 / OBS-03) -- a frozen sibling of :class:`RunView` carrying
    exactly what :func:`dark_factory.events.reader.read_events` selects,
    nothing synthesized. ``type`` is typed ``str``, not ``EventType``:
    ``RunEvent.type`` is a ``String(64)`` column, and this module must keep
    importing nothing from ``dark_factory.events``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    created_at: datetime
    type: str
    role_execution_id: UUID | None
    payload: dict[str, Any]

    def as_line(self, *, redactor: Redactor | None = None) -> str:
        """One line: ``seq``, the ISO-8601 ``created_at`` at second precision,
        ``type``, and a short payload summary. The whole payload is passed
        through ``redactor`` once -- ``redact`` is recursive over mappings, so
        one call covers every key. The ``role`` value is surfaced on its own
        when the payload carries one."""
        payload: dict[str, Any] = (
            redactor(self.payload) if redactor is not None else self.payload
        )
        timestamp = self.created_at.isoformat(timespec="seconds")
        role = payload.get("role") if isinstance(payload, dict) else None
        line = f"{self.seq} {timestamp} {self.type}"
        if role is not None:
            line = f"{line} role={role}"
        if self.role_execution_id is not None:
            line = f"{line} role_execution_id={self.role_execution_id}"
        return f"{line} payload={payload}"


class ArtifactRow(BaseModel):
    """One ``artifacts`` row, read back for ``dark-factory artifacts`` (Plan
    12-05, OBS-01 / TRIG-02) -- a frozen sibling of :class:`RunListRow`
    carrying metadata only (D-04): no ``checksum`` and no content. The first
    field is named ``artifact_id``, not ``id`` -- the value an operator
    pastes into ``--show`` must be unambiguous in both the table header and
    the JSON, and ``id`` next to a run id in the same session is exactly the
    ambiguity that produces a wrong paste."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    type: str
    role: str
    path: str
    created_at: datetime


class RoleAttemptRow(BaseModel):
    """One ``role_executions`` row, read back for ``dark-factory status``'s
    per-role history (Plan 12-06, OBS-01) -- a frozen sibling of
    :class:`ArtifactRow`. Unlike :func:`~dark_factory.observability.status.read_status`'s
    single latest row, :func:`~dark_factory.observability.run_detail.read_run_detail`
    returns **one of these per attempt** -- a role that ran twice appears
    twice, each with its own column-sourced ``attempt`` (D-19: never a row
    count or a list position)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    worker: str
    attempt: int
    status: str
    worker_session_id: str | None
    wip_commit_sha: str | None
    created_at: datetime


class InteractionRow(BaseModel):
    """One ``human_interactions`` row, read back for ``dark-factory status``
    (Plan 12-06, OBS-01) -- the question asked, the human's answer (if any),
    and the interaction's own lifecycle timestamps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    answer: str | None
    status: InteractionStatus
    created_at: datetime
    answered_at: datetime | None


class GateCommandRow(BaseModel):
    """One command's outcome inside a quality-gate run, as read back from the
    committed ``verification/quality_gate.json`` (Plan 12-06, D-01). Carries
    only ``command`` and ``exit_code`` -- the two fields the report renders;
    ``stdout``/``stderr``/``timed_out`` stay in the committed file and are
    not surfaced here.

    ``exit_code`` is ``int | None``, matching
    :class:`dark_factory.orchestrator.quality_gate.GateCommandResult` exactly:
    a command that timed out has no exit code (``ShellResult``'s own
    documented contract). Pinning this to a bare ``int`` would make a timed
    -out command fail validation, which would make the whole
    :func:`~dark_factory.observability.run_detail.read_quality_gate` call
    degrade to ``None`` -- silently hiding the one command outcome an
    operator most needs to see (the OBS-01 "never hide a failure"
    prohibition)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str
    exit_code: int | None


class QualityGateView(BaseModel):
    """The whole quality-gate run's outcome, as read back from the committed
    file (Plan 12-06, D-01) -- the gate has no ``role_executions`` row of its
    own, so this is the only place its result can be read from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    commands: list[GateCommandRow]


class RunDetail(BaseModel):
    """Everything about a run that is not already in :class:`RunView`
    (Plan 12-06, OBS-01) -- every role attempt, every artifact, every
    interaction, every error, and the PR identifiers. Read by
    :func:`~dark_factory.observability.run_detail.read_run_detail`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: list[RoleAttemptRow]
    artifacts: list[ArtifactRow]
    interactions: list[InteractionRow]
    errors: list[str]
    pr_number: int | None
    pr_url: str | None
    published_commit_sha: str | None


class RunReport(BaseModel):
    """The whole ``dark-factory status`` answer (Plan 12-06, OBS-01 / D-01):
    the eleven-field :class:`RunView` composed with :class:`RunDetail`, an
    optional :class:`QualityGateView`, and the state-transition history
    (:class:`EventRow`). Composed at the CLI layer, never inside a query --
    ``run`` is the output of ``read_status`` and ``events`` is the output of
    ``read_events``, two independent reads that meet here and nowhere
    earlier, keeping ``observability/status.py`` and ``run_detail.py``
    event-free."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run: RunView
    detail: RunDetail
    quality_gate: QualityGateView | None
    events: list[EventRow]

    # The nine section keys this report adds to RunView's eleven, in render
    # order. The single source of truth the text/JSON parity guard
    # (tests/integration/test_status_cli.py) derives its expected key set
    # from -- a section added to one output mode and not the other fails
    # that test rather than shipping as a quiet asymmetry.
    SECTION_KEYS: ClassVar[tuple[str, ...]] = (
        "roles",
        "artifacts",
        "interactions",
        "errors",
        "quality_gate",
        "pr_number",
        "pr_url",
        "published_commit_sha",
        "events",
    )

    def as_json(self, *, redactor: Redactor | None = None) -> str:
        """A single flat JSON object: :class:`RunView`'s eleven fields at the
        top level (reusing ``RunView._rendered_fields`` so this report cannot
        apply weaker redaction than ``status`` already did), plus the nine
        :data:`SECTION_KEYS` as siblings.

        Flattening rather than nesting under a ``run`` key is a compatibility
        decision, not a taste one: ``status --json`` is a documented contract
        every existing reader (including the CI phases) parses at the top
        level, and nesting would break every one of them for a cosmetic gain.
        """
        dumped = self.run._rendered_fields(redactor)

        detail_dump = self.detail.model_dump(mode="json")
        quality_gate_dump = (
            self.quality_gate.model_dump(mode="json")
            if self.quality_gate is not None
            else None
        )
        events_dump = [event.model_dump(mode="json") for event in self.events]

        sections: dict[str, Any] = {
            "roles": detail_dump["roles"],
            "artifacts": detail_dump["artifacts"],
            "interactions": detail_dump["interactions"],
            "errors": detail_dump["errors"],
            "quality_gate": quality_gate_dump,
            "pr_number": detail_dump["pr_number"],
            "pr_url": detail_dump["pr_url"],
            "published_commit_sha": detail_dump["published_commit_sha"],
            "events": events_dump,
        }
        if redactor is not None:
            sections = {key: redactor(value) for key, value in sections.items()}

        dumped.update(sections)
        return json.dumps(dumped)
