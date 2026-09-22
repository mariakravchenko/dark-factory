"""``HermesWorker`` -- the third real :class:`~dark_factory.workers.base.
CodingWorker` adapter (WORK-06, Plan 08-02), completing the three-real-
runtime set and emptying ``WorkerRegistry`` of placeholders (D-04).

Spawns the ``hermes`` CLI non-interactively (``hermes chat -q "<prompt>"
--oneshot -Q --ignore-user-config``), streams its stdout/stderr directly to
``<run_root>/logs/<role>/attempt-<N>.std{out,err}.log`` (D-04), and
normalizes its plain-text stdout into a
:class:`~dark_factory.domain.worker.WorkerResult`. D-02 keeps this adapter
on plain-text parsing -- no structured-output mode is adopted this phase --
so ``worker_session_id`` is always ``None`` and
``capabilities().structured_output`` is ``False``.

Hermes differs from Copilot/Claude Code in three ways this module handles
explicitly:

1. **No dedicated credential.** Hermes is multi-provider and documents
   ``ANTHROPIC_API_KEY`` among its own recognised provider keys, so this
   adapter reuses ``Settings.anthropic_api_key`` rather than inventing a
   ``Settings.hermes_api_key`` field the CLI would never read
   (08-RESEARCH.md Finding 1).
2. **Home-directory state.** Hermes does not follow the XDG specification
   and would otherwise read/write a session database and environment file
   under the operator's real home directory. This adapter points
   ``HERMES_HOME`` at a role-scoped subdirectory of the same disposable
   root ``build_worker_env`` uses for its ``XDG_*`` entries
   (08-RESEARCH.md Pitfall 3).
3. **No per-tool native restriction flag.** ``NATIVE_TOOL_CONTRACT``
   records that Hermes exposes no native mechanism to narrow its own
   tools at all. :func:`spawn_is_permitted` is the enforcement point this
   forces: a role denied a capability with no compensating post-hoc
   control is never spawned at all (checkpoint decision, Option A -- see
   ``.planning/phases/08-copilot-hermes-worker-independence-proven/
   08-02-SUMMARY.md`` for the full decision record). That covers the
   *denied* case only. For the *granted* case (plan 08-05, CR-01/WR-03):
   a granted ``artifacts.write`` is confined to the role's own
   ``artifacts/<role>/`` subtree only after the fact, by
   :func:`dark_factory.git.scope.enforce_artifact_scope`, never natively on
   this runtime; a granted ``artifacts.read`` carries reach identical to
   ``repo.read``, with no mechanism of any kind narrowing it.

``execute()``/``resume()`` each wrap their entire body in a catch-all
``try/except Exception``, mirroring ``dark_factory.workers.copilot``'s own
rationale verbatim: ``orchestrator/runner.py`` calls
``worker.execute(context)`` / ``worker.resume(...)`` with **no** surrounding
``try/except`` of its own, so an exception escaping this adapter would abort
the whole ``advance()`` step and strand the ``role_executions`` row at
``RUNNING`` with no terminal event. Every exit path here is therefore a
returned ``WorkerResult``, never a raised exception.
"""

from __future__ import annotations

from collections.abc import Collection

from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.tools.env import build_worker_env, role_worker_root

# 08-CONTEXT.md / checkpoint (Option A): this adapter is NATIVE_TOOL_CONTRACT's
# third real runtime consumer, mirroring what 07-04 did for claude_code.py
# and 08-01 did for copilot.py. Guarded, not un-guarded, by
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
    "HERMES_BINARY",
    "HERMES_CREDENTIAL_ENV_VAR",
    "HERMES_STATE_ENV_VAR",
    "HermesWorker",
    "MissingWorkerCredentialError",
    "UnenforceableGrantError",
    "spawn_is_permitted",
]

HERMES_CREDENTIAL_ENV_VAR = "ANTHROPIC_API_KEY"
HERMES_BINARY = "hermes"
HERMES_STATE_ENV_VAR = "HERMES_HOME"


