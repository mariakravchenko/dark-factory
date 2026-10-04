"""Render already-read event DTOs for ``dark-factory events`` (Plan 12-01,
OBS-03).

Pure rendering: no I/O, no database access, and -- critically -- no import
of ``dark_factory.events`` anywhere in this module. That is what keeps the
whole ``observability`` package's transitive import closure events-free
(``tests/unit/test_observability_import_graph.py``) even though its sibling
module ``dark_factory.events.reader`` legitimately queries ``run_events``: a
renderer that only formats rows someone else already read can never become
the read path that folds the append-only log into control state.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from typing import IO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dark_factory.domain.views import (
    NULL_MARKER,
    ArtifactRow,
    EventRow,
    Redactor,
    RunListRow,
    RunReport,
    RunView,
)

__all__ = [
    "DEFAULT_RENDER_WIDTH",
    "render_artifacts_table",
    "render_events_json",
    "render_events_text",
    "render_run_report",
    "render_runs_table",
]

# The explicit-width test seam (A1, 12-RESEARCH.md): ``rich`` auto-detects 80
# columns for a non-tty pipe and ellipsizes an over-wide cell with "..."
# rather than wrapping it -- a run id or a UUID clipped that way is
# unusable. Passing an explicit width keeps rendering deterministic
# regardless of the calling terminal/pipe.
DEFAULT_RENDER_WIDTH = 120


def _console(file: IO[str], width: int | None) -> Console:
    return Console(file=file, width=width or DEFAULT_RENDER_WIDTH, no_color=True)


def render_events_text(
    events: Sequence[EventRow],
    *,
    redactor: Redactor | None = None,
    width: int | None = None,
) -> str:
    """One redacted :meth:`EventRow.as_line` per line, newline-joined.

    Each line is printed with ``markup=False`` (payload content -- e.g. a
    list-shaped value -- must never be interpreted as rich markup) and
    ``soft_wrap=True`` (a line is never wrapped or cropped, so "one line per
    event" holds regardless of the configured ``width``, which matters for
    the T-12-01 redaction-before-render contract: every line entering the
    buffer has already passed through ``redactor``).
    """
    buffer = io.StringIO()
    console = _console(buffer, width)
    for event in events:
        console.print(event.as_line(redactor=redactor), markup=False, soft_wrap=True)
    return buffer.getvalue().rstrip("\n")


def render_events_json(
    events: Sequence[EventRow], *, redactor: Redactor | None = None
) -> str:
    """A single JSON array, one object per event, keys mirroring the
    ``run_events`` columns the DTO carries (``seq``, ``created_at``,
    ``type``, ``role_execution_id``, ``payload``) -- no preamble, no
    trailing text.

    Follows :meth:`RunView.as_json`'s ``model_dump(mode="json")``
    discipline, so UUIDs and datetimes serialise as strings. ``redactor``,
    when supplied, is applied to the whole dumped structure in one call --
    ``redact`` is recursive over mappings and lists, so the nested
    ``payload`` is covered without a per-key walk.

    Takes no ``width``: JSON is not a terminal rendering and must never be
    wrapped, ellipsized or boxed.
    """
    dumped = [event.model_dump(mode="json") for event in events]
    if redactor is not None:
        dumped = redactor(dumped)
    return json.dumps(dumped)


def render_runs_table(
    rows: Sequence[RunListRow],
    *,
    redactor: Redactor | None = None,
    width: int | None = None,
) -> str:
    """A ``rich`` table of every run -- ``id``, ``status``, ``source``,
    ``created_at``, ``updated_at`` -- in the order ``rows`` is given (newest
    first, per :func:`dark_factory.observability.run_detail.read_run_list`).

    ``min_width`` is declared on the first four columns -- ``36`` on ``id``
    (a UUID's exact rendered length), ``13`` on ``status`` (the longest
    ``RunStatus`` value, ``WAITING_HUMAN``), and ``20`` on each timestamp
    column -- and this is the single most important detail here, not a
    stylistic choice: with no ``min_width``, ``rich`` ellipsizes an
    over-wide cell with a ``...`` character rather than wrapping it, and a
    five-column row containing a UUID and two ISO-8601 timestamps overflows
    at both width 80 and width 120. An ellipsized id cannot be pasted into
    ``resume``.

    Each timestamp is rendered with ``isoformat(timespec="seconds")`` --
    second precision is the declared contract for this table; a reader who
    needs exact event timing should use ``events --json``, which carries
    ``seq``-ordered, unrounded timestamps.

    ``source_kind`` is passed through ``redactor`` when one is supplied,
    mirroring how :meth:`RunView._rendered_fields` already scrubs that
    field.
    """
    table = Table()
    table.add_column("id", min_width=36)
    table.add_column("status", min_width=13)
    table.add_column("source", min_width=0)
    table.add_column("created_at", min_width=20)
    table.add_column("updated_at", min_width=20)

    for row in rows:
        source = redactor(row.source_kind) if redactor is not None else row.source_kind
        table.add_row(
            str(row.run_id),
            row.status.value,
            str(source),
            row.created_at.isoformat(timespec="seconds"),
            row.updated_at.isoformat(timespec="seconds"),
        )

    buffer = io.StringIO()
    console = _console(buffer, width)
    console.print(table)
    return buffer.getvalue().rstrip("\n")


def render_artifacts_table(
    rows: Sequence[ArtifactRow],
    *,
    redactor: Redactor | None = None,
    width: int | None = None,
) -> str:
    """A ``rich`` table of every artifact -- ``artifact_id``, ``type``,
    ``role``, ``path``, ``created_at`` -- in the order ``rows`` is given
    (per :func:`dark_factory.observability.run_detail.read_artifact_rows`).

    Mirrors :func:`render_runs_table`'s ``min_width`` discipline: ``36`` on
    ``artifact_id`` -- the value ``--show`` consumes, so an ellipsized id
    here is a dead end for the operator -- and a ``min_width`` on ``type``
    and ``role`` sized to the longest value each can hold (the longest
    configured role name, ``ARCHITECTURE``, and a typical artifact filename
    such as ``quality_gate.json``). ``path`` declares no ``min_width`` and
    absorbs the remaining width -- a clipped path is readable context rather
    than a value to copy.

    Each ``created_at`` is rendered with ``isoformat(timespec="seconds")``,
    the same second-precision contract :func:`render_runs_table` uses.
    ``type``, ``role`` and ``path`` are passed through ``redactor`` when one
    is supplied.
    """
    table = _build_artifacts_table(rows, redactor=redactor)
    buffer = io.StringIO()
    console = _console(buffer, width)
    console.print(table)
    return buffer.getvalue().rstrip("\n")


def _build_artifacts_table(
    rows: Sequence[ArtifactRow], *, redactor: Redactor | None, title: str | None = None
) -> Table:
    """The column construction :func:`render_artifacts_table` prints on its
    own, factored out so :func:`render_run_report` (Plan 12-06) can embed the
    identical table under its own ``title`` rather than holding a second
    copy of the column layout."""
    table = Table(title=title)
    table.add_column("artifact_id", min_width=36)
    table.add_column("type", min_width=18)
    table.add_column("role", min_width=12)
    table.add_column("path")
    table.add_column("created_at", min_width=20)

    for row in rows:
        artifact_type = redactor(row.type) if redactor is not None else row.type
        role = redactor(row.role) if redactor is not None else row.role
        path = redactor(row.path) if redactor is not None else row.path
        table.add_row(
            str(row.artifact_id),
            str(artifact_type),
            str(role),
            str(path),
            row.created_at.isoformat(timespec="seconds"),
        )
    return table


def render_run_report(
    report: RunReport, *, redactor: Redactor | None = None, width: int | None = None
) -> str:
    """The whole ``dark-factory status`` answer, as ``rich`` panels and
    tables (Plan 12-06, D-01, D-02): the eleven :class:`RunView` fields plus
    the PR identifiers in one panel, then one table or panel per
    :data:`~dark_factory.domain.views.RunReport.SECTION_KEYS` entry.

    Every section's title is the exact :class:`RunView` field name or
    :data:`RunReport.SECTION_KEYS` entry it renders, because
    ``tests/integration/test_status_cli.py``'s text/JSON parity guard
    asserts each one appears verbatim in this output. An empty section
    still renders its title and an explicit :data:`NULL_MARKER` (or an
    empty table carrying its header row) rather than being omitted --
    omission is indistinguishable from "this field does not exist", which
    is exactly the transparency failure TRIG-03 forbids.
    """
    buffer = io.StringIO()
    console = _console(buffer, width)

    run_fields = report.run._rendered_fields(redactor)
    detail_dump = report.detail.model_dump(mode="json")
    pr_number = detail_dump["pr_number"]
    pr_url = detail_dump["pr_url"]
    published_commit_sha = detail_dump["published_commit_sha"]
    if redactor is not None:
        if pr_url is not None:
            pr_url = redactor(pr_url)
        if published_commit_sha is not None:
            published_commit_sha = redactor(published_commit_sha)

    def _line(name: str, value: object) -> str:
        return f"{name}: {NULL_MARKER if value is None else value}"

    run_lines = [_line(name, run_fields[name]) for name in RunView.model_fields]
    run_lines.append(_line("pr_number", pr_number))
    run_lines.append(_line("pr_url", pr_url))
    run_lines.append(_line("published_commit_sha", published_commit_sha))
    console.print(Panel("\n".join(run_lines), title="run"))

    roles_table = Table(title="roles")
    roles_table.add_column("role")
    roles_table.add_column("worker")
    roles_table.add_column("attempt")
    roles_table.add_column("status")
    roles_table.add_column("worker_session_id", min_width=36)
    roles_table.add_column("created_at", min_width=20)
    for role_row in report.detail.roles:
        worker_session_id = role_row.worker_session_id
        if redactor is not None and worker_session_id is not None:
            worker_session_id = redactor(worker_session_id)
        roles_table.add_row(
            role_row.role,
            role_row.worker,
            str(role_row.attempt),
            role_row.status,
            NULL_MARKER if worker_session_id is None else str(worker_session_id),
            role_row.created_at.isoformat(timespec="seconds"),
        )
    console.print(roles_table)

    console.print(
        _build_artifacts_table(
            report.detail.artifacts, redactor=redactor, title="artifacts"
        )
    )

    interactions_table = Table(title="interactions")
    interactions_table.add_column("question")
    interactions_table.add_column("answer")
    interactions_table.add_column("status")
    interactions_table.add_column("created_at", min_width=20)
    interactions_table.add_column("answered_at", min_width=20)
    for interaction in report.detail.interactions:
        question = interaction.question
        answer = interaction.answer
        if redactor is not None:
            question = redactor(question)
            if answer is not None:
                answer = redactor(answer)
        interactions_table.add_row(
            str(question),
            NULL_MARKER if answer is None else str(answer),
            interaction.status.value,
            interaction.created_at.isoformat(timespec="seconds"),
            NULL_MARKER
            if interaction.answered_at is None
            else interaction.answered_at.isoformat(timespec="seconds"),
        )
    console.print(interactions_table)

    if report.quality_gate is None:
        console.print(Panel(f"no gate result\n{NULL_MARKER}", title="quality_gate"))
    else:
        gate_table = Table(title=f"quality_gate ({report.quality_gate.status})")
        gate_table.add_column("command")
        gate_table.add_column("exit_code")
        for command_row in report.quality_gate.commands:
            command_text = (
                redactor(command_row.command)
                if redactor is not None
                else command_row.command
            )
            gate_table.add_row(
                str(command_text),
                NULL_MARKER
                if command_row.exit_code is None
                else str(command_row.exit_code),
            )
        console.print(gate_table)

    errors = report.detail.errors
    if redactor is not None:
        errors = [redactor(error) for error in errors]
    errors_body = "\n".join(str(error) for error in errors) if errors else NULL_MARKER
    console.print(Panel(errors_body, title="errors"))

    events_table = Table(title="events")
    events_table.add_column("event")
    for event in report.events:
        events_table.add_row(event.as_line(redactor=redactor))
    console.print(events_table)

    return buffer.getvalue().rstrip("\n")
