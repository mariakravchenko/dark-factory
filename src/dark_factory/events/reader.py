"""``read_events`` -- the ``dark-factory events`` data source (Plan 12-01,
OBS-02 / OBS-03).

This is the **one** module permitted to query ``run_events`` for a read path.
It is deliberately a *sibling* of ``dark_factory.observability.status``
rather than part of the ``observability`` package itself, so that read
path's events-free transitive import closure (STATE-06) stays trivially
provable: nothing under ``dark_factory.observability`` needs to reach this
module, or the ``run_events`` table it queries, to do its job. See
``tests/unit/test_observability_import_graph.py``'s module docstring for why
the asymmetry -- a reader that never feeds the status path cannot fold the
audit log into control state, even though it legitimately reads it.

``read_events`` performs **no write of any kind** -- the same posture as
``read_status``: one session opened, one session closed in ``finally``, and
no mutation anywhere in between.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.views import EventRow
from dark_factory.events.catalog import EventType
from dark_factory.observability.status import UnknownRunError
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import Run, RunEvent

__all__ = ["read_events"]

SessionFactory = Callable[[], Session]


def read_events(
    run_id: UUID,
    *,
    event_types: Sequence[EventType] | None = None,
    session_factory: SessionFactory = new_session,
) -> list[EventRow]:
    """Return every ``run_events`` row for ``run_id``, in ``seq`` order.

    Raises :class:`~dark_factory.observability.status.UnknownRunError` when
    the run id has no ``runs`` row -- the same type ``read_status`` raises,
    so the CLI has one error type to map to exit 2 regardless of which read
    path it is calling. Narrows the result to ``event_types`` when a
    non-empty sequence is supplied. Ordering is always by ``seq``, never by
    ``created_at`` -- see ``persistence/models.py``'s ``RunEvent`` docstring.
    """
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        if run is None:
            raise UnknownRunError(run_id)

        stmt = select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        if event_types:
            stmt = stmt.where(RunEvent.type.in_([t.value for t in event_types]))

        rows = session.scalars(stmt).all()
        return [
            EventRow(
                seq=row.seq,
                created_at=row.created_at,
                type=row.type,
                role_execution_id=row.role_execution_id,
                payload=row.payload,
            )
            for row in rows
        ]
    finally:
        session.close()