class MissingWorkerCredentialError(RuntimeError):
    """Raised by :meth:`HermesWorker.execute`/:meth:`HermesWorker.resume`
    when ``Settings.anthropic_api_key`` is unset.

    Raised *before* anything is spawned; ``execute()``/``resume()``'s outer
    ``try/except Exception`` converts this into a ``WorkerResult(FAILED)``,
    so both "a clear typed error" and "never raises out of the public
    method" hold at once -- mirroring
    ``copilot.MissingWorkerCredentialError``'s shape.

    No ``Settings.hermes_api_key`` field exists: Hermes is multi-provider
    and documents ``ANTHROPIC_API_KEY`` among its own recognised provider
    keys, not a NousResearch-branded single credential (08-RESEARCH.md
    Finding 1) -- this message states that so a reader who expected a
    Hermes-specific field learns from the error itself why none exists.
    """

    def __init__(self) -> None:
        super().__init__(
            f"{HERMES_CREDENTIAL_ENV_VAR} is not configured -- set "
            "Settings.anthropic_api_key before running a role whose worker "
            "is 'hermes'. Hermes has no dedicated credential of its own: it "
            "is multi-provider and reads ANTHROPIC_API_KEY among its own "
            "recognised provider keys, so this adapter reuses "
            "Settings.anthropic_api_key rather than inventing a "
            "Hermes-specific field the CLI would never read."
        )


# Checkpoint decision (Option A, recorded in 08-02-SUMMARY.md): the two
# write capabilities are compensated after the fact by enforce_write_scope
# (ROLE-05), which reverts and fails any changed path outside a role's
# configured write_scope -- including the zero-tolerance empty scope -- so
# this adapter may spawn for a role denied only one (or both) of these even
# though NATIVE_TOOL_CONTRACT records no native flag to enforce the denial
# with. Every other capability has no such post-hoc control, so denial of
# any of those blocks the spawn entirely (T-08-12).
_WRITE_COMPENSATED_CAPABILITIES: frozenset[str] = frozenset(
    {"repo.write", "repo.write_tests"}
)


def _write_compensated_capabilities_are_a_subset_of_the_contract() -> bool:
    """``True`` iff every name in ``_WRITE_COMPENSATED_CAPABILITIES`` is a
    real ``NATIVE_TOOL_CONTRACT`` capability, so a renamed or removed
    capability fails a unit test rather than silently widening or
    narrowing the compensated set."""
    return set(NATIVE_TOOL_CONTRACT) >= _WRITE_COMPENSATED_CAPABILITIES


class UnenforceableGrantError(RuntimeError):
    """Raised by :meth:`HermesWorker._spawn_and_parse` when
    :func:`spawn_is_permitted` names a blocking capability.

    Hermes cannot narrow its own native tools (``NATIVE_TOOL_CONTRACT``
    documents no per-tool restriction flag for it at all), so for any
    capability whose denial has no post-hoc compensating control, the only
    honest enforcement available to this adapter is not to run the role at
    all.
    """

    def __init__(self, capability: str) -> None:
        super().__init__(
            f"hermes cannot spawn for this role: it is denied {capability!r}, "
            "NATIVE_TOOL_CONTRACT documents no per-tool native restriction "
            "flag for Hermes, and this capability has no post-hoc "
            "compensating control -- the only honest enforcement is to "
            "refuse the spawn entirely rather than run unrestricted "
            "(T-08-12)."
        )


