"""``ClaudeCodeWorker`` -- the first real :class:`~dark_factory.workers.base.
CodingWorker` adapter (WORK-04, Plan 07-01).

Spawns the ``claude`` CLI non-interactively (``claude -p "<prompt>"
--output-format json --permission-mode dontAsk``), streams its stdout/stderr
directly to ``<run_root>/logs/<role>/attempt-<N>.std{out,err}.log`` (D-04),
and normalizes the CLI's single JSON result object into a
:class:`~dark_factory.domain.worker.WorkerResult`.

``execute()`` wraps its entire body in a catch-all ``try/except Exception``:
``orchestrator/runner.py`` calls ``worker.execute(context)`` /
``worker.resume(...)`` with **no** surrounding ``try/except`` of its own, so
an exception escaping this adapter would abort the whole ``advance()`` step
and strand the ``role_executions`` row at ``RUNNING`` with no terminal
event -- the exact state SC5 requires never to occur. Every exit path here is
therefore a returned ``WorkerResult``, never a raised exception.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping

from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.tools.env import build_worker_env

# 06-CONTEXT.md D-02: NATIVE_TOOL_CONTRACT is the design contract Phase 7
# adapters implement from -- this import is that contract's first real
# (non-inert) runtime consumer (07-04, Task 1). Guarded, not un-guarded, by
# tests/unit/test_native_tool_contract.py's narrowed reference allowlist.
from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
from dark_factory.workers.base import CodingWorker

# D-03 (08-CONTEXT.md): the NEEDS_INPUT pause contract and the shared
# spawn/timeout/redact pipeline live in cli_runtime.py (08-01 Task 1, a pure
# move out of this module) so every CLI adapter -- this one, CopilotWorker,
# and later HermesWorker -- shares one contract instead of re-deriving it.
# Re-exported below via __all__ so existing importers of these names keep
# resolving from this module.
from dark_factory.workers.cli_runtime import (
    MAX_ERROR_EXCERPT,
    NEEDS_INPUT_MARKER,
    NEEDS_INPUT_PROTOCOL,
    RESUME_CONTINUATION_PROMPT,
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
    "CLAUDE_BINARY",
    "CLAUDE_CREDENTIAL_ENV_VAR",
    "NEEDS_INPUT_MARKER",
    "NEEDS_INPUT_PROTOCOL",
    "PERMISSION_MODE",
    "RESUME_CONTINUATION_PROMPT",
    "ClaudeCodeWorker",
    "MissingWorkerCredentialError",
    "allowed_tools_for",
    "attempt_log_paths",
]

CLAUDE_CREDENTIAL_ENV_VAR = "ANTHROPIC_API_KEY"
CLAUDE_BINARY = "claude"
PERMISSION_MODE = "dontAsk"

# Metadata keys copied verbatim from the CLI's ResultMessage object when
# present -- never a hardcoded superset, so an absent field is simply absent
# from metadata rather than appearing as a fabricated None.
_RESULT_METADATA_KEYS = (
    "subtype",
    "duration_ms",
    "duration_api_ms",
    "num_turns",
    "total_cost_usd",
    "usage",
    "is_error",
    "permission_denials",
)


class MissingWorkerCredentialError(RuntimeError):
    """Raised by :meth:`ClaudeCodeWorker.execute` when
    ``Settings.anthropic_api_key`` is unset (D-02).

    Raised *before* anything is spawned; ``execute()``'s outer
    ``try/except Exception`` converts this into a ``WorkerResult(FAILED)``,
    so both "a clear typed error" and "never raises out of the public
    method" hold at once.
    """

    def __init__(self) -> None:
        super().__init__(
            f"{CLAUDE_CREDENTIAL_ENV_VAR} is not configured -- set "
            "Settings.anthropic_api_key before running a role whose worker "
            "is 'claude-code'"
        )


# The per-capability native tool name(s), keyed by the same `tools:` grant
# vocabulary `ToolRegistry` enforces (`dark_factory.tools.registry.default_
# registry.names()`). "artifacts.write" and "artifacts.read" are deliberately
# absent -- the whole point of either grant is a scope narrower than
# repo.read/repo.write (write: the role's own artifacts/<role>/ subtree;
# read: the run's whole artifacts/ tree, still short of the full worktree
# repo.read would give), so a bare tool name here would silently widen both.
# They are handled separately in `allowed_tools_for()` as path-scoped
# specifiers instead (CR-01: artifacts.read previously leaked in as a bare
# `Read` grant here -- fixed by removing it from this table).
_TOOL_NAMES: Mapping[str, tuple[str, ...]] = {
    "repo.read": ("Read", "Glob"),
    "repo.search": ("Grep", "Glob"),
    "repo.write": ("Write", "Edit"),
    "repo.write_tests": ("Write", "Edit"),
    "shell.execute": ("Bash",),
}


def _tool_names_cover_native_contract() -> bool:
    """``True`` iff every capability in ``NATIVE_TOOL_CONTRACT`` has a
    translation here (``artifacts.write`` and ``artifacts.read`` counted via
    their path-scoped handling in :func:`allowed_tools_for` rather than a
    ``_TOOL_NAMES`` entry). A plain function -- not an import-time
    assertion -- so a future capability added to the contract without a
    translation fails a unit test rather than silently granting nothing
    (Task 1 acceptance criterion, T-07-18)."""
    return set(_TOOL_NAMES) | {"artifacts.write", "artifacts.read"} == set(
        NATIVE_TOOL_CONTRACT
    )


def allowed_tools_for(
    granted: Collection[str],
    artifacts_glob: str | None,
    artifacts_read_glob: str | None = None,
) -> list[str]:
    """The ``--allowedTools`` element's value for a role holding ``granted``
    capabilities: a sorted, de-duplicated list of native tool names.

    Deny by omission (the documented ``NativeToolGrant.absent_behaviour``):
    a capability with no ``_TOOL_NAMES`` entry contributes nothing, so the
    CLI itself refuses a tool that is not in the list. ``artifacts.write``
    is translated to a single path-scoped ``Edit(<artifacts_glob>/**)``
    specifier -- never a bare ``Write`` -- when it is held and
    ``artifacts_glob`` is not ``None`` (a context-free call passes
    ``None``, and the specifier is skipped). ``artifacts.read`` gets the
    same treatment via ``Read(<artifacts_read_glob>/**)``, scoped to the
    run's whole ``artifacts/`` tree rather than one role's subtree -- a
    worker legitimately reads a *prior* role's artifact output, so its
    read scope is deliberately broader than its own write scope (CR-01).

    Sorting is not cosmetic: it makes the returned list a deterministic
    function of ``granted``, so two spawns with the same grant set produce
    byte-identical argv and a diff between them is meaningful.
    """
    names: set[str] = set()
    for capability in granted:
        names.update(_TOOL_NAMES.get(capability, ()))
    if "artifacts.write" in granted and artifacts_glob is not None:
        names.add(f"Edit({artifacts_glob}/**)")
    if "artifacts.read" in granted and artifacts_read_glob is not None:
        names.add(f"Read({artifacts_read_glob}/**)")
    return sorted(names)


def _base_argv(context: object) -> list[str]:
    """The fixed argv prefix shared by every invocation. An explicit
    ``list[str]`` -- never joined into a string, never run with
    ``shell=True``. No ``--permission-mode`` value scopes file access to a
    directory -- worktree confinement comes from ``cwd=work_dir`` at spawn
    (07-RESEARCH.md Summary finding 1 / Pitfall 3).

    ``--allowedTools`` (07-04, Task 1) is derived from ``context.tools`` --
    the same grant list ``ToolRegistry.invoke`` enforces for Dark-Factory-
    initiated calls -- translated through :func:`allowed_tools_for`. Because
    both :meth:`ClaudeCodeWorker._execute` and
    :meth:`ClaudeCodeWorker._resume` build their argv from this function,
    the restriction applies identically to both entry points with no
    special-casing. An empty grant list produces no ``--allowedTools``
    element at all -- an ``--allowedTools`` flag with an empty value is not
    the same as no flag, and only the omission expresses "grants nothing".
    """
    granted = getattr(context, "tools", None) or []
    run_id = getattr(context, "run_id", None)
    artifacts_dir = getattr(context, "artifacts_dir", None)
    artifacts_glob = (
        f".dark-factory/runs/{run_id}/{artifacts_dir}"
        if run_id and artifacts_dir
        else None
    )
    # Run-scoped (not role-scoped) -- a worker legitimately reads a prior
    # role's artifact output, so read spans the whole run's artifacts/ tree
    # rather than being narrowed to this role's own subtree like write is.
    artifacts_read_glob = f".dark-factory/runs/{run_id}/artifacts" if run_id else None
    argv = [
        CLAUDE_BINARY,
        "--output-format",
        "json",
        "--permission-mode",
        PERMISSION_MODE,
    ]
    names = allowed_tools_for(granted, artifacts_glob, artifacts_read_glob)
    if names:
        argv.extend(["--allowedTools", ",".join(names)])
    return argv


class ClaudeCodeWorker(CodingWorker):
    """Spawns the real ``claude`` CLI and normalizes its output (WORK-04).

    Constructible with zero arguments, so it is usable directly as a
    ``Callable[[], CodingWorker]`` factory (see ``workers/registry.py``).
    """

    def execute(self, context: object) -> WorkerResult:
        """Run one role attempt through the real ``claude`` CLI.

        See the module docstring for why this method never raises: the
        orchestrator call site has no surrounding ``try/except``.
        """
        try:
            return self._execute(context)
        except Exception as exc:  # see module docstring for why this is intentional
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude-code worker failed",
                error=str(exc),
            )

    def _execute(self, context: object) -> WorkerResult:
        argv = [*_base_argv(context), "-p", build_prompt(context)]
        return self._spawn_and_parse(argv, context)

    def _spawn_and_parse(self, argv: list[str], context: object) -> WorkerResult:
        """The shared spawn/timeout/redact/parse pipeline (Task 2): both
        ``execute()`` and ``resume()`` fully assemble their own argv (the
        only thing that differs between them) and hand it here. Factoring
        this out -- rather than duplicating it -- is what keeps the
        redaction ``finally`` block and the never-raise wrapper from
        drifting between the two entry points.
        """
        settings = get_settings()
        if settings.anthropic_api_key is None:
            raise MissingWorkerCredentialError()

        role = getattr(context, "role", None) or "unknown"
        attempt = getattr(context, "attempt", None) or 1
        run_id = getattr(context, "run_id", None)
        work_dir, root = resolve_dirs(run_id)

        env = build_worker_env(
            role,
            env_var_name=CLAUDE_CREDENTIAL_ENV_VAR,
            value=settings.anthropic_api_key,
        )
        stdout_path, stderr_path = attempt_log_paths(root, role, attempt)

        # Task 3 (T-07-01): scrub_log_in_place runs in `finally`, immediately
        # after run_streamed returns OR raises, so it executes on the
        # success path, the non-zero-exit path and the timeout-kill path
        # alike -- and, critically, before any code below reads these files
        # again. See scrub_log_in_place's own docstring for why this
        # ordering is mandatory, not decorative.
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
                summary="claude-code worker timed out",
                error=(
                    "claude subprocess killed with its process group after "
                    f"{settings.worker_timeout_seconds} seconds"
                ),
                metadata={"timed_out": True, "exit_code": None},
            )

        if exit_code != 0:
            stderr_text = stderr_path.read_text("utf-8", errors="replace")
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude-code worker exited non-zero",
                error=(f"claude exited {exit_code}: {stderr_text[:MAX_ERROR_EXCERPT]}"),
                metadata={"timed_out": False, "exit_code": exit_code},
            )

        stdout_text = stdout_path.read_text("utf-8", errors="replace")
        try:
            parsed: object = json.loads(stdout_text.strip())
        except json.JSONDecodeError:
            parsed = None
        if not isinstance(parsed, dict):
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude-code worker returned unparseable output",
                error=(
                    "claude's stdout was not the single JSON object "
                    "--output-format json promises: "
                    f"{stdout_text[:MAX_ERROR_EXCERPT]!r}"
                ),
            )

        if parsed.get("is_error"):
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude reported an error",
                error=str(parsed.get("result", "")),
                worker_session_id=parsed.get("session_id"),
            )

        metadata = {key: parsed[key] for key in _RESULT_METADATA_KEYS if key in parsed}
        result_text = str(parsed.get("result", ""))
        session_id = parsed.get("session_id")

        # D-01: a non-error result may still be a pause request. Precedence
        # is: is_error / non-zero exit (handled above) always wins; a
        # NEEDS_INPUT marker wins over COMPLETED; otherwise COMPLETED.
        question = extract_needs_input(result_text)
        if question is not None:
            return WorkerResult(
                status=WorkerResultStatus.NEEDS_INPUT,
                summary=result_text,
                questions=[question],
                worker_session_id=session_id,
                metadata=metadata,
            )

        # Artifacts are reported only on the COMPLETED branch (08-01 Task 3):
        # a paused or failed attempt has not satisfied its outputs contract,
        # and collect_role_artifacts only runs after a completed signal.
        # changed_files stays empty here (and for CopilotWorker) because
        # git/diff.py::collect_diff computes the authoritative diff after
        # the worker returns and emits_changed_files remains False --
        # artifact reporting and changed-file reporting are different
        # contracts and only the former moves through this shared helper.
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=result_text,
            worker_session_id=session_id,
            artifacts=collect_declared_artifacts(root, context),
            metadata=metadata,
        )

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Continue a paused role attempt (HITL-04/HITL-05, Plan 07-03).

        The call site is ``orchestrator/runner.py:825-829``:
        ``result = worker.resume(context, previous, state.pending_answer)`` --
        identical for every adapter, with no worker-name conditional. Both
        branches below return through that same shape, which is the whole of
        HITL-05: the orchestrator cannot tell which branch ran.

        See the module docstring for why this method never raises: the
        orchestrator call site has no surrounding ``try/except``.
        """
        try:
            return self._resume(context, previous, answer)
        except Exception as exc:  # see module docstring for why this is intentional
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude-code worker failed",
                error=str(exc),
            )

    def _resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        session_id = getattr(previous, "worker_session_id", None)
        if session_id:
            # HITL-04: the native branch. The id crosses as a single opaque
            # argv element after --resume -- never parsed, split, validated
            # or reformatted. Neither this adapter nor the orchestrator
            # interprets another system's session handle as structured data.
            argv = [
                *_base_argv(context),
                "--resume",
                session_id,
                "-p",
                answer or RESUME_CONTINUATION_PROMPT,
            ]
        else:
            # HITL-05: the context-reconstruction branch -- no --resume
            # element at all.
            argv = [
                *_base_argv(context),
                "-p",
                build_resume_prompt(context, previous, answer),
            ]
        return self._spawn_and_parse(argv, context)

    def capabilities(self) -> WorkerCapabilities:
        """The final capability declaration (Plan 07-03).

        ``native_resume=True`` is justified by the CLI's real
        ``--resume <session-id>`` flag (HITL-04). ``emits_changed_files=False``
        is deliberate -- ``git/diff.py::collect_diff`` computes the
        authoritative diff from git after the worker returns, so this adapter
        must not invent its own changed-file list.
        """
        return WorkerCapabilities(
            native_resume=True,
            session_id=True,
            structured_output=True,
            non_interactive=True,
            emits_changed_files=False,
        )
