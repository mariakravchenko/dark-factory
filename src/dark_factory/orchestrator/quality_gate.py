"""The independent quality gate (D-01, D-09, D-10, D-11; GATE-01..04).

Once the pipeline's terminal role's own attempt transitions to
``ROLE_COMPLETED`` with a PASS ``verdict.json``, ``orchestrator/runner.py``
calls :func:`run_quality_gate` directly -- a plain function call, never
through ``ToolRegistry`` (D-01: the gate is an orchestrator-only step, with
no ``WorkerRegistry`` entry, no role config and no ``role_executions`` row of
its own). Every configured command runs through
:func:`dark_factory.tools.env.shell_execute`, in the run's own worktree
(D-03), with :class:`~dark_factory.config.settings.Settings`'s single
``worker_timeout_seconds`` knob (D-10) -- never a bespoke ``subprocess`` call
and never a second timeout concept.

The PASS/FAIL fold is a computed field, never a constructor argument
(:class:`QualityGateResult.status`) -- the same "never hand-set, always
derived" discipline :class:`dark_factory.domain.artifacts.Verdict`'s own
``computed_status`` already uses. All commands run to completion regardless
of an earlier failure (D-09): the Developer's next bounce gets every
command's result in one pass, not one failure discovered per iteration.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, computed_field

from dark_factory.artifacts.paths import resolve_under_run_root
from dark_factory.domain.status import VerdictStatus
from dark_factory.events.redaction import redact
from dark_factory.tools.env import shell_execute

__all__ = [
    "GateCommandResult",
    "QualityGateResult",
    "run_quality_gate",
    "write_quality_gate_result",
]

# T-09-06: the cap a single captured stream (stdout or stderr) may occupy in
# the persisted result, applied *after* redaction. verification/quality_gate.json
# is read back through dark_factory.artifacts.store.read_artifact_text, whose
# own _MAX_ARTIFACT_BYTES cap (262144) would otherwise make an unbounded
# failure dump (e.g. a large pytest traceback) unreadable and crash a later
# role attempt.
_MAX_CAPTURED_OUTPUT_BYTES = 16 * 1024

# Deliberately not one of the six RunStatus role values -- this is the
# `role` argument threaded into `shell_execute` (and, purely for git commit
# message text, into `commit_run_artifacts`), naming the orchestrator-only
# nature of every gate-spawned child process (T-09-01). Never a RunStatus
# role literal, so tests/unit/test_no_role_name_literal.py stays green.
_QUALITY_GATE_ROLE_LABEL = "quality_gate"


def _cap_output(text: str) -> str:
    """Tail-preserve ``text`` to at most :data:`_MAX_CAPTURED_OUTPUT_BYTES`
    bytes, prepending an explicit marker naming the dropped byte count when
    truncation happens -- never a silent truncation.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= _MAX_CAPTURED_OUTPUT_BYTES:
        return text

    dropped = len(encoded) - _MAX_CAPTURED_OUTPUT_BYTES
    marker = f"[dark-factory: {dropped} bytes dropped from the head of this stream]\n"
    marker_bytes = marker.encode("utf-8")
    budget = max(_MAX_CAPTURED_OUTPUT_BYTES - len(marker_bytes), 0)
    tail = encoded[len(encoded) - budget :] if budget else b""
    return marker + tail.decode("utf-8", errors="ignore")


