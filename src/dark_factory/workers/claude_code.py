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

import contextlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

from dark_factory.artifacts.paths import run_root
from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import (
    WorkerCapabilities,
    WorkerResult,
    WorkerResultStatus,
)
from dark_factory.events.redaction import redact
from dark_factory.tools.env import build_worker_env
from dark_factory.workers.base import CodingWorker

__all__ = [
    "CLAUDE_BINARY",
    "CLAUDE_CREDENTIAL_ENV_VAR",
    "PERMISSION_MODE",
    "ClaudeCodeWorker",
    "MissingWorkerCredentialError",
    "attempt_log_paths",
]

CLAUDE_CREDENTIAL_ENV_VAR = "ANTHROPIC_API_KEY"
CLAUDE_BINARY = "claude"
PERMISSION_MODE = "dontAsk"

# The cap on a stderr/stdout excerpt folded into a WorkerResult.error, so a
# runaway transcript cannot bloat the JSONB `result`/`error` column the
# orchestrator persists (Task 2).
_MAX_ERROR_EXCERPT = 2000

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


def attempt_log_paths(root: Path, role: str, attempt: int) -> tuple[Path, Path]:
    """The D-04 log destination for one role attempt: ``(stdout, stderr)``
    paths under ``<root>/logs/<role>/``, alongside ``artifacts/<role>/`` --
    reusing ``run_root()`` rather than inventing a new path scheme. The
    parent directory is created (``mkdir(parents=True, exist_ok=True)``)."""
    log_dir = root / "logs" / role
    log_dir.mkdir(parents=True, exist_ok=True)
    return (
        log_dir / f"attempt-{attempt}.stdout.log",
        log_dir / f"attempt-{attempt}.stderr.log",
    )


def _build_prompt(context: object) -> str:
    """Assemble the plain-text ``-p`` prompt from ``context`` (a
    :class:`~dark_factory.context.builder.RoleContext`, read defensively via
    ``getattr`` so a bare test double still degrades cleanly). A section
    whose source field is empty is skipped entirely."""
    sections: list[str] = []

    instructions = getattr(context, "instructions", None)
    if instructions:
        sections.append(f"## Instructions\n{instructions}")

    task = getattr(context, "task", None)
    if task:
        sections.append(f"## Task\n{json.dumps(task, indent=2)}")

    answer = getattr(context, "answer", None)
    if answer:
        sections.append(f"## Human answer\n{answer}")

    baseline_docs = getattr(context, "baseline_docs", None) or {}
    if baseline_docs:
        blocks = "\n\n".join(
            f"### {filename}\n{content}" for filename, content in baseline_docs.items()
        )
        sections.append(f"## Baseline documents\n{blocks}")

    inputs = getattr(context, "inputs", None) or []
    if inputs:
        blocks = "\n\n".join(
            f"### {item.filename} (produced by {item.produced_by})\n{item.content}"
            for item in inputs
        )
        sections.append(f"## Inputs\n{blocks}")

    examples = getattr(context, "examples", None) or []
    if examples:
        blocks = "\n\n".join(f"### {item.path}\n{item.content}" for item in examples)
        sections.append(f"## Examples\n{blocks}")

    constraints = getattr(context, "constraints", None)
    if constraints:
        sections.append(f"## Constraints\n{json.dumps(constraints, indent=2)}")

    outputs = getattr(context, "outputs", None) or []
    if outputs:
        artifacts_dir = getattr(context, "artifacts_dir", "")
        bullets = "\n".join(
            f"- {filename} (write under {artifacts_dir})" for filename in outputs
        )
        sections.append(f"## Expected outputs\n{bullets}")

    # Seam for the 07-03 clarification protocol (NEEDS_INPUT marker
    # instructions) -- intentionally left empty here.

    return "\n\n".join(sections)


def _base_argv(context: object) -> list[str]:
    """The fixed argv prefix shared by every invocation. An explicit
    ``list[str]`` -- never joined into a string, never run with
    ``shell=True``. ``--allowedTools`` is deliberately absent; plan 07-04
    adds it. No ``--permission-mode`` value scopes file access to a
    directory -- worktree confinement comes from ``cwd=work_dir`` at spawn
    (07-RESEARCH.md Summary finding 1 / Pitfall 3)."""
    return [
        CLAUDE_BINARY,
        "--output-format",
        "json",
        "--permission-mode",
        PERMISSION_MODE,
    ]


def _scrub_log_in_place(path: Path) -> None:
    """Rewrite ``path`` through the existing ``redact()`` pipeline using
    ``Settings.known_secret_values()`` (Task 3, T-07-01).

    A missing file is a no-op, not an error. Reads/writes as UTF-8 with
    ``errors="replace"`` so a raw non-UTF-8 byte the subprocess wrote never
    raises here -- it becomes a replacement character instead.

    **Why this exists and must never be optimised away:**
    ``git.diff.commit_run_artifacts`` (``src/dark_factory/git/diff.py``,
    around the ``relative_path = f".dark-factory/runs/{run_id}"`` line) force-
    adds and commits the *entire* ``.dark-factory/runs/<run_id>/`` tree --
    not just ``artifacts/`` -- onto the run's working branch, which becomes
    the PR branch. That commit step runs *after* this adapter returns, and
    nothing downstream re-scrubs these files. This function is therefore the
    only place a live credential value gets removed from the captured
    ``claude`` transcript before it becomes part of a public PR diff.
    """
    if not path.exists():
        return
    settings = get_settings()
    raw = path.read_text("utf-8", errors="replace")
    scrubbed = redact(raw, known_secrets=settings.known_secret_values())
    path.write_text(scrubbed, "utf-8")


