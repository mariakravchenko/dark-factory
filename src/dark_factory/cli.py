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

from uuid import UUID

import typer

from dark_factory.domain.status import RunStatus
from dark_factory.input.loaders import SourceNotSupportedError
from dark_factory.input.resolver import UnresolvableSourceError
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


def _drive_and_exit(run_id: UUID) -> None:
    final = drive(run_id, on_transition=_echo_transition)
    _echo_summary(run_id, final)
    raise typer.Exit(code=0 if final is RunStatus.COMPLETED else 1)


@app.command()
def run(source: str) -> None:
    """Start a run from a ``text:`` / ``spec:`` / ``github:`` source and drive it."""
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
