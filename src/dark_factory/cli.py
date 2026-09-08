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
from uuid import UUID

import structlog
import typer

from dark_factory.config.settings import get_settings
from dark_factory.domain.status import RunStatus
from dark_factory.events.redaction import redact
from dark_factory.input.loaders import SourceNotSupportedError
from dark_factory.input.resolver import UnresolvableSourceError
from dark_factory.logging import configure_logging
from dark_factory.observability.status import UnknownRunError, read_status
from dark_factory.orchestrator.runner import drive, run_state, start_run

app = typer.Typer(no_args_is_help=True, add_completion=False)

_ARROW = "→"


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


def _drive_and_exit(run_id: UUID) -> None:
    final = drive(run_id, on_transition=_echo_transition)
    _echo_summary(run_id, final)
    raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)


@app.command()
def run(source: str) -> None:
    """Start a run from a ``text:`` / ``spec:`` / ``github:`` source and drive it."""
    _route_logs_to_stderr()
    try:
        run_id = start_run(source)
    except (UnresolvableSourceError, SourceNotSupportedError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(str(run_id))
    _drive_and_exit(run_id)


@app.command()
def resume(run_id: str) -> None:
    """Resume an existing run by id -- the identical drive loop, no other argument (D-03)."""
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
