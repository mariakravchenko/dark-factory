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
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import ArtifactRow, RunListRow
from dark_factory.observability.status import UnknownRunError
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import ArtifactReference, RoleExecution, Run

__all__ = [
    "ArtifactTarget",
    "UnknownArtifactError",
    "read_artifact_rows",
    "read_artifact_target",
    "read_run_list",
]

SessionFactory = Callable[[], Session]


class UnknownArtifactError(LookupError):
    """Raised by :func:`read_artifact_target` when no ``artifacts`` row
    exists for the id.

    A distinct type so the CLI can map it to exit 2 with an empty stdout
    without catching -- and swallowing -- an unrelated ``LookupError``.
    """


@dataclass(frozen=True)
class ArtifactTarget:
    """The result of resolving an artifact id to a readable location
    (Plan 12-05). An internal read result that never reaches a renderer or a
    JSON payload -- it lives here, not in ``domain/views.py``, for exactly
    that reason."""

    run_id: UUID
    working_branch: str | None
    path: str


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


def read_artifact_rows(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> list[ArtifactRow]:
    """Return every ``artifacts`` row for ``run_id`` as an :class:`ArtifactRow`.

    Ordered ``ArtifactReference.created_at.asc(), ArtifactReference.id.asc()``
    -- the same tiebreak reason :func:`read_run_list` carries one: artifacts
    written inside a single transaction share one server-clock
    ``created_at``, and an unstable order makes two consecutive listings
    disagree about which row is which.

    Raises :class:`~dark_factory.observability.status.UnknownRunError` when
    the run id has no ``runs`` row. Returns an empty list for a real run
    with no artifacts -- never raises for that case.
    """
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        if run is None:
            raise UnknownRunError(run_id)

        stmt = (
            select(ArtifactReference, RoleExecution.role)
            .join(
                RoleExecution,
                ArtifactReference.role_execution_id == RoleExecution.id,
            )
            .where(ArtifactReference.run_id == run_id)
            .order_by(ArtifactReference.created_at.asc(), ArtifactReference.id.asc())
        )
        rows = session.execute(stmt).all()
        return [
            ArtifactRow(
                artifact_id=artifact.id,
                type=artifact.type,
                role=role,
                path=artifact.path,
                created_at=artifact.created_at,
            )
            for artifact, role in rows
        ]
    finally:
        session.close()


def read_artifact_target(
    artifact_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> ArtifactTarget:
    """Resolve ``artifact_id`` (a primary key, never a path) to an
    :class:`ArtifactTarget`.

    Raises :class:`UnknownArtifactError` when no ``artifacts`` row exists for
    the id. This function is the whole of the path-selection surface: the
    caller supplies a primary key and receives a path the system itself
    wrote, so no argument value can name a file the run did not produce --
    ``path`` was already validated through
    :func:`~dark_factory.artifacts.paths.resolve_under_run_root` at write
    time inside ``collect_role_artifacts``, so it cannot carry an escape;
    nothing here re-derives or accepts a path.
    """
    session = session_factory()
    try:
        artifact = session.get(ArtifactReference, artifact_id)
        if artifact is None:
            raise UnknownArtifactError(artifact_id)

        run = session.get(Run, artifact.run_id)
        working_branch = run.working_branch if run is not None else None

        return ArtifactTarget(
            run_id=artifact.run_id,
            working_branch=working_branch,
            path=artifact.path,
        )
    finally:
        session.close()
