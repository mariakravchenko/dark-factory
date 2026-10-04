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

import json
import os
from collections.abc import Callable, Mapping, Sequence
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
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.artifacts.validation import collect_role_artifacts
from dark_factory.config.settings import get_settings
from dark_factory.context.builder import build_role_context
from dark_factory.domain.artifacts import Verdict
from dark_factory.domain.signal import Signal, signal_from_result
from dark_factory.domain.status import STOP_STATUSES, RunStatus, VerdictStatus
from dark_factory.domain.worker import WorkerResult
from dark_factory.events.catalog import EventType
from dark_factory.events.redaction import redact
from dark_factory.git import (
    ArtifactScopeViolation,
    DetachedHeadError,
    GitError,
    WriteScopeViolation,
)
from dark_factory.git.diff import commit_run_artifacts, push_working_branch
from dark_factory.git.lifecycle import head_sha, wip_commit_if_dirty
from dark_factory.git.scope import (
    DEFAULT_WRITE_SCOPE,
    enforce_artifact_scope,
    enforce_write_scope,
)
from dark_factory.git.worktree import ensure_worktree, remove_worktree
from dark_factory.github import GitHubError
from dark_factory.github.client import GitHubClient, GitHubComment
from dark_factory.input.loaders import load
from dark_factory.input.resolver import SourceKind, classify
from dark_factory.orchestrator.lease import LeaseHandle, run_lease
from dark_factory.orchestrator.lifecycle import IllegalTransitionError, transition
from dark_factory.orchestrator.publish import PublishResult, run_publish_step
from dark_factory.orchestrator.quality_gate import (
    run_quality_gate,
    write_quality_gate_result,
)
from dark_factory.persistence.engine import new_session
from dark_factory.persistence.mutations import (
    ArtifactReferenceWrite,
    EventWrite,
    HumanInteractionWrite,
    LeaseLost,
    PublishFieldsWrite,
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
    next_node,
    pipeline_from_snapshot,
    previous_node,
)

