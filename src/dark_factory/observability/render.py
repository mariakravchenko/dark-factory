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
from collections.abc import Sequence
from typing import IO

from rich.console import Console
from rich.table import Table

from dark_factory.domain.views import EventRow, Redactor, RunListRow

__all__ = ["DEFAULT_RENDER_WIDTH", "render_events_text", "render_runs_table"]

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