def spawn_is_permitted(granted: Collection[str]) -> str | None:
    """``None`` when a role holding ``granted`` capabilities may spawn
    Hermes; otherwise the name of the first (in sorted order, for
    determinism) capability the role does not hold whose denial
    ``NATIVE_TOOL_CONTRACT`` requires this adapter to refuse over.

    Hermes cannot narrow its own native tools, so for any capability whose
    denial has no post-hoc control the only honest enforcement is not to
    run the role at all. The two write capabilities are the sole exception
    (checkpoint decision, Option A): their denial is independently
    compensated by ``enforce_write_scope`` (ROLE-05), so this function
    treats them as never blocking.

    This function decides admission only -- it says nothing about what a
    *granted* capability may reach, and a caller must not read "permitted to
    spawn" as "confined once running" (plan 08-05, CR-01/WR-03). A granted
    ``artifacts.write`` is confined to the role's own ``artifacts/<role>/``
    subtree only after the fact, by
    :func:`dark_factory.git.scope.enforce_artifact_scope`, never natively on
    this runtime. A granted ``artifacts.read`` carries reach identical to
    ``repo.read``, with no mechanism of any kind -- native or post-hoc --
    narrowing it.
    """
    granted_set = set(granted)
    for capability in sorted(NATIVE_TOOL_CONTRACT):
        if capability in granted_set:
            continue
        if capability in _WRITE_COMPENSATED_CAPABILITIES:
            continue
        return capability
    return None


def _base_argv(context: object) -> list[str]:
    """The fixed argv prefix shared by every invocation. An explicit
    ``list[str]`` -- never joined into a string, never run with
    ``shell=True``. No path-permission flag scopes file access to a
    directory -- worktree confinement comes from ``cwd=work_dir`` at spawn,
    same as ``claude_code._base_argv`` / ``copilot._base_argv``.

    ``--oneshot`` guarantees answer-and-exit determinism regardless of
    stdin plumbing, even though it is implied automatically whenever stdin
    is not a terminal (08-RESEARCH.md Finding 4). ``-Q`` (quiet) suppresses
    banner, spinner and tool previews so the captured log is clean text.
    ``--ignore-user-config`` keeps a host machine's personal Hermes
    configuration out of a run. The interactive-terminal flag documented in
    Finding 4 (``--tui``) must never be emitted here -- it would force an
    interactive session this adapter can never satisfy with a DEVNULL
    stdin, and would hang until the worker timeout. No ``--allow-tool``-
    style element exists for this CLI, which is exactly why
    :func:`spawn_is_permitted` is the enforcement point instead.
    """
    return [HERMES_BINARY, "chat", "--oneshot", "-Q", "--ignore-user-config"]


