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
import re
import signal
import subprocess
import tempfile
from collections.abc import Collection, Mapping
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

# 06-CONTEXT.md D-02: NATIVE_TOOL_CONTRACT is the design contract Phase 7
# adapters implement from -- this import is that contract's first real
# (non-inert) runtime consumer (07-04, Task 1). Guarded, not un-guarded, by
# tests/unit/test_native_tool_contract.py's narrowed reference allowlist.
from dark_factory.tools.native import NATIVE_TOOL_CONTRACT
from dark_factory.workers.base import CodingWorker

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

# D-01: the fixed line-initial token that signals a clarifying question. The
# CLI's own `result` text is the only channel the agent has to ask for a
# human decision -- this constant is the two-sided contract's shared literal:
# the prompt below states the rule and `_NEEDS_INPUT_RE` parses it back out.
NEEDS_INPUT_MARKER = "NEEDS_INPUT:"

NEEDS_INPUT_PROTOCOL = f"""## Clarification protocol
If you cannot proceed without a human decision, end your final message with a
single line that begins with the exact token "{NEEDS_INPUT_MARKER}" followed
by the one question the human must answer. Write nothing after that line.
Never emit this token for any other purpose."""

# D-01: MULTILINE anchors the marker to the start of a line (`^`), so an
# ordinary sentence that merely mentions the token mid-line never matches --
# only a line that begins with it is treated as the signal. DOTALL makes `.`
# match newlines too, and combined with the `\Z` end-of-string anchor, the
# capture group grabs everything from right after the marker to the end of
# the result text in one shot -- which is how a multi-line question is
# extracted without a second delimiter marking where it ends. Both flags are
# load-bearing: drop MULTILINE and a stray mention anywhere in prose would
# trigger a pause; drop DOTALL/`\Z` and only the marker's own line would be
# captured, truncating a multi-line question.
_NEEDS_INPUT_RE = re.compile(
    rf"^{re.escape(NEEDS_INPUT_MARKER)}[ \t]*(.*)\Z", re.MULTILINE | re.DOTALL
)

# D-03/Task 2: the fixed -p value used on the native --resume branch when no
# human answer is available (a resume triggered by something other than a
# human reply is a legitimate call shape the contract suite pins). The CLI
# must never be invoked with an empty prompt argument.
RESUME_CONTINUATION_PROMPT = (
    "Continue the previous attempt from where it paused. No new human "
    "answer was supplied for this resume."
)

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


def _extract_needs_input(result_text: str) -> str | None:
    """Return the clarification question if ``result_text`` ends with a
    line-initial ``NEEDS_INPUT:`` marker, else ``None`` (D-01).

    An empty capture -- a marker line followed only by whitespace -- degrades
    to "no marker" rather than an empty-string question: returning an empty
    string here would let a caller build
    ``WorkerResult(status=NEEDS_INPUT, questions=[""])``, which
    ``WorkerResult._require_question_for_needs_input`` rejects with a
    ``ValidationError`` raised *inside* this adapter -- ``execute()``'s outer
    ``except Exception`` would then downgrade that into a spurious ``FAILED``
    instead of the ``COMPLETED`` this case should be.
    """
    match = _NEEDS_INPUT_RE.search(result_text)
    if match is None:
        return None
    question = match.group(1).strip()
    return question or None


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


def _context_prompt_sections(context: object) -> list[str]:
    """The ``## Instructions`` / ``## Task`` / ... sections built from
    ``context`` alone (a :class:`~dark_factory.context.builder.RoleContext`,
    read defensively via ``getattr`` so a bare test double still degrades
    cleanly). A section whose source field is empty is skipped entirely.

    Shared by :func:`_build_prompt` (the fresh-attempt prompt) and
    :func:`_build_resume_prompt` (the context-reconstruction resume prompt)
    so both start from the identical task/instructions/inputs material --
    neither the clarification protocol nor any resume-specific section is
    included here.
    """
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

    return sections


def _build_prompt(context: object) -> str:
    """Assemble the plain-text ``-p`` prompt for a fresh attempt: the
    ``context``-derived sections, then the clarification protocol last, so
    the agent sees D-01's convention as its final instruction."""
    sections = _context_prompt_sections(context)
    sections.append(NEEDS_INPUT_PROTOCOL)
    return "\n\n".join(sections)


def _build_resume_prompt(
    context: object, previous: WorkerResult, answer: str | None
) -> str:
    """Assemble the ``-p`` prompt for the context-reconstruction resume
    branch (HITL-05: taken when ``previous.worker_session_id`` is absent).

    Starts from the same ``context``-derived sections a fresh attempt uses,
    then appends the previous attempt's own account of itself -- its
    summary, its outstanding questions, and the human's answer (or a note
    that none was supplied) -- so the agent can pick up where it paused. The
    clarification protocol is appended last, exactly as in
    :func:`_build_prompt`, so a reconstructed attempt can pause again.
    """
    sections = _context_prompt_sections(context)

    sections.append(f"## Previous attempt\n{previous.summary}")

    if previous.questions:
        bullets = "\n".join(f"- {question}" for question in previous.questions)
    else:
        bullets = "(none recorded)"
    sections.append(f"## Outstanding questions\n{bullets}")

    sections.append(f"## Human answer\n{answer or '(no answer was supplied)'}")

    sections.append(NEEDS_INPUT_PROTOCOL)
    return "\n\n".join(sections)


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
        argv = [*_base_argv(context), "-p", _build_prompt(context)]
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
        work_dir, root = self._resolve_dirs(run_id)

        env = build_worker_env(
            role,
            env_var_name=CLAUDE_CREDENTIAL_ENV_VAR,
            value=settings.anthropic_api_key,
        )
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
        result_text = str(parsed.get("result", ""))
        session_id = parsed.get("session_id")

        # D-01: a non-error result may still be a pause request. Precedence
        # is: is_error / non-zero exit (handled above) always wins; a
        # NEEDS_INPUT marker wins over COMPLETED; otherwise COMPLETED.
        question = _extract_needs_input(result_text)
        if question is not None:
            return WorkerResult(
                status=WorkerResultStatus.NEEDS_INPUT,
                summary=result_text,
                questions=[question],
                worker_session_id=session_id,
                metadata=metadata,
            )

        return WorkerResult(
            status=WorkerResultStatus.COMPLETED,
            summary=result_text,
            worker_session_id=session_id,
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
                _build_resume_prompt(context, previous, answer),
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
