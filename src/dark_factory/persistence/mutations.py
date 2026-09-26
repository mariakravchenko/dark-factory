"""The one lifecycle mutation path (Plan 01-05 — ORCH-06, STATE-03, SEC-02).

This module is the *entire* write surface for ``runs.status`` / ``runs.current_role``
/ ``runs.current_step`` / the two iteration counters, for every ``role_executions``
row, for every ``run_events`` row, and (from Phase 2) for every
``human_interactions`` row. Nothing else in ``dark_factory`` may write those —
``tests/unit/test_single_mutation_path.py`` walks the source tree and fails on any
violation.

The single-owner **lease** columns (``runs.owner_token`` / ``runs.lock_expires_at``)
are *claimed / renewed / released* by ``orchestrator/lease.py`` — that is ownership,
not lifecycle state — but they are also *cleared here* whenever a transition
reaches a stop status. The clear lives in this module, not the lease module,
because the release must be atomic with the state change that stopped the run: a
crash between "the run is WAITING_HUMAN" and "the lease is free" must be
impossible.

Two sibling functions, one discipline (RESEARCH Open Question 3): "one mutation
path" means **one module, one transaction discipline, one redaction call** — not
literally one function. ``create_run`` cannot use the ``expected_status`` guard
because there is no row yet, so it is a sibling rather than a call into
``apply_transition``.

* ``create_run`` — inserts the ``CREATED`` row and the ``RUN_CREATED`` event.
* ``apply_transition`` — the guarded, single-transaction lifecycle mutation:
  role-execution row + ``runs`` state columns + counters + audit events, all
  inside one ``with session.begin():`` block that commits exactly once.

Redaction (``dark_factory.events.redaction.redact``) is applied *inside* this
module immediately before each ``session.add`` / attribute assignment, at the
single call site, so no caller can persist an unredacted JSONB payload. The
call-shape models ``RoleExecutionWrite`` and ``EventWrite`` deliberately carry
**raw** payloads — scrubbing is this module's responsibility, never the caller's.

No explicit commit call is ever made anywhere here: the
``with session.begin():`` context manager *is* the atomicity guarantee — one
BEGIN, one COMMIT, full ROLLBACK on any exception.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dark_factory.config.settings import get_settings
from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import STOP_STATUSES, RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.catalog import EventType
from dark_factory.events.redaction import redact, scrub_known_values
from dark_factory.git.worktree import working_branch_name
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)

__all__ = [
    "ArtifactReferenceWrite",
    "ConcurrentTransition",
    "EventWrite",
    "HumanInteractionWrite",
    "LeaseLost",
    "PublishFieldsWrite",
    "RoleExecutionWrite",
    "apply_transition",
    "create_run",
]

# The only ``runs`` columns ``apply_transition`` will increment via
# ``counter_increments`` (D-19). Anything else is a caller error.
_INCREMENTABLE_COUNTERS = frozenset(
    {"qa_developer_iterations", "quality_gate_iterations"}
)


class ConcurrentTransition(RuntimeError):
    """Raised when ``apply_transition``'s ``expected_status`` guard fails: the row's
    current status is not what the caller expected, so another process advanced
    the run first. Nothing is written."""


class LeaseLost(RuntimeError):
    """Raised inside ``apply_transition`` when ``expected_owner_token`` was
    supplied and does not match the already-locked ``runs`` row's
    ``owner_token``: the lease was taken by another process while this one was
    working. Nothing is written — the commit itself is fenced by the token, so a
    stale owner can never write over the new owner's work (RESEARCH Pitfall 2)."""


