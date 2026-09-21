"""``CopilotWorker`` -- the second real :class:`~dark_factory.workers.base.
CodingWorker` adapter (WORK-05, Plan 08-01).

Spawns the ``copilot`` CLI non-interactively (``copilot -p "<prompt>"
--no-ask-user -s [--allow-tool <name> ...] [--model <pin>]``), streams its
stdout/stderr directly to ``<run_root>/logs/<role>/attempt-<N>.std{out,err}.
log`` (D-04), and normalizes its plain-text stdout into a
:class:`~dark_factory.domain.worker.WorkerResult`. D-02 keeps this adapter on
plain-text parsing -- no ``--output-format=json`` mode is adopted this phase,
because its field schema was never confirmed against a live binary
(08-RESEARCH.md Finding 2 / Open Question 2) -- so ``worker_session_id`` is
always ``None`` and ``capabilities().structured_output`` is ``False``.

``execute()``/``resume()`` each wrap their entire body in a catch-all
``try/except Exception``, mirroring ``dark_factory.workers.claude_code``'s
own rationale verbatim: ``orchestrator/runner.py`` calls
``worker.execute(context)`` / ``worker.resume(...)`` with **no** surrounding
``try/except`` of its own, so an exception escaping this adapter would abort
the whole ``advance()`` step and strand the ``role_executions`` row at
``RUNNING`` with no terminal event. Every exit path here is therefore a
returned ``WorkerResult``, never a raised exception.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.tools.env import build_worker_env

# 06-CONTEXT.md D-02 / 08-CONTEXT.md: this adapter is NATIVE_TOOL_CONTRACT's
# first real Copilot runtime consumer, mirroring what 07-04 did for
# claude_code.py. Guarded, not un-guarded, by
# tests/unit/test_native_tool_contract.py's narrowed reference allowlist.
from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.cli_runtime import (
    MAX_ERROR_EXCERPT,
    attempt_log_paths,
    build_prompt,
    build_resume_prompt,
    collect_declared_artifacts,
    extract_needs_input,
    resolve_dirs,
    run_streamed,
    scrub_log_in_place,
)

__all__ = [
    "COPILOT_BINARY",
    "COPILOT_CREDENTIAL_ENV_VAR",
    "CopilotWorker",
    "MissingWorkerCredentialError",
    "allowed_tools_for",
]

COPILOT_CREDENTIAL_ENV_VAR = "COPILOT_GITHUB_TOKEN"
COPILOT_BINARY = "copilot"


class MissingWorkerCredentialError(RuntimeError):
    """Raised by :meth:`CopilotWorker.execute`/:meth:`CopilotWorker.resume`
    when ``Settings.copilot_github_token`` is unset (D-01).

    Raised *before* anything is spawned; ``execute()``/``resume()``'s outer
    ``try/except Exception`` converts this into a ``WorkerResult(FAILED)``,
    so both "a clear typed error" and "never raises out of the public
    method" hold at once -- mirroring
    ``claude_code.MissingWorkerCredentialError``'s shape.
    """

    def __init__(self) -> None:
        super().__init__(
            f"{COPILOT_CREDENTIAL_ENV_VAR} is not configured -- set "
            "Settings.copilot_github_token before running a role whose "
            "worker is 'copilot'. The GitHub Copilot CLI requires a "
            "fine-grained, personal-account-owned personal access token "
            "carrying the 'Copilot Requests' permission; a classic PAT "
            "(ghp_*) is rejected by the CLI."
        )


# The Copilot native-tool translation, keyed by the same `tools:` grant
# vocabulary `NATIVE_TOOL_CONTRACT` uses. Two honest deviations from the
# contract prose (T-08-04, T-08-05):
#
# 1. The CLI has no path-scoped read or write specifier, so the artifacts.*
#    capabilities collapse onto the same unscoped `read`/`write` names as
#    the repository capabilities -- broader than Claude Code's path-scoped
#    equivalents. `enforce_write_scope` (ROLE-05) and the subprocess `cwd`
#    remain the effective boundary (accepted, T-08-05).
# 2. The contract describes a per-command shell specifier
#    (`shell(<command>)`), but Dark Factory's own `shell.execute` grant
#    carries no command list, so the unscoped `shell` name is the faithful
#    translation of the grant's actual breadth rather than an invented
#    narrowing.
_TOOL_NAMES: Mapping[str, tuple[str, ...]] = {
    "repo.read": ("read",),
    "repo.search": ("read",),
    "repo.write": ("write",),
    "repo.write_tests": ("write",),
    "artifacts.read": ("read",),
    "artifacts.write": ("write",),
    "shell.execute": ("shell",),
}


def _tool_names_cover_native_contract() -> bool:
    """``True`` iff every capability in ``NATIVE_TOOL_CONTRACT`` has a
    translation here. A plain function -- not an import-time assertion --
    so a future capability added to the contract without a Copilot
    translation fails a unit test rather than silently granting nothing
    (mirrors ``claude_code._tool_names_cover_native_contract``)."""
    return set(_TOOL_NAMES) == set(NATIVE_TOOL_CONTRACT)


def allowed_tools_for(granted: Collection[str]) -> list[str]:
    """The sorted, de-duplicated list of Copilot native tool names for a
    role holding ``granted`` capabilities.

    Deny by omission: a capability with no ``_TOOL_NAMES`` entry contributes
    nothing, so the CLI itself refuses a tool that is not in the
    ``--allow-tool`` list. Sorting is not cosmetic -- it makes the returned
    list a deterministic function of ``granted``, so two spawns with the
    same grant set produce byte-identical argv.
    """
    names: set[str] = set()
    for capability in granted:
        names.update(_TOOL_NAMES.get(capability, ()))
    return sorted(names)


# T-08-01/T-08-04 (08-RESEARCH.md Anti-Patterns to Avoid): these four flags
# must never appear in the argv this adapter builds. The blanket
# tool-permission and blanket path-permission flags bypass the
# deny-by-omission translation `_TOOL_NAMES` exists to perform and disable
# the CLI's own path confinement; the two sharing flags export the
# transcript to a destination outside Dark Factory's log tree, where
# `scrub_log_in_place`'s redaction rewrite never reaches it.
def _base_argv(context: object) -> list[str]:
    """The fixed argv prefix shared by every invocation. An explicit
    ``list[str]`` -- never joined into a string, never run with
    ``shell=True``. No path-permission flag scopes file access to a
    directory -- worktree confinement comes from ``cwd=work_dir`` at spawn,
    same as ``claude_code._base_argv``.

    ``-s`` suppresses stats and decoration so the captured log is clean
    text (08-RESEARCH.md Finding 3). ``--allow-tool`` is derived from
    ``context.tools`` through :func:`allowed_tools_for` -- an empty grant
    list produces no ``--allow-tool`` element at all, the same "omission
    expresses grants nothing" discipline ``claude_code._base_argv`` follows.
    ``--model`` is appended only when ``Settings.copilot_model`` is a
    non-empty string.
    """
    settings = get_settings()
    granted = getattr(context, "tools", None) or []
    argv = [COPILOT_BINARY, "--no-ask-user", "-s"]
    for name in allowed_tools_for(granted):
        argv.extend(["--allow-tool", name])
    if settings.copilot_model:
        argv.extend(["--model", settings.copilot_model])
    return argv


class CopilotWorker(CodingWorker):
    """Spawns the real ``copilot`` CLI and normalizes its output (WORK-05).

    Constructible with zero arguments, so it is usable directly as a
    ``Callable[[], CodingWorker]`` factory (see ``workers/registry.py``).
    """

    def execute(self, context: object) -> WorkerResult:
        """Run one role attempt through the real ``copilot`` CLI.

        See the module docstring for why this method never raises: the
        orchestrator call site has no surrounding ``try/except``.
        """
        try:
            return self._execute(context)
        except Exception as exc:  # see module docstring for why this is intentional
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="copilot worker failed",
                error=str(exc),
            )

    def _execute(self, context: object) -> WorkerResult:
        argv = [*_base_argv(context), "-p", build_prompt(context)]
        return self._spawn_and_parse(argv, context)

    def _spawn_and_parse(self, argv: list[str], context: object) -> WorkerResult:
        """The shared spawn/timeout/redact/parse pipeline, mirroring
        ``ClaudeCodeWorker._spawn_and_parse`` with three differences: the
        credential checked is ``settings.copilot_github_token``; the
        environment is built with ``COPILOT_CREDENTIAL_ENV_VAR``; and on a
        clean exit the stdout text is used directly as the result text --
        there is no JSON decode step, because D-02 keeps this adapter on
        plain-text parsing and no structured-output flag is passed, so
        ``worker_session_id`` is always ``None``.
        """
        settings = get_settings()
        if settings.copilot_github_token is None:
            raise MissingWorkerCredentialError()

        role = getattr(context, "role", None) or "unknown"
        attempt = getattr(context, "attempt", None) or 1
        run_id = getattr(context, "run_id", None)
        work_dir, root = resolve_dirs(run_id)

        env = build_worker_env(
            role,
            env_var_name=COPILOT_CREDENTIAL_ENV_VAR,
            value=settings.copilot_github_token,
        )
        stdout_path, stderr_path = attempt_log_paths(root, role, attempt)

        # scrub_log_in_place runs in `finally`, immediately after
        # run_streamed returns OR raises, so it executes on the success
        # path, the non-zero-exit path and the timeout-kill path alike --
        # and, critically, before any code below reads these files again.
        try:
            exit_code, timed_out = run_streamed(
                argv,
                cwd=work_dir,
                env=env,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout=settings.worker_timeout_seconds,
            )
        finally:
            scrub_log_in_place(stdout_path)
            scrub_log_in_place(stderr_path)

        if timed_out:
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="copilot worker timed out",
                error=(
                    "copilot subprocess killed with its process group after "
                    f"{settings.worker_timeout_seconds} seconds"
                ),
                metadata={"timed_out": True, "exit_code": None},
            )

        if exit_code != 0:
            stderr_text = stderr_path.read_text("utf-8", errors="replace")
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="copilot worker exited non-zero",
                error=(
                    f"copilot exited {exit_code}: "
                    f"{stderr_text[:MAX_ERROR_EXCERPT]}"
                ),
                metadata={"timed_out": False, "exit_code": exit_code},
            )

        result_text = stdout_path.read_text("utf-8", errors="replace")

        # D-01: a non-error result may still be a pause request. Precedence
        # is: non-zero exit (handled above) always wins; a NEEDS_INPUT
        # marker wins over COMPLETED; otherwise COMPLETED.
        question = extract_needs_input(result_text)
        if question is not None:
            return WorkerResult(
                status=WorkerResultStatus.NEEDS_INPUT,
                summary=result_text,
                questions=[question],
                metadata={"timed_out": False, "exit_code": exit_code},
            )

        # Artifacts are reported only on the COMPLETED branch (Task 3): a
        # paused or failed attempt has not satisfied its outputs contract,
        # and collect_role_artifacts only runs after a completed signal.
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=result_text,
            artifacts=collect_declared_artifacts(root, context),
            metadata={"timed_out": False, "exit_code": exit_code},
        )

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Continue a paused role attempt (HITL-04/HITL-05).

        See the module docstring for why this method never raises: the
        orchestrator call site has no surrounding ``try/except``.
        """
        try:
            return self._resume(context, previous, answer)
        except Exception as exc:  # see module docstring for why this is intentional
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="copilot worker failed",
                error=str(exc),
            )

    def _resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Because ``capabilities().native_resume`` is ``False`` and this
        CLI exposes no programmatic session-resume entry point
        (08-RESEARCH.md Finding 2 / Pitfall 1), there is only one branch:
        context reconstruction. Deliberately does not read
        ``previous.worker_session_id`` -- this adapter never produces one,
        so a branch on it would be dead code that falsely implies a native
        path exists. The orchestrator call site
        (``orchestrator/runner.py``: ``worker.resume(context, previous,
        state.pending_answer)``) is identical for every adapter, with no
        worker-name conditional (HITL-05): the orchestrator cannot tell
        which adapter or which branch ran.
        """
        argv = [
            *_base_argv(context),
            "-p",
            build_resume_prompt(context, previous, answer),
        ]
        return self._spawn_and_parse(argv, context)

    def capabilities(self) -> WorkerCapabilities:
        """The capability declaration, each axis cited to 08-RESEARCH.md
        Finding 2:

        - ``native_resume=False``: the CLI's resume flag is documented only
          as an interactive session picker and is absent from its
          programmatic reference.
        - ``session_id=False``: no session identifier is available to
          capture from plain-text output.
        - ``structured_output=False``: the CLI has a real JSON output mode,
          deliberately not adopted this phase (D-02) -- declaring it true
          would describe the CLI rather than this adapter.
        - ``emits_changed_files=False``: ``git/diff.py::collect_diff``
          computes the authoritative diff from git after the worker
          returns, so this adapter must not invent its own changed-file
          list.
        """
        return WorkerCapabilities(
            native_resume=False,
            session_id=False,
            structured_output=False,
            non_interactive=True,
            emits_changed_files=False,
        )
