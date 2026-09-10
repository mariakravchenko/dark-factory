"""The Typer CLI: ``run`` and ``resume`` (D-01 / D-03 / D-04 / D-05).

Both commands are thin wrappers around the same drive loop over the resume-first
``advance``. They contain no lifecycle logic: a command that inspected the run
status to decide what to do next would be doing the orchestrator's job.

Output contract, asserted by Plans 07-09:

* stdout line 1 is the bare run id, printed immediately after the ``runs`` row is
  committed and *before* the drive loop -- a process killed mid-run still leaves
  the operator an id to pass to ``resume`` (D-01);
* then one line per state transition in ``PREVIOUS -> NEXT`` form (D-04);
* then a short summary block: run id, terminal state, last role, attempt.

Exit codes (D-05): ``0`` for COMPLETED, ``1`` for a persisted FAILED, ``2`` for a
bad invocation where nothing was persisted (unresolvable input, unsupported
source, unknown run id).
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from uuid import UUID

import structlog
import typer

from dark_factory.config.loader import ConfigError, load_effective_config
from dark_factory.config.settings import get_settings
from dark_factory.domain.status import RunStatus
from dark_factory.events.redaction import redact
from dark_factory.input.loaders import SourceNotSupportedError
from dark_factory.input.resolver import UnresolvableSourceError
from dark_factory.logging import configure_logging
from dark_factory.observability.status import UnknownRunError, read_status
from dark_factory.orchestrator.answers import (
    NoPendingInteraction,
    NotWaitingForHuman,
    submit_answer,
)
from dark_factory.orchestrator.lease import LeaseNotAcquired
from dark_factory.orchestrator.lifecycle import IllegalTransitionError
from dark_factory.orchestrator.runner import (
    DriveLoopExhausted,
    RunNotFoundError,
    drive,
    run_state,
    start_run,
)
from dark_factory.persistence.mutations import ConcurrentTransition, LeaseLost
from dark_factory.workers.fake import ScriptExhaustedError
from dark_factory.workers.registry import UnknownWorkerError

app = typer.Typer(no_args_is_help=True, add_completion=False)

_ARROW = "→"

# Orchestration errors that mean "the run could not be advanced and nothing new
# was persisted": distinct from a persisted FAILED terminal (exit 1). They exit
# 2 -- the same "not a clean terminal outcome / nothing persisted" code as a bad
# invocation -- rather than escaping as a traceback with Typer's default exit 1,
# which an operator scripting the D-05 contract would misread as "failed and
# recorded" (cli docstring; D-05).
_ORCHESTRATION_ERRORS = (
    ConcurrentTransition,
    IllegalTransitionError,
    DriveLoopExhausted,
    RunNotFoundError,
    ScriptExhaustedError,
    UnknownWorkerError,
    LeaseLost,
    NotWaitingForHuman,
    NoPendingInteraction,
    # ``apply_transition`` and its helpers raise bare ``LookupError`` when a
    # row vanishes mid-operation (``runs`` gone at lock time, a
    # ``role_executions`` row to update missing, no WAITING ``human_interaction``
    # in answer mode) and bare ``ValueError`` from the ``RoleExecutionWrite`` /
    # ``HumanInteractionWrite`` guards. Without these, such a failure escapes as
    # an unhandled traceback and Typer exits 1 -- the code D-05 reserves for
    # "persisted FAILED" -- which an operator scripting the contract misreads.
    LookupError,
    ValueError,
)


def _echo_transition(previous: RunStatus, new: RunStatus) -> None:
    typer.echo(f"{previous.value} {_ARROW} {new.value}")


def _echo_summary(run_id: UUID, final: RunStatus) -> None:
    state = run_state(run_id)
    last_role = state.current_role if state is not None else None
    attempt = (
        state.latest_execution.attempt
        if state is not None and state.latest_execution is not None
        else None
    )
    typer.echo("")
    typer.echo(f"run {run_id}")
    typer.echo(f"  terminal state: {final.value}")
    typer.echo(f"  last role:      {last_role}")
    typer.echo(f"  attempt:        {attempt}")


def _route_logs_to_stderr() -> None:
    """Install the production structlog chain (redaction processor included) with
    every log line going to **stderr**.

    Two reasons this runs before any lifecycle work on ``run`` / ``resume`` /
    ``status --json``:

    * without it, structlog is in its library-default configuration -- no
      ``_redaction_processor`` -- so the first ``log.*`` call added anywhere on
      the advance path would bypass ``redact()`` (the project credential-boundary
      invariant: credentials must never reach logs);
    * library-default structlog also writes to **stdout**, which would interleave
      JSON/console lines into the parseable ``run`` output contract (run id on
      line 1, one ``PREVIOUS -> NEXT`` line per transition, D-04) and the
      ``status --json`` object (D-13, T-01-34).
    """
    configure_logging(structlog.PrintLoggerFactory(file=sys.stderr))


_CLEAN_FINALS = (RunStatus.COMPLETED, RunStatus.WAITING_HUMAN)


def _report_orchestration_error(run_id: UUID, exc: Exception) -> typer.Exit:
    typer.echo(
        f"run {run_id} could not be advanced ({type(exc).__name__}): {exc}; "
        "nothing new was persisted -- inspect with 'dark-factory status'",
        err=True,
    )
    return typer.Exit(code=2)


def _report_lease_not_acquired(run_id: UUID) -> typer.Exit:
    # Losing the race for ownership is a normal result, not a fault: exit 0.
    typer.echo(
        f"run {run_id} is owned by another process; exiting without changes",
        err=True,
    )
    return typer.Exit(code=0)


def _drive_and_exit(run_id: UUID) -> None:
    try:
        final = drive(run_id, on_transition=_echo_transition)
    except LeaseNotAcquired as exc:
        raise _report_lease_not_acquired(run_id) from exc
    except _ORCHESTRATION_ERRORS as exc:
        raise _report_orchestration_error(run_id, exc) from exc
    _echo_summary(run_id, final)
    # A clean pause (WAITING_HUMAN) is a success -- the operator's process did
    # exactly what it was supposed to and there is nothing to retry.
    raise typer.Exit(code=0 if final in _CLEAN_FINALS else 1)


@app.command()
def run(source: str) -> None:
    """Start a run from a ``text:`` / ``spec:`` / ``github:`` source and drive it.

    The effective-config snapshot is resolved from ``.dark-factory.yaml`` under
    the current working directory *before* the run is created; a ``ConfigError``
    (unknown role / worker / action name, missing / oversized / escaping
    instruction file, empty or non-mapping YAML) exits 2 with nothing on stdout
    and no ``runs`` row. This command is the single composition point that reads
    repo config -- the orchestrator never does (config is never re-read live on
    resume).
    """
    _route_logs_to_stderr()
    try:
        snapshot = load_effective_config(Path.cwd())
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    try:
        run_id = start_run(source, snapshot=snapshot)
    except (UnresolvableSourceError, SourceNotSupportedError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(str(run_id))
    _drive_and_exit(run_id)


@app.command()
def resume(
    run_id: str,
    answer: str | None = typer.Option(
        None,
        "--answer",
        help="Answer the run's open human question, then resume it.",
    ),
) -> None:
    """Resume an existing run by id.

    Without ``--answer`` this is the identical Phase 1 drive loop (D-03): re-drive
    a run that stopped for a non-human reason. With ``--answer`` it first records
    the answer to the run's open question (``submit_answer``) and then enters the
    same loop. The command never inspects the run status to decide what to do --
    it branches on the presence of the option and on exception types only.
    """
    _route_logs_to_stderr()
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        typer.echo(f"not a run id: {run_id}", err=True)
        raise typer.Exit(code=2) from exc
    if run_state(parsed) is None:
        typer.echo(f"unknown run: {run_id}", err=True)
        raise typer.Exit(code=2)
    typer.echo(str(parsed))
    if answer is not None:
        try:
            submit_answer(parsed, answer)
        except LeaseNotAcquired as exc:
            raise _report_lease_not_acquired(parsed) from exc
        except _ORCHESTRATION_ERRORS as exc:
            raise _report_orchestration_error(parsed, exc) from exc
    _drive_and_exit(parsed)


@app.command()
def status(
    run_id: str,
    output_json: bool = typer.Option(
        False, "--json", help="Emit one JSON object instead of the text field list."
    ),
) -> None:
    """Report where a run is -- read from state columns, never the event log (D-11 / D-12).

    A pure read: it calls ``read_status`` and renders. It never inspects the
    status to decide on an action -- that is the orchestrator's job, and letting
    a read command grow a decision is exactly what Phase 11's single-``advance``
    funnel starts by refusing.
    """
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        typer.echo(f"not a run id: {run_id}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        view = read_status(parsed)
    except UnknownRunError as exc:
        typer.echo(f"unknown run: {run_id}", err=True)
        raise typer.Exit(code=2) from exc

    redactor = functools.partial(
        redact, known_secrets=get_settings().known_secret_values()
    )
    if output_json:
        _route_logs_to_stderr()
        typer.echo(view.as_json(redactor=redactor))
    else:
        typer.echo(view.as_text(redactor=redactor))
