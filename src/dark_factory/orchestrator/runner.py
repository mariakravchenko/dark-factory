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
from dark_factory.context.builder import build_role_context
from dark_factory.domain.signal import Signal, signal_from_result
from dark_factory.domain.status import STOP_STATUSES, RunStatus
from dark_factory.domain.worker import WorkerResult
from dark_factory.events.catalog import EventType
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
from dark_factory.persistence.repositories import RunState, load_run_state
from dark_factory.workers.registry import WorkerRegistry, default_registry
from dark_factory.workflows.pipeline import (
    Pipeline,
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
) -> RunStatus:
    """Reconstruct from Neon, execute exactly one committed step under the lease,
    return the new status.

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

    run_dir = run_root(resolved_root, run_id)
    ensure_run_tree(run_dir)

    context_session = session_factory()
    try:
        context = build_role_context(
            context_session, resolved_root, run_id, state, role_def
        )
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
                )
            )

    _run_hooks("before")
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
    if signal is Signal.ROLE_COMPLETED:
        try:
            artifact_writes = collect_role_artifacts(
                run_dir,
                node.name,
                latest.id,
                list(role_def.get("outputs", [])),
                list(result.artifacts),
            )
        except ArtifactError as exc:
            signal = Signal.ROLE_FAILED
            outcome = {**outcome, "error": str(exc)}

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
            )
            if new_status != status and on_transition is not None:
                on_transition(status, new_status)
            status = new_status

    raise DriveLoopExhausted(
        f"drive loop for {run_id} exceeded {_MAX_DRIVE_ITERATIONS} iterations"
    )