def _run_streamed(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
) -> tuple[int | None, bool]:
    """Spawn ``argv`` with stdout/stderr redirected directly to open file
    objects (never ``PIPE`` -- D-04 forbids buffering the transcript in the
    parent's memory) and ``Popen.wait(timeout=...)``.

    Returns ``(exit_code, timed_out)``; ``exit_code`` is ``None`` exactly
    when ``timed_out`` is ``True``. On :class:`subprocess.TimeoutExpired`,
    the whole process group is killed via ``os.killpg(...,
    signal.SIGKILL)`` (``start_new_session=True`` makes the child head its
    own group), so a killed child leaves no grandchild running.
    """
    with stdout_path.open("wb") as out_fh, stderr_path.open("wb") as err_fh:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out_fh,
            stderr=err_fh,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()  # reap; no PIPE to drain, so this cannot deadlock
            return None, True
    return proc.returncode, False


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
        settings = get_settings()
        if settings.anthropic_api_key is None:
            raise MissingWorkerCredentialError()

        role = getattr(context, "role", None) or "unknown"
        attempt = getattr(context, "attempt", None) or 1
        run_id = getattr(context, "run_id", None)
        work_dir, root = self._resolve_dirs(run_id)

        env = build_worker_env(
            role,
            env_var_name=CLAUDE_CREDENTIAL_ENV_VAR,
            value=settings.anthropic_api_key,
        )
        argv = [*_base_argv(context), "-p", _build_prompt(context)]
        stdout_path, stderr_path = attempt_log_paths(root, role, attempt)

        # Task 3 (T-07-01): _scrub_log_in_place runs in `finally`, immediately
        # after _run_streamed returns OR raises, so it executes on the
        # success path, the non-zero-exit path and the timeout-kill path
        # alike -- and, critically, before any code below reads these files
        # again. See _scrub_log_in_place's own docstring for why this
        # ordering is mandatory, not decorative.
        try:
            exit_code, timed_out = _run_streamed(
                argv,
                cwd=work_dir,
                env=env,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout=settings.worker_timeout_seconds,
            )
        finally:
            _scrub_log_in_place(stdout_path)
            _scrub_log_in_place(stderr_path)

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
                error=(
                    f"claude exited {exit_code}: "
                    f"{stderr_text[:_MAX_ERROR_EXCERPT]}"
                ),
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
                    f"{stdout_text[:_MAX_ERROR_EXCERPT]!r}"
                ),
            )

        if parsed.get("is_error"):
            return WorkerResult(
                status=WorkerResultStatus.FAILED,
                summary="claude reported an error",
                error=str(parsed.get("result", "")),
                worker_session_id=parsed.get("session_id"),
            )

        metadata = {
            key: parsed[key] for key in _RESULT_METADATA_KEYS if key in parsed
        }
        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=str(parsed.get("result", "")),
            worker_session_id=parsed.get("session_id"),
            metadata=metadata,
        )

    def _resolve_dirs(self, run_id: object) -> tuple[Path, Path]:
        """``(work_dir, root)`` for this attempt.

        When ``run_id`` is a parseable UUID, mirrors ``fake.py:319``'s
        sibling-of-``cwd`` formula verbatim (GIT-02: no worker module may
        import ``dark_factory.git`` -- guarded by
        ``tests/unit/test_git_ownership_boundary.py``). Otherwise falls back
        to a fresh temp directory so the streamed-to-file invariant still
        holds for a context-free call (the shared contract suite calls
        ``execute(None)``).
        """
        parsed_run_id: UUID | None = None
        if run_id:
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                parsed_run_id = UUID(str(run_id))

        if parsed_run_id is not None:
            work_dir = Path.cwd().resolve().parent / "dark-factory-runs" / str(run_id)
            # In production this directory is the git worktree
            # `ensure_worktree` already created; mkdir here is a defensive
            # no-op there and what makes `cwd=work_dir` valid for a
            # context-only unit test that never calls `ensure_worktree`.
            work_dir.mkdir(parents=True, exist_ok=True)
            root = run_root(work_dir, parsed_run_id)
        else:
            work_dir = Path.cwd()
            root = Path(tempfile.mkdtemp(prefix="dark-factory-worker-log-"))
        return work_dir, root

    def resume(
        self, context: object, previous: WorkerResult, answer: str | None
    ) -> WorkerResult:
        """Continue a paused role attempt.

        Not implemented by this plan: 07-01 proves ``execute()`` end to end;
        plan 07-03 adds the native ``--resume <session_id>`` argv branch and
        the ``NEEDS_INPUT`` marker parsing this method routes on. Raising
        here (rather than silently delegating to ``execute()``) makes the
        gap explicit instead of returning a plausible-looking but wrong
        ``WorkerResult``.
        """
        raise NotImplementedError("ClaudeCodeWorker.resume() lands in plan 07-03")

    def capabilities(self) -> WorkerCapabilities:
        """Plan 07-03 lands the final capability declaration
        (``native_resume=True``, matching the confirmed ``--resume
        <session_id>`` flag). Until then this reports only what this plan
        implements."""
        return WorkerCapabilities(
            native_resume=False,
            session_id=True,
            structured_output=True,
            non_interactive=True,
        )