class RoleExecutionWrite(BaseModel):
    """Insert-or-update spec for a ``role_executions`` row. ``result`` / ``error``
    are **raw** — redaction happens inside ``apply_transition``. ``attempt`` is
    never supplied by the caller; it is computed in SQL inside the transaction.

    Three modes, each with a distinct contract (A-05-05, Phase 5): ``insert``
    creates the attempt row and computes ``attempt`` in SQL; ``update`` records
    the attempt's terminal outcome and **fully overwrites** ``status``,
    ``worker_session_id``, ``result`` and ``error``; ``patch`` assigns **only**
    the non-``None`` fields supplied and touches nothing else — the mode a
    mid-attempt write (e.g. the WIP-recovery SHA) must use, because ``update``
    would blind-assign ``result`` to ``None`` and ``result`` is the column a
    ``RESUMING`` attempt reads back to reconstruct its previous
    ``WorkerResult``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["insert", "update", "patch"]
    role: str
    worker: str
    status: str
    id: UUID | None = None  # required for mode="update"/"patch"
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    wip_commit_sha: str | None = None


class EventWrite(BaseModel):
    """One ``run_events`` row to append in the same transaction as the state change
    it describes. ``payload`` is **raw** — redacted inside ``apply_transition``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: EventType
    role_execution_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class HumanInteractionWrite(BaseModel):
    """Insert-or-update spec for the ``human_interactions`` row that accompanies a
    pause (``ask``) or a resume (``answer``). Mirrors :class:`RoleExecutionWrite`:
    ``question`` / ``answer`` are **raw** — redaction happens inside
    ``apply_transition`` at the single call site, never in the caller.

    * ``ask`` — requires ``role_execution_id`` and ``question``; inserts a
      ``WAITING`` row. ``clarification_comment_id`` (Phase 10, plan 10-03,
      D-05) is the id of the GitHub comment Dark Factory itself posted
      alongside the question, or ``None`` when no comment was posted (a
      non-GitHub-sourced run, or ``create_comment`` failing).
    * ``answer`` — requires ``answer``; the target row is the run's single
      ``WAITING`` interaction, located inside the transaction (not by a caller
      id) so the find and the write are one atomic step. ``github_comment_id``
      (Phase 10, plan 10-04, D-05) is the id of the inbound GitHub comment
      that answered the question, or ``None`` when the answer arrived through
      a different channel; assigned only when supplied, so an ``answer`` call
      that does not carry one never clears an already-recorded value.

    ``clarification_comment_id`` / ``github_comment_id`` are numeric GitHub
    identifiers, not free text -- like ``base_branch`` / ``working_branch`` on
    ``create_run`` above, they do not pass through ``redact()``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["ask", "answer"]
    role_execution_id: UUID | None = None
    question: str | None = None
    answer: str | None = None
    clarification_comment_id: int | None = None
    github_comment_id: int | None = None


class ArtifactReferenceWrite(BaseModel):
    """Insert spec for one ``artifacts`` row (ART-01/02/03). ``metadata`` is
    **raw** -- redaction happens inside ``apply_transition`` at the single call
    site, exactly as ``result`` / ``error`` / ``question`` / ``answer`` do,
    should it ever carry free text. Phase 4 always writes ``{}``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role_execution_id: UUID
    type: str
    path: str
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishFieldsWrite(BaseModel):
    """Patch-spec for the three publish-identifier columns on ``runs``
    (Phase 10, GIT-03/GIT-04, D-06). 10-RESEARCH.md Open Question 1's
    resolution: a typed write-spec model matching this file's established
    one-model-per-write-target convention, not a generic ``Mapping[str, Any]``.

    Every field defaults to ``None`` and ``apply_transition`` applies only the
    non-``None`` fields supplied -- patch semantics, not replace -- so a
    second publish attempt can record a fresh ``pr_number`` without
    blind-clearing an already-recorded ``published_commit_sha``. None of the
    three fields is free text (a PR number/URL/commit SHA), so none passes
    through ``redact()``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pr_number: int | None = None
    pr_url: str | None = None
    published_commit_sha: str | None = None


def _known_secrets() -> Mapping[str, str]:
    """The live ``{secret value: label}`` map from the single settings choke point."""
    return get_settings().known_secret_values()


def create_run(
    session: Session,
    *,
    task: NormalizedTask,
    workflow: dict[str, Any],
) -> UUID:
    """Insert the ``CREATED`` run row and its ``RUN_CREATED`` event; return the id.

    One ``with session.begin():`` block, one commit. ``normalized_task`` is scrubbed
    for **exact known secret values only** (D-18 — a task legitimately discussing
    connection-string syntax persists as written); the ``workflow`` snapshot and
    the ``RUN_CREATED`` payload get full pattern redaction like every other JSONB
    write in this module — no JSONB value reaches Neon without passing ``redact()``.

    Since Phase 3 (03-03) ``workflow`` carries the full effective-config snapshot
    resolved by ``load_effective_config`` at run creation — ordered ``roles`` with
    their resolved ``worker`` / inlined ``instruction_text`` / ``before`` / ``after``
    / ``tools`` / ``permissions``, plus ``repository`` / ``quality_gate`` / ``retry``
    / ``publishing`` — not just ``{"roles": [...]}``. It is still redacted at this
    one call site, and it is the sole configuration source for every later resume
    (``pipeline_from_snapshot`` rebuilds the pipeline from it; no config file is
    re-read).

    GIT-01: ``base_branch`` / ``working_branch`` are written here, in the same
    transaction as the ``CREATED`` row, **before any git command is executed**
    anywhere in the process — the ROADMAP invariant "git effects are guarded
    by persisted identifiers before acting". A crash between this commit and
    the first role entry still leaves the run's git identity fully knowable
    from Neon alone. ``base_branch`` is read defensively from the snapshot's
    ``repository.base_branch`` (``None`` for the legacy bare-``{"roles": [...]}``
    shape); ``working_branch`` is always the deterministic
    ``working_branch_name(run_id)`` (D-01). Both are structural identifiers,
    not free text, so — unlike every other value in this block — they do not
    pass through ``redact()``.
    """
    known = _known_secrets()
    run_id = uuid4()
    base_branch = (workflow.get("repository") or {}).get("base_branch")

    with session.begin():
        session.add(
            Run(
                id=run_id,
                source_kind=task.source_kind,
                source_ref=scrub_known_values(task.source_ref, known_secrets=known),
                normalized_task=scrub_known_values(
                    task.model_dump(mode="json"), known_secrets=known
                ),
                workflow=redact(workflow, known_secrets=known),
                status=RunStatus.CREATED,
                current_role=None,
                current_step=None,
                base_branch=base_branch,
                working_branch=working_branch_name(run_id),
            )
        )
        session.add(
            RunEvent(
                run_id=run_id,
                role_execution_id=None,
                type=EventType.RUN_CREATED.value,
                payload=redact(
                    {
                        "source_kind": task.source_kind,
                        "source_ref": task.source_ref,
                        "title": task.title,
                    },
                    known_secrets=known,
                ),
            )
        )

    return run_id


def apply_transition(
    session: Session,
    *,
    run_id: UUID,
    expected_status: RunStatus,
    next_status: RunStatus,
    next_current_role: str | None,
    next_current_step: int | None,
    role_execution: RoleExecutionWrite | None = None,
    events: Sequence[EventWrite] = (),
    counter_increments: Mapping[str, int] | None = None,
    expected_owner_token: UUID | None = None,
    human_interaction: HumanInteractionWrite | None = None,
    artifact_references: Sequence[ArtifactReferenceWrite] = (),
    publish_fields: PublishFieldsWrite | None = None,
) -> RunStatus:
    """Apply one lifecycle transition atomically and return the new status.

    Order inside the single ``with session.begin():`` block:

    1. lock the ``runs`` row (``with_for_update``); ``LookupError`` if absent
    2. ``ConcurrentTransition`` if its status is not ``expected_status`` — no writes
    3. ``LeaseLost`` if ``expected_owner_token`` was supplied and the already-locked
       row's ``owner_token`` differs — no writes. The row is already locked for
       update, so this is a free, correct fence: no second select.
    4. insert, update or patch the ``role_executions`` row; for an insert,
       ``attempt`` is ``MAX(attempt) + 1`` for this run + role computed **in
       SQL, in this transaction** (D-19, RESEARCH Pitfall 2), never from an
       in-memory counter. ``patch`` exists (Phase 5, A-05-05) because a
       mid-attempt write — persisting a WIP-recovery commit SHA before that
       attempt's own worker call — must not use ``update``: ``update`` is a
       full overwrite that would blind-assign ``result`` to ``None``, and
       ``result`` is the column a ``RESUMING`` attempt reads back to
       reconstruct its previous ``WorkerResult``. ``patch`` assigns only the
       non-``None`` fields supplied and leaves every other column untouched.
    5. write the ``human_interactions`` row (``ask`` inserts the WAITING question;
       ``answer`` fills in the run's single WAITING row), when supplied
    6. insert one ``artifacts`` row per ``artifact_references`` entry (ART-01/03)
    7. assign ``status`` / ``current_role`` / ``current_step`` / ``updated_at``;
       additionally, when ``next_status`` is a **stop** status, clear both lease
       columns — the release must be atomic with the state change that stopped
       the run, so a crash between the two is impossible (which is why the
       *clear* lives here and not in ``orchestrator/lease.py``)
    8. apply each non-``None`` field of ``publish_fields`` to its matching
       ``runs`` column (Phase 10, GIT-03/GIT-04, D-06), when supplied — patch
       semantics deliberately, exactly like the ``role_executions`` ``patch``
       mode above: a second publish attempt can record a fresh ``pr_number``
       without blind-clearing an already-recorded ``published_commit_sha``
    9. apply each ``counter_increments`` entry to its column
    10. append one ``RunEvent`` per ``EventWrite``

    ``result`` / ``error`` / ``question`` / ``answer`` / every event ``payload``
    pass through ``redact()`` immediately before assignment — the single
    scrubbing call site. A new persisted text field that bypassed it would be an
    unrecoverable leak, because a secret is only redactable before it is written.

    A status change (``next_status != expected_status``) with an empty ``events``
    sequence is rejected outright (``ValueError``) before the transaction opens: a
    state change with no audit row is exactly the corruption ORCH-06 prevents.
    """
    events = tuple(events)
    increments = dict(counter_increments or {})

    if next_status != expected_status and not events:
        raise ValueError(
            "apply_transition refuses a status change with no audit event: "
            f"{expected_status.value} -> {next_status.value} with events=[]"
        )
    for name in increments:
        if name not in _INCREMENTABLE_COUNTERS:
            raise ValueError(f"unknown counter column: {name!r}")

    known = _known_secrets()

    with session.begin():
        run = session.get(Run, run_id, with_for_update=True)
        if run is None:
            raise LookupError(run_id)
        if run.status != expected_status:
            raise ConcurrentTransition(
                f"expected {expected_status.value}, found {run.status.value}"
            )
        if expected_owner_token is not None and run.owner_token != expected_owner_token:
            raise LeaseLost(
                f"expected owner {expected_owner_token}, found {run.owner_token}"
            )

        if role_execution is not None:
            _write_role_execution(session, run_id, role_execution, known)

        if human_interaction is not None:
            _write_human_interaction(session, run_id, human_interaction, known)

        for artifact_ref in artifact_references:
            _write_artifact_reference(session, run_id, artifact_ref, known)

        run.status = next_status
        run.current_role = next_current_role
        run.current_step = next_current_step
        run.updated_at = func.now()
        if next_status in STOP_STATUSES:
            run.owner_token = None
            run.lock_expires_at = None

        if publish_fields is not None:
            if publish_fields.pr_number is not None:
                run.pr_number = publish_fields.pr_number
            if publish_fields.pr_url is not None:
                run.pr_url = publish_fields.pr_url
            if publish_fields.published_commit_sha is not None:
                run.published_commit_sha = publish_fields.published_commit_sha

        for name, delta in increments.items():
            setattr(run, name, getattr(run, name) + delta)

        for event in events:
            session.add(
                RunEvent(
                    run_id=run_id,
                    role_execution_id=event.role_execution_id,
                    type=event.type.value,
                    payload=redact(event.payload, known_secrets=known),
                )
            )

    return next_status


def _write_role_execution(
    session: Session,
    run_id: UUID,
    spec: RoleExecutionWrite,
    known: Mapping[str, str],
) -> None:
    """Insert, update or patch the ``role_executions`` row for this transition
    (see :class:`RoleExecutionWrite`'s docstring for the three modes' contract).
    Redaction of ``result`` / ``error`` happens here, at the single call site."""
    result = (
        redact(spec.result, known_secrets=known) if spec.result is not None else None
    )
    error = redact(spec.error, known_secrets=known) if spec.error is not None else None

    if spec.mode == "insert":
        next_attempt = session.scalar(
            select(func.coalesce(func.max(RoleExecution.attempt), 0) + 1).where(
                RoleExecution.run_id == run_id,
                RoleExecution.role == spec.role,
            )
        )
        assert next_attempt is not None  # coalesce(..., 0) + 1 always returns a row
        session.add(
            RoleExecution(
                run_id=run_id,
                role=spec.role,
                worker=spec.worker,
                status=spec.status,
                attempt=next_attempt,
                worker_session_id=spec.worker_session_id,
                result=result,
                error=error,
            )
        )
        return

    if spec.mode == "update":
        if spec.id is None:
            raise ValueError("RoleExecutionWrite(mode='update') requires id")
        row = session.get(RoleExecution, spec.id, with_for_update=True)
        if row is None:
            raise LookupError(spec.id)
        row.status = spec.status
        row.worker_session_id = spec.worker_session_id
        row.result = result
        row.error = error
        row.updated_at = func.now()
        return

    # mode == "patch" (Phase 5, A-05-05): a mid-attempt write that must not
    # touch any field the caller did not explicitly supply -- in particular
    # it must never blind-assign ``result`` to ``None``, which is exactly
    # what the ``update`` branch above does and is precisely the data-loss
    # bug this mode exists to avoid. Only non-``None`` supplied fields are
    # assigned; ``status`` is written only when the caller explicitly passed
    # one that differs from the row's current value.
    if spec.id is None:
        raise ValueError("RoleExecutionWrite(mode='patch') requires id")
    row = session.get(RoleExecution, spec.id, with_for_update=True)
    if row is None:
        raise LookupError(spec.id)
    if spec.wip_commit_sha is not None:
        row.wip_commit_sha = spec.wip_commit_sha
    if spec.worker_session_id is not None:
        row.worker_session_id = spec.worker_session_id
    if result is not None:
        row.result = result
    if error is not None:
        row.error = error
    if spec.status != row.status:
        row.status = spec.status
    row.updated_at = func.now()


def _write_human_interaction(
    session: Session,
    run_id: UUID,
    spec: HumanInteractionWrite,
    known: Mapping[str, str],
) -> None:
    """Insert the WAITING question row (``ask``) or answer the open one
    (``answer``). ``question`` / ``answer`` are redacted here, at the single call
    site, exactly as ``_write_role_execution`` redacts its result and error.

    In ``answer`` mode the row is located *inside* this transaction — the single
    ``WAITING`` interaction for the run, taken with a row-level update lock —
    rather than by an id from the caller: it keeps the find and the write in one
    atomic step, and the partial unique index
    ``uq_one_waiting_interaction_per_run`` guarantees at most one candidate.
    """
    if spec.mode == "ask":
        if spec.role_execution_id is None:
            raise ValueError(
                "HumanInteractionWrite(mode='ask') requires role_execution_id"
            )
        if spec.question is None:
            raise ValueError("HumanInteractionWrite(mode='ask') requires question")
        session.add(
            HumanInteraction(
                run_id=run_id,
                role_execution_id=spec.role_execution_id,
                question=redact(spec.question, known_secrets=known),
                status=InteractionStatus.WAITING,
                clarification_comment_id=spec.clarification_comment_id,
            )
        )
        return

    if spec.answer is None:
        raise ValueError("HumanInteractionWrite(mode='answer') requires answer")
    row = session.scalar(
        select(HumanInteraction)
        .where(
            HumanInteraction.run_id == run_id,
            HumanInteraction.status == InteractionStatus.WAITING,
        )
        .with_for_update()
    )
    if row is None:
        raise LookupError(f"no WAITING human_interaction for run {run_id}")
    row.answer = redact(spec.answer, known_secrets=known)
    row.status = InteractionStatus.ANSWERED
    row.answered_at = func.now()
    if spec.github_comment_id is not None:
        row.github_comment_id = spec.github_comment_id


def _write_artifact_reference(
    session: Session,
    run_id: UUID,
    spec: ArtifactReferenceWrite,
    known: Mapping[str, str],
) -> None:
    """Insert one ``artifacts`` row (ART-01/03). ``metadata`` is redacted here,
    at the single call site, exactly as every other JSONB write in this module.
    Never merges with an existing row -- ``uq_artifact_role_execution_path``
    turns a duplicate ``(role_execution_id, path)`` into a constraint violation
    rather than a silent overwrite."""
    session.add(
        ArtifactReference(
            run_id=run_id,
            role_execution_id=spec.role_execution_id,
            type=spec.type,
            path=spec.path,
            checksum=spec.checksum,
            artifact_metadata=redact(spec.metadata, known_secrets=known),
        )
    )
