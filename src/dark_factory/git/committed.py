"""Read artifact content out of a run's working branch, through ``git show``
-- the one production read path for already-committed artifact content
(Plan 12-05, OBS-01, D-04).

This function exists in production at all for a non-obvious reason, stated
here so a future reader is not tempted to replace it with a
``Path.read_text()``: a run's worktree is removed by ``_cleanup_run_worktree``
on every ``COMPLETED`` transition (D-04, Phase 5), so once a run has
succeeded its working branch is the *only* place its artifact content still
exists -- the worktree directory that once held it is gone. Reading through
git also makes the code path uniform: identical for a mid-flight run (whose
worktree still exists) and a finished one, rather than branching on
``run.status``, which would put a lifecycle decision inside a read.

Built entirely on :func:`dark_factory.git.client.run_git` -- the one child
process wrapper this project enforces, carrying the explicit
``["git", *args]`` argument list (T-05-01), the ``GIT_ENV_ALLOWLIST``
comprehension rather than a parent-environment copy (T-05-04, exactly how a
``DATABASE_URL`` or a ``GITHUB_TOKEN`` would otherwise reach a child process
with no business seeing one), the mandatory ``timeout`` and
``GIT_TERMINAL_PROMPT=0`` (T-05-10), and the pinned commit identity
(T-05-11). A second low-level ``git show`` invocation anywhere would
duplicate all four invariants in a second place.

A ``GitCommandError`` (a missing path, an unknown branch) is never caught
here -- it is information the caller needs to produce a useful exit-2
message, and swallowing it into an empty string would make "the file is
empty" and "the file does not exist" indistinguishable.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dark_factory.git.client import run_git

__all__ = ["read_committed", "run_artifact_text"]


def read_committed(repo_root: Path, branch: str, relative_path: str) -> str:
    """``git show <branch>:<relative_path>`` -- read a file's content as it
    exists on ``branch``, regardless of whether a worktree checking out that
    branch exists on disk."""
    return run_git(["show", f"{branch}:{relative_path}"], cwd=repo_root).stdout


def run_artifact_text(
    repo_root: Path, run_id: UUID, working_branch: str, relative_path: str
) -> str:
    """Read one artifact's text content through the run's working branch.

    Composes ``.dark-factory/runs/<run_id>/`` with ``relative_path`` -- the
    same run-root-relative path an ``artifacts`` row's ``path`` column
    stores -- and delegates to :func:`read_committed`.
    """
    return read_committed(
        repo_root, working_branch, f".dark-factory/runs/{run_id}/{relative_path}"
    )