__all__ = [
    "CLARIFICATION_COMMENT_PREFIX",
    "DriveLoopExhausted",
    "GitHubClientFactory",
    "RunNotFoundError",
    "advance",
    "build_clarification_comment",
    "default_github_client_factory",
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
# GIT-05/GIT-06 enabler: the injection seam plan 10-02 (existing-PR check) and
# plan 10-03 (clarification comment) both reuse rather than inventing a
# second one. Threaded through exactly like ``tool_registry`` /
# ``action_registry`` are, and called lazily -- only on the branch that
# actually needs a client -- so a run that publishes nothing and asks nothing
# never constructs one and works with ``github_token`` unset.
GitHubClientFactory = Callable[[], GitHubClient]


def default_github_client_factory() -> GitHubClient:
    """The production factory: a real client from the process's own settings."""
    return GitHubClient.from_settings(get_settings())


# GIT-05, D-08 (Phase 10, plan 10-03): the fixed, human-legible lead-in every
# clarification comment carries, naming Dark Factory as the asker so a
# maintainer scrolling the issue can tell at a glance that a machine asked
# (T-10-14, spoofing). Kept a constant, not an f-string built at the call
# site, so "the prefix is fixed" is checkable and plan 10-04's self-comment
# filter can reference it if it ever needs to.
CLARIFICATION_COMMENT_PREFIX = (
    "**Dark Factory needs your input to continue this task.**"
)


def build_clarification_comment(questions: Sequence[str]) -> str:
    """The exact text posted as a clarification comment (GIT-05, D-08).

    Takes **only** the question list -- no run id, role name, attempt
    number, worktree path or branch name: a parameter this function does
    not receive is a value it cannot leak, which is the cheapest possible
    enforcement of the no-internal-state prohibition (T-10-12). The result
    is :data:`CLARIFICATION_COMMENT_PREFIX`, a blank line, then the exact
    newline-join of ``questions`` -- the identical text
    ``human_interactions.question`` stores, so the posted comment and the
    persisted question can never disagree. No escaping, no normalization, no
    truncation: the question text -- including emoji, CJK and Markdown -- is
    posted verbatim.
    """
    return f"{CLARIFICATION_COMMENT_PREFIX}\n\n" + "\n".join(questions)


def _github_issue_ref(state: RunState) -> tuple[str, str, int] | None:
    """``(owner, repo, issue_number)`` when ``state`` is a GitHub-sourced run
    whose task metadata carries the identifying triple plan 10-01's loader
    populates, else ``None`` (GIT-05).

    Structural, never a bare-string branch: ``source_kind`` is compared
    against :class:`~dark_factory.input.resolver.SourceKind.GITHUB` and the
    three metadata keys are read defensively, mirroring
    ``orchestrator/publish.py``'s ``_pr_body`` precedent -- a non-GitHub run,
    or a GitHub run whose metadata is somehow missing a key, both fold into
    ``None`` rather than raising.
    """
    if state.normalized_task.source_kind != SourceKind.GITHUB:
        return None
    metadata = state.normalized_task.metadata
    owner = metadata.get("owner")
    repo = metadata.get("repo")
    issue_number = metadata.get("issue_number")
    if not isinstance(owner, str) or not owner:
        return None
    if not isinstance(repo, str) or not repo:
        return None
    if not isinstance(issue_number, int):
        return None
    return owner, repo, issue_number


def _find_own_clarification_comment(
    client: GitHubClient, owner: str, repo: str, issue_number: int, *, body: str
) -> GitHubComment | None:
    """The clarification-comment analogue of ``publish.py``'s
    ``find_pull_request_for_branch`` existence check (CR-01, 10-REVIEW.md).

    A pure read, issued before ``create_comment`` ever runs: it answers "did
    Dark Factory's own identity already post this exact question text to
    this issue" so a process crash between a successful ``create_comment``
    call and the transaction that persists ``clarification_comment_id`` can
    self-heal on resume by adopting the already-posted comment instead of
    duplicate-posting the question -- the same partial-completion hazard
    ``run_publish_step`` closes for ``create_pull_request`` (10-RESEARCH.md
    Pitfall 1), applied to the other GitHub side effect this phase
    introduces.

    Matches on **both** author identity (``client.authenticated_login()`` --
    never spoofable by another commenter on the issue) and exact body
    equality (the verbatim text ``build_clarification_comment`` would
    produce for *this* attempt's question list) -- narrower than
    ``find_pull_request_for_branch``'s branch-only match, because an issue's
    comment list is not scoped to one Dark Factory run the way a branch name
    is: two different questions from two different attempts on the same
    issue must never be conflated.
    """
    issue = client.fetch_issue(owner, repo, issue_number=issue_number)
    own_login = client.authenticated_login()
    for comment in issue.comments:
        if comment.author == own_login and comment.body == body:
            return comment
    return None


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


# LOOP-02/LOOP-03/LOOP-04 (Phase 9, plan 09-02): maps the exhaustion reason
# string ``_bounce_or_fail`` writes into ``outcome["error"]`` back to the
# counter column it names, so the ``RUN_FAILED`` payload can carry the
# exhausted counter's name/value/cap without a second, divergent lookup.
_EXHAUSTION_REASON_TO_COUNTER: Mapping[str, str] = {
    "qa_developer_max_iterations_exhausted": "qa_developer_iterations",
    "quality_gate_max_iterations_exhausted": "quality_gate_iterations",
}


def _bounce_or_fail(
    *,
    current_value: int,
    cap: int,
    counter_name: str,
    exhaustion_reason: str,
    bounce_target: RoleNode | None,
) -> tuple[Signal, dict[str, int], str | None]:
    """Decide bounce vs. fail for a QA-verdict or quality-gate FAIL (D-04/D-06).

    When ``bounce_target`` exists and ``current_value`` is strictly less than
    ``cap``, the run bounces: returns ``Signal.ROLE_BOUNCED`` with a one-entry
    ``counter_increments`` mapping for ``counter_name`` and no error string. A
    cap of 0 needs no special case -- ``0 < 0`` is already false, so the very
    first rejection is terminal with no zero-value branch anywhere here.

    Otherwise the run fails: returns ``Signal.ROLE_FAILED`` with an empty
    increment mapping and an error string -- ``"no_earlier_role_to_bounce_to"``
    when ``bounce_target`` is ``None`` (LOOP-04's adjacency case: the failing
    role is the pipeline's first node, so there is nowhere to loop back to and
    the runner must never hand ``transition()`` a signal it would reject), or
    ``exhaustion_reason`` when the counter has simply reached its cap.
    """
    if bounce_target is not None and current_value < cap:
        return Signal.ROLE_BOUNCED, {counter_name: 1}, None
    if bounce_target is None:
        return Signal.ROLE_FAILED, {}, "no_earlier_role_to_bounce_to"
    return Signal.ROLE_FAILED, {}, exhaustion_reason


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

    Phase 10 (INTAKE-03 wiring half): the snapshot's ``repository`` block is
    passed straight into ``load`` so a ``github:`` locator can resolve --
    ``start_run`` still reads no live config itself, it only forwards the
    already-resolved snapshot value.
    """
    kind, locator = classify(source)
    task = load(kind, locator, repository=snapshot.get("repository"))
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
    github_client_factory: GitHubClientFactory = default_github_client_factory,
) -> RunStatus:
    """Reconstruct from Neon, execute exactly one committed step under the lease,
    return the new status.

    ``tool_registry`` defaults to :data:`~dark_factory.tools.default_registry`
    and is threaded straight through to :func:`_advance_once` -> (eventually)
    :func:`_run_current_role`, exactly mirroring how ``action_registry`` is
    already threaded -- the test injection seam for a synthetic capability
    (TOOL-02, SC3).

    ``github_client_factory`` defaults to :func:`default_github_client_factory`
    and is threaded straight through the same way, mirroring ``tool_registry``
    -- the test injection seam plans 10-02/10-03 reuse for
    :class:`~tests.support.fake_github.FakeGitHubClient`. Called lazily,
    only on the branch that actually needs a client.

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
            github_client_factory=github_client_factory,
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
    github_client_factory: GitHubClientFactory = default_github_client_factory,
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
    ``action_registry``. ``github_client_factory`` is threaded the same way.
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
            github_client_factory=github_client_factory,
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
    github_client_factory: GitHubClientFactory = default_github_client_factory,
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

    CR-01, plan 08-05: immediately after the worker call, and only when its
    signal is ``ROLE_COMPLETED``,
    :func:`~dark_factory.git.scope.enforce_artifact_scope` checks this
    attempt's changes under the run's own
    ``.dark-factory/runs/<run_id>/artifacts/`` tree against the role's own
    ``artifacts/<role>/`` subtree and reverts anything outside it, folding a
    violation into ``ROLE_FAILED`` exactly like every other post-worker
    check here. This runs **first**, before artifact collection/commit/push
    below, because D-09's schema check operates on artifact *content* the
    worker already wrote to disk, not on the repository diff --
    :func:`~dark_factory.git.scope.attempt_changed_paths` has nothing to
    say about the run tree at all, since it is gitignored and deliberately
    excluded by A-05-15 -- so nothing downstream of this check would
    otherwise catch a role that read or overwrote another role's artifact
    output. Once
    ``commit_run_artifacts`` below commits, a tampered path is folded into
    that commit and no longer visible to a ``HEAD`` diff; once
    ``push_working_branch`` runs it has left the machine -- so this check
    must come before both.

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
    key at all grants nothing (deny-by-default, never allow-by-omission).
    This read is now hoisted above the artifact-scope check above (plan
    08-05), since that check also needs it. ``granted`` is threaded into
    :func:`~dark_factory.artifacts.validation.collect_role_artifacts`, whose
    every artifact read now goes through
    ``tool_registry.invoke(role, "artifacts.read", granted, ...)``. A denied
    read raises :class:`~dark_factory.tools.CapabilityDeniedError`, caught in
    its own arm placed *before* the ``ArtifactError`` catch below so the
    denial's structured facts (role, capability, reason) can be captured
    separately: the overall ordering becomes **enforce artifact scope, then
    check the grant, then read, then validate, then commit, then push, then
    enforce write scope, then transition**, and a denial reuses the
    identical ``FAILED`` shape every
    other post-worker check here already writes (D-05).

    LOOP-02/LOOP-03/LOOP-04 (Phase 9, plan 09-02): for the pipeline's terminal
    role only, once the gate/verdict block above has run, the ordering is
    **fold the verdict, then run the gate, then check the relevant cap, then
    choose bounce-or-fail, then transition** -- the cap check happens before
    dispatch, per LOOP-03's literal wording. A FAIL verdict or a FAIL gate no
    longer downgrades unconditionally to ``ROLE_FAILED``: :func:`_bounce_or_fail`
    reads the relevant iteration counter (``qa_developer_iterations`` or
    ``quality_gate_iterations``) against its own configured cap and returns
    ``Signal.ROLE_BOUNCED`` under cap or ``Signal.ROLE_FAILED`` at/over it,
    with the chosen counter's increment riding the same ``apply_transition``
    call every other write in this function already commits through -- no new
    locking site is introduced for these two columns.

    GIT-03, D-07, D-09 (Phase 10, plan 10-06): immediately after a PASS gate
    result, still inside the terminal-role block and still gated on
    ``state.workflow["publishing"]["create_pr"]`` (default ``True``), this
    calls :func:`~dark_factory.orchestrator.publish.run_publish_step`.
    ``github_client_factory`` is called lazily -- only when ``create_pr`` is
    true -- so a run that publishes nothing never constructs a client and
    never needs ``github_token`` configured. A publish failure sets
    ``signal = Signal.ROLE_FAILED`` and folds the redacted error into
    ``outcome``, in the same shape the ``GitError`` catch below already uses,
    so a run whose PR was never created does not reach ``COMPLETED`` (T-10-32).
    The chosen ``PublishResult`` rides into the single ``apply_transition``
    call at the end of this function as ``publish_fields=PublishFieldsWrite(...)``.

    GIT-05, D-05, D-08 (Phase 10, plan 10-03): inside the ``Signal.ROLE_NEEDS_INPUT``
    arm, a GitHub-sourced run (:func:`_github_issue_ref` reads the owner/repo/
    issue-number triple from the persisted task metadata) posts the question as
    a fresh comment on the source issue via ``github_client_factory`` --
    skipped entirely when ``state.pending_clarification_comment_id`` is already
    set (D-05: check the persisted identifier before acting). The posted
    comment's id threads into the same ``HumanInteractionWrite(mode="ask",
    ...)`` that already builds, so the question and its comment id commit
    together in the one ``apply_transition`` call below. A ``GitHubError`` is
    caught, never propagated: the pause, the ``QUESTION_CREATED``/``RUN_PAUSED``
    events and the ``ask`` write are unchanged, ``clarification_comment_id``
    stays ``None``, and the redacted failure text rides the existing
    ``QUESTION_CREATED`` payload rather than a new event type -- a GitHub
    outage must never be able to lose a question a role actually asked.
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
    # GATE-01..04 (Phase 9, plan 09-01): populated only inside the terminal-role
    # gate block below; stays empty for every other role and for a run whose
    # terminal role never reaches ROLE_COMPLETED. Declared here, unconditionally,
    # so the event-dispatch ladder further down can splice it in with no
    # NameError regardless of which branch above actually ran.
    gate_events: list[EventWrite] = []
    # Phase 12 (plan 12-04), D-07: populated only inside the terminal-role
    # verdict block below, by exactly one QA_FAILED or QA_PASSED EventWrite --
    # stays empty for every other role and for a run whose terminal role
    # never reaches the verdict block. Declared here, unconditionally, for
    # the same NameError-avoidance reason ``gate_events`` is, so all three
    # signal arms below can splice it unconditionally.
    qa_verdict_events: list[EventWrite] = []
    # LOOP-02/LOOP-03/LOOP-04 (Phase 9, plan 09-02): ``counter_increments`` is
    # populated only inside the terminal-role gate block below, by
    # ``_bounce_or_fail``, and passed into ``apply_transition`` unconditionally
    # at the bottom of this function -- empty for every other role and for a
    # run whose terminal role never reaches the bounce/fail decision.
    # ``bounce_reason`` names which edge fired (``qa_verdict_fail`` or
    # ``quality_gate_fail``) for the ``ROLE_BOUNCED`` event's payload. Both
    # declared here, unconditionally, for the same NameError-avoidance reason
    # ``gate_events`` is.
    counter_increments: dict[str, int] = {}
    bounce_reason: str | None = None
    # GIT-03 (Phase 10, plan 10-06): populated only inside the terminal-role
    # gate-PASS block below, by ``run_publish_step`` -- stays ``None`` for
    # every other role, for a run that never reaches the terminal role's gate
    # PASS, and for a run whose ``publishing.create_pr`` is false (no publish
    # attempt is ever made). Declared here, unconditionally, so the
    # ``apply_transition`` call at the bottom of this function can build its
    # ``publish_fields`` keyword with no NameError regardless of which branch
    # above actually ran.
    publish_result: PublishResult | None = None
    # D-01/D-06: read once from the persisted snapshot -- ``.get`` with an
    # empty-list default means a legacy snapshot entry with no ``tools`` key
    # at all grants nothing (deny-by-default, never allow-by-omission).
    # Hoisted above both post-worker ROLE_COMPLETED blocks below (plan
    # 08-05, CR-01): the new artifact-scope check immediately below needs
    # this same grant list, and reading it once here keeps the two blocks
    # from ever computing it differently.
    granted = list(role_def.get("tools", []))
    # LOOP-03 (Phase 9, plan 09-02): the two iteration caps, read once from
    # the persisted snapshot the same defensive-dict way ``_role_definition``
    # and ``build_role_context`` already read ``state.workflow`` elsewhere --
    # never re-import ``dark_factory.config.loader`` here. The literal
    # fallbacks mirror ``RetryConfig``'s own declared defaults (3 and 2), so a
    # legacy snapshot with no ``retry`` key resolves identically to a fresh
    # one. Hoisted unconditionally (not just inside the terminal-role block)
    # so the RUN_FAILED exhaustion payload below can read them regardless of
    # which branch set ``signal`` to ``ROLE_FAILED``.
    retry_config = state.workflow.get("retry", {})
    qa_developer_max_iterations = retry_config.get("qa_developer_max_iterations", 3)
    quality_gate_max_iterations = retry_config.get("quality_gate_max_iterations", 2)
    _counter_caps = {
        "qa_developer_iterations": qa_developer_max_iterations,
        "quality_gate_iterations": quality_gate_max_iterations,
    }

    # CR-01, plan 08-05: enforce_artifact_scope is its own sibling
    # ROLE_COMPLETED block -- not a branch nested inside the block below --
    # the same shape enforce_write_scope already uses, placed BEFORE the
    # artifact validate/commit/push sequence. This ordering is load-bearing:
    # once commit_run_artifacts below commits this role's run-tree content,
    # a tampered path from an earlier role is folded into that commit and no
    # longer visible to a HEAD diff, and once push_working_branch runs it
    # has left the machine entirely -- so a violating change must be caught
    # and reverted before either of those can act on it. A violation reuses
    # the exact ROLE_FAILED/RUN_FAILED shape every other post-worker check
    # in this function already writes -- no new event type, no new
    # role-execution status.
    if signal is Signal.ROLE_COMPLETED:
        try:
            enforce_artifact_scope(
                work_dir,
                run_id,
                role=node.name,
                attempt=latest.attempt,
                granted=granted,
            )
        except ArtifactScopeViolation as exc:
            signal = Signal.ROLE_FAILED
            outcome = {**outcome, "error": str(exc)}

    if signal is Signal.ROLE_COMPLETED:
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

            # GATE-01..04 (Phase 9, plan 09-01): only for the pipeline's
            # terminal role -- detected structurally via
            # ``next_node(pipeline, node.name) is None``, the same predicate
            # the RUN_COMPLETED emission below already relies on, never a
            # role-name literal (tests/unit/test_no_role_name_literal.py).
            # Deliberately placed here, BEFORE commit_run_artifacts below,
            # rather than after enforce_write_scope as first sketched: the
            # gate writes verification/quality_gate.json into this same
            # gitignored run tree (``.dark-factory/runs/<run_id>/``), and
            # only a force-add against that whole tree -- exactly what
            # commit_run_artifacts below already does for this role's own
            # artifacts -- stages a *new* file under it. Writing the gate
            # result first means it rides that one existing commit, so no
            # second, distinctly-labelled commit is introduced for
            # tests/db/test_artifact_commit_per_role.py's "one artifact
            # commit per role" invariant to trip over, and the file survives
            # the terminal role's own worktree cleanup on COMPLETED (D-04)
            # instead of being silently lost: the cleanup pass's
            # ``wip_commit_if_dirty`` stages with a plain ``git add -A``,
            # which never picks up a brand-new file under an ignored path.
            if (
                signal is Signal.ROLE_COMPLETED
                and next_node(pipeline, node.name) is None
            ):
                verdict_write = next(
                    (w for w in artifact_writes if w.type == "verdict.json"), None
                )
                if verdict_write is not None:
                    verdict_text = read_artifact_text(run_dir, verdict_write.path)
                    verdict = Verdict.model_validate(json.loads(verdict_text))
                    # LOOP-02/LOOP-03/LOOP-04 (Phase 9, plan 09-02): the bounce
                    # target is always computed structurally -- never a
                    # role-name literal (tests/unit/test_no_role_name_literal.py).
                    bounce_target = previous_node(pipeline, node.name)

                    if verdict.computed_status is VerdictStatus.FAIL:
                        # GATE-01 keys the gate on QA having passed -- a FAIL
                        # verdict short-circuits before the gate ever runs.
                        # The cap is checked BEFORE the signal is chosen
                        # (LOOP-03): under cap bounces the run back to
                        # ``bounce_target`` with a fresh Developer attempt; at
                        # or over cap ends the run, same as plan 09-01's
                        # unconditional FAILED outcome did.
                        signal, counter_increments, bounce_error = _bounce_or_fail(
                            current_value=state.qa_developer_iterations,
                            cap=qa_developer_max_iterations,
                            counter_name="qa_developer_iterations",
                            exhaustion_reason="qa_developer_max_iterations_exhausted",
                            bounce_target=bounce_target,
                        )
                        if signal is Signal.ROLE_BOUNCED:
                            bounce_reason = "qa_verdict_fail"
                        else:
                            outcome = {**outcome, "error": bounce_error}
                        # Phase 12 (plan 12-04), D-07: the verdict fact rides
                        # independently of the bounce-vs-fail routing decision
                        # above -- a FAIL verdict always leaves exactly one
                        # QA_FAILED event, whichever arm the run then lands in.
                        qa_verdict_events.append(
                            EventWrite(
                                type=EventType.QA_FAILED,
                                role_execution_id=latest.id,
                                payload={
                                    "role": node.name,
                                    "criteria_failed": [
                                        c.criterion_id
                                        for c in verdict.criteria
                                        if c.result is VerdictStatus.FAIL
                                    ],
                                },
                            )
                        )
                    else:
                        # Phase 12 (plan 12-04), D-07: a PASS verdict is
                        # recorded alongside the quality-gate events this
                        # branch is about to build -- the two signal
                        # families answer different questions and must
                        # coexist, never substitute for one another.
                        qa_verdict_events.append(
                            EventWrite(
                                type=EventType.QA_PASSED,
                                role_execution_id=latest.id,
                                payload={"role": node.name},
                            )
                        )
                        gate_commands = list(
                            state.workflow.get("quality_gate", {}).get("commands", [])
                        )
                        gate_settings = get_settings()
                        gate_result = run_quality_gate(
                            commands=gate_commands,
                            cwd=work_dir,
                            timeout=gate_settings.worker_timeout_seconds,
                            known_secrets=gate_settings.known_secret_values(),
                        )
                        gate_path = write_quality_gate_result(run_dir, gate_result)
                        exit_codes = [c.exit_code for c in gate_result.commands]
                        gate_events = [
                            EventWrite(
                                type=EventType.QUALITY_GATE_STARTED,
                                payload={
                                    "role": node.name,
                                    "command_count": len(gate_commands),
                                },
                            ),
                        ]
                        if gate_result.status is VerdictStatus.PASS:
                            gate_events.append(
                                EventWrite(
                                    type=EventType.QUALITY_GATE_PASSED,
                                    payload={
                                        "role": node.name,
                                        "path": gate_path,
                                        "exit_codes": exit_codes,
                                    },
                                )
                            )
                            # GIT-03, D-07, D-09 (Phase 10, plan 10-06):
                            # publishing is gated solely on
                            # ``publishing.create_pr`` (default true) -- when
                            # false, no client is ever constructed and no
                            # publish attempt (and no PUBLISH_* event) is
                            # made at all, so a run with no GitHub
                            # configuration keeps completing exactly as it
                            # did before this phase.
                            publishing_config = state.workflow.get("publishing") or {}
                            if publishing_config.get("create_pr", True):
                                gate_events.append(
                                    EventWrite(
                                        type=EventType.PUBLISH_STARTED,
                                        payload={"role": node.name},
                                    )
                                )
                                # A construction failure (most commonly
                                # MissingGitHubCredentialError -- no
                                # `github_token` configured for a repository
                                # that publishes) is folded into the same
                                # PublishResult.error shape run_publish_step
                                # itself returns for a create_pull_request
                                # failure, rather than propagating uncaught.
                                try:
                                    publish_client = github_client_factory()
                                except GitHubError as exc:
                                    publish_result = PublishResult(
                                        published_commit_sha=None,
                                        pr_number=None,
                                        pr_url=None,
                                        error=str(
                                            redact(
                                                str(exc),
                                                known_secrets=(
                                                    gate_settings.known_secret_values()
                                                ),
                                            )
                                        ),
                                    )
                                else:
                                    publish_result = run_publish_step(
                                        run_id=run_id,
                                        state=state,
                                        work_dir=work_dir,
                                        client=publish_client,
                                        create_pr=True,
                                        known_secrets=(
                                            gate_settings.known_secret_values()
                                        ),
                                        push_token=(
                                            gate_settings.github_token.get_secret_value()
                                            if gate_settings.github_token is not None
                                            else None
                                        ),
                                    )
                                if publish_result.error is None:
                                    gate_events.append(
                                        EventWrite(
                                            type=EventType.PR_CREATED,
                                            payload={
                                                "pr_number": (publish_result.pr_number),
                                                "pr_url": publish_result.pr_url,
                                            },
                                        )
                                    )
                                else:
                                    gate_events.append(
                                        EventWrite(
                                            type=EventType.PUBLISH_FAILED,
                                            payload={"error": publish_result.error},
                                        )
                                    )
                                    # T-10-32: a run whose PR was never
                                    # created must not reach COMPLETED --
                                    # fold the error into `outcome` in the
                                    # same shape the GitError catch below
                                    # already uses.
                                    signal = Signal.ROLE_FAILED
                                    outcome = {
                                        **outcome,
                                        "error": publish_result.error,
                                    }
                        else:
                            gate_events.append(
                                EventWrite(
                                    type=EventType.QUALITY_GATE_FAILED,
                                    payload={
                                        "role": node.name,
                                        "path": gate_path,
                                        "exit_codes": exit_codes,
                                    },
                                )
                            )
                            # LOOP-02/LOOP-03/LOOP-04: same cap-then-choose
                            # decision as the QA-verdict branch above, keyed
                            # on the gate's own independent counter/cap pair
                            # (D-06) -- at most one of the two counters is
                            # ever touched in a single attempt, because the
                            # verdict FAIL branch above already short-circuits
                            # before the gate ever runs.
                            signal, counter_increments, bounce_error = _bounce_or_fail(
                                current_value=state.quality_gate_iterations,
                                cap=quality_gate_max_iterations,
                                counter_name="quality_gate_iterations",
                                exhaustion_reason=(
                                    "quality_gate_max_iterations_exhausted"
                                ),
                                bounce_target=bounce_target,
                            )
                            if signal is Signal.ROLE_BOUNCED:
                                bounce_reason = "quality_gate_fail"
                            else:
                                outcome = {**outcome, "error": bounce_error}

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
                # The gate's own result -- if it ran -- rode the same commit
                # this except block just discovered never happened; its
                # audit events must not claim a persisted fact that was
                # never actually durable.
                gate_events = []
                # Phase 12 (plan 12-04), D-07: identical reasoning -- a
                # verdict decision whose commit never landed must leave no
                # event claiming the run durably acted on it.
                qa_verdict_events = []
                # A bounce decision made above (if any) is void once the
                # commit/push that would have carried it never landed: the
                # signal is now ROLE_FAILED, so neither the counter increment
                # nor the bounce reason must survive to the dispatch below.
                counter_increments = {}
                bounce_reason = None

    # ROLE-05, D-12/D-13/D-14 (Phase 5, plan 05-04). Widened in gap CR-01
    # (Phase 9, plan 09-04): enforce_write_scope runs for every signal under
    # which this attempt's worktree changes are *retained* rather than
    # ending the run outright -- that is ``ROLE_COMPLETED`` and
    # ``ROLE_BOUNCED`` -- never only ``ROLE_COMPLETED``. A bounce is the
    # sharper of the two cases, not the safer one: a failed run has no
    # downstream role left to contaminate, whereas a bounce hands the
    # worktree to an earlier role, whose own WIP-recovery commit would
    # otherwise silently absorb an out-of-scope write under that earlier
    # role's name -- an authorization bypass wearing a routing decision's
    # clothes. The patterns are read from the persisted snapshot's role
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
    if signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED):
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
            # CR-01: a scope violation turns a would-be bounce into a
            # genuine failure, so the bounce decision's side effects must
            # not survive the downgrade -- an increment applied for a loop
            # iteration that never happened would silently spend the
            # operator's configured retry budget, and a non-empty
            # ``counter_increments`` paired with ``ROLE_FAILED`` would also
            # be dispatched into ``apply_transition`` as a real column
            # write. Deliberately NOT mirrored from this block:
            # ``gate_events`` is left alone -- by the time this check runs,
            # ``commit_run_artifacts`` has already succeeded and the gate
            # artifact is durably on the working branch, so its
            # ``QUALITY_GATE_*`` events remain true statements and must
            # still be emitted on the ``ROLE_FAILED`` path.
            counter_increments = {}
            bounce_reason = None

    # Phase 12 (plan 12-01), D-06, Pitfall 3: built ONCE from the final
    # `artifact_writes` value, after every arm above that can reset it to an
    # empty list has already run (the `WriteScopeViolation` block
    # immediately above included) and before `transition()` below -- so an
    # `ARTIFACT_CREATED` event is never emitted for an artifact row this
    # attempt will not actually write. One event per write, mirroring
    # `gate_events`'s own accumulate-then-splice shape; spliced into the
    # `ROLE_COMPLETED` and `ROLE_BOUNCED` arms only, never `ROLE_FAILED` /
    # `ROLE_NEEDS_INPUT` -- `artifact_writes` is already empty by the time
    # either of those runs, so an empty splice there would be dead code
    # claiming a decision it is not making.
    artifact_events = [
        EventWrite(
            type=EventType.ARTIFACT_CREATED,
            role_execution_id=latest.id,
            payload={"role": node.name, "type": w.type, "path": w.path},
        )
        for w in artifact_writes
    ]

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
        # GATE-01..04 (Phase 9, plan 09-01): the gate's own audit events (if
        # it ran) belong between "the role finished" and "the run completed"
        # -- the audit order reads "the role finished, then the gate ran,
        # then the run completed". Empty for every role but the pipeline's
        # terminal one, so this is a no-op for BA/ARCHITECTURE/DEVELOPMENT.
        events.extend(gate_events)
        # Phase 12 (plan 12-04), D-07: the QA-verdict fact rides alongside
        # this generic ROLE_COMPLETED, never instead of it -- empty for
        # every role but the pipeline's terminal one.
        events.extend(qa_verdict_events)
        # Phase 12 (plan 12-01), D-06: one ARTIFACT_CREATED per artifact this
        # attempt actually wrote, rides the same apply_transition call as the
        # artifacts rows below it ties to -- empty for an attempt that wrote
        # no declared machine artifact.
        events.extend(artifact_events)
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
        # LOOP-04 (Phase 9, plan 09-02): when this FAILED outcome is one of
        # the two exhaustion reasons `_bounce_or_fail` names, the RUN_FAILED
        # payload also carries the exhausted counter's name, its
        # (pre-increment -- exhaustion never increments further) value and
        # its configured cap, so the reason is persisted as machine-readable
        # fact, not only as a string. A no-earlier-role-to-bounce-to failure
        # and every pre-Phase-9 failure reason are untouched: the lookup
        # simply misses and the payload stays `{"role": node.name}`.
        run_failed_payload: dict[str, Any] = {"role": node.name}
        exhausted_counter = _EXHAUSTION_REASON_TO_COUNTER.get(outcome.get("error", ""))
        if exhausted_counter is not None:
            run_failed_payload = {
                **run_failed_payload,
                "reason": outcome["error"],
                "counter": exhausted_counter,
                "value": getattr(state, exhausted_counter),
                "cap": _counter_caps[exhausted_counter],
            }
        events = [
            EventWrite(
                type=EventType.ROLE_FAILED,
                payload={
                    "role": node.name,
                    "error": outcome.get("error") or result.summary,
                },
            ),
            EventWrite(type=EventType.RUN_FAILED, payload=run_failed_payload),
        ]
        # GATE-01..04 (Phase 9, plan 09-01): a gate that ran and failed (or a
        # commit/push failure discovered after it ran) still needs its own
        # audit trace -- appended after the ROLE_FAILED/RUN_FAILED pair
        # (and after any capability_denial prepend below), never instead of
        # them. Empty whenever the gate never ran (verdict FAIL
        # short-circuit, an earlier failure, or a non-terminal role).
        events.extend(gate_events)
        # Phase 12 (plan 12-04), D-07: a FAIL verdict at or over the
        # iteration cap still carries its QA_FAILED event into this arm --
        # the QA-outcome signal must survive into whichever arm the run
        # lands in, including the dead-run case.
        events.extend(qa_verdict_events)
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
    elif signal is Signal.ROLE_BOUNCED:
        # LOOP-02/LOOP-03/LOOP-04 (Phase 9, plan 09-02): the worker itself
        # genuinely completed -- only the run-level routing differs -- so
        # `re_status` stays "COMPLETED", never a new status string. This is
        # load-bearing for plan 09-03: `context/builder.py`'s
        # `_latest_completed_execution` filters on
        # `RoleExecution.status == "COMPLETED"`, so a bounced QA attempt
        # must stay visible to that filter for the Developer's next attempt
        # to resolve `verdict.json`/`quality_gate.json` feedback at all.
        re_status = _ROLE_COMPLETED
        re_result = outcome
        re_error = None
        events = [
            EventWrite(
                type=EventType.ROLE_COMPLETED,
                payload={"role": node.name, "summary": result.summary},
            ),
        ]
        # Audit order: "the role finished, then the gate ran (if it ran),
        # then the run bounced" -- mirrors the ROLE_COMPLETED arm's ordering.
        events.extend(gate_events)
        # Phase 12 (plan 12-04), D-07: a FAIL verdict under the cap still
        # carries its QA_FAILED event into this arm -- mirrors the
        # ROLE_COMPLETED arm's splice.
        events.extend(qa_verdict_events)
        # Phase 12 (plan 12-01), D-06: same splice as the ROLE_COMPLETED arm
        # -- a bounced attempt's own artifacts are still durable (ROLE-05's
        # enforce_write_scope already ran above and left artifact_writes
        # intact for this signal), so its ARTIFACT_CREATED events must still
        # be emitted.
        events.extend(artifact_events)
        (bounced_counter_name, bounced_counter_delta) = next(
            iter(counter_increments.items())
        )
        events.append(
            EventWrite(
                type=EventType.ROLE_BOUNCED,
                payload={
                    "role": node.name,
                    "reason": bounce_reason,
                    "counter": bounced_counter_name,
                    # The value BEFORE this attempt's increment -- `state` was
                    # loaded at the top of this step, before the decision.
                    "value": getattr(state, bounced_counter_name),
                    "cap": _counter_caps[bounced_counter_name],
                },
            )
        )
        assert bounced_counter_delta == 1  # _bounce_or_fail's only shape
    elif signal is Signal.ROLE_NEEDS_INPUT:
        # Mirror the failure arm's shape. The serialised NEEDS_INPUT outcome MUST
        # be stored, not discarded: it is what a resume validates back into
        # ``previous``.
        re_status = _ROLE_WAITING_HUMAN
        re_result = outcome
        re_error = None
        question_payload: dict[str, Any] = {
            "role": node.name,
            "questions": list(result.questions),
        }

        # GIT-05, D-05/D-08 (Phase 10, plan 10-03); crash-safety net CR-01
        # (10-REVIEW.md, Phase 10, plan 10-fix): give a GitHub-sourced run a
        # voice on its own issue. The persisted-identifier check (D-05) comes
        # first -- a pending interaction that already carries a
        # ``clarification_comment_id`` is never re-posted, and issues zero
        # GitHub calls. A non-GitHub run (``_github_issue_ref`` returns
        # ``None``) never constructs a client and never calls
        # ``github_client_factory`` at all.
        #
        # Before ever calling ``create_comment`` -- an external, non-
        # idempotent side effect -- ``_find_own_clarification_comment`` asks
        # GitHub itself whether Dark Factory's own identity already posted
        # this exact question text to this issue (mirrors
        # ``orchestrator/publish.py``'s ``find_pull_request_for_branch``
        # existence check before ``create_pull_request``). This closes the
        # crash window between a successful ``create_comment`` call and the
        # single ``apply_transition`` call below that persists
        # ``clarification_comment_id``: a process killed in that window
        # leaves nothing committed, so a resumed attempt that reaches this
        # branch again finds the already-posted comment and adopts it
        # instead of posting a duplicate.
        clarification_comment_id = state.pending_clarification_comment_id
        issue_ref = _github_issue_ref(state)
        if issue_ref is not None and clarification_comment_id is None:
            owner, repo, issue_number = issue_ref
            # T-12-08 (OBS-01, SEC-01/SEC-02): a GitHub issue comment is an
            # external, public, non-revocable sink -- scrub once, before the
            # idempotency lookup, so both ``_find_own_clarification_comment``
            # and ``create_comment`` consume the identical scrubbed value.
            # Redacting only at the ``create_comment`` call (and not before
            # the lookup) would make a resumed attempt compare raw text
            # against its own already-posted *scrubbed* body, fail to match,
            # and post a duplicate comment to a real GitHub issue (D-05).
            clarification_body = build_clarification_comment(result.questions)
            comment_body = redact(
                clarification_body,
                known_secrets=get_settings().known_secret_values(),
            )
            try:
                client = github_client_factory()
                existing_comment = _find_own_clarification_comment(
                    client, owner, repo, issue_number, body=comment_body
                )
                comment = existing_comment or client.create_comment(
                    owner,
                    repo,
                    issue_number=issue_number,
                    body=comment_body,
                )
            except GitHubError as exc:
                # Fail soft, never silent (D-08): the pause, the events and
                # the ``ask`` write still commit unchanged --
                # ``clarification_comment_id`` simply stays ``None``, so
                # ``resume --answer`` still works and a later attempt can
                # post. The redacted failure text rides the existing
                # QUESTION_CREATED payload rather than a new event type.
                question_payload = {
                    **question_payload,
                    "clarification_comment_error": str(
                        redact(
                            str(exc),
                            known_secrets=get_settings().known_secret_values(),
                        )
                    ),
                }
            else:
                clarification_comment_id = comment.id

        events = [
            EventWrite(type=EventType.QUESTION_CREATED, payload=question_payload),
            EventWrite(type=EventType.RUN_PAUSED, payload={"role": node.name}),
        ]
        human_interaction = HumanInteractionWrite(
            mode="ask",
            role_execution_id=latest.id,
            question="\n".join(result.questions),
            clarification_comment_id=clarification_comment_id,
        )
    else:  # pragma: no cover - transition() already rejects any other signal
        raise IllegalTransitionError(f"runner cannot act on {signal.value}")

    # GIT-03/GIT-04, D-06 (Phase 10, plan 10-06): non-None only when the
    # terminal-role gate-PASS block above actually attempted a publish --
    # ``None`` (a no-op patch) for every other role and for a run whose
    # ``publishing.create_pr`` is false, so a run that never publishes leaves
    # every publish-identifier column untouched.
    publish_fields = (
        PublishFieldsWrite(
            pr_number=publish_result.pr_number,
            pr_url=publish_result.pr_url,
            published_commit_sha=publish_result.published_commit_sha,
        )
        if publish_result is not None
        else None
    )

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
            counter_increments=counter_increments or None,
            expected_owner_token=lease.token,
            human_interaction=human_interaction,
            artifact_references=artifact_writes,
            publish_fields=publish_fields,
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
    github_client_factory: GitHubClientFactory = default_github_client_factory,
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
    loop, mirroring ``action_registry``. ``github_client_factory`` is
    threaded the same way.
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
                github_client_factory=github_client_factory,
            )
            if new_status != status and on_transition is not None:
                on_transition(status, new_status)
            status = new_status

    raise DriveLoopExhausted(
        f"drive loop for {run_id} exceeded {_MAX_DRIVE_ITERATIONS} iterations"
    )