class HermesWorker(CodingWorker):
    """Spawns the real ``hermes`` CLI and normalizes its output (WORK-06).

    Constructible with zero arguments, so it is usable directly as a
    ``Callable[[], CodingWorker]`` factory (see ``workers/registry.py``).
    """

    def execute(self, context: object) -> WorkerResult:
        """Run one role attempt through the real ``hermes`` CLI.

        See the module docstring for why this method never raises: the
        orchestrator call site has no surrounding ``try/except``.
        """
        try:
            return self._execute(context)
        except Exception as exc:  # see module docstring for why this is intentional
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="hermes worker failed",
                error=str(exc),
            )

    def _execute(self, context: object) -> WorkerResult:
        argv = [*_base_argv(context), "-q", build_prompt(context)]
        return self._spawn_and_parse(argv, context)

    def _spawn_and_parse(self, argv: list[str], context: object) -> WorkerResult:
        """The shared spawn/timeout/redact/parse pipeline, mirroring
        ``CopilotWorker._spawn_and_parse`` with three Hermes-specific
        additions ahead of it: a spawn-admission check
        (:func:`spawn_is_permitted`), the credential check against
        ``settings.anthropic_api_key``, and an isolated ``HERMES_HOME``
        added to the built environment.
        """
        # A None context is the shared CodingWorker contract suite's shape
        # (`worker.execute(None)` / `worker.resume(None, ...)`), never a
        # configured role -- a real role attempt always carries a
        # RoleContext, even one whose `tools` list happens to be empty. Only
        # the latter is a genuine "denied every capability" grant that
        # spawn_is_permitted must block; a call carrying no context at all
        # is exempted so this adapter's admission rule degrades the same
        # way CopilotWorker/ClaudeCodeWorker already do for the identical
        # call shape (08-02 Task 2).
        if context is not None:
            blocking_capability = spawn_is_permitted(
                getattr(context, "tools", None) or []
            )
            if blocking_capability is not None:
                raise UnenforceableGrantError(blocking_capability)

        settings = get_settings()
        if settings.anthropic_api_key is None:
            raise MissingWorkerCredentialError()

        role = getattr(context, "role", None) or "unknown"
        attempt = getattr(context, "attempt", None) or 1
        run_id = getattr(context, "run_id", None)
        work_dir, root = resolve_dirs(run_id)

        root_dir = role_worker_root(role)
        env = build_worker_env(
            role,
            env_var_name=HERMES_CREDENTIAL_ENV_VAR,
            value=settings.anthropic_api_key,
            xdg_root=root_dir,
        )
        # 08-RESEARCH.md Pitfall 3: Hermes does not follow the XDG
        # specification and would otherwise use the operator's real home
        # directory for its session database and environment file, leaking
        # state between runs and roles and breaking the clean-container
        # success criterion. HERMES_HOME is pointed at a subdirectory of
        # the same disposable root the XDG_* entries above already use, so
        # two roles never share Hermes state.
        hermes_home = root_dir / "hermes"
        hermes_home.mkdir(parents=True, exist_ok=True)
        env[HERMES_STATE_ENV_VAR] = str(hermes_home)

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
                summary="hermes worker timed out",
                error=(
                    "hermes subprocess killed with its process group after "
                    f"{settings.worker_timeout_seconds} seconds"
                ),
                metadata={"timed_out": True, "exit_code": None},
            )

        if exit_code != 0:
            stderr_text = stderr_path.read_text("utf-8", errors="replace")
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="hermes worker exited non-zero",
                error=(
                    f"hermes exited {exit_code}: "
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

        # Artifacts are reported only on the COMPLETED branch: a paused or
        # failed attempt has not satisfied its outputs contract, and
        # collect_role_artifacts only runs after a completed signal.
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=result_text,
            artifacts=collect_declared_artifacts(root, context),
            worker_session_id=None,
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
                summary="hermes worker failed",
                error=str(exc),
            )

    def _resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Because ``capabilities().native_resume`` is ``False``, there is
        only one branch: context reconstruction. Deliberately does not
        attempt the CLI's own ``--resume`` flag: 08-RESEARCH.md Open
        Question 1 records that no fetched source confirms it completes
        headlessly when combined with the one-shot and query flags this
        adapter always passes, so adopting it could hang an attempt until
        the worker timeout. This is the first thing the deferred live spike
        (D-02) should falsify. The orchestrator call site
        (``orchestrator/runner.py``: ``worker.resume(context, previous,
        state.pending_answer)``) is identical for every adapter, with no
        worker-name conditional (HITL-05): the orchestrator cannot tell
        which adapter or which branch ran.
        """
        argv = [
            *_base_argv(context),
            "-q",
            build_resume_prompt(context, previous, answer),
        ]
        return self._spawn_and_parse(argv, context)

    def capabilities(self) -> WorkerCapabilities:
        """The capability declaration, each axis cited to 08-RESEARCH.md
        Finding 2 / Open Question 1:

        - ``native_resume=False``: no fetched source confirms the CLI's
          ``--resume`` flag completes headlessly when combined with the
          one-shot and query flags this adapter always passes -- declaring
          it true would be an unverified claim, not a documented fact.
        - ``session_id=False``: no fetched source confirms a session
          identifier is printed to stdout during a ``--oneshot`` run for a
          caller to capture.
        - ``structured_output=False``: D-02 keeps this adapter on
          plain-text parsing this phase; a real JSON/JSONL mode exists but
          its field schema was never confirmed against a live binary.
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
