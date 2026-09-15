"""Artifact-commit, PR-bound-diff, and push primitives (D-09, D-10, D-11, D-16).

No database access anywhere in this module -- every function takes explicit
paths and returns a plain value or raises a typed error from
``dark_factory.git``'s hierarchy, exactly like ``git/lifecycle.py`` and
``git/worktree.py`` beside it. This is what lets ``orchestrator/runner.py``
call these functions directly and what lets ``actions/builtins.py``'s
``collect_diff`` dispatch into :func:`collect_pr_diff` while staying git-only
(WR-01): nothing here opens a ``Session`` or constructs a lifecycle ORM row.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

import tenacity

from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact
from dark_factory.git import GitCommandError, GitPushError
from dark_factory.git.client import run_git
from dark_factory.git.lifecycle import head_sha

__all__ = [
    "ARTIFACT_COMMIT_SUBJECT_PREFIX",
    "ARTIFACT_EXCLUDE_PATHSPEC",
    "DIFF_PATCH_FILENAME",
    "GIT_PUSH_TOKEN_ENV_VAR",
    "MAX_DIFF_BYTES",
    "collect_pr_diff",
    "commit_run_artifacts",
    "pr_changed_paths",
    "push_working_branch",
]

# A module constant so the artifact-commit subject is greppable from
# ``git log`` and cannot drift between the writer here and any test that
# looks for it. Deliberately distinct from
# ``dark_factory.git.lifecycle.WIP_COMMIT_SUBJECT_PREFIX`` -- this is how an
# operator reading ``git log`` on a run's working branch tells a WIP
# recovery from a role's own artifact commit (D-09, 05-CONTEXT.md's
# discretion note).
ARTIFACT_COMMIT_SUBJECT_PREFIX = "chore(dark-factory):"

# The magic pathspec D-10 names, shared by both the artifact-commit path
# search and the PR-bound diff -- one constant, so the exclusion cannot
# silently drift between the two call sites that both must honour it.
ARTIFACT_EXCLUDE_PATHSPEC = ":(exclude).dark-factory"

# The cap a single PR-bound diff may occupy in memory / on disk (T-05-07),
# in the register of ``artifacts/paths.py::_MAX_ARTIFACT_BYTES`` and
# ``config/loader.py``'s ``_MAX_INSTRUCTION_BYTES``.
MAX_DIFF_BYTES = 1024 * 1024

# The filename ``collect_diff`` writes under ``<run_root>/verification/``.
DIFF_PATCH_FILENAME = "diff.patch"

# The dedicated environment variable the GIT_ASKPASS helper script reads for
# the push token (D-16). Deliberately NOT part of
# ``dark_factory.git.client.GIT_ENV_ALLOWLIST`` -- it must reach only the one
# subprocess invocation that pushes, never every other git call.
GIT_PUSH_TOKEN_ENV_VAR = "DARK_FACTORY_GIT_PUSH_TOKEN"

# git invokes an askpass helper once for the username prompt and once for
# the password prompt during HTTPS auth; this answers both from its own
# environment, never from argv. "x-access-token" is GitHub's documented
# fixed username for token-based HTTPS auth -- the actual token is the
# password half, read from GIT_PUSH_TOKEN_ENV_VAR.
_ASKPASS_SCRIPT = (
    "#!/bin/sh\n"
    'case "$1" in\n'
    "Username*) printf '%s\\n' \"x-access-token\" ;;\n"
    f"Password*) printf '%s\\n' \"${GIT_PUSH_TOKEN_ENV_VAR}\" ;;\n"
    "esac\n"
)


def commit_run_artifacts(worktree: Path, run_id: UUID, *, role: str) -> str | None:
    """Force-add and commit ``role``'s newly-written run-tree content onto
    the branch already checked out in ``worktree``; return the new commit's
    SHA, or ``None`` on either legitimate no-op path (D-09, A-05-08).

    The run-tree path is computed as ``.dark-factory/runs/<run_id>``
    **relative to** ``worktree`` -- git pathspecs are relative to the
    repository, and passing an absolute path here would work by accident
    rather than by contract.

    Two legitimate no-op paths, both returning ``None`` with no error:

    * the run's artifact directory does not exist under the worktree (a role
      that produced nothing new to commit -- this function is called on
      every completed role's attempt, not only ones with fresh content);
    * ``git add -f`` staged nothing new relative to the last commit (calling
      this a second time for the same role with no new content).

    Everything else -- a git failure of any other kind -- propagates as
    :class:`~dark_factory.git.GitCommandError` and is never swallowed
    (ART-04's transparency prohibition): a role's artifacts must never be
    reported as durably committed when the commit that was meant to carry
    them did not actually happen.

    ``git add -f`` is mandatory (A-05-08): ``.gitignore`` excludes
    ``.dark-factory/runs/`` from the base branch's own history (D-11), and
    ``git add`` refuses an explicitly-named ignored path without ``-f`` --
    without the flag this call exits 1 and, if that exit were not checked,
    would silently leave a run's artifacts never committed at all. The
    empty-change-set check (``git diff --cached --quiet``) runs *before* the
    commit is attempted, so "nothing to commit" is detected as a distinct,
    intentional branch rather than relying on ``git commit`` itself failing
    on an empty index. The final commit's message carries a trailing
    pathspec limiting it to the artifact directory, so any source-code
    change a worker happened to leave staged in the index is never swept
    into a Dark-Factory-attributed commit -- it stays staged and untouched
    (T-05-17).
    """
    relative_path = f".dark-factory/runs/{run_id}"
    if not (worktree / relative_path).is_dir():
        return None

    run_git(["add", "-f", "--", relative_path], cwd=worktree)

    empty_change_set = run_git(
        ["diff", "--cached", "--quiet", "--", relative_path],
        cwd=worktree,
        check=False,
    )
    if empty_change_set.returncode == 0:
        return None

    run_git(
        [
            "commit",
            "-m",
            f"{ARTIFACT_COMMIT_SUBJECT_PREFIX} {role} artifacts (run {run_id})",
            "--",
            relative_path,
        ],
        cwd=worktree,
    )
    return head_sha(worktree)


def collect_pr_diff(worktree: Path, *, base_branch: str, working_branch: str) -> str:
    """The unified merge-base diff of ``working_branch`` against
    ``base_branch``, with every ``.dark-factory`` path excluded (D-10).

    Uses the three-dot (``base...working``) merge-base form, not the two-dot
    direct-tree form: the three-dot form is what a forge computes for a pull
    request, and it is a commit-range diff anchored at the branches' common
    ancestor. The two-dot form would include the base branch's own commits
    made *after* the working branch was cut, appearing as apparent
    reversals the working branch never actually made -- verified empirically
    against a real repository during research, which is why D-10 names the
    three-dot form specifically.

    A-05-10 (an honest limitation, stated rather than worked around): this
    is a commit-range diff, so at the moment a role's ``after:`` hook runs,
    that role's own still-uncommitted edits are not yet in it -- they join
    on the *next* role's entry, when plan 05-02's WIP recovery commits them,
    and the terminal role's join during this plan's ``COMPLETED`` cleanup
    pass. The diff is therefore complete by the time a run finishes, which
    is exactly when Phase 9's quality gate and Phase 10's publisher read it.

    A diff whose encoded byte length exceeds :data:`MAX_DIFF_BYTES` is
    truncated to the cap on a line boundary, with a final marker line naming
    the original byte count appended -- so a pathological diff can neither
    exhaust memory nor fill the run tree (T-05-07).
    """
    result = run_git(
        [
            "diff",
            f"{base_branch}...{working_branch}",
            "--",
            ".",
            ARTIFACT_EXCLUDE_PATHSPEC,
        ],
        cwd=worktree,
    )
    text = result.stdout
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_DIFF_BYTES:
        return text

    truncated = encoded[:MAX_DIFF_BYTES]
    last_newline = truncated.rfind(b"\n")
    if last_newline != -1:
        truncated = truncated[: last_newline + 1]
    marker = (
        f"\n... [dark-factory: diff truncated; original size {len(encoded)} bytes]\n"
    )
    return truncated.decode("utf-8", errors="ignore") + marker


def pr_changed_paths(
    worktree: Path, *, base_branch: str, working_branch: str
) -> list[str]:
    """The same merge-base comparison as :func:`collect_pr_diff`, as changed
    path names only (``--name-only``), with ``.dark-factory`` excluded.

    Ordering is git's own and is not a contract -- every consumer looks
    paths up by value, never by position.
    """
    result = run_git(
        [
            "diff",
            "--name-only",
            f"{base_branch}...{working_branch}",
            "--",
            ".",
            ARTIFACT_EXCLUDE_PATHSPEC,
        ],
        cwd=worktree,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def push_working_branch(
    worktree: Path, *, working_branch: str, token: str | None
) -> None:
    """Push ``working_branch`` to ``origin`` immediately after
    :func:`commit_run_artifacts` succeeds (D-16).

    This function pushes what :func:`commit_run_artifacts` already
    committed; it does not commit anything itself. A caller that wants
    "commit, and make it survive a lost disk" calls both, in that order.

    Returns immediately, writing nothing and calling no subprocess, when
    ``token`` is ``None`` -- a repository with no configured push token
    keeps working exactly as it did before D-16: the local commit still
    exists, nothing is pushed, and the role still completes. The same
    no-op applies, and for the identical reason, when the repository has no
    ``origin`` remote configured at all (checked with a cheap
    ``git remote get-url origin`` before any push is attempted): D-16 exists
    to let an *already-configured* ephemeral-CI-retry path reconstruct via
    D-15, and a repository with no remote has no such path to serve in the
    first place -- treating "no remote" as a role failure would make every
    purely local Dark Factory deployment (and this project's own test
    suite, which drives roles against throwaway repositories with no
    ``origin``) fail every completed role the moment a push token merely
    happens to be configured in the environment.

    The token reaches git **only** through ``GIT_ASKPASS`` and the
    call-scoped :data:`GIT_PUSH_TOKEN_ENV_VAR` -- never as a subprocess
    argument and never embedded in the remote URL, both of which are
    visible to any co-resident process via ``ps`` and tend to be echoed
    verbatim in git's own failure output (T-05-21). The askpass helper
    script is written to a temporary file created with mode ``0o700``
    (owner-execute-only -- a world-readable askpass script would itself be
    a disclosure path) and unlinked in a ``finally`` block.

    The push subprocess call is retried up to 3 times with capped
    exponential backoff on a :class:`~dark_factory.git.GitCommandError` --
    the ``tenacity.retry`` decorator wraps only the inner push call, not the
    askpass-script setup/teardown around it. When every attempt fails, the
    captured stderr is passed through
    :func:`~dark_factory.events.redaction.redact` (defense in depth: this
    project's one redaction implementation, reused rather than duplicated --
    ``Settings.known_secret_values()`` already knows the live token value,
    so even if some future git version leaks it into stderr despite
    ``GIT_ASKPASS``, the redaction pass scrubs it before this message can
    reach a log or Neon) before it is folded into a raised
    :class:`~dark_factory.git.GitPushError` (T-05-22).
    """
    if token is None:
        return None

    remote_check = run_git(["remote", "get-url", "origin"], cwd=worktree, check=False)
    if remote_check.returncode != 0:
        return None

    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-dark-factory-askpass.sh", delete=False
    ) as askpass_file:
        askpass_path = Path(askpass_file.name)
        askpass_file.write(_ASKPASS_SCRIPT)
    try:
        askpass_path.chmod(0o700)

        env_extra = {
            "GIT_ASKPASS": str(askpass_path),
            GIT_PUSH_TOKEN_ENV_VAR: token,
            "GIT_TERMINAL_PROMPT": "0",
        }

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
            retry=tenacity.retry_if_exception_type(GitCommandError),
            reraise=True,
        )
        def _push() -> None:
            run_git(
                ["push", "origin", working_branch],
                cwd=worktree,
                env_extra=env_extra,
            )

        try:
            _push()
        except GitCommandError as exc:
            known_secrets = get_settings().known_secret_values()
            redacted_stderr = redact(exc.stderr, known_secrets=known_secrets)
            raise GitPushError(
                f"git push origin {working_branch} failed after retries: "
                f"{redacted_stderr}"
            ) from exc
    finally:
        askpass_path.unlink(missing_ok=True)
    return None
