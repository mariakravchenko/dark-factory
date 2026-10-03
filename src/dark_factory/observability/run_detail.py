"""``read_run_list`` -- the ``dark-factory runs`` data source (Plan 12-02, D-03).

The non-events read-model sibling of ``observability/status.py``: this module
issues no query against ``run_events``, imports nothing from
``dark_factory.events``, and performs no write of any kind.
``tests/unit/test_observability_import_graph.py``'s package-wide sweep (shipped
with Plan 12-01) now enforces that for the whole ``observability`` directory on
arrival -- a sibling module added here needs no edit to that guard.

That boundary is architectural, not merely behavioural. A read path that *can*
fold the append-only audit log will eventually be asked to, and at that moment
the log has silently become the control state -- exactly the failure STATE-06
exists to prevent.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import RunListRow
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import Run

__all__ = ["read_run_list"]

SessionFactory = Callable[[], Session]


def read_run_list(
    *,
    status: RunStatus | None = None,
    session_factory: SessionFactory = new_session,
) -> list[RunListRow]:
    """Return every ``runs`` row as a :class:`RunListRow`, newest first.

    Ordered ``Run.created_at.desc(), Run.id.desc()``. The ``Run.id`` tiebreak
    is load-bearing, not decoration: ``created_at`` comes from the server
    clock and two runs created inside one tick would otherwise render in an
    order PostgreSQL is free to vary between calls, which makes the list
    untrustworthy for exactly the operator who is comparing two screenfuls.

    Narrows to ``status`` when supplied. Returns an empty list for an empty
    table -- never raises, never a sentinel row.
    """
    session = session_factory()
    try:
        stmt = select(Run).order_by(Run.created_at.desc(), Run.id.desc())
        if status is not None:
            stmt = stmt.where(Run.status == status)

        rows = session.scalars(stmt).all()
        return [
            RunListRow(
                run_id=row.id,
                status=row.status,
                source_kind=row.source_kind,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    finally:
        session.close()
