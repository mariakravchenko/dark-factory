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

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.domain.status import RunStatus
from dark_factory.domain.views import (
    ArtifactRow,
    GateCommandRow,
    InteractionRow,
    QualityGateView,
    RoleAttemptRow,
    RunDetail,
    RunListRow,
)
from dark_factory.git.committed import run_artifact_text
from dark_factory.git.errors import GitError
from dark_factory.observability.status import UnknownRunError
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
)

__all__ = [
    "ArtifactTarget",
    "UnknownArtifactError",
    "read_artifact_rows",
    "read_artifact_target",
    "read_quality_gate",
    "read_run_detail",
    "read_run_list",
]

_QUALITY_GATE_ARTIFACT_PATH = "verification/quality_gate.json"

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


def read_run_detail(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> RunDetail:
    """Return everything about ``run_id`` not already in ``RunView`` (Plan
    12-06, OBS-01): every role attempt, every artifact, every interaction,
    every error, and the PR identifiers.

    Unlike :func:`~dark_factory.observability.status.read_status`'s single
    latest ``role_executions`` row, this fetches **every** attempt --
    dropping the ``LIMIT 1`` is the whole point: OBS-01 asks for role
    *history*, and a role that ran twice must appear twice, each with its
    own column-sourced ``attempt`` (D-19 -- never a row count or a list
    position).

    Raises :class:`~dark_factory.observability.status.UnknownRunError` when
    the run id has no ``runs`` row. One session, closed in ``finally``, no
    write of any kind.
    """
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        if run is None:
            raise UnknownRunError(run_id)

        attempts = session.scalars(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(
                RoleExecution.created_at.asc(),
                RoleExecution.attempt.asc(),
                RoleExecution.id.asc(),
            )
        ).all()

        roles = [
            RoleAttemptRow(
                role=attempt.role,
                worker=attempt.worker,
                attempt=attempt.attempt,
                status=attempt.status,
                worker_session_id=attempt.worker_session_id,
                wip_commit_sha=attempt.wip_commit_sha,
                created_at=attempt.created_at,
            )
            for attempt in attempts
        ]
        errors = [
            str(attempt.error) for attempt in attempts if attempt.error is not None
        ]

        interactions = session.scalars(
            select(HumanInteraction)
            .where(HumanInteraction.run_id == run_id)
            .order_by(HumanInteraction.created_at.asc(), HumanInteraction.id.asc())
        ).all()
        interaction_rows = [
            InteractionRow(
                question=interaction.question,
                answer=interaction.answer,
                status=interaction.status,
                created_at=interaction.created_at,
                answered_at=interaction.answered_at,
            )
            for interaction in interactions
        ]

        artifact_stmt = (
            select(ArtifactReference, RoleExecution.role)
            .join(
                RoleExecution,
                ArtifactReference.role_execution_id == RoleExecution.id,
            )
            .where(ArtifactReference.run_id == run_id)
            .order_by(ArtifactReference.created_at.asc(), ArtifactReference.id.asc())
        )
        artifact_rows = [
            ArtifactRow(
                artifact_id=artifact.id,
                type=artifact.type,
                role=role,
                path=artifact.path,
                created_at=artifact.created_at,
            )
            for artifact, role in session.execute(artifact_stmt).all()
        ]

        return RunDetail(
            roles=roles,
            artifacts=artifact_rows,
            interactions=interaction_rows,
            errors=errors,
            pr_number=run.pr_number,
            pr_url=run.pr_url,
            published_commit_sha=run.published_commit_sha,
        )
    finally:
        session.close()


def read_quality_gate(
    repo_root: Path,
    run_id: UUID,
    working_branch: str | None,
) -> QualityGateView | None:
    """Return the quality gate's outcome for ``run_id``, read from the
    committed ``verification/quality_gate.json`` on ``working_branch`` (Plan
    12-06, D-01).

    This is the only function in this module that performs I/O outside the
    database: the quality gate has no ``role_executions`` row of its own
    (D-01 in ``orchestrator/quality_gate.py``), so the committed file is the
    only place its result exists.

    Returns ``None`` when ``working_branch`` is ``None`` (the run never
    reached a role that set one), when the committed file does not exist yet
    (:class:`~dark_factory.git.GitError` -- a run that never reached its
    terminal role has no gate file, which is a normal state, not a
    failure), or when the file's content cannot be parsed as a
    :class:`~dark_factory.domain.views.QualityGateView` (a corrupt gate file
    must not make the whole ``status`` report unavailable). Never raises for
    any of those cases.
    """
    if working_branch is None:
        return None

    try:
        text = run_artifact_text(
            repo_root, run_id, working_branch, _QUALITY_GATE_ARTIFACT_PATH
        )
    except GitError:
        return None

    try:
        payload = json.loads(text)
        commands = [
            GateCommandRow(command=entry["command"], exit_code=entry["exit_code"])
            for entry in payload["commands"]
        ]
        return QualityGateView(status=payload["status"], commands=commands)
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
        return None