class GateCommandResult(BaseModel):
    """One command's outcome inside a quality-gate run (D-11).

    Mirrors :class:`dark_factory.tools.env.ShellResult` plus the originating
    command string -- exactly five fields, named to match. Do not add a
    sixth field; D-11 pins this shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


class QualityGateResult(BaseModel):
    """The whole gate run's outcome (D-11).

    ``status`` is a :func:`pydantic.computed_field` over a ``@property``,
    never a constructor argument -- passing ``status=`` raises a pydantic
    ``ValidationError`` (``extra="forbid"`` plus no such declared field),
    which is what makes "never hand-set" structural rather than a
    convention, exactly like
    :attr:`dark_factory.domain.artifacts.Verdict.computed_status`. A
    zero-length ``commands`` list folds to PASS with no empty-list special
    case, the same way ``Verdict.computed_status``'s ``all(...)`` does.
    Pydantic serialises computed fields after declared fields, so
    ``model_dump_json()``'s key order is ``commands`` then ``status`` --
    that is correct and must not be worked around by adding a settable
    ``status`` field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    commands: list[GateCommandResult]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> VerdictStatus:
        """PASS iff every command exited 0 and did not time out."""
        all_commands_ok = all(
            entry.exit_code == 0 and not entry.timed_out for entry in self.commands
        )
        if all_commands_ok:
            return VerdictStatus.PASS
        return VerdictStatus.FAIL


def run_quality_gate(
    *,
    commands: Sequence[str],
    cwd: Path,
    timeout: int,
    known_secrets: Mapping[str, str],
) -> QualityGateResult:
    """Run every entry in ``commands``, in order, through
    :func:`dark_factory.tools.env.shell_execute`; never stop at the first
    failure (D-09).

    Each configured command string is converted to an argv list with
    :func:`shlex.split` before the call -- ``shell_execute``'s ``command``
    parameter is a ``Sequence[str]`` and explicitly rejects a bare string
    (it would have to be split or shell-interpreted to run at all, reopening
    the command-injection surface T-06-02 exists to close).
    ``shell_execute`` is called directly as a plain function, with
    ``role="quality_gate"`` -- no ``ToolRegistry`` involvement, matching
    ``shell_execute``'s own documented contract for orchestrator-invoked
    calls.

    Each captured ``stdout`` / ``stderr``, and the configured ``command``
    string itself, are redacted (:func:`dark_factory.events.redaction.redact`,
    patterns enabled) against ``known_secrets`` before the result is
    constructed -- the cap is applied to ``stdout``/``stderr`` afterward
    (T-09-03) but never to ``command``, so no unredacted copy of a leaked
    credential ever exists in the returned model. The command string belongs
    in this set because ``verification/quality_gate.json`` is force-added and
    committed onto the run's working branch by ``commit_run_artifacts``
    (D-16): unlike a transient log line, a credential written there is
    permanent and unrecallable, and a ``quality_gate.commands`` entry --
    e.g. an authenticated health-check ``curl -H "Authorization: Bearer
    <token>"`` -- is the surface an operator is most likely to embed one in
    by hand. This closes gap CR-02 and restores this project's Security
    constraint (``CLAUDE.md``: infrastructure credentials "must
    never reach workers, artifacts, prompts, event payloads, comments, logs,
    or reports").
    """
    results: list[GateCommandResult] = []
    for command in commands:
        argv = shlex.split(command)
        outcome = shell_execute(
            command=argv,
            cwd=cwd,
            role=_QUALITY_GATE_ROLE_LABEL,
            timeout=timeout,
        )
        stdout = _cap_output(str(redact(outcome.stdout, known_secrets=known_secrets)))
        stderr = _cap_output(str(redact(outcome.stderr, known_secrets=known_secrets)))
        results.append(
            GateCommandResult(
                command=str(redact(command, known_secrets=known_secrets)),
                exit_code=outcome.exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=outcome.timed_out,
            )
        )
    return QualityGateResult(commands=results)


def write_quality_gate_result(run_dir: Path, result: QualityGateResult) -> str:
    """Write ``result`` to ``verification/quality_gate.json`` under
    ``run_dir`` (GATE-04); return the run-root-relative path so the caller
    can put it in an event payload.

    Follows ``dark_factory.actions.builtins.collect_diff``'s exact
    precedent for a ``verification/`` write: resolve through
    :func:`dark_factory.artifacts.paths.resolve_under_run_root`, create the
    parent directory idempotently, then write UTF-8 text.
    """
    relative_path = "verification/quality_gate.json"
    destination = resolve_under_run_root(run_dir, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(result.model_dump_json(), encoding="utf-8")
    return relative_path
