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

from dark_factory.domain.views import EventRow, Redactor

__all__ = ["DEFAULT_RENDER_WIDTH", "render_events_text"]

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
