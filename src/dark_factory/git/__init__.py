"""The ``dark_factory.git`` package -- the ONLY place in ``dark_factory`` that
invokes the ``git`` binary (GIT-02).

Nothing in this package opens a ``Session`` or constructs a lifecycle ORM row
(WR-01) -- ``tests/unit/test_git_ownership_boundary.py`` proves this package
(and no other module under ``src/dark_factory/``) ever shells out to ``git``.
Every function here takes explicit paths and returns plain values or raises a
typed error from the hierarchy below; nothing reads ``Path.cwd()`` or opens a
database connection.

Error hierarchy:

* :class:`GitError` -- the base class for every failure this package raises.
* :class:`GitCommandError` -- a ``git`` subprocess exited non-zero on a
  checked invocation; carries ``args``, ``returncode`` and ``stderr`` as
  attributes alongside a message naming the subcommand, the exit code and the
  first line of stderr.
* :class:`DetachedHeadError` -- raised by :func:`~dark_factory.git.lifecycle.assert_attached_head`
  when a role enters a worktree whose ``HEAD`` is detached (plan 05-02).
* :class:`WorktreePathError` -- raised by :func:`~dark_factory.git.worktree.ensure_worktree`
  for a run with no persisted ``working_branch`` / ``base_branch``, and by
  other worktree-path failures.
* :class:`WriteScopeViolation` -- declared now, raised by plan 05-04's
  write-scope enforcement when a role's diff touches a path outside its
  configured ``write_scope``.
* :class:`GitPushError` -- raised by :func:`~dark_factory.git.diff.push_working_branch`
  (plan 05-03, D-16) when every retry of ``git push origin <working_branch>``
  fails. A distinguishable subtype of :class:`GitError` (not of
  :class:`GitCommandError`, since its message is already redacted and
  reworded rather than the raw subprocess failure) so a caller (or a future
  retry-aware caller) can tell "the artifact commit itself failed" from "the
  commit succeeded but publishing it did not," even though this plan's
  runner wiring currently treats both the same way (folds into the existing
  ``ROLE_FAILED`` path).

Declaring the whole hierarchy in one place, even though two members are not
yet raised by any code in this plan, keeps the package's error surface
legible to a caller from the start.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ARTIFACT_COMMIT_SUBJECT_PREFIX",
    "ARTIFACT_EXCLUDE_PATHSPEC",
    "DIFF_PATCH_FILENAME",
    "GIT_ENV_ALLOWLIST",
    "GIT_IDENTITY_ENV",
    "GIT_PUSH_TOKEN_ENV_VAR",
    "MAX_DIFF_BYTES",
    "WIP_COMMIT_SUBJECT_PREFIX",
    "WORKTREE_PARENT_DIRNAME",
    "DetachedHeadError",
    "GitCommandError",
    "GitError",
    "GitPushError",
    "WorktreePathError",
    "WriteScopeViolation",
    "assert_attached_head",
    "collect_pr_diff",
    "commit_run_artifacts",
    "dirty_paths",
    "ensure_worktree",
    "git_env",
    "head_sha",
    "is_dirty",
    "pr_changed_paths",
    "push_working_branch",
    "remove_worktree",
    "run_git",
    "wip_commit_if_dirty",
    "working_branch_name",
    "worktree_path",
]


class GitError(RuntimeError):
    """Base class for every ``dark_factory.git`` failure."""


class GitCommandError(GitError):
    """A ``git`` subprocess exited non-zero on a checked invocation.

    Carries the argument list, the exit code and the captured stderr as
    attributes (``args`` / ``returncode`` / ``stderr``), in addition to a
    human-readable message naming the subcommand, the exit code, the working
    directory the subprocess ran in (when known), and the first line of
    stderr -- so a caller can inspect the failure programmatically as well as
    read it. The working directory is included because some git failures
    (e.g. "not a git repository") never name a path in their own stderr,
    which would otherwise leave a caller with no way to tell which directory
    was at fault.
    """

    def __init__(
        self,
        args: tuple[str, ...],
        returncode: int,
        stderr: str,
        *,
        cwd: Path | None = None,
    ) -> None:
        stripped = stderr.strip()
        first_line = stripped.splitlines()[0] if stripped else ""
        subcommand = args[0] if args else "<empty>"
        cwd_part = f" (cwd={cwd})" if cwd is not None else ""
        message = f"git {subcommand} exited {returncode}{cwd_part}: {first_line}"
        super().__init__(message)
        # ``super().__init__(message)`` sets ``self.args = (message,)`` --
        # overwrite it with the actual git argument list, per this class's
        # documented attribute contract, and keep the human-readable message
        # available separately so ``__str__`` stays correct regardless.
        self.args = args
        self.returncode = returncode
        self.stderr = stderr
        self._message = message

    def __str__(self) -> str:
        return self._message


class DetachedHeadError(GitError):
    """Raised when a run's worktree ``HEAD`` is detached (plan 05-02)."""


class WorktreePathError(GitError):
    """Raised by :func:`~dark_factory.git.worktree.ensure_worktree` for a
    missing persisted branch identifier, or other worktree-path failures."""


class WriteScopeViolation(GitError):
    """Raised when a role's diff touches a path outside its configured
    ``write_scope`` (plan 05-04)."""


class GitPushError(GitError):
    """Raised by :func:`~dark_factory.git.diff.push_working_branch` (plan
    05-03, D-16) when every retry of ``git push origin <working_branch>``
    fails. Its message has already been passed through
    :func:`~dark_factory.events.redaction.redact` -- defense in depth
    against a future git version or network intermediary echoing the push
    token into an error string despite the ``GIT_ASKPASS`` mechanism."""


# Import the submodules after the error hierarchy is declared, so their own
# ``from dark_factory.git import <ErrorClass>`` succeeds against this
# module's already-populated namespace (avoids a circular-import ordering
# problem: the submodules are the ones that raise these errors).
from dark_factory.git.client import (
    GIT_ENV_ALLOWLIST,
    GIT_IDENTITY_ENV,
    git_env,
    run_git,
)
from dark_factory.git.diff import (
    ARTIFACT_COMMIT_SUBJECT_PREFIX,
    ARTIFACT_EXCLUDE_PATHSPEC,
    DIFF_PATCH_FILENAME,
    GIT_PUSH_TOKEN_ENV_VAR,
    MAX_DIFF_BYTES,
    collect_pr_diff,
    commit_run_artifacts,
    pr_changed_paths,
    push_working_branch,
)
from dark_factory.git.lifecycle import (
    WIP_COMMIT_SUBJECT_PREFIX,
    assert_attached_head,
    dirty_paths,
    head_sha,
    is_dirty,
    wip_commit_if_dirty,
)
from dark_factory.git.worktree import (
    WORKTREE_PARENT_DIRNAME,
    ensure_worktree,
    remove_worktree,
    working_branch_name,
    worktree_path,
)
