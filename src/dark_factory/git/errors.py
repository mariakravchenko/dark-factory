"""The ``dark_factory.git`` error hierarchy -- a standalone, dependency-free
leaf module (Plan 12-06).

These classes used to be declared directly inside ``dark_factory/git/__init__.py``
and re-exported from there unchanged. They are extracted into their own module
for exactly one reason: ``dark_factory.git.client`` (and therefore
``dark_factory.git.committed``, which is built on it) used to import
``GitCommandError`` via ``from dark_factory.git import GitCommandError`` --
the bare package name. Importing *any* name from the bare ``dark_factory.git``
package forces Python to execute ``dark_factory/git/__init__.py`` in full,
which eagerly imports ``dark_factory.git.diff`` for its own re-export block,
which in turn imports ``dark_factory.events.redaction`` (for
:class:`GitPushError`'s pre-redacted message). That made ``dark_factory.git.client``
-- and transitively ``dark_factory.git.committed``, and anything that imports
either -- reach ``dark_factory.events``, even though neither module's own
logic has anything to do with event redaction.

That coupling was never real: it was two unrelated concerns (the git error
*types*, and the push-token redaction behaviour of one function) sharing a
single file. Plan 12-06 needs ``dark_factory.observability.run_detail`` --
architecturally events-free (STATE-06) -- to catch :class:`GitError` from
``dark_factory.git.committed.run_artifact_text`` while reading a committed
quality-gate file. Splitting the error hierarchy into this leaf module, with
``dark_factory.git.client`` importing from here instead of the package root,
breaks the accidental coupling without changing any public import path:
``dark_factory.git.__init__`` still imports and re-exports every class below,
so ``from dark_factory.git import GitError`` keeps working for every existing
caller.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ArtifactScopeViolation",
    "DetachedHeadError",
    "GitCommandError",
    "GitError",
    "GitPushError",
    "WorktreePathError",
    "WriteScopeViolation",
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


class ArtifactScopeViolation(GitError):
    """Raised when a role's attempt changes an artifact path outside its own
    ``artifacts/<role>/`` subtree of the run's
    ``.dark-factory/runs/<run_id>/artifacts/`` tree (plan 08-05, CR-01)."""


class GitPushError(GitError):
    """Raised by :func:`~dark_factory.git.diff.push_working_branch` (plan
    05-03, D-16) when every retry of ``git push origin <working_branch>``
    fails. Its message has already been passed through
    :func:`~dark_factory.events.redaction.redact` -- defense in depth
    against a future git version or network intermediary echoing the push
    token into an error string despite the ``GIT_ASKPASS`` mechanism."""
