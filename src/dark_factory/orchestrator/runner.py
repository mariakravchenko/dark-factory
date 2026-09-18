"""The resume-first orchestrator entry points: ``start_run``, ``advance``, ``drive``.

``advance(run_id)`` is the single orchestrator entry point and it is *always*
resume-first (D-02). Every call, without exception:

* opens a fresh session and calls ``load_run_state`` -- the whole run is
  reconstructed from Neon columns, never from a value held between calls;
* returns immediately, writing nothing, when the run is already terminal;
* determines the current node from the pipeline plus ``current_role``;
* executes exactly **one** committed step through ``apply_transition``;
* returns the new status.

Nothing is carried between ``advance`` calls -- no run object, no task, no
worker instance, no attempt counter. If a step needs a value it is a column read
fresh by ``load_run_state``. That is what makes the happy path and the resume
path the same code: the drive loop below exercises resume on every iteration.

The one-role happy path is therefore **two** committed ``advance`` calls --
``CREATED -> BA`` commits the role start, ``BA -> COMPLETED`` commits the worker
result -- so there is a real committed intermediate state at ``BA`` for a later
plan to kill at. An N-role pipeline generalises this to one *extra* committed
"enter" step per non-first role (Phase 4, 04-03): completing role K sets
``runs.status`` / ``current_role`` straight to role K+1 in the same transaction
that completes K, but role K+1's own ``role_executions`` row -- its STATE-03
"one row per attempt" -- is inserted by a dedicated step (:func:`_enter_role`,
the same insert-then-run split :func:`_enter_first_role` already uses for
``CREATED`` -> the first role) the next time ``advance`` runs, *before* that
role's worker is ever called. Without this, ``_run_current_role`` would find no
``role_executions`` row yet belonging to the new role and would incorrectly
reuse the previous role's row (WINDOWS.md #6, open since Phase 2, closed here).

``start_run`` requires a resolved effective-config ``snapshot`` -- the CLI is the
composition root that reads ``.dark-factory.yaml`` (``load_effective_config``);
this module imports nothing from ``dark_factory.config.loader``. The snapshot is
persisted to ``runs.workflow`` at creation and is the *only* configuration source
thereafter: ``advance`` / ``drive`` / ``_advance_once`` rebuild the pipeline from
that column via ``pipeline_from_snapshot``, never from a live file read, so a
config edit during a pause cannot change an in-flight run.

``DARK_FACTORY_CRASH_AFTER`` is a **test-only** environment variable, honoured by
:func:`_maybe_crash_after` in exactly one place, that abruptly ends the process
immediately after a named transition commits. It is inert on every ordinary run
and has no production role -- it exists so the SC2 fresh-process resume proof can
kill a process at a precisely chosen, already-committed point.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.orm import Session
from structlog.contextvars import bind_contextvars, unbind_contextvars

from dark_factory.actions import default_registry as action_default_registry
from dark_factory.actions.context import ActionContext
from dark_factory.actions.registry import ActionRegistry
from dark_factory.artifacts import ArtifactError
from dark_factory.artifacts.paths import ensure_run_tree, run_root
from dark_factory.artifacts.validation import collect_role_artifacts
from dark_factory.config.settings import get_settings
from dark_factory.context.builder import build_role_context
from dark_factory.domain.signal import Signal, signal_from_result
from dark_factory.domain.status import STOP_STATUSES, RunStatus
from dark_factory.domain.worker import WorkerResult
from dark_factory.events.catalog import EventType
from dark_factory.git import DetachedHeadError, GitError, WriteScopeViolation
from dark_factory.git.diff import commit_run_artifacts, push_working_branch
from dark_factory.git.lifecycle import head_sha, wip_commit_if_dirty
from dark_factory.git.scope import DEFAULT_WRITE_SCOPE, enforce_write_scope
from dark_factory.git.worktree import ensure_worktree, remove_worktree
from dark_factory.input.loaders import load
from dark_factory.input.resolver import classify
from dark_factory.orchestrator.lease import LeaseHandle, run_lease
from dark_factory.orchestrator.lifecycle import IllegalTransitionError, transition
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.mutations import (
    ArtifactReferenceWrite,
    EventWrite,
    HumanInteractionWrite,
    LeaseLost,
    RoleExecutionWrite,
    apply_transition,
    create_run,
)
from dark_factory.persistence.repositories import (
    LatestExecution,
    RunState,
    load_run_state,
)
from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools import default_registry as tool_default_registry
from dark_factory.tools.registry import ToolRegistry
from dark_factory.workers.registry import WorkerRegistry, default_registry
from dark_factory.workflows.pipeline import (
    Pipeline,
    RoleNode,
    current_node,
    pipeline_from_snapshot,
)

__all__ = [
    "DriveLoopExhausted",
    "RunNotFoundError",
    "advance",
    "drive",
    "run_state",
    "start_run",
]

# A generous bound so a transition-graph bug becomes a loud error rather than a
# process that spins forever writing events.
_MAX_DRIVE_ITERATIONS = 1000

# ``role_executions.status`` values. "RUNNING" is the in-flight marker written
# when a role starts; the worker outcome overwrites it in the same attempt row.
# "WAITING_HUMAN" marks an attempt paused on a question; "RESUMING" marks the
# same attempt row once an answer has been submitted, and is what tells
# ``_run_current_role`` to call ``worker.resume`` rather than ``worker.execute``.
_ROLE_RUNNING = "RUNNING"
_ROLE_COMPLETED = "COMPLETED"
_ROLE_FAILED = "FAILED"
_ROLE_WAITING_HUMAN = "WAITING_HUMAN"
_ROLE_RESUMING = "RESUMING"

_log = structlog.get_logger(__name__)

# Test seam only -- consumed by ``_maybe_crash_after`` and nowhere else. Never set
# on an ordinary run; see that function's docstring.
_CRASH_AFTER_ENV = "DARK_FACTORY_CRASH_AFTER"
_CRASH_EXIT_STATUS = 137

SessionFactory = Callable[[], Session]
TransitionCallback = Callable[[RunStatus, RunStatus], None]


class RunNotFoundError(LookupError):
    """Raised when ``advance`` / ``drive`` is given a run id with no ``runs`` row."""


class DriveLoopExhausted(RuntimeError):
    """Raised when the drive loop exceeds :data:`_MAX_DRIVE_ITERATIONS` -- a
    transition-graph bug, surfaced loudly instead of spinning."""


def _role_definition(state: RunState, role: str) -> Mapping[str, Any]:
    """The persisted snapshot's entry for ``role`` -- a data lookup by name.

    ``state.workflow["roles"]`` is the ordered role list written at run creation.
    The Phase 3 shape is a list of mappings, each carrying ``before`` / ``after``
    hook-name lists; the legacy Phase 1 / Phase 2 shape is a list of bare
    role-name strings with no hooks. A bare-string entry yields empty ``before``
    / ``after`` lists, so the hook loops in ``_run_current_role`` are simply
    no-ops for it. This is a lookup keyed on the role *value*, never a branch on
    which role it is.
    """
    for entry in state.workflow["roles"]:
        if isinstance(entry, str):
            name = entry
            definition: Mapping[str, Any] = {
                "name": entry,
                "before": [],
                "after": [],
            }
        else:
            name = entry["name"]
            definition = entry
        if name == role:
            return definition
    raise LookupError(f"role {role!r} is not in the run snapshot")


def _maybe_crash_after(previous: RunStatus, new: RunStatus) -> None:
    """Abruptly terminate the process after a just-committed transition -- a test
    seam with **no production role**.

    When ``DARK_FACTORY_CRASH_AFTER`` is set to the name of the transition that
    just committed -- ``"<PREVIOUS>_<NEXT>"`` in status values, e.g.
    ``"CREATED_BA"``, ``"BA_COMPLETED"`` or ``"BA_FAILED"`` -- this calls
    :func:`os._exit`, which ends the interpreter immediately: no exception is
    raised, so no ``finally`` block, context manager or handler runs, and no
    rollback or further write can happen. That is what makes it a faithful
    stand-in for a power loss the instant after the commit returned.

    The variable is read from the environment on every call, never cached at
    import, so the hook is inert on every ordinary run -- the function returns at
    once when the variable is unset or names a different transition -- and a test
    can arm it for a single subprocess.
    """
    target = os.environ.get(_CRASH_AFTER_ENV)
    if target and target == f"{previous.value}_{new.value}":
        os._exit(_CRASH_EXIT_STATUS)


def start_run(
    source: str,
    *,
    session_factory: SessionFactory = new_session,
    snapshot: Mapping[str, Any],
) -> UUID:
    """Classify, load and create -- return the new run id.

    ``snapshot`` is the effective-config snapshot the caller (the CLI, via
    ``load_effective_config(Path.cwd(), ...)``) has already resolved; it is
    persisted verbatim to ``runs.workflow`` and is the only configuration source
    for every later resume. There is no default -- a run with no resolved config
    is a caller error, never a silently-hardcoded pipeline. ``start_run`` imports
    nothing from ``dark_factory.config.loader``.

    Raises ``UnresolvableSourceError`` / ``SourceNotSupportedError`` *before*
    anything is persisted; the CLI turns either into exit 2 (as it does the
    ``ConfigError`` from the pre-``start_run`` config resolution). Once this
    returns, a ``runs`` row exists and the outcome is 0 or 1.
    """
    kind, locator = classify(source)
    task = load(kind, locator)
    session = session_factory()
    try:
        return create_run(session, task=task, workflow=dict(snapshot))
    finally:
        session.close()


def run_state(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> RunState | None:
    """Reconstruct a run's state, or ``None`` if the id is unknown.

    Used by the CLI to check a ``resume`` target exists and to render the final
    summary block. It is a read, not lifecycle logic.
    """
    session = session_factory()
    try:
        return load_run_state(session, run_id)
    finally:
        session.close()


def advance(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline | None = None,
    action_registry: ActionRegistry = action_default_registry,
    repo_root: Path | None = None,
    tool_registry: ToolRegistry = tool_default_registry,
) -> RunStatus:
    """Reconstruct from Neon, execute exactly one committed step under the lease,
    return the new status.

    ``tool_registry`` defaults to :data:`~dark_factory.tools.default_registry`
    and is threaded straight through to :func:`_advance_once` -> (eventually)
    :func:`_run_current_role`, exactly mirroring how ``action_registry`` is
    already threaded -- the test injection seam for a synthetic capability
    (TOOL-02, SC3).

    A run already in a **stop** status -- terminal *or* ``WAITING_HUMAN`` -- is
    returned immediately, without claiming a lease and without writing anything
    (RESEARCH Pitfall 7). Only ``submit_answer`` moves a run out of
    ``WAITING_HUMAN``. Otherwise the lease is claimed for this single step and
    released when it returns; ``LeaseNotAcquired`` propagates unchanged when
    another process owns the run.

    ``pipeline`` defaults to ``None``: the pipeline is then rebuilt from the
    run's persisted snapshot (``pipeline_from_snapshot(state.workflow)``) inside
    ``_advance_once``, so resume never re-reads a config file. Tests inject an
    explicit ``Pipeline`` through this keyword-only seam.

    ``repo_root`` defaults to ``None``: resolved to ``Path.cwd()`` at call time
    inside ``_advance_once`` (never as a default argument value evaluated at
    import), so it always reflects the process's working directory when a step
    actually runs.
    """
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
    finally:
        read_session.close()

    if state is None:
        raise RunNotFoundError(run_id)
    if state.status in STOP_STATUSES:
        return state.status

    with run_lease(run_id, session_factory=session_factory) as lease:
        return _advance_once(
            run_id,
            session_factory=session_factory,
            registry=registry,
            pipeline=pipeline,
            lease=lease,
            action_registry=action_registry,
            repo_root=repo_root,
            tool_registry=tool_registry,
        )


def _advance_once(
    run_id: UUID,
    *,
    session_factory: SessionFactory,
    registry: WorkerRegistry,
    pipeline: Pipeline | None,
    lease: LeaseHandle,
    action_registry: ActionRegistry = action_default_registry,
    repo_root: Path | None = None,
    tool_registry: ToolRegistry = tool_default_registry,
) -> RunStatus:
    """One reconstruct-and-commit step. **Assumes the lease is already held** and
    never claims it -- ``drive`` claims once for the whole loop, ``advance``
    claims once for its single call. Returns the new status.

    When ``pipeline`` is ``None`` (the production path) it is built here from
    ``state.workflow`` -- the effective-config snapshot persisted at run creation
    -- via ``pipeline_from_snapshot``. The snapshot is the sole configuration
    source on resume; no ``.dark-factory.yaml`` / ``.dark-factory/`` file is read.
    A test may pass an explicit ``Pipeline`` to bypass the snapshot.

    ``repo_root`` is resolved to ``Path.cwd()`` here when not supplied -- the
    one place this whole call chain evaluates the working directory -- and
    threaded down to :func:`_run_current_role`, which is where a role's
    context and its run-tree directory are actually resolved against it.

    ``tool_registry`` defaults to :data:`~dark_factory.tools.default_registry`
    and is threaded straight through to :func:`_run_current_role`, mirroring
    ``action_registry``.
    """
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
    finally:
        read_session.close()

    if state is None:
        raise RunNotFoundError(run_id)
    if state.status in STOP_STATUSES:
        return state.status

    if pipeline is None:
        pipeline = pipeline_from_snapshot(state.workflow)

    resolved_repo_root = repo_root if repo_root is not None else Path.cwd()

    attempt = state.latest_execution.attempt if state.latest_execution else None
    bind_contextvars(run_id=str(run_id), role=state.current_role, attempt=attempt)
    try:
        if state.status is RunStatus.CREATED:
            return _enter_first_role(run_id, state, pipeline, session_factory, lease)
        if (
            state.latest_execution is None
            or state.latest_execution.role != state.current_role
        ):
            # ``runs.current_role`` already names this role (the previous role's
            # own completion set it), but no role_executions row exists for it
            # yet -- entering role K+1 always takes its own committed step,
            # mirroring CREATED -> first role (see the module docstring).
            return _enter_role(run_id, state, pipeline, session_factory, lease)
        return _run_current_role(
            run_id,
            state,
            pipeline,
            registry,
            session_factory,
            lease,
            action_registry=action_registry,
            repo_root=resolved_repo_root,
            tool_registry=tool_registry,
        )
    finally:
        unbind_contextvars("run_id", "role", "attempt")


def _enter_first_role(
    run_id: UUID,
    state: RunState,
    pipeline: Pipeline,
    session_factory: SessionFactory,
    lease: LeaseHandle,
) -> RunStatus:
    """Commit ``CREATED -> <first role>``: insert the attempt row, emit ROLE_STARTED."""
    next_status, next_role, next_step = transition(state, Signal.ENTER, pipeline)
    assert next_role is not None
    node = current_node(pipeline, next_role)
    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=RunStatus.CREATED,
            next_status=next_status,
            next_current_role=next_role,
            next_current_step=next_step,
            role_execution=RoleExecutionWrite(
                mode="insert",
                role=node.name,
                worker=node.worker,
                status=_ROLE_RUNNING,
            ),
            events=[
                EventWrite(
                    type=EventType.ROLE_STARTED,
                    payload={"role": node.name, "worker": node.worker},
                )
            ],
            expected_owner_token=lease.token,
        )
        _maybe_crash_after(RunStatus.CREATED, new_status)
        return new_status
    finally:
        session.close()


def _enter_role(
    run_id: UUID,
    state: RunState,
    pipeline: Pipeline,
    session_factory: SessionFactory,
    lease: LeaseHandle,
) -> RunStatus:
    """Insert the ``role_executions`` row for ``state.current_role`` when it has
    none yet, emit its own ``ROLE_STARTED``, and return (STATE-03, WINDOWS.md #6).

    Reached only for a role *after* the first: ``runs.status`` /
    ``current_role`` already name this role -- the previous role's own
    completing ``apply_transition`` call set them -- so this step changes
    neither (``next_status == expected_status``); its only job is the INSERT
    that :func:`_enter_first_role` already does for ``CREATED`` -> the first
    role, generalised to every later role. ``apply_transition`` still requires
    an event for the call to be meaningful, which ``ROLE_STARTED`` supplies
    even though the status itself does not change here.

    Splitting "insert this role's row" from "run this role's worker" into two
    committed steps keeps every role's attempt computed in SQL inside its own
    transaction (D-19) and keeps the resume-first invariant intact: a crash
    between this step and the next finds, on the next ``advance``, a
    ``RUNNING`` row whose ``role`` already equals ``current_role`` and resumes
    straight into :func:`_run_current_role`.
    """
    node = current_node(pipeline, state.current_role)
    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=state.status,
            next_status=state.status,
            next_current_role=state.current_role,
            next_current_step=state.current_step,
            role_execution=RoleExecutionWrite(
                mode="insert",
                role=node.name,
                worker=node.worker,
                status=_ROLE_RUNNING,
            ),
            events=[
                EventWrite(
                    type=EventType.ROLE_STARTED,
                    payload={"role": node.name, "worker": node.worker},
                )
            ],
            expected_owner_token=lease.token,
        )
        _maybe_crash_after(state.status, new_status)
        return new_status
    finally:
        session.close()


def _persist_wip_commit(
    run_id: UUID,
    state: RunState,
    latest: LatestExecution,
    session_factory: SessionFactory,
    lease: LeaseHandle,
    *,
    sha: str,
) -> None:
    """Persist a WIP-recovery commit's SHA on the recovering attempt, with its
    ``WIP_COMMIT_CREATED`` audit event, before that attempt's own worker call
    (D-07, T-05-13). A self-transition, exactly like :func:`_enter_role`'s:
    ``expected_status`` and ``next_status`` are both ``state.status`` and
    neither ``current_role`` nor ``current_step`` change -- this write's only
    job is the ``patch``, not a state change. ``apply_transition``'s "no
    audit row for a state change" guard does not apply here (the status is
    unchanged), but the event is written anyway: a permanent git commit with
    no accompanying audit row is precisely the gap this project's
    durability-is-observability core value forbids.
    """
    session = session_factory()
    try:
        apply_transition(
            session,
            run_id=run_id,
            expected_status=state.status,
            next_status=state.status,
            next_current_role=state.current_role,
            next_current_step=state.current_step,
            role_execution=RoleExecutionWrite(
                mode="patch",
                id=latest.id,
                role=latest.role,
                worker=latest.worker,
                status=latest.status,
                wip_commit_sha=sha,
            ),
            events=[
                EventWrite(
                    type=EventType.WIP_COMMIT_CREATED,
                    role_execution_id=latest.id,
                    payload={
                        "role": latest.role,
                        "attempt": latest.attempt,
                        "commit": sha,
                    },
                )
            ],
            expected_owner_token=lease.token,
        )
    finally:
        session.close()


def _fail_role_before_worker(
    run_id: UUID,
    state: RunState,
    node: RoleNode,
    latest: LatestExecution,
    pipeline: Pipeline,
    session_factory: SessionFactory,
    lease: LeaseHandle,
    *,
    error: str,
) -> RunStatus:
    """Fail the role and the run when the before-hook pass raises
    ``DetachedHeadError`` -- the worker is never called (D-08). Reuses the
    exact ``ROLE_FAILED`` / ``RUN_FAILED`` failure shape the D-09
    schema-violation branch below already writes; this helper exists to give
    the before-hook arm a call site, not to introduce a second failure
    vocabulary.
    """
    next_status, next_role, next_step = transition(state, Signal.ROLE_FAILED, pipeline)
    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=state.status,
            next_status=next_status,
            next_current_role=next_role,
            next_current_step=next_step,
            role_execution=RoleExecutionWrite(
                mode="update",
                id=latest.id,
                role=latest.role,
                worker=latest.worker,
                status=_ROLE_FAILED,
                result=None,
                error={"status": "FAILED", "summary": "", "error": error},
            ),
            events=[
                EventWrite(
                    type=EventType.ROLE_FAILED,
                    payload={"role": node.name, "error": error},
                ),
                EventWrite(type=EventType.RUN_FAILED, payload={"role": node.name}),
            ],
            expected_owner_token=lease.token,
        )
        _maybe_crash_after(state.status, new_status)
        return new_status
    finally:
        session.close()


def _cleanup_run_worktree(
    run_id: UUID,
    work_dir: Path,
    repo_root: Path,
    *,
    role: str,
    attempt: int,
) -> None:
    """Recover any trailing uncommitted content and remove the run's
    worktree for a run that just reached ``COMPLETED`` (D-04, A-05-07,
    A-05-11).

    Runs **after** the terminal transition has already committed to Neon,
    never before: a lingering worktree after a recorded ``COMPLETED``
    status is a recoverable disk-space gap, whereas a removed worktree
    paired with a database write that then failed would be an unrecoverable
    loss window.

    Calls :func:`~dark_factory.git.lifecycle.wip_commit_if_dirty` first --
    the terminal role has no "next entry" to recover it the way every
    earlier role's own before-hook pass would (A-05-07, RESEARCH Pitfall 5)
    -- and only then :func:`~dark_factory.git.worktree.remove_worktree`
    **without** ``force``: the recovery pass has just made the tree clean,
    so a non-forced removal succeeding is itself the proof that nothing
    uncommitted was discarded, and a non-forced removal failing on some
    other git-level obstruction is a signal worth surfacing rather than one
    to suppress by forcing through it.

    A run's artifact content occupies two locations while it is in flight:
    the worktree filesystem (the working copy) and the run's working branch
    (the durable record, per D-09/D-11). After this function returns, only
    the durable record remains -- the worktree filesystem copy is gone, and
    every later reader (a fresh clone, Phase 9's quality gate, Phase 10's
    publisher) reads the branch, never the worktree.

    A :class:`~dark_factory.git.GitError` here is caught, logged as a
    warning naming the run id and the worktree path, and swallowed: a
    cleanup failure never downgrades an already-``COMPLETED`` run back to
    ``FAILED`` -- the run genuinely is complete regardless of whether its
    disk-space reclamation succeeded.
    """
    try:
        wip_commit_if_dirty(work_dir, role=role, attempt=attempt)
        remove_worktree(repo_root, run_id)
    except GitError as exc:
        _log.warning(
            "worktree.cleanup_failed",
            run_id=str(run_id),
            worktree=str(work_dir),
            error=str(exc),
        )


def _run_current_role(
    run_id: UUID,
    state: RunState,
    pipeline: Pipeline,
    registry: WorkerRegistry,
    session_factory: SessionFactory,
    lease: LeaseHandle,
    *,
    action_registry: ActionRegistry = action_default_registry,
    repo_root: Path | None = None,
    tool_registry: ToolRegistry = tool_default_registry,
) -> RunStatus:
    """Run the current role's worker outside any transaction, then commit the outcome.

    The execute-versus-resume choice is read from the **persisted** latest
    role-execution status: a ``RESUMING`` marker means an answer was submitted, so
    ``worker.resume(context, previous, answer)`` is called with the persisted
    ``NEEDS_INPUT`` result and the stored answer; otherwise ``worker.execute``.
    Reading the decision from a column (never from anything held in memory) is
    what makes a crash between storing the answer and dispatching the role
    recoverable by the next process.

    A ``NEEDS_INPUT`` outcome pauses the run: the branch keys off the *signal*,
    never a role name, so every present and future pipeline node gets the
    ask-a-human mechanism with no per-role code (HITL-01).

    The role's configured ``before`` action names run through the
    ``action_registry`` immediately before the worker call and its ``after``
    names immediately after -- both **outside** the one mutation transaction,
    bracketing the worker call exactly where it already sits (CFG-04). The names
    come from the persisted snapshot via :func:`_role_definition`; there is no
    branch on which role it is, and an ``UnknownActionError`` here would be a bug
    (the loader validated every name at run creation) so it is left to propagate.

    After the worker call, and only when its signal is ``ROLE_COMPLETED``, every
    JSON artifact the role's ``outputs`` marks as a machine type is schema
    validated via :func:`~dark_factory.artifacts.validation.collect_role_artifacts`
    (D-09, ART-02): a violation forces the signal to ``ROLE_FAILED`` instead of
    trusting the worker's own ``COMPLETED`` status, and no ``artifacts`` row is
    written for that attempt.

    D-09/D-11/D-16 (Phase 5, plan 05-03): once ``collect_role_artifacts``
    succeeds, this role's newly-written run-tree content is committed onto
    the working branch via :func:`~dark_factory.git.diff.commit_run_artifacts`
    and, when that produced a new commit, immediately pushed to ``origin``
    via :func:`~dark_factory.git.diff.push_working_branch` (skipped silently
    when no push token is configured) -- both inside the same ``GitError``
    catch that downgrades the signal to ``ROLE_FAILED``, exactly as the
    schema-violation branch immediately above does for ``ArtifactError``.
    The ordering is deliberate and plain: **validate, then commit, then
    push, then transition.** A committed *and pushed* artifact is therefore
    always one that already passed its schema check, and a role that
    reaches its transition below has either pushed its progress to a remote
    an ephemeral CI retry can reconstruct via D-15's path, or had nothing
    new to push in the first place.

    GIT-01, D-02/D-03: immediately after ``resolved_root`` is computed, this
    calls :func:`~dark_factory.git.worktree.ensure_worktree` -- an
    unconditional call for every role attempt, deliberately not a role-YAML
    hook, because the worktree is a run-level invariant ("all roles operate
    on the same run repository state") and the run tree cannot be resolved
    without it. The worktree is created once per run, on the first role
    attempt that reaches this function, and every later attempt (including
    every resume) reuses it -- ``ensure_worktree`` is idempotent, so the call
    is safe to make unconditionally on every attempt. Its return value,
    ``work_dir`` -- not ``resolved_root`` -- is what the run tree and the
    role context resolve against, which is what makes "every role operates
    on the same run repository state" literally true.

    D-05/D-06/D-07/D-08 (Phase 5, GIT-01/GIT-02): the before-hook pass has
    exactly two outcomes, both persisted before the worker is ever called.
    (1) A configured ``ensure_clean_worktree`` finds the worktree dirty and
    leaves a WIP-recovery commit on the working branch -- observed by
    comparing ``head_sha(work_dir)`` before and after the hook pass (the
    hook's own return type carries nothing) and persisted via
    :func:`_persist_wip_commit`, a ``patch``-mode write that records the SHA
    on the recovering attempt with a ``WIP_COMMIT_CREATED`` event without
    touching that attempt's ``result``/``error`` (D-07). (2) The worktree's
    ``HEAD`` is detached and ``assert_attached_head`` raises
    ``DetachedHeadError``: the worker call, the lease-loss check and the
    after-hooks are all skipped, and :func:`_fail_role_before_worker` fails
    the role and the run in the identical shape the D-09 schema-violation
    branch below already uses (D-08) -- never a second failure vocabulary.

    ROLE-05, D-12/D-13/D-14 (Phase 5, plan 05-04): once the artifact
    validate/commit/push sequence above leaves the signal at
    ``ROLE_COMPLETED``, :func:`~dark_factory.git.scope.enforce_write_scope`
    checks this attempt's own uncommitted repository changes against the
    role's configured ``write_scope`` and reverts anything outside it --
    restoring a tracked edit from ``HEAD``, removing a newly-created file
    from both the working tree and the index. A violation downgrades the
    signal to ``ROLE_FAILED`` and reuses the same failure branch every other
    post-worker check in this function already writes through; the ordering
    is **validate, then commit, then push, then enforce scope, then
    transition**, so a role that reaches its transition below has either
    stayed inside its declared boundary or had the offending change reverted
    before the attempt was ever accepted.

    TOOL-01/TOOL-03, D-01/D-06 (Phase 6, plan 06-01): the role's grant list
    is read once from the persisted snapshot as ``granted =
    list(role_def.get("tools", []))`` -- the ``.get`` with an empty-list
    default is deliberate, so a legacy snapshot entry carrying no ``tools``
    key at all grants nothing (deny-by-default, never allow-by-omission). It
    is threaded into
    :func:`~dark_factory.artifacts.validation.collect_role_artifacts`, whose
    every artifact read now goes through
    ``tool_registry.invoke(role, "artifacts.read", granted, ...)``. A denied
    read raises :class:`~dark_factory.tools.CapabilityDeniedError`, caught in
    its own arm placed *before* the ``ArtifactError`` catch below so the
    denial's structured facts (role, capability, reason) can be captured
    separately: the overall ordering becomes **check the grant, then read,
    then validate, then commit, then push, then enforce scope, then
    transition**, and a denial reuses the identical ``FAILED`` shape every
    other post-worker check here already writes (D-05).
    """
    resolved_root = repo_root if repo_root is not None else Path.cwd()
    node = current_node(pipeline, state.current_role)
    latest = state.latest_execution
    if latest is None:
        raise RuntimeError(
            f"run {run_id} is in {state.status.value} with no role_executions row"
        )

    worker = registry.get(node.worker)
    role_def = _role_definition(state, node.name)

    work_dir = ensure_worktree(
        resolved_root,
        run_id,
        base_branch=state.base_branch,
        working_branch=state.working_branch,
    )

    run_dir = run_root(work_dir, run_id)
    ensure_run_tree(run_dir)

    context_session = session_factory()
    try:
        context = build_role_context(context_session, work_dir, run_id, state, role_def)
    finally:
        context_session.close()

    def _run_hooks(hook_phase: Literal["before", "after"]) -> None:
        for action_name in role_def.get(hook_phase, []):
            action_registry.get(action_name)(
                ActionContext(
                    run_id=run_id,
                    role=node.name,
                    worker=node.worker,
                    attempt=context.attempt,
                    phase=hook_phase,
                    task=context.task,
                    answer=state.pending_answer,
                    role_definition=dict(role_def),
                    worktree=str(work_dir),
                    run_root=str(run_dir),
                    base_branch=state.base_branch,
                    working_branch=state.working_branch,
                )
            )

    # D-05/D-06/D-08: the before-hook pass is the recovery/detached-HEAD seam.
    # ``head_before`` / ``head_after`` bracket it so a WIP-recovery commit
    # made by ``ensure_clean_worktree`` (if a role's YAML configures it) can
    # be observed with no DB read and no widened action return type -- the
    # registered action-callable type is ``(ActionContext) -> None``, so
    # comparing the branch's own HEAD before and after is the only channel.
    # ``DetachedHeadError`` raised from inside the hook pass skips the worker
    # call, the lease-loss check and the after-hooks entirely: a role
    # entered on a detached HEAD never reaches its worker (D-08).
    head_before = head_sha(work_dir)
    try:
        _run_hooks("before")
    except DetachedHeadError as exc:
        return _fail_role_before_worker(
            run_id,
            state,
            node,
            latest,
            pipeline,
            session_factory,
            lease,
            error=str(exc),
        )
    head_after = head_sha(work_dir)
    if head_after != head_before:
        _persist_wip_commit(
            run_id, state, latest, session_factory, lease, sha=head_after
        )

    if latest.status == _ROLE_RESUMING:
        previous = WorkerResult.model_validate(latest.result)
        result = worker.resume(context, previous, state.pending_answer)
    else:
        result = worker.execute(context)

    # The lease-loss Event races with the worker call returning; it is only a
    # fast abort. When it is set, discard the result and write nothing -- the
    # commit itself is fenced by the token inside ``apply_transition``, so the
    # step re-runs cleanly on the same attempt from the next process.
    if lease.lease_lost.is_set():
        _log.warning("lease.lost_mid_step", run_id=str(run_id), role=node.name)
        raise LeaseLost(
            f"lease for run {run_id} was lost while the worker call was running"
        )

    _run_hooks("after")

    signal = signal_from_result(result)
    outcome = result.model_dump(mode="json")

    # D-09: schema-validate every declared machine artifact BEFORE the signal is
    # trusted. Only reached when the worker itself reported COMPLETED; any other
    # signal already has its own terminal handling below and never writes
    # artifacts.
    artifact_writes: list[ArtifactReferenceWrite] = []
    # TOOL-01/TOOL-03, D-07/D-08 (Phase 6, plan 06-01): non-None only when the
    # ArtifactError-adjacent try/except below actually caught a
    # CapabilityDeniedError -- carries the three payload keys the
    # CAPABILITY_DENIED event below writes verbatim.
    capability_denial: dict[str, str] | None = None
    if signal is Signal.ROLE_COMPLETED:
        # D-01/D-06: read once from the persisted snapshot -- ``.get`` with
        # an empty-list default means a legacy snapshot entry with no
        # ``tools`` key at all grants nothing (deny-by-default, never
        # allow-by-omission).
        granted = list(role_def.get("tools", []))
        try:
            artifact_writes = collect_role_artifacts(
                run_dir,
                node.name,
                latest.id,
                list(role_def.get("outputs", [])),
                list(result.artifacts),
                granted=granted,
                tool_registry=tool_registry,
            )
        except CapabilityDeniedError as exc:
            signal = Signal.ROLE_FAILED
            outcome = {**outcome, "error": str(exc)}
            capability_denial = {
                "role": node.name,
                "capability": exc.capability,
                "reason": "capability not granted",
            }
        except ArtifactError as exc:
            signal = Signal.ROLE_FAILED
            outcome = {**outcome, "error": str(exc)}
        else:
            # D-09/D-11/D-16: validate, then commit, then push, then
            # transition -- in that order. commit_run_artifacts runs only
            # now that collect_role_artifacts has succeeded, so a
            # schema-invalid artifact is never committed; push_working_branch
            # runs immediately after, inside the same GitError catch, so a
            # committed *and pushed* artifact is always one that passed its
            # schema check, and a role that reaches its transition below has
            # either pushed its progress or had nothing new to push. Neither
            # call introduces a new failure vocabulary: a commit or push
            # failure is a role failure, folded into the same ROLE_FAILED /
            # RUN_FAILED pair the ArtifactError branch above already uses.
            assert (
                state.working_branch is not None
            )  # ensure_worktree already required it
            try:
                artifact_sha = commit_run_artifacts(work_dir, run_id, role=node.name)
                if artifact_sha is not None:
                    settings = get_settings()
                    push_token = (
                        settings.github_token.get_secret_value()
                        if settings.github_token is not None
                        else None
                    )
                    push_working_branch(
                        work_dir,
                        working_branch=state.working_branch,
                        token=push_token,
                    )
            except GitError as exc:
                signal = Signal.ROLE_FAILED
                outcome = {**outcome, "error": str(exc)}
                # Mirror the ArtifactError branch above: a role that fails at
                # the commit/push step must not leave `artifacts` rows
                # referencing content whose durability guarantee (D-09/D-11)
                # never actually landed -- ART-04's transparency prohibition
                # forbids reporting artifacts as durable when the commit
                # meant to carry them did not happen.
                artifact_writes = []

    # ROLE-05, D-12/D-13/D-14 (Phase 5, plan 05-04): enforce_write_scope runs
    # only when the signal is still ROLE_COMPLETED after the artifact
    # validate/commit/push sequence above -- an attempt that already failed
    # schema validation or the commit/push step has nothing further to
    # enforce. The patterns are read from the persisted snapshot's role
    # entry, defensively (`(role_def.get("permissions") or {}).get(...)`),
    # so a legacy bare-string snapshot (whose `_role_definition` fallback
    # carries no `permissions` key at all) falls back to
    # ``DEFAULT_WRITE_SCOPE`` rather than raising -- and under D-14 an empty
    # scope is correct here too: a legacy run with no declared scope has
    # effectively declared none, and a role with no declared scope may not
    # change source. The fallback reads the same
    # ``dark_factory.git.scope.DEFAULT_WRITE_SCOPE`` constant
    # ``config/loader.py``'s ``RolePermissions.write_scope`` default reads
    # (WR-03), so this call site cannot silently diverge from that one. A
    # violation reuses the exact ROLE_FAILED/RUN_FAILED shape the
    # ArtifactError/GitError branches above already write -- no new event
    # type, no new role-execution status -- and clears `artifact_writes` for
    # the same reason the GitError branch does: a FAILED attempt records no
    # `artifacts` rows, even though the artifact content itself is already
    # durably committed on the working branch by the time this check runs.
    if signal is Signal.ROLE_COMPLETED:
        write_scope = (role_def.get("permissions") or {}).get(
            "write_scope", list(DEFAULT_WRITE_SCOPE)
        )
        try:
            enforce_write_scope(
                work_dir,
                write_scope=write_scope,
                role=node.name,
                attempt=latest.attempt,
            )
        except WriteScopeViolation as exc:
            signal = Signal.ROLE_FAILED
            outcome = {**outcome, "error": str(exc)}
            artifact_writes = []

    next_status, next_role, next_step = transition(state, signal, pipeline)

    human_interaction: HumanInteractionWrite | None = None
    if signal is Signal.ROLE_COMPLETED:
        re_status = _ROLE_COMPLETED
        re_result: dict[str, Any] | None = outcome
        re_error: dict[str, Any] | None = None
        events = [
            EventWrite(
                type=EventType.ROLE_COMPLETED,
                payload={"role": node.name, "summary": result.summary},
            ),
        ]
        # RUN_COMPLETED belongs only to the transition that actually reaches the
        # terminal COMPLETED state -- i.e. the last node in the pipeline. For any
        # earlier role, transition() returns the next role status and the run
        # continues, so emitting RUN_COMPLETED here would write a false terminal
        # audit row (the "never assume one role" hazard in workflows/pipeline.py).
        if next_status is RunStatus.COMPLETED:
            events.append(
                EventWrite(type=EventType.RUN_COMPLETED, payload={"role": node.name})
            )
    elif signal is Signal.ROLE_FAILED:
        re_status = _ROLE_FAILED
        re_result = None
        re_error = outcome
        events = [
            EventWrite(
                type=EventType.ROLE_FAILED,
                payload={
                    "role": node.name,
                    "error": outcome.get("error") or result.summary,
                },
            ),
            EventWrite(type=EventType.RUN_FAILED, payload={"role": node.name}),
        ]
        # D-07/D-08: a capability denial is prepended ahead of ROLE_FAILED /
        # RUN_FAILED, in the SAME apply_transition call -- additive, never
        # instead of them, so no existing observability consumer needs a new
        # branch to recognise a failed run.
        if capability_denial is not None:
            events.insert(
                0,
                EventWrite(
                    type=EventType.CAPABILITY_DENIED,
                    payload=capability_denial,
                ),
            )
    elif signal is Signal.ROLE_NEEDS_INPUT:
        # Mirror the failure arm's shape. The serialised NEEDS_INPUT outcome MUST
        # be stored, not discarded: it is what a resume validates back into
        # ``previous``.
        re_status = _ROLE_WAITING_HUMAN
        re_result = outcome
        re_error = None
        events = [
            EventWrite(
                type=EventType.QUESTION_CREATED,
                payload={"role": node.name, "questions": list(result.questions)},
            ),
            EventWrite(type=EventType.RUN_PAUSED, payload={"role": node.name}),
        ]
        human_interaction = HumanInteractionWrite(
            mode="ask",
            role_execution_id=latest.id,
            question="\n".join(result.questions),
        )
    else:  # pragma: no cover - transition() already rejects any other signal
        raise IllegalTransitionError(f"runner cannot act on {signal.value}")

    session = session_factory()
    try:
        new_status = apply_transition(
            session,
            run_id=run_id,
            expected_status=state.status,
            next_status=next_status,
            next_current_role=next_role,
            next_current_step=next_step,
            role_execution=RoleExecutionWrite(
                mode="update",
                id=latest.id,
                role=latest.role,
                worker=latest.worker,
                status=re_status,
                worker_session_id=result.worker_session_id,
                result=re_result,
                error=re_error,
            ),
            events=events,
            expected_owner_token=lease.token,
            human_interaction=human_interaction,
            artifact_references=artifact_writes,
        )
        _maybe_crash_after(state.status, new_status)
        if new_status is RunStatus.COMPLETED:
            _cleanup_run_worktree(
                run_id,
                work_dir,
                resolved_root,
                role=node.name,
                attempt=latest.attempt,
            )
        return new_status
    finally:
        session.close()


def drive(
    run_id: UUID,
    on_transition: TransitionCallback | None = None,
    *,
    session_factory: SessionFactory = new_session,
    registry: WorkerRegistry = default_registry,
    pipeline: Pipeline | None = None,
    action_registry: ActionRegistry = action_default_registry,
    repo_root: Path | None = None,
    tool_registry: ToolRegistry = tool_default_registry,
) -> RunStatus:
    """Loop one step until the run reaches a stop status; return that status.

    ``on_transition(previous, new)`` is invoked once per status change. The stop
    condition is the named constant :data:`STOP_STATUSES` -- Phase 2 adds
    ``WAITING_HUMAN`` to that set and nothing else (D-06).

    The lease is claimed **once** for the whole loop (not once per step), so a
    re-claim can never race the process's own token; the private per-step
    function assumes it is held. A run already in a stop status returns
    immediately without claiming anything.

    ``repo_root`` is threaded straight through to every ``_advance_once`` call
    in the loop, unresolved -- each step resolves it (to ``Path.cwd()`` when
    ``None``) independently, exactly as a single ``advance`` call would.

    ``tool_registry`` defaults to :data:`~dark_factory.tools.default_registry`
    and is threaded straight through to every ``_advance_once`` call in the
    loop, mirroring ``action_registry``.
    """
    read_session = session_factory()
    try:
        state = load_run_state(read_session, run_id)
    finally:
        read_session.close()
    if state is None:
        raise RunNotFoundError(run_id)

    status = state.status
    if status in STOP_STATUSES:
        return status

    with run_lease(run_id, session_factory=session_factory) as lease:
        for _ in range(_MAX_DRIVE_ITERATIONS):
            if status in STOP_STATUSES:
                return status
            new_status = _advance_once(
                run_id,
                session_factory=session_factory,
                registry=registry,
                pipeline=pipeline,
                lease=lease,
                action_registry=action_registry,
                repo_root=repo_root,
                tool_registry=tool_registry,
            )
            if new_status != status and on_transition is not None:
                on_transition(status, new_status)
            status = new_status

    raise DriveLoopExhausted(
        f"drive loop for {run_id} exceeded {_MAX_DRIVE_ITERATIONS} iterations"
    )
