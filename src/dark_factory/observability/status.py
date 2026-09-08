"""``read_status`` -- the ``dark-factory status`` data source (Plan 01-08, STATE-06 / SC3).

``read_status(run_id)`` reconstructs a :class:`RunView` from **two selects and no
more**: the ``runs`` row, and the single latest ``role_executions`` row for that
run (``ORDER BY created_at DESC, attempt DESC, id DESC LIMIT 1`` -- ``attempt``
restarts at 1 per role, so it is not a "most recent" key once a pipeline has
more than one role). It issues **no** query against
``run_events`` and this module imports **nothing** from ``dark_factory.events`` --
``tests/unit/test_status_import_graph.py`` walks the transitive import closure and
fails on a violation.

That boundary is architectural, not merely behavioural. A read path that *can*
fold the append-only audit log will eventually be asked to, and at that moment
the log has silently become the control state -- which is exactly the failure
STATE-06 and SC3 exist to prevent, and it would surface at the worst possible
time: an operator staring at a run they already do not trust.

``read_status`` also performs **no write of any kind**. A status command that
repairs, backfills or normalises what it finds turns an observability surface
into an unaudited mutation path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.views import RunView
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import RoleExecution, Run

__all__ = ["UnknownRunError", "read_status"]

SessionFactory = Callable[[], Session]


class UnknownRunError(LookupError):
    """Raised by :func:`read_status` when no ``runs`` row exists for the id.

    A distinct type so the CLI can map it to exit 2 with an empty stdout without
    catching -- and swallowing -- an unrelated ``LookupError``.
    """


def _default_session() -> Session:
    """A real ``Session`` bound to the process-wide, cold-start-warmed engine."""
    return cast(Session, new_session())


def read_status(
    run_id: UUID,
    *,
    session_factory: SessionFactory = _default_session,
) -> RunView:
    """Return a :class:`RunView` built from state columns alone.

    Raises :class:`UnknownRunError` when the run id has no ``runs`` row. Returns a
    ``RunView`` whose ``current_role`` / ``latest_attempt`` are ``None`` when the
    run has no ``role_executions`` row yet, rather than raising.
    """
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        if run is None:
            raise UnknownRunError(run_id)

        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(
                RoleExecution.created_at.desc(),
                RoleExecution.attempt.desc(),
                RoleExecution.id.desc(),
            )
            .limit(1)
        )

        return RunView(
            run_id=run.id,
            source_kind=run.source_kind,
            source_ref=run.source_ref,
            status=run.status,
            current_role=run.current_role,
            current_step=run.current_step,
            latest_attempt=latest.attempt if latest is not None else None,
            created_at=run.created_at,
            updated_at=run.updated_at,
            base_branch=run.base_branch,
            working_branch=run.working_branch,
        )
    finally:
        session.close()
