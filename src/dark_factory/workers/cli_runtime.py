"""The binary-agnostic half of every CLI-adapter :class:`~dark_factory.
workers.base.CodingWorker` implementation (D-03, 08-01 Task 1).

Extracted verbatim from :mod:`dark_factory.workers.claude_code` (Phase 7,
07-CONTEXT.md D-01/D-02/D-03/D-04) so every subsequent adapter --
:mod:`dark_factory.workers.copilot` and, later, ``workers/hermes.py`` --
shares one ``NEEDS_INPUT`` pause contract, one spawn/timeout/redact
pipeline, and one declared-artifact reporter instead of re-deriving them
per adapter. What stays binary-specific (argv construction, the
credential-missing error, the CLI's own output parsing) lives in each
adapter module, not here.

This module must never import ``dark_factory.git`` (GIT-02 --
``tests/unit/test_git_ownership_boundary.py`` guards this) and must never
import an adapter module -- the dependency direction is adapters depend on
this shared runtime, never the reverse.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

from dark_factory.artifacts.paths import run_root
from dark_factory.config.settings import get_settings
from dark_factory.domain.worker import WorkerResult
from dark_factory.events.redaction import redact

__all__ = [
    "MAX_ERROR_EXCERPT",
    "NEEDS_INPUT_MARKER",
    "NEEDS_INPUT_PROTOCOL",
    "NEEDS_INPUT_RE",
    "RESUME_CONTINUATION_PROMPT",
    "attempt_log_paths",
    "build_prompt",
    "build_resume_prompt",
    "context_prompt_sections",
    "extract_needs_input",
    "resolve_dirs",
    "run_streamed",
    "scrub_log_in_place",
]

# D-01 (07-CONTEXT.md): the fixed line-initial token that signals a clarifying
# question. The CLI's own result text is the only channel the agent has to ask
# for a human decision -- this constant is the two-sided contract's shared
# literal: the prompt below states the rule and `NEEDS_INPUT_RE` parses it
# back out. D-03 (08-CONTEXT.md): reused verbatim by every CLI adapter so
# HITL-01/02 behavior is identical regardless of which worker a role is
# assigned to.
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
NEEDS_INPUT_RE = re.compile(
    rf"^{re.escape(NEEDS_INPUT_MARKER)}[ \t]*(.*)\Z", re.MULTILINE | re.DOTALL
)

# D-03/Task 2 (07-CONTEXT.md): the fixed -p value used on the native --resume
# branch when no human answer is available (a resume triggered by something
# other than a human reply is a legitimate call shape the contract suite
# pins). The CLI must never be invoked with an empty prompt argument.
RESUME_CONTINUATION_PROMPT = (
    "Continue the previous attempt from where it paused. No new human "
    "answer was supplied for this resume."
)

# The cap on a stderr/stdout excerpt folded into a WorkerResult.error, so a
# runaway transcript cannot bloat the JSONB `result`/`error` column the
# orchestrator persists (Task 2).
MAX_ERROR_EXCERPT = 2000


def extract_needs_input(result_text: str) -> str | None:
    """Return the clarification question if ``result_text`` ends with a
    line-initial ``NEEDS_INPUT:`` marker, else ``None`` (D-01).

    An empty capture -- a marker line followed only by whitespace -- degrades
    to "no marker" rather than an empty-string question: returning an empty
    string here would let a caller build
    ``WorkerResult(status=NEEDS_INPUT, questions=[""])``, which
    ``WorkerResult._require_question_for_needs_input`` rejects with a
    ``ValidationError`` raised *inside* the adapter -- the adapter's outer
    ``except Exception`` would then downgrade that into a spurious ``FAILED``
    instead of the ``COMPLETED`` this case should be.
    """
    match = NEEDS_INPUT_RE.search(result_text)
    if match is None:
        return None
    question = match.group(1).strip()
    return question or None


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


def context_prompt_sections(context: object) -> list[str]:
    """The ``## Instructions`` / ``## Task`` / ... sections built from
    ``context`` alone (a :class:`~dark_factory.context.builder.RoleContext`,
    read defensively via ``getattr`` so a bare test double still degrades
    cleanly). A section whose source field is empty is skipped entirely.

    Shared by :func:`build_prompt` (the fresh-attempt prompt) and
    :func:`build_resume_prompt` (the context-reconstruction resume prompt)
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


def build_prompt(context: object) -> str:
    """Assemble the plain-text ``-p`` prompt for a fresh attempt: the
    ``context``-derived sections, then the clarification protocol last, so
    the agent sees D-01's convention as its final instruction."""
    sections = context_prompt_sections(context)
    sections.append(NEEDS_INPUT_PROTOCOL)
    return "\n\n".join(sections)


def build_resume_prompt(
    context: object, previous: WorkerResult, answer: str | None
) -> str:
    """Assemble the ``-p`` prompt for the context-reconstruction resume
    branch (HITL-05: taken when ``previous.worker_session_id`` is absent).

    Starts from the same ``context``-derived sections a fresh attempt uses,
    then appends the previous attempt's own account of itself -- its
    summary, its outstanding questions, and the human's answer (or a note
    that none was supplied) -- so the agent can pick up where it paused. The
    clarification protocol is appended last, exactly as in
    :func:`build_prompt`, so a reconstructed attempt can pause again.
    """
    sections = context_prompt_sections(context)

    sections.append(f"## Previous attempt\n{previous.summary}")

    if previous.questions:
        bullets = "\n".join(f"- {question}" for question in previous.questions)
    else:
        bullets = "(none recorded)"
    sections.append(f"## Outstanding questions\n{bullets}")

    sections.append(f"## Human answer\n{answer or '(no answer was supplied)'}")

    sections.append(NEEDS_INPUT_PROTOCOL)
    return "\n\n".join(sections)


def scrub_log_in_place(path: Path) -> None:
    """Rewrite ``path`` through the existing ``redact()`` pipeline using
    ``Settings.known_secret_values()`` (07-01 Task 3, T-07-01).

    A missing file is a no-op, not an error. Reads/writes as UTF-8 with
    ``errors="replace"`` so a raw non-UTF-8 byte the subprocess wrote never
    raises here -- it becomes a replacement character instead.

    **Why this exists and must never be optimised away:**
    ``git.diff.commit_run_artifacts`` (``src/dark_factory/git/diff.py``,
    around the ``relative_path = f".dark-factory/runs/{run_id}"`` line) force-
    adds and commits the *entire* ``.dark-factory/runs/<run_id>/`` tree --
    not just ``artifacts/`` -- onto the run's working branch, which becomes
    the PR branch. That commit step runs *after* an adapter returns, and
    nothing downstream re-scrubs these files. This function is therefore the
    only place a live credential value gets removed from a captured CLI
    transcript before it becomes part of a public PR diff.
    """
    if not path.exists():
        return
    settings = get_settings()
    raw = path.read_text("utf-8", errors="replace")
    scrubbed = redact(raw, known_secrets=settings.known_secret_values())
    path.write_text(scrubbed, "utf-8")


def run_streamed(
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


def resolve_dirs(run_id: object) -> tuple[Path, Path]:
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
